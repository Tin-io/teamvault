---
name: teamvault-doctor
description: Diagnose AND remediate the TeamVault install — deeper than /teamvault-status. Use when the sidecar is misbehaving, a search returns nothing, MCP tools aren't surfacing, or the user asks "why isn't TeamVault working?" Runs structural checks (plist shape, MCP-vs-sidecar path consistency, embedding cache, disk free, PID-lockfile / running-PID consistency, /readyz), surfaces specific failure modes with suggested fixes, and offers a support-bundle builder. ALL remediation requires explicit user confirmation — doctor is a guide, not an autopilot.
---

# TeamVault Doctor

A deeper diagnostic + remediation companion to `/teamvault-status`. Where status is "is it broken?", doctor is "**why** is it broken, and **how do I fix it?**"

## When to use

- `/teamvault-status` reported `DEGRADED` / `DOWN` and the next question is "why?"
- `vault_search` returns 0 results when it should
- Sidecar restarted but vault MCP tools still aren't surfacing in Claude Code
- About to ask for help — bundle logs + config for the support channel
- After a macOS upgrade, kernel update, or anything that might have nuked launchd state

## Preconditions

```bash
ls "$HOME/.teamvault" 2>&1 | head -3
ls "$HOME/Library/LaunchAgents/dev.teamvault.sidecar.plist" 2>&1
```

If the install is fundamentally absent (no `~/.teamvault/`), surface that and direct the user to `/teamvault-setup` — don't run the deeper diagnostics on a non-install.

## Flow

Doctor runs checks in three layers (Liveness → Structure → Data), produces a verdict per check, then surfaces a single consolidated remediation menu. Each remediation requires explicit user confirmation.

---

### Layer 1 — Liveness (does the sidecar process exist + respond?)

#### 1.1 Sidecar process + PID lockfile consistency

```bash
PORT=${TEAMVAULT_PORT:-8100}
RUNNING_PID=$(lsof -ti :"$PORT" 2>/dev/null | head -1)
LOCK_PID=$(cat "$HOME/.teamvault/sidecar.pid" 2>/dev/null || echo "")

if [ -z "$RUNNING_PID" ]; then
  echo "1.1 DOWN: no process listening on port $PORT"
elif [ -z "$LOCK_PID" ]; then
  echo "1.1 DEGRADED: sidecar PID $RUNNING_PID running but lockfile missing (pre-P1.13 build?)"
elif [ "$RUNNING_PID" != "$LOCK_PID" ]; then
  echo "1.1 DEGRADED: lockfile PID ($LOCK_PID) != running PID ($RUNNING_PID) — stale lockfile, sidecar crashed unclean"
else
  echo "1.1 OK: process $RUNNING_PID matches lockfile"
fi
```

#### 1.2 launchd job status

```bash
launchctl print "gui/$(id -u)/dev.teamvault.sidecar" 2>&1 | grep -E "^[[:space:]]*(state|last exit|throttle interval)" | head -5
```

Interpret:
- `state = running` → OK
- `state = waiting` + `last exit code = N (non-zero) within ThrottleInterval` → crash loop; tail logs (3.2) for cause
- Plist not loaded (the print errors) → registration broke; remediation: re-run `/teamvault-setup` §5

#### 1.3 `/healthz` + `/readyz`

```bash
PORT=${TEAMVAULT_PORT:-8100}
curl -s --max-time 5 -o /tmp/teamvault-healthz.json -w "1.3 /healthz HTTP %{http_code}\n" "http://localhost:$PORT/healthz"
curl -s --max-time 5 -o /tmp/teamvault-readyz.json  -w "1.3 /readyz  HTTP %{http_code}\n" "http://localhost:$PORT/readyz"
```

Interpret:
- `/healthz 200` = process alive
- `/readyz 200 ready=true` = ready to serve queries
- `/readyz 503 reason="no space registered"` → `space.yaml` missing or unreadable in `TEAMVAULT_SPACE_ROOT`
- `/readyz 503 reason="space(s) not yet indexed"` → trigger reindex (remediation R1 below)
- `/readyz 503 reason="space in error state"` → see `recent_errors` in `/healthz` body (Layer 3.2)

---

### Layer 2 — Structure (is the install correctly wired?)

#### 2.1 Plist shape verification

