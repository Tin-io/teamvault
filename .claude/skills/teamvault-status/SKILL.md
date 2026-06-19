---
name: teamvault-status
description: Diagnose the TeamVault install — sidecar health, registered spaces, last pull times, vault index state, MCP registration, port listener. Use when the user asks "is TeamVault running", "why isn't vault_search returning anything", "what space am I in", or anything similar. Read-only; safe to invoke at any time.
---

# TeamVault Status

A diagnostic for the local TeamVault install. Reports what's healthy, what's not, and what to look at next.

## When to use

- User says "is TeamVault working" / "what's the status" / "vault_search returns nothing"
- User just installed and wants to confirm everything is wired up
- Debugging "why does the agent not see the team's KB"
- Before a demo, to confirm sidecar is alive

## Flow

Run these checks in parallel (Bash), then format a concise report:

### 1. Sidecar process + listener

```bash
PORT=${TEAMVAULT_PORT:-8100}
lsof -ti :"$PORT"   # PID(s) listening on the sidecar port
launchctl list | grep dev.teamvault.sidecar 2>&1 || true
```

### 2. /healthz response

```bash
curl -s --max-time 5 "http://localhost:${PORT}/healthz" | python3 -m json.tool
```

Parse: `status`, `version`, registered spaces (name, last_pull, last_error).

### 3. cwd → space routing

```bash
PROJECT_REMOTE=$(git -C "$PWD" remote get-url origin 2>/dev/null || echo "<no git remote>")
echo "current project remote: $PROJECT_REMOTE"
```

For each registered space, check if `repos.yaml` includes this remote:

```bash
SPACE_DIR="$HOME/teamvault-<space-name>"   # discover from registry
grep -F "$PROJECT_REMOTE" "${SPACE_DIR}/repos.yaml" || echo "not bound to <space-name>"
```

### 4. MCP registration

```bash
claude mcp list 2>&1 | grep teamvault || echo "teamvault MCP NOT registered"
```

### 5. Vault state (per registered space)

```bash
ls -la "$HOME/.teamvault/<space>/"      # vault.lance + fts.db should exist
du -sh "$HOME/.teamvault/<space>/vault.lance"
```

### 6. Logs (last 10 lines if /healthz unhealthy)

```bash
tail -n 20 "$HOME/.teamvault/logs/sidecar.err.log"
tail -n 20 "$HOME/.teamvault/logs/sidecar.out.log"
```

## Output format

A compact table the user can scan in 5 seconds:

```
TeamVault status

Component             Status   Detail
--------------------- -------- --------------------------------
sidecar process       OK       PID 12345 listening on :8100
launchd job           OK       dev.teamvault.sidecar
/healthz              OK       version 0.0.1
space: example-space  OK       last_pull: 2026-06-15T10:42Z
project bind          OK       remote → space example-space
MCP registration      OK       teamvault registered (user scope)
vault index           OK       vault.lance 42MB, fts.db 1.2MB
```

If any component is degraded, replace OK with a clear status (DEGRADED / DOWN / UNKNOWN) and surface the underlying error message.

### Specific failure tells

- **/healthz times out or refuses**: sidecar crashed or wedged → tail sidecar.err.log; surface `launchctl kickstart -k gui/$(id -u)/dev.teamvault.sidecar` as remediation.
- **MCP NOT registered**: `claude mcp add teamvault ...` step of the setup skill didn't run or rolled back. Re-run setup §6.
- **MCP registered but tools missing**: user didn't restart Claude Code after `claude mcp add`. Tell them: "Run `/quit` and relaunch — MCP servers only load at session start."
- **project bind: not bound to any space**: the current project repo's git remote isn't in any space's `repos.yaml`. Walk them through `/teamvault-bind`.
- **last_pull stale (>5min)**: git_sync isn't running OR upstream is unreachable. Check sidecar.err.log for `git error:` messages.
- **vault.lance missing**: no reindex has run yet. Suggest: `curl -X POST http://localhost:${PORT}/reindex -d '{"space":"..."}'`.

## Don't do

- Don't attempt to fix anything autonomously. Status is read-only; remediation requires explicit user confirmation.
- Don't run `/healthz` more than once per invocation.
- Don't enumerate logs longer than 20 lines.
