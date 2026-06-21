---
name: teamvault-setup
description: Install TeamVault on this machine and bind it to the project repo the user is in. Use when the user pastes the TeamVault setup prompt, says "install TeamVault", or asks to set up the team's shared KB / config substrate. Walks through cloning the team space, installing the sidecar, registering the MCP endpoint, writing the project's CLAUDE.md TeamVault block, and smoke-testing.
---

# TeamVault Setup

Walks through a clean install of TeamVault on the user's Mac, bound to the project repo their current shell is in.

## Preconditions

Verify these BEFORE proceeding. Surface any failure and STOP — do not try to work around.

```bash
gh auth status                                 # gh CLI authed (browser flow if not)
python3 --version                              # need 3.10+
git --version                                  # git installed
echo "${SHELL}"                                # zsh or bash
uname -m                                       # arm64 or x86_64
claude mcp list 2>&1 | head -3 || true         # `claude` CLI present; needed for MCP registration
lsof -i :8100 2>&1 | grep LISTEN || echo "port 8100 free"
```

If `claude mcp list` errors with "command not found", surface that — the user needs Claude Code installed and the `claude` CLI on PATH. If port 8100 is in use, ask the user to free it OR set `TEAMVAULT_PORT` to a different value (carry it through all subsequent steps).

## Flow

### 1. Identify the team space repo

Ask the user once: **"What is the URL of your team's TeamVault space repo?"**

For example: `https://github.com/your-org/teamvault-<space>`.

If the user doesn't have one yet, walk them through forking the master template:

```bash
gh repo fork tin-io/teamvault --org your-org --fork-name teamvault-<team> --clone=false
```

### 2. Derive paths + clone the space + reconcile space.yaml::name

```bash
SPACE_URL=<from user>
SPACE_NAME=$(basename "$SPACE_URL" | sed 's/\.git$//')
SPACE_DIR="$HOME/$SPACE_NAME"   # e.g. ~/teamvault-<space>
mkdir -p "$HOME/.teamvault/logs" "$HOME/Library/LaunchAgents"
git clone "$SPACE_URL" "$SPACE_DIR"
```

**Reconcile `space.yaml::name` with SPACE_NAME.** The master template ships with
`name: teamvault-template`; if the user forked without renaming, the sidecar
registers the WRONG space and reindex/search calls miss. Update in place:

```bash
# Set space.yaml::name to match SPACE_NAME (URL-derived)
if [ -f "$SPACE_DIR/space.yaml" ]; then
  python3 -c "
import sys, pathlib, yaml
p = pathlib.Path('$SPACE_DIR/space.yaml')
doc = yaml.safe_load(p.read_text()) or {}
doc['name'] = '$SPACE_NAME'
p.write_text(yaml.safe_dump(doc, sort_keys=False))
"
fi
```

If `space.yaml::name` was already set to `$SPACE_NAME` (because the fork was prepared properly), this is a no-op.

### 3. Detect the current project repo and stage a bind

```bash
PROJECT_REMOTE=$(git -C "$PWD" remote get-url origin)
```

Append to the space's `repos.yaml`. **The file is a YAML list and may be empty;
just append a new item at the bottom of the file** (do NOT replace existing
content):

```bash
cat >> "$SPACE_DIR/repos.yaml" <<EOF
- remote: $PROJECT_REMOTE
  workspace: default
EOF
```

Validate it parses:

```bash
python3 -c "import yaml, sys; yaml.safe_load(open('$SPACE_DIR/repos.yaml')) or []" \
  || { echo "ERROR: repos.yaml is malformed after append; abort and surface to user"; exit 1; }
```

If `space.yaml::compliance: true`: instead of direct push, open a PR:

```bash
cd "$SPACE_DIR"
git checkout -b "bind/$(echo "$PROJECT_REMOTE" | shasum | cut -c1-8)"
git add repos.yaml
git commit -m "bind: $PROJECT_REMOTE"
git push -u origin "$(git branch --show-current)"
gh pr create --title "bind: $PROJECT_REMOTE" --body "Adds $PROJECT_REMOTE to repos.yaml."
```

For a group onboarding the team space SHOULD pre-seed `repos.yaml` with all participant project repos BEFORE the session so there's no live-merge bottleneck during the install.

If `space.yaml::compliance: false` or unset: direct push allowed:

```bash
cd "$SPACE_DIR"
git add repos.yaml
git commit -m "bind: $PROJECT_REMOTE"
git push
```

### 4. Install the sidecar

```bash
cd "$SPACE_DIR/sidecar"
python3 -m venv .venv
.venv/bin/pip install --upgrade pip
.venv/bin/pip install -r requirements.txt
```

**Tell the user explicitly:** "This install pulls torch (~2.5 GB) and downloads the Nomic embedding model (~547 MB) on first reindex. On corporate Wi-Fi this can take 5–10 minutes; on conference Wi-Fi with multiple devs hitting PyPI simultaneously, plan 15–30 minutes. For a tight demo, pre-bake a wheelhouse or have devs install ahead of time."