```bash
PLIST="$HOME/Library/LaunchAgents/dev.teamvault.sidecar.plist"
if [ ! -f "$PLIST" ]; then
  echo "2.1 DOWN: plist missing at $PLIST"
else
  plutil -lint "$PLIST" 2>&1
  python3 - <<'PY'
import plistlib, pathlib
p = pathlib.Path.home() / "Library/LaunchAgents/dev.teamvault.sidecar.plist"
doc = plistlib.loads(p.read_bytes())
required = ["Label", "ProgramArguments", "WorkingDirectory", "EnvironmentVariables", "RunAtLoad", "KeepAlive"]
missing = [k for k in required if k not in doc]
print("missing keys:", missing or "none")
print("Label:", doc.get("Label"))
print("uvicorn path:", (doc.get("ProgramArguments") or [None])[0])
env = doc.get("EnvironmentVariables") or {}
print("TEAMVAULT_SPACE_ROOT:", env.get("TEAMVAULT_SPACE_ROOT"))
print("PYTHONPATH:", env.get("PYTHONPATH"))
PY
fi
```

Verify:
- `plutil -lint` returns OK
- All required keys present
- `Label = "dev.teamvault.sidecar"`
- `ProgramArguments[0]` points to a real `.venv/bin/uvicorn` — sometimes survives upgrades pointing at a deleted path
- `EnvironmentVariables.TEAMVAULT_SPACE_ROOT` exists on disk
- `${...}` substitutions ARE expanded — if you see literal `${TEAMVAULT_PORT:-8100}` strings, the plist was written with a quoted heredoc (a `/teamvault-setup` §5 bug)

#### 2.2 MCP registration vs. sidecar path consistency

```bash
claude mcp list 2>&1 | grep teamvault
claude mcp get teamvault 2>&1 | head -20
```

The MCP shim launches `<SPACE_DIR>/sidecar/.venv/bin/python -m sidecar.mcp_server`. Verify:
- That python interpreter actually exists (`ls -la <path>`)
- It can import `sidecar.mcp_server` (`<python> -c "import sidecar.mcp_server"`)
- Its `TEAMVAULT_SIDECAR_URL` env points at the live sidecar's port (matches the plist's port)

**Common drift:** MCP was registered against an old `$SPACE_DIR`; user re-cloned to a new location; MCP still points at the deleted dir → no `vault_*` tools surface in Claude Code. Remediation: re-run `/teamvault-setup` §6.

#### 2.3 Embedding model cache

```bash
HF_CACHE="${HF_HOME:-$HOME/.cache/huggingface}/hub"
MODEL_DIR="$HF_CACHE/models--nomic-ai--nomic-embed-text-v1.5"
if [ -d "$MODEL_DIR" ]; then
  echo "2.3 OK: nomic-embed-text-v1.5 cached at $MODEL_DIR ($(du -sh "$MODEL_DIR" | cut -f1))"
else
  echo "2.3 PENDING: $MODEL_DIR not present yet — first reindex will download (~547 MB, 1-3 min)"
fi
```

If missing → first reindex will download it. Not necessarily a fault, but worth surfacing if `/readyz` is 503 and the user is waiting for the index.

#### 2.4 Disk free

```bash
HF_CACHE="${HF_HOME:-$HOME/.cache/huggingface}/hub"
df -h "$HOME/.teamvault/" "$HF_CACHE" 2>/dev/null | tail -n +2 | awk '{print "2.4 " $NF ": " $4 " free"}'
```

Surface if any partition has `<2 GB` free — vector store + audit log growth + HF cache all live here. Remediation: clean `~/.cache/huggingface/hub` (cheap to redownload) or rotate audit logs.

---

### Layer 3 — Data (is what we serve actually there?)

#### 3.1 Vault index per space

For each registered space (from `/healthz.spaces`):

```bash
SPACE_NAME=<from healthz>
VAULT_DIR="$HOME/.teamvault/$SPACE_NAME"
[ -d "$VAULT_DIR/vault.lance" ] && echo "3.1[$SPACE_NAME] vault.lance OK ($(du -sh "$VAULT_DIR/vault.lance" | cut -f1))" || echo "3.1[$SPACE_NAME] DEGRADED: vault.lance missing — no reindex has run yet"
[ -f "$VAULT_DIR/fts.db" ]      && echo "3.1[$SPACE_NAME] fts.db OK ($(du -sh "$VAULT_DIR/fts.db" | cut -f1))" || echo "3.1[$SPACE_NAME] DEGRADED: fts.db missing"
```

If both missing → no reindex has ever run; remediation R1 (reindex).
If exactly one is missing → split-state bug; full reindex needed.

#### 3.2 Recent errors tail (P1.4 `/healthz.recent_errors`)

