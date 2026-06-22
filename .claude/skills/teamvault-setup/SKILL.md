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

**First, ask the user:** "Do you already have a TeamVault space fork for your team, or are you the first dev — meaning we need to create the fork now?"

**If they have a fork already:** ask "What's the URL of your team's TeamVault space repo?" — e.g. `https://github.com/your-org/teamvault-<team>`. Capture as `SPACE_URL`.

**If they're the seeder (no fork yet):** walk them through forking the master template:

```bash
gh repo fork tin-io/teamvault --org <their-org> --fork-name teamvault-<team> --clone=false
```

Then derive `SPACE_URL=https://github.com/<their-org>/teamvault-<team>` and proceed.

Either branch ends with `SPACE_URL` captured.

### 2. Derive paths + clone the space + reconcile space.yaml::name

```bash
SPACE_URL=<from user, captured in §1>
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

**If `space.yaml::name` was actually changed by the reconcile, commit the rename now** so the fork carries the renamed identity forward — otherwise it sits dirty in the working tree and may contaminate the §3 bind commit:

```bash
if [ -n "$(git -C "$SPACE_DIR" status --porcelain space.yaml)" ]; then
  cd "$SPACE_DIR"
  git add space.yaml
  git commit -m "fork: rename space to $SPACE_NAME"
  git push 2>/dev/null || echo "(push deferred — no upstream yet or no permission)"