### 5. Generate launchd plist

The plist must run uvicorn with the **sidecar package importable on `sys.path`**. Setting `WorkingDirectory` to `$SPACE_DIR` and adding `PYTHONPATH=$SPACE_DIR` is the simplest correct shape.

Write `$HOME/Library/LaunchAgents/dev.teamvault.sidecar.plist`:

```xml
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>dev.teamvault.sidecar</string>
    <key>ProgramArguments</key>
    <array>
        <string>${SPACE_DIR}/sidecar/.venv/bin/uvicorn</string>
        <string>sidecar.app:app</string>
        <string>--port</string>
        <string>${TEAMVAULT_PORT:-8100}</string>
    </array>
    <key>WorkingDirectory</key>
    <string>${SPACE_DIR}</string>
    <key>EnvironmentVariables</key>
    <dict>
        <key>TEAMVAULT_SPACE_ROOT</key>
        <string>${SPACE_DIR}</string>
        <key>TEAMVAULT_PORT</key>
        <string>${TEAMVAULT_PORT:-8100}</string>
        <key>PYTHONPATH</key>
        <string>${SPACE_DIR}</string>
    </dict>
    <key>RunAtLoad</key>
    <true/>
    <key>KeepAlive</key>
    <true/>
    <key>ThrottleInterval</key>
    <integer>10</integer>
    <key>StandardOutPath</key>
    <string>${HOME}/.teamvault/logs/sidecar.out.log</string>
    <key>StandardErrorPath</key>
    <string>${HOME}/.teamvault/logs/sidecar.err.log</string>
</dict>
</plist>
```

Load it:

```bash
launchctl bootstrap "gui/$(id -u)" "$HOME/Library/LaunchAgents/dev.teamvault.sidecar.plist"
```

Confirm:

```bash
launchctl list | grep dev.teamvault.sidecar
```

### 6. Register the MCP endpoint with Claude Code

Use the `claude` CLI — do NOT write `~/.claude/mcp_servers.json` directly; that is not the path Claude Code reads.

```bash
claude mcp add teamvault \
  --scope user \
  -e TEAMVAULT_SIDECAR_URL=http://localhost:${TEAMVAULT_PORT:-8100} \
  -e TEAMVAULT_SPACE_ROOT="$SPACE_DIR" \
  -e PYTHONPATH="$SPACE_DIR" \
  -- "$SPACE_DIR/sidecar/.venv/bin/python" -m sidecar.mcp_server
```

After adding, **tell the user to `/quit` and relaunch Claude Code** — MCP servers are only loaded at session start. Without the restart, `vault_status` / `vault_search` won't surface as tools.

### 7. Write the project-side `CLAUDE.md` block

Add a static TeamVault block to the project's `CLAUDE.md` so any agent
working in this repo knows how + when to use the vault MCP tools. The
helper is **idempotent** — re-running on a re-bind replaces the block in
place instead of duplicating it.

```bash
"$SPACE_DIR/sidecar/.venv/bin/python" -m sidecar.scripts.write_claude_md_block "$PWD"
```

Expected output, one of:

- `teamvault-block created in /path/to/project/CLAUDE.md` — new file
- `teamvault-block replaced in /path/to/project/CLAUDE.md` — existing block updated in place
- `teamvault-block appended in /path/to/project/CLAUDE.md` — added to existing CLAUDE.md without markers

The block is **static** — it never enumerates the team's `knowledge_topics`.
The agent learns them at runtime by calling `vault_packs()`. That way the
project CLAUDE.md doesn't drift when the space adds or removes packs.

### 7.5. Deploy opinionated PR workflow skills (optional)

The space repo ships an opinionated PR workflow as composable skills:
`pr-push`, `pr-review`, `pr-fix`, and `pr-pipeline` (conductor). They
need to be deployed INTO the bound project's `.claude/skills/` so they
fire when working in that project — not just when working in the space
repo. `code-structure` is NOT auto-deployed (each project owner writes
their own tailored version).

Detect what the space ships:

```bash
AVAILABLE=$(ls -d "$SPACE_DIR/.claude/skills/pr-"*/ 2>/dev/null | xargs -n1 basename | tr '\n' ' ')
```

If `$AVAILABLE` is empty (this space's fork stripped out the pr-*
skills), surface that and SKIP this entire step.

Otherwise, ask the user:

> "Deploy TeamVault's PR workflow skills (`$AVAILABLE`) into this
> project? Copies into `<project>/.claude/skills/` and commits to
> project git. You can delete later via `rm -rf .claude/skills/pr-*`.
> [Y/n]"

If yes, for each skill in `$AVAILABLE`:

1. If `<project>/.claude/skills/<name>/` already exists, ask the user
   whether to overwrite. Default: skip to preserve any project-side
   customizations.
2. Otherwise, copy the skill directory from space to project:

```bash
mkdir -p "$PROJECT_DIR/.claude/skills"
cp -r "$SPACE_DIR/.claude/skills/$NAME" "$PROJECT_DIR/.claude/skills/$NAME"
```

After all copies, commit to the project repo — stage only the deployed
paths, NEVER a blanket `git add .` (would sweep up unrelated working-
tree changes):

```bash
cd "$PROJECT_DIR"
for NAME in "${DEPLOYED[@]}"; do
    git add ".claude/skills/$NAME"
done
git commit -m "deploy teamvault pr-workflow skills: ${DEPLOYED[*]}"
```

Do NOT push automatically. The user pushes when ready (subject to their
normal "no push without approval" preference).

Confirm to the user:
- Which skills were deployed; which were skipped (already present)
- That after the Claude Code restart in §9 they'll have new slash
  commands available in this project: `/pr-push`, `/pr-review`,
  `/pr-fix`, `/pr-pipeline`
- That the commit is local — they need to push when ready

If the user answered no: skip silently. Mention they can deploy later
by re-running this setup skill, or by manually copying from
`$SPACE_DIR/.claude/skills/pr-*` into `<project>/.claude/skills/`.

**Why commit (not just copy)?** The team needs visibility into which
projects have the workflow deployed (consistency across repos). A copy-
only deploy benefits only this dev's machine; teammates who pull the
project don't get the skills.

**Why not auto-deploy `code-structure`?** That skill ships in the space
as a teamvault-tailored EXAMPLE of the reference-skill pattern. Each
project should write its own `code-structure` tuned to its conventions
— copying the example verbatim into a non-teamvault project would
inject wrong architectural guidance.

### 8. Smoke test (BEFORE the user restarts Claude Code)

The sidecar can take 8-15s to come up on first launch (cold imports + torch lazy
loading). Retry instead of sleeping a fixed amount:

```bash
PORT=${TEAMVAULT_PORT:-8100}
for i in 1 2 3 4 5 6 7 8 9 10; do
  curl -sf "http://localhost:$PORT/healthz" >/dev/null && break
  sleep 2
done
curl -s "http://localhost:$PORT/healthz" | python3 -m json.tool
```

Expect `status: ok` and the space registered (with `name` matching `$SPACE_NAME`
because §2 reconciled it). Then trigger initial reindex:

```bash
curl -s -X POST "http://localhost:$PORT/reindex" \
  -H 'Content-Type: application/json' \
  -d "{\"space\":\"$SPACE_NAME\"}"
```

First reindex downloads the Nomic model (~547 MB) — tell the user "this can take 1-3 minutes on first run; subsequent reindexes are <1s on warm cache."

### 9. Confirm to user, then prompt restart

Show:

- The space they're now bound to (`SPACE_NAME` + `SPACE_DIR`)
- That the sidecar is running (`launchctl list | grep teamvault`)
- That the MCP server is registered (`claude mcp list | grep teamvault`)
- The slash commands they now have: `/teamvault-publish`, `/teamvault-review` (always); plus `/pr-push`, `/pr-review`, `/pr-fix`, `/pr-pipeline` if §7.5 deployed them

Then: **"Run `/quit` to exit Claude Code and relaunch from your terminal. After relaunch, the `vault_search`, `vault_publish`, and `vault_status` MCP tools will be available."**

## On failure

- **`pip install` fails**: surface the exact error; on Apple Silicon, common cause is missing build tools — run `xcode-select --install`.
- **`launchctl bootstrap` fails**: try `launchctl bootstrap` without `gui/$UID`, surface the output, ensure `$HOME/Library/LaunchAgents` exists.
- **MCP registration fails**: `claude mcp list` errors mean the `claude` CLI isn't on PATH or the version is too old to support `mcp add`. Surface the version (`claude --version`) and ask the user to update.
- **`/healthz` doesn't respond**: tail `$HOME/.teamvault/logs/sidecar.err.log`; common causes are missing deps, port collision, plist module-path mismatch.
- **`vault_status` not found after restart**: confirm `claude mcp list` shows `teamvault`; if it does but tools don't appear, the sidecar may not have come up — re-check `/healthz`.

## Sandbox mode (for testing the setup-skill itself during development)

If `$TEAMVAULT_DEV_SANDBOX` is set, target it instead of `$HOME/teamvault-<space>/` and use `TEAMVAULT_HOME=$TEAMVAULT_DEV_SANDBOX/.teamvault-test/` instead of `$HOME/.teamvault/`. Skip the launchd plist + `claude mcp add` steps in sandbox mode — run the sidecar manually with `uvicorn sidecar.app:app --port 18100` and connect to it directly. Used during build dry-runs to avoid touching real user state.