```bash
python3 - <<'PY'
import json, urllib.request, os
port = os.environ.get("TEAMVAULT_PORT", "8100")
try:
    data = json.loads(urllib.request.urlopen(f"http://localhost:{port}/healthz", timeout=3).read())
except Exception as e:
    print(f"3.2 SKIP: /healthz unreachable: {e}")
    raise SystemExit(0)
errors = data.get("recent_errors") or {}
if not errors:
    print("3.2 OK: no WARNING+ records in tail")
else:
    for space, records in errors.items():
        print(f"3.2 [{space}] {len(records)} recent WARNING+:")
        for r in records:
            print(f"      {r['ts']} {r['level']:>7}: {r['message']}")
PY
```

If recent errors point at a specific subsystem (e.g., `git_sync failed`, `audit.record failed`), surface the underlying message in the verdict + map to a remediation if known.

For deeper context, tail the JSON log file:

```bash
tail -n 20 "$HOME/.teamvault/logs/sidecar.log" 2>&1
```

#### 3.3 Audit-log chain integrity

```bash
curl -s --max-time 3 "http://localhost:${TEAMVAULT_PORT:-8100}/query_log?limit=1" 2>/dev/null | python3 -c "
import json, sys
try:
    d = json.load(sys.stdin)
    print('3.3', 'OK' if d.get('chain_ok') else 'BROKEN', 'chain_ok:', d.get('chain_ok'))
except Exception as e:
    print('3.3 SKIP:', e)
"
```

If `chain_ok: false` → tamper-evident hash chain broken; audit log was modified outside the sidecar's writer. Forensic concern — do NOT auto-repair. Surface to user; escalate to maintainer / compliance lead.

---

## Output: consolidated verdict table

Produce a single compact table the user can scan in 5 seconds:

```
TeamVault Doctor — diagnosis

Layer  Check                             Verdict   Detail
-----  --------------------------------  --------  ----------------------------------
1.1    process + PID lockfile            OK        PID 12345 matches lockfile
1.2    launchd job                       OK        running, last exit 0
1.3    /healthz                          OK        version 0.0.1
1.3    /readyz                           DEGRADED  503 — space(s) not yet indexed: [my-space]
2.1    plist shape                       OK        all required keys, paths exist
2.2    MCP registration                  OK        teamvault → /Users/.../python
2.3    embedding model cache             OK        nomic-embed-text-v1.5 (547M)
2.4    disk free                         OK        ~/.teamvault: 215G free
3.1    vault.lance (my-space)            OK        42M
3.1    fts.db       (my-space)           OK        1.2M
3.2    recent errors                     OK        no WARNING+ in tail
3.3    audit chain                       OK        chain_ok: true

Overall: 1 DEGRADED (1.3 /readyz)
```

---

## Remediation menu (after diagnosis)

Surface a numbered list of suggested fixes, ONE per non-OK row, plus the generic two:

```
Suggested fixes (run AT MOST ONE per invocation; re-run doctor after to verify):

[R1] 1.3 /readyz DEGRADED → trigger reindex for the listed space
     curl -s -X POST "http://localhost:${TEAMVAULT_PORT:-8100}/reindex" \
       -H 'Content-Type: application/json' \
       -d '{"space":"<space-name>"}'

[R2] Restart sidecar (clears most transient issues — stale lockfile, hung git_sync, etc.)
     launchctl kickstart -k gui/$(id -u)/dev.teamvault.sidecar

[R3] Build a support bundle (logs + config + plist + probes — scrubbed of kb/ content)
     Creates /tmp/teamvault-support-<timestamp>.tar.gz

[R4] None — print the diagnosis and exit.
```

**Each remediation requires explicit user confirmation before running.** Do NOT chain them; do NOT batch them; one fix per invocation. Re-run doctor afterwards to verify the underlying issue resolved.

---

## Support-bundle builder (option R3)