fi
```

### 2.5. Confirm enabled packs

Read what the space currently declares:

```bash
PACKS_NOW=$(python3 -c "
import yaml; d = yaml.safe_load(open('$SPACE_DIR/space.yaml'))
print(','.join(d.get('enabled_packs') or []))
")
```

**Ask the user:**

> "This space currently enables packs: `$PACKS_NOW` (master template defaults to `hipaa-reference + clickup`). Keep as-is, modify, or set to none? Available in the master template: `hipaa-reference`, `clickup`, `jira-linkage`. (keep / new comma-separated list / none)"

If the user says "keep" (or confirms by saying anything affirmative), do nothing further. Otherwise persist their choice:

```bash
PACKS_INPUT="<from user, e.g. 'hipaa-reference,jira-linkage' or 'none'>"
if [ "$PACKS_INPUT" != "keep" ] && [ -n "$PACKS_INPUT" ]; then
  python3 -c "
import pathlib, yaml
p = pathlib.Path('$SPACE_DIR/space.yaml')
doc = yaml.safe_load(p.read_text()) or {}
if '$PACKS_INPUT' == 'none':
    doc['enabled_packs'] = []
else:
    doc['enabled_packs'] = [s.strip() for s in '$PACKS_INPUT'.split(',') if s.strip()]
# hipaa-reference implies compliance: true (PR-gated binds + no-auto-deploy)
if 'hipaa-reference' in (doc.get('enabled_packs') or []):
    doc['compliance'] = True
p.write_text(yaml.safe_dump(doc, sort_keys=False))
"
  cd "$SPACE_DIR"
  git add space.yaml
  git commit -m "seed: enabled_packs=$PACKS_INPUT"
  git push 2>/dev/null || echo "(push deferred — no upstream yet or no permission)"
fi
```

**Compliance side-effect to surface explicitly:** enabling `hipaa-reference` automatically sets `space.yaml::compliance: true`, which makes §3's bind step PR-gated (instead of direct-push) and disables auto-deploy of pack updates. Tell the user before persisting so they're not surprised.

Verify the final state:

```bash
python3 -c "
import yaml
d = yaml.safe_load(open('$SPACE_DIR/space.yaml'))
print('enabled_packs:', d.get('enabled_packs', []))
print('compliance:', d.get('compliance', False))
"
```

### 3. Detect the current project repo and stage a bind

```bash
PROJECT_REMOTE=$(git -C "$PWD" remote get-url origin)
```

**Ask the user before persisting:**

> "I'm about to bind `$PROJECT_REMOTE` to space `$SPACE_NAME` by appending to `repos.yaml`. This commits and pushes to the space repo (or opens a PR if `compliance: true`). Confirm? (Y/n — defaults Y)"

If the user declines: ask which repo they DID want bound (they can `cd` to the right project dir and re-run this skill), or skip the bind entirely and proceed to sidecar install — the install works without the bind; binding can be added later by re-running this skill from the correct project directory.

If confirmed, append to the space's `repos.yaml`. **The file is a YAML list and may be empty; just append a new item at the bottom of the file** (do NOT replace existing content):

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

**Tell the user explicitly:** "This install pulls torch (~2.5 GB) and downloads the Nomic embedding model (~547 MB) on first reindex. On corporate Wi-Fi this can take 5–10 minutes; on conference Wi-Fi with multiple devs hitting PyPI simultaneously, plan 15–30 minutes. For a tight demo, have devs install ahead of time."

### 5. Generate launchd plist

The plist must run uvicorn with the **sidecar package importable on `sys.path`**. Setting `WorkingDirectory` to `$SPACE_DIR` and adding `PYTHONPATH=$SPACE_DIR` is the simplest correct shape.

Write `$HOME/Library/LaunchAgents/dev.teamvault.sidecar.plist` — **use an unquoted heredoc** (`cat > $PLIST <<EOF ... EOF`, NOT `<<'EOF'`) so bash expands `${SPACE_DIR}`, `${TEAMVAULT_PORT:-8100}`, and `${HOME}` inline before launchd reads the file. A quoted heredoc produces a plist with literal `${...}` strings; launchd rejects the port as invalid and the sidecar never starts.

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

Detect what the space ships, and capture the project directory (= the agent's current working dir — the project repo the user started the skill in):

```bash
PROJECT_DIR="$PWD"
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

### 7.6. Deploy TeamVault substrate skills to user-global

The `teamvault-*` slash commands (`/teamvault-publish`, `/teamvault-status`, `/teamvault-review`, `/teamvault-doctor`) need to be visible from any directory — not just from inside the space dir — so devs can invoke them while working in bound project repos. Claude Code looks in `~/.claude/skills/` for user-global skills regardless of cwd. Copy them from the space fork into `~/.claude/skills/`. Re-runnable: ask before overwriting any existing destination (preserves per-team customizations).

```bash
mkdir -p "$HOME/.claude/skills"

SUBSTRATE_SKILLS=(teamvault-publish teamvault-status teamvault-review teamvault-doctor)
DEPLOYED_GLOBAL=()
SKIPPED_GLOBAL=()

for NAME in "${SUBSTRATE_SKILLS[@]}"; do
    SRC="$SPACE_DIR/.claude/skills/$NAME"
    DST="$HOME/.claude/skills/$NAME"

    if [ ! -d "$SRC" ]; then
        SKIPPED_GLOBAL+=("$NAME (not in fork — skipping)")
        continue
    fi

    if [ -d "$DST" ]; then
        # Ask the user — default Y; preserve customizations if they say n.
        echo "  $DST already exists. Overwrite with the version from the space fork? [Y/n]"
        # If user answers no: SKIPPED_GLOBAL+=("$NAME (existing preserved)"); continue
        rm -rf "$DST"
    fi

    cp -r "$SRC" "$DST"
    DEPLOYED_GLOBAL+=("$NAME")
done
```

Confirm to the user:

- Which substrate skills are now in `~/.claude/skills/` (the `DEPLOYED_GLOBAL` list); which were skipped + why
- After the Claude Code restart in §9, slash commands `/teamvault-publish`, `/teamvault-status`, `/teamvault-review`, `/teamvault-doctor` will work from ANY directory — not just from inside `$SPACE_DIR`
- Re-running this setup skill (or v0.1.5+'s planned `/teamvault-deploy-skills`) refreshes these copies after an upstream sync into the space fork

**Why user-global, not per-project?** These skills talk to the sidecar over `localhost` regardless of which project the dev is currently in. The MCP tools (`vault_search`, `vault_publish`, etc.) already work everywhere because MCP was registered with `--scope user` in §6 — this step matches that scope for the slash commands.

**Why not `teamvault-setup` itself?** Re-installs always start from the master template at `/tmp/teamvault-master`. Setup stays in the space dir; no need to clone it to user-global.

**Why not `pr-*`?** Those are project-workflow skills, deployed per-project via §7.5 (and committed to project repos so teammates without TeamVault still get them via git). Different lifecycle entirely.

### 7.7. Deploy pack-shipped skills (v0.2+ pack contract)

Each enabled pack MAY declare workflow skills under `contributions.skills` in its `PACK.yaml`. These ship inside the pack as `<pack-root>/skills/<skill-name>/SKILL.md` directories. They need to be copied into `~/.claude/skills/` so the slash commands become available from any project the dev is in.

This step makes a pack a self-contained domain capability bundle: enable `clickup` and you get `clickup-linkage-reviewer` (via /teamvault-review) AND `/start-clickup` (via slash command) AND any other ClickUp skills the pack ships — all from one `enabled_packs: [clickup]` declaration.

Discover what each enabled pack ships:

```bash
PACK_SKILLS_DEPLOYED=()
PACK_SKILLS_SKIPPED=()

for PACK_DIR in "$SPACE_DIR/packs/"*/; do
    PACK_NAME=$(basename "$PACK_DIR")
    PACK_YAML="$PACK_DIR/PACK.yaml"
    [ ! -f "$PACK_YAML" ] && continue

    # Only deploy skills from ENABLED packs (per space.yaml::enabled_packs)
    IS_ENABLED=$(python3 -c "
import yaml
space = yaml.safe_load(open('$SPACE_DIR/space.yaml')) or {}
enabled = space.get('enabled_packs') or []
print('yes' if '$PACK_NAME' in enabled else 'no')
")
    [ "$IS_ENABLED" != "yes" ] && continue

    # Read declared skills from PACK.yaml::contributions.skills
    SKILL_PATHS=$(python3 -c "
import yaml
doc = yaml.safe_load(open('$PACK_YAML')) or {}
for sk in (doc.get('contributions', {}) or {}).get('skills', []) or []:
    print(sk['path'])
")

    while IFS= read -r SK_REL; do
        [ -z "$SK_REL" ] && continue
        SRC="$PACK_DIR$SK_REL"
        SK_NAME=$(basename "$SK_REL")
        DST="$HOME/.claude/skills/$SK_NAME"

        if [ ! -d "$SRC" ]; then
            PACK_SKILLS_SKIPPED+=("$PACK_NAME/$SK_NAME (declared but dir missing)")
            continue
        fi
        if [ ! -f "$SRC/SKILL.md" ]; then
            PACK_SKILLS_SKIPPED+=("$PACK_NAME/$SK_NAME (no SKILL.md)")
            continue
        fi

        if [ -d "$DST" ]; then
            # Conflict — ASK the user (overwrite / skip). Default: skip,
            # to preserve user-side customizations.
            echo "  $DST already exists. Overwrite with the version from pack '$PACK_NAME'? [y/N]"
            # If user answers y: rm -rf "$DST"; cp -r "$SRC" "$DST"; PACK_SKILLS_DEPLOYED+=("$PACK_NAME/$SK_NAME (overwrote)")
            # If user answers anything else: PACK_SKILLS_SKIPPED+=("$PACK_NAME/$SK_NAME (preserved existing)"); continue
            continue
        fi

        cp -r "$SRC" "$DST"
        PACK_SKILLS_DEPLOYED+=("$PACK_NAME/$SK_NAME")
    done <<< "$SKILL_PATHS"
done
```

**Conflict policy:** when `~/.claude/skills/<name>/` already exists, ASK the user (via `AskUserQuestion`) whether to overwrite or skip. Default: skip (preserves customizations). Do NOT silently overwrite — agent skills often contain per-user tweaks the dev wants to keep.

Confirm to the user:
- Which pack skills were deployed (the `DEPLOYED` list) — e.g. `clickup/start-clickup`
- Which were skipped + why (`existing preserved`, `declared but missing`, `no SKILL.md`)
- After the Claude Code restart in §9, the new slash commands will be available from any directory: e.g. `/start-clickup`

**Re-deploy after upstream pack update:** when a pack's skills are revised upstream and your space pulls them via `git_sync`, re-run this setup skill to refresh. v0.1.5+'s planned `/teamvault-pack-upgrade` will do this incrementally instead of running the full setup.

**Why user-global, not per-project?** Pack-shipped skills are tied to the enabled packs of the bound space — they're capabilities the space provides, not the project. If a dev later binds a project to a DIFFERENT space with different enabled packs, they'll re-run this setup to refresh the user-global skill set. (v0.1.5+ may add per-project scoping for packs that declare it.)

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
