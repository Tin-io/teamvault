# 🛠️ TeamVault — Troubleshooting

> ✨ Day-of failure modes and recovery for your team's devs. Read top-down — most-likely-first.

<p align="center">
  <img src="https://img.shields.io/badge/scope-Mac%20v0.0-orange?style=flat-square&logo=apple&logoColor=white" alt="Scope: Mac v0.0">
  <img src="https://img.shields.io/badge/format-symptom%20%E2%86%92%20check%20%E2%86%92%20fix-7c3aed?style=flat-square" alt="Symptom → Check → Fix">
</p>

For each symptom: **Check** (one command), then **Fix** (one or two commands).

> 🍎 **OS scope:** the recovery commands below are Mac-only — `launchctl`, `~/Library/LaunchAgents/`, `~/.teamvault/logs/`, `lsof`, etc. v0.0 supports macOS only. Linux support lands in v0.1 (systemd user unit equivalents); Windows in v0.2 (Service/scheduled task + PowerShell). On Linux today: substitute `systemctl --user status teamvault-sidecar` for `launchctl list | grep dev.teamvault.sidecar`, `journalctl --user -u teamvault-sidecar` for the launchd log paths, and adapt the `~/Library/...` paths to `~/.config/systemd/user/` + `~/.local/share/teamvault/`. Full table in `docs/USER_GUIDE.md::OS support`.

## 🦾 Sidecar

### 🚨 Symptom: `vault_search` / `vault_publish` returns nothing or errors

**Check first** (this is usually the answer):

```bash
curl -s --max-time 5 http://localhost:8100/healthz
```

If that hangs or refuses, the sidecar isn't running. If it returns JSON, scroll to "Search returns nothing" further down.

**Fix — sidecar down**:

```bash
launchctl list | grep dev.teamvault.sidecar     # is the launch agent registered?
launchctl kickstart -k gui/$(id -u)/dev.teamvault.sidecar
sleep 5
curl -s http://localhost:8100/healthz | head
```

**Fix — sidecar wedged** (launchctl shows it but /healthz hangs):

```bash
tail -n 30 ~/.teamvault/logs/sidecar.err.log    # look for the last exception
launchctl kickstart -k gui/$(id -u)/dev.teamvault.sidecar
```

### 🚨 Symptom: Sidecar crashes on boot

**Check**: `tail -n 30 ~/.teamvault/logs/sidecar.err.log`

Common causes:

| Log line contains | Cause | Fix |
|---|---|---|
| 📦 `ModuleNotFoundError: No module named 'sidecar'` | PYTHONPATH not set in plist | Edit `~/Library/LaunchAgents/dev.teamvault.sidecar.plist` `EnvironmentVariables.PYTHONPATH` to the space dir; reload plist |
| 🔌 `OSError: [Errno 48] Address already in use` | Port 8100 collision | Stop the conflicting process (`lsof -ti :8100 | xargs kill`) or change `TEAMVAULT_PORT` in the plist + `claude mcp add` env |
| 📁 `FileNotFoundError: ... space.yaml` | TEAMVAULT_SPACE_ROOT wrong | Confirm `~/teamvault-<space>/space.yaml` exists; correct the plist `EnvironmentVariables.TEAMVAULT_SPACE_ROOT` |
| 🔒 `OSError: Read-only file system` | macOS sealed write to `/Library` | Don't put state under `/Library`; default `~/.teamvault/` is right |
| 📝 `yaml.YAMLError: while parsing a block collection` | Bad `space.yaml` or `repos.yaml` | Validate with `python3 -c "import yaml; yaml.safe_load(open('repos.yaml'))"`; fix the YAML |

## 🔌 MCP

### 🚨 Symptom: `vault_*` tools missing in Claude Code

**Check**:

```bash
claude mcp list | grep teamvault
```

If empty: never registered. Re-run setup §6:

```bash
claude mcp add teamvault --scope user \
  -e TEAMVAULT_SIDECAR_URL=http://localhost:8100 \
  -e TEAMVAULT_SPACE_ROOT="$HOME/teamvault-<space>" \
  -e PYTHONPATH="$HOME/teamvault-<space>" \
  -- "$HOME/teamvault-<space>/sidecar/.venv/bin/python" -m sidecar.mcp_server
```

Then `/quit` Claude Code and relaunch.

If `claude mcp list` shows `teamvault` but the tools don't appear in the session: **you didn't restart Claude Code after `mcp add`**. MCP servers only load at session start. `/quit` and relaunch.

If the tools surface but always return errors: the MCP shim can't reach the sidecar. Check `vault_status` (returns `error: ...`); usually the sidecar is down — go back to the sidecar section above.

## 🔍 Search

### 🚨 Symptom: `vault_search` returns no hits even for content that's clearly in the KB

**Check**:

```bash
# 1. is the index populated?
curl -s -X POST http://localhost:8100/reindex -H 'Content-Type: application/json' \
  -d '{"space":"<your-space>"}'
# look at indexed / skipped counts

# 2. confirm the space name
curl -s http://localhost:8100/healthz | python3 -m json.tool
```

If `indexed: 0, skipped: 0` and you have entries in `kb/entries/`: the sidecar isn't looking in the right place. The `space` field in `/reindex` must match the registered space name in `/healthz`. Either:

- Update `space.yaml::name` to match what your reindex POST is sending; restart sidecar
- Or update your POST body to use the registered name

If `skipped` matches the entry count and you still see no hits: the LanceDB vault may have been built with a different embedding model. Wipe and re-embed:

```bash
rm -rf ~/.teamvault/<space>/vault.lance ~/.teamvault/<space>/fts.db
curl -s -X POST http://localhost:8100/reindex -d '{"space":"<space>"}' \
  -H 'Content-Type: application/json'
```

### 🚨 Symptom: Search hits look stale (entry was edited but old content surfaces)

This was a known bug in Phase 1 (ghost chunks), fixed in Phase 2. If you're still seeing it:

```bash
# Force a full reindex
rm -rf ~/.teamvault/<space>/vault.lance ~/.teamvault/<space>/fts.db
curl -s -X POST http://localhost:8100/reindex -d '{"space":"<space>"}' \
  -H 'Content-Type: application/json'
```

## 📤 Publish

### 🚨 Symptom: `/teamvault-publish` says "Content blocked by pack scrubber"

Working as designed — the HIPAA pack matched a PHI pattern in your content (or in frontmatter values). The response message names the matched pattern.

**Fix**: redact the matched content. Common cases:

- `mrn_with_prefix` matched: replace with `SYNTHETIC_MRN_<index>` if it was test data; otherwise summarize without the identifier
- `email` matched: replace with `<redacted-email>` or `name@example.com` placeholder
- `dob_full_with_prefix` matched: don't include DOB at all unless the entry is about a non-patient

### 🚨 Symptom: Entry published but not visible on other devs' machines

Eventual consistency. Each dev's sidecar pulls every 60s. Within ~60-90s the entry should be on every clone. If it's been longer:

```bash
# On the dev's machine that's missing the entry
curl -s http://localhost:8100/healthz | python3 -m json.tool   # see last_pull
tail -n 20 ~/.teamvault/logs/sidecar.err.log                   # any git fetch errors?
```

If `last_pull` is stale: the git fetch is failing. Common cause: expired gh auth. Run `gh auth status` on that machine.

If `last_pull` is recent but the entry isn't searchable on that machine: their reindex may have errored. Trigger manually: `curl -X POST http://localhost:8100/reindex -d '{"space":"<space>"}' -H 'Content-Type: application/json'`.

## 👀 Review

### 🚨 Symptom: PR `teamvault-review` GHA fails with `ModuleNotFoundError: sidecar`

The workflow runs `python -c "..."` from the checkout root. The checkout must have `sidecar/` at its top level. Confirm:

- Your space repo is a fork of `tin-io/teamvault` (which has `sidecar/` at root)
- You haven't moved or renamed the `sidecar/` directory

### 🚨 Symptom: PR `teamvault-review` blocks but I don't see PHI in my diff

The pack runtime scans **added lines** (lines starting with `+` but not `+++`). The match could be:

- In a test file with hardcoded test data
- In a docstring or comment that mentions an MRN-shape number
- In a commit message that became part of the PR body

Check the workflow's posted comment — it names the matched pattern. If the match is a false positive (you're documenting the format, not leaking PHI), restructure the line so the pattern doesn't match (e.g., split the prefix from the digits across whitespace, or put the example in a fenced code block the regex doesn't see).

### 🚨 Symptom: `clickup-linkage` keeps failing on PRs that DO have a ClickUp link

The pack checks the diff text for `clickup.com` substring. If your link is only in the PR description (not the diff), the v0.0 check misses it. v0.1 will read PR description from `${{ github.event.pull_request.body }}`. For now: include the ClickUp URL in your first commit message body so it ends up in the diff context, or add it as a comment in any file you're touching.

## 🔄 Git sync

### 🚨 Symptom: `last_pull` in `/healthz` is older than 5 minutes

The background sync loop has stopped or is hitting an error.

**Check**: `tail -n 30 ~/.teamvault/logs/sidecar.err.log` and look for `sync failed:` or `git error:` lines.

Common causes:

- **`local changes block sync`**: the space clone has uncommitted edits. Don't edit `~/teamvault-<space>/` directly; use `/teamvault-publish` for KB entries and PRs for config. Stash or commit the local edit.
- **`non-fast-forward upstream`**: someone force-pushed to the space repo's main. v0.0 refuses non-FF; recovery is manual:

  ```bash
  cd ~/teamvault-<space>
  git fetch origin
  git reset --hard origin/main   # ONLY if you accept the rewritten history
  ```

- **`git error: ... Authentication failed`**: expired auth. `gh auth refresh` on that machine.

## 🎤 Demo-day

### ⏱️ "The install is taking too long"

Expected. Torch is 2.5GB; on conference Wi-Fi with N devs hitting PyPI simultaneously, plan 15-30 min. Mitigations for next demo:

- Pre-install on attendee laptops the day before
- Bring a USB stick with a pre-baked wheelhouse (v0.1)

### 🗺️ "I'm in the wrong space"

Each dev's sidecar can only register one space in v0.0 (multi-space is v0.1). To switch:

```bash
launchctl bootout gui/$(id -u)/dev.teamvault.sidecar
# Edit ~/Library/LaunchAgents/dev.teamvault.sidecar.plist:
#   TEAMVAULT_SPACE_ROOT → the new space dir
launchctl bootstrap gui/$(id -u) ~/Library/LaunchAgents/dev.teamvault.sidecar.plist
```

### 💥 "I want to start fresh — nuke everything and try again"

```bash
# Stop and remove the launch agent
launchctl bootout gui/$(id -u)/dev.teamvault.sidecar 2>/dev/null
rm -f ~/Library/LaunchAgents/dev.teamvault.sidecar.plist

# Remove sidecar state (keeps the space clone)
rm -rf ~/.teamvault

# Remove MCP registration
claude mcp remove teamvault --scope user

# Now re-run the setup prompt
```

### ❓ "Should I commit my edit to `kb/entries/foo.md` directly?"

Yes if it's a KB entry edit (the file you'd publish via `/teamvault-publish` — direct push is allowed for `kb/**`). No for `config/**`, `packs/**`, `repos.yaml`, `space.yaml` — those want a PR per the team's CODEOWNERS.

---

> 💡 If none of the above match: open a `teamvault-debug-<date>` ticket in ClickUp, attach `~/.teamvault/logs/sidecar.err.log`, and tag the maintainer.