```bash
TS=$(date +%Y%m%d-%H%M%S)
BUNDLE="/tmp/teamvault-support-$TS.tar.gz"
SUPPORT_DIR=$(mktemp -d)

# Config + plist (not kb/)
cp "$HOME/Library/LaunchAgents/dev.teamvault.sidecar.plist" "$SUPPORT_DIR/" 2>/dev/null

# Logs (not vault.lance, not audit.log content — audit chain integrity is in healthz.json instead)
mkdir -p "$SUPPORT_DIR/logs/"
cp -r "$HOME/.teamvault/logs/." "$SUPPORT_DIR/logs/" 2>/dev/null

# PID lockfile
cp "$HOME/.teamvault/sidecar.pid" "$SUPPORT_DIR/" 2>/dev/null

# Live probes
PORT=${TEAMVAULT_PORT:-8100}
curl -s --max-time 3 "http://localhost:$PORT/healthz" > "$SUPPORT_DIR/healthz.json" 2>/dev/null
curl -s --max-time 3 "http://localhost:$PORT/readyz"  > "$SUPPORT_DIR/readyz.json"  2>/dev/null

# launchd + MCP state
launchctl print "gui/$(id -u)/dev.teamvault.sidecar" > "$SUPPORT_DIR/launchd-print.txt" 2>&1
claude mcp list                                       > "$SUPPORT_DIR/claude-mcp-list.txt" 2>&1
claude mcp get teamvault                              > "$SUPPORT_DIR/claude-mcp-get-teamvault.txt" 2>&1

# System info
{ sw_vers; uname -a; python3 --version; } > "$SUPPORT_DIR/system.txt"

# Doctor's diagnosis table (the agent pastes the verdict block from this invocation)
echo "<paste the verdict table from this doctor invocation here>" > "$SUPPORT_DIR/diagnosis.txt"

tar -czf "$BUNDLE" -C "$SUPPORT_DIR" .
rm -rf "$SUPPORT_DIR"
echo "Support bundle: $BUNDLE ($(du -h "$BUNDLE" | cut -f1))"
echo ""
echo "Bundle contents (no kb/ content, no audit.log content, no vault.lance content):"
tar -tzf "$BUNDLE" | head
```

**Bundle scope tell the user explicitly:** "This bundle contains config, plist, sidecar logs, HTTP probes, launchd + MCP state, and the diagnosis. It does **NOT** include any `kb/` content, `vault.lance` data, or `audit.log` content. Safe to share with TeamVault maintainers; do not include in HIPAA breach reports without legal review."

---

## Failure-mode reference (Layer 1-3 mapping)

| Symptom | Likely cause | Layer | Remediation |
|---|---|---|---|
| `vault_search` returns nothing | Not bound, OR /readyz=503 | 1.3 | R1 (reindex), verify bind via `/teamvault-status` |
| Sidecar crash loop | Plist shape broken, missing venv binary | 1.2 / 2.1 | Re-run `/teamvault-setup` §5 |
| `vault_*` MCP tools missing in Claude Code | MCP registered against deleted SPACE_DIR | 2.2 | Re-run `/teamvault-setup` §6 |
| First reindex hangs forever | Nomic model not cached, slow Wi-Fi | 2.3 | Wait + tail 3.2 logs OR pre-download model |
| `last_pull` stale (>5 min) | git_sync auth failure | 3.2 | `gh auth refresh` |
| `chain_ok: false` | Audit log modified externally | 3.3 | DO NOT auto-repair; escalate forensic |
| Lockfile PID ≠ running PID | Sidecar crashed unclean | 1.1 | R2 (kickstart) |
| `1.3 /readyz` 503 immediately after restart | Restart resets in-memory `last_indexed` until next reindex | 1.3 | R1 OR wait ≤60 s for next git_sync→reindex cycle |
| Literal `${TEAMVAULT_PORT:-8100}` string in plist | `/teamvault-setup` §5 written with quoted heredoc | 2.1 | Re-run `/teamvault-setup` §5 with unquoted heredoc |

---

## Don't do

- **Don't auto-fix.** Every remediation requires explicit user confirmation. Doctor is a guide, not an autopilot.
- **Don't include `kb/`, `vault.lance`, or `audit.log` content in the support bundle.** Only configuration + observability artifacts.
- **Don't run multiple remediations in one invocation.** Run one, re-run doctor, verify resolution, then run the next if needed.
- **Don't `kill` the sidecar PID directly.** Use `launchctl kickstart -k` so launchd respects ThrottleInterval and the lockfile flow.
- **Don't suggest `git push --force` to fix `audit.log` chain mismatches.** That's a forensic concern, not a sidecar bug — escalate to the maintainer / compliance lead.

## Sandbox mode (for testing the doctor skill itself during development)

If `$TEAMVAULT_DEV_SANDBOX` is set, target `$TEAMVAULT_DEV_SANDBOX/.teamvault-test/` instead of `~/.teamvault/`, and probe the sandbox sidecar's port (default 18100) instead of 8100. Skip Layer 1.2 (launchd) and Layer 2.2 (MCP) — those are host-state checks and aren't part of the doctor logic under test.
