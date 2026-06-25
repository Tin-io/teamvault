# 📚 TeamVault — User Guide

> ✨ Everything you need to install, use, extend, and integrate TeamVault into your team's AI coding workflow. Reading time: ~15 minutes. Working knowledge afterward: enough to install on day one and use it on day two.

<p align="center">
  <img src="https://img.shields.io/badge/status-v0.0%20alpha-orange?style=flat-square" alt="Status: v0.0 alpha">
  <img src="https://img.shields.io/badge/audience-end%20users-blue?style=flat-square" alt="Audience: end users">
  <img src="https://img.shields.io/badge/sections-11-555?style=flat-square" alt="11 sections">
</p>

## 📋 Table of contents

1. [OS support](#os-support) — Mac in v0.0; Linux + Windows in upcoming releases
2. [What TeamVault is](#what-teamvault-is) — the 2-paragraph mental model
3. [Quick start](#quick-start) — paste this prompt, you're installed in ~10 min
4. [The four daily moves](#the-four-daily-moves) — publish · search · review · status
5. [Packs: how compliance & ticket-linkage work](#packs-how-compliance--ticket-linkage-work)
6. [Workflow integration](#workflow-integration) — `/start-ticket`, OMC, vanilla Claude Code, Codex
7. [Your responsibility](#your-responsibility) — what TeamVault does and doesn't do
8. [Frictionless adoption — recommendations](#frictionless-adoption--recommendations)
9. [Troubleshooting](#troubleshooting) — symptom → fix
10. [Glossary](#glossary)
11. [Where to go next](#where-to-go-next)

---

## 💻 OS support

**TL;DR — v0.0 is Mac-only as written. Linux and Windows support are on the roadmap for the next release.**

<p align="center">
  🍎 <b>macOS</b> v0.0 &nbsp;·&nbsp; 🐧 <b>Linux</b> v0.1 &nbsp;·&nbsp; 🪟 <b>Windows</b> v0.2 &nbsp;·&nbsp; 🐳 <b>Docker</b> v0.2
</p>

| OS | Runtime (sidecar, packs, MCP) | Install + supervisor + docs | Status |
|---|---|---|---|
| 🍎 **macOS** | ✓ Works | ✓ Documented (launchd plist, `~/Library/LaunchAgents/`, `claude mcp add`) | **Supported in v0.0** |
| 🐧 **Linux** | ✓ Works (pure Python; all deps have Linux wheels) | ✗ Needs systemd user unit instead of launchd; setup-skill bash adaptation | **Coming in v0.1** (~2-3h adaptation, sized in `docs/ROADMAP.md` as P2) |
| 🪟 **Windows** | ✓ Works (pure Python; torch + lancedb have Windows wheels) | ✗ Needs Windows Service or scheduled-task; PowerShell setup-skill rewrite | **Coming in v0.2** (~4-8h adaptation, sized in ROADMAP) |

The runtime layer is OS-agnostic by design — the sidecar is pure Python with cross-platform dependencies (FastAPI, LanceDB, SQLite FTS5, sentence-transformers, gitpython, MCP). What's Mac-only in v0.0 is the **process-supervisor + install recipe**: launchd plist, `~/Library/LaunchAgents/`, the bash-heavy setup skill, and the troubleshooting commands.

**If you want to run on Linux or Windows in v0.0**, you're forking the setup skill — the rest works as-is. The fork needed:

- 🐧 **Linux (~2-3h):** replace the launchd plist with a systemd user unit (`~/.config/systemd/user/teamvault-sidecar.service`); swap `launchctl bootstrap` for `systemctl --user enable --now`. Bash stays. ~30 lines of skill rewrite.
- 🪟 **Windows (~4-8h):** replace launchd with a Windows Service or scheduled task; rewrite the bash setup to PowerShell; replace `~/Library/...` paths with `%APPDATA%\teamvault\...`. Larger lift because bash-heavy ops need PowerShell equivalents.

Linux support lands first (next release, v0.1). Windows follows (v0.2). Both are sized + sequenced in `docs/ROADMAP.md`.

### 🐳 Docker (v0.2, parallel install path)

A Docker image (`ghcr.io/tin-io/teamvault-sidecar`) is planned for v0.2 as a **parallel** install option alongside the per-OS native installs. The image would pre-bake the torch dep + Nomic model (cutting first-run from ~10 min to ~30s) and replace the launchd / systemd / Windows Service supervisor with `docker run --restart=unless-stopped` — one command, three OSes.

The MCP shim stays native (it has to run as a Claude Code stdio subprocess); only the FastAPI sidecar gets containerized. Sidecar talks to the shim via `host.docker.internal`.

**Why parallel, not primary:** native pip install works today and many devs don't have Docker Desktop. v0.2 ships both paths; v0.3 decides based on adoption data whether Docker becomes primary. Full tradeoff analysis + sizing in `docs/ROADMAP.md::P2.9`.

---

## 🧩 What TeamVault is

**Mental model in two paragraphs.**

TeamVault is a git-synced knowledge base + configuration substrate that your AI coding agents can read AND write. The substrate is plain markdown files (`kb/entries/*.md`) in a team-owned git repo. Agents query via an MCP tool (`vault_search`). Humans browse via GitHub's web UI. When one teammate publishes a decision, it propagates to every teammate's machine within ~60 seconds via a background `git pull`. **Same source of truth, two access patterns.**

Packs extend it. Drop a `packs/hipaa-reference/` directory containing regex patterns + a reviewer-agent prompt, and every PR opened against your team's repos gets reviewed for PHI leaks — fails the merge check if patterns match. Drop a `packs/clickup-linkage/` directory and PRs without a ticket URL get flagged. The runtime is generic; what your team cares about is declared in packs you enable in `space.yaml`. Add or remove packs; the runtime adapts.

**Two things to remember:**

- **Substrate = markdown in git.** Indexes (LanceDB vector + SQLite FTS5) are disposable; they're rebuilt from `kb/` in minutes.
- **Packs = composable team policy.** TeamVault knows nothing about HIPAA, SOC 2, PCI, or your specific compliance regime — you do, and you declare it via packs.

---

## 🚀 Quick start

### 📋 Prerequisites (one-time, per Mac)

> See [OS support](#os-support) above. v0.0's quick start targets macOS; Linux instructions ship in v0.1, Windows in v0.2.

- macOS (Linux support coming in v0.1; Windows in v0.2)
- Python 3.10+ (`python3 --version`)
- Git
- `gh` CLI authenticated (`gh auth status`)
- Claude Code with the `claude` CLI on PATH (`claude --version`; need MCP support)

### 🍎 Install on your Mac

> 👥 **The fork model:** your team forks `tin-io/teamvault` into your org once — that fork is your team's **space**, where KB entries, pack config, and binds live. Every teammate clones the **fork** (not master) and runs the sidecar against it. The paste-in below clones master to `/tmp` ONLY so the agent can read the setup skill; the real working tree lands at `~/teamvault-<space-name>/` (cloned from your team's fork).

```text
tin-io/teamvault   ── fork once ─►   your-org/teamvault-<team>   ── clone per dev ─►   ~/teamvault-<team>/
 (upstream code)                     (team SPACE: KB entries +                         (each dev's working
                                      packs + space.yaml + repos.yaml)                  tree; sidecar watches)

                   ◄── targeted upstream sync: code updates flow IN; your kb/ stays yours ──►
```

Inside the project repo you want to bind to your team's TeamVault space, paste this into your Claude Code session:

```
Install TeamVault for this project.

1. Clone the master template to /tmp ONLY so the setup skill is readable
   (this is NOT your working tree — just where the agent reads SKILL.md from):
   git clone https://github.com/tin-io/teamvault /tmp/teamvault-master

2. Read /tmp/teamvault-master/.claude/skills/teamvault-setup/SKILL.md and execute it.

3. When the skill asks for the team space URL, use:
   <YOUR TEAM'S TEAMVAULT SPACE FORK URL>

4. Confirm install completion by:
   - running the MCP `vault_status` tool and showing me the output
   - showing me a `vault_search` query result
```

The agent walks the install: forks tin-io/teamvault into your org if you don't have a fork yet OR clones the existing team fork if you do (asks 5 conversational questions — fork-flow, space URL, enabled packs, project bind, optional PR-workflow skills), installs the Python sidecar (FastAPI, LanceDB, SQLite FTS5, Nomic embedding), generates a launchd plist so the sidecar runs on boot, registers the MCP endpoint with Claude Code via `claude mcp add`, then smoke-tests `/healthz` (and `/readyz` once the first reindex completes).

> ⚠️ **Heads up: the install pulls `torch` (~2.5 GB) and downloads the Nomic embedding model (~547 MB) on first reindex.** Plan 8-15 minutes on good Wi-Fi; longer on shared Wi-Fi. For demos, pre-install on attendee laptops the day before.

### ✅ After install: confirm it's wired up

```
vault_status
```

Should return `status: ok` and your registered space. Then:

```
vault_search "anything in the kb yet"
```

If the space has seed entries (most teams ship `kb/entries/*-seed-*.md` to get started), you'll see them.

> 📌 **Restart Claude Code (`/quit`, then relaunch) before the MCP tools surface.** This catches people every time.

---

## ⚡ The four daily moves

Once installed, your daily interaction is four things. Memorize these and you're 90% of the way to using TeamVault well.

### 🔍 1. Search — "check the KB for X"

When you're about to do something the team might have done before, ask the agent:

> "Check the KB — how did we handle the checkout abandonment flow when we hit a similar timing issue last quarter?"

The agent calls `vault_search`, finds the matching entry, summarizes. You decide whether to follow the prior approach.

### 📝 2. Publish — "save this for the team"

When you've made a decision, closed an incident, or landed a pattern worth remembering:

> "Publish this to the KB: short title 'sandbox clock drift incident', the decision was to widen the token validity window from 5min to 15min, related to PROJ-123."

The agent calls `vault_publish`. The HIPAA pack scrubber runs first — if PHI sneaks in, the publish is refused. Otherwise the entry is committed and pushed to the team space repo, and re-indexed on every team member's machine within ~60s.

### 🛡️ 3. Review — "run a TeamVault review on this diff"

Before opening a PR (or when investigating a PR check failure):

> "Run a TeamVault review on my current diff."

The pack runtime loads enabled packs (HIPAA, ClickUp linkage, whatever your team uses), runs them against your diff, returns a verdict (pass / block) with per-pack reasons.

The same runtime fires automatically as a GitHub Action when you push a PR. The local invocation is for pre-flight checking.

### 🩺 4. Status — "is TeamVault healthy?"

If anything feels off — search returns nothing, publish errors, the agent says the MCP tool isn't available:

> "Run /teamvault-status"

The status skill checks the sidecar process, the MCP registration, the cwd→space binding, the vault index state, and the last successful pull per space. It tells you exactly what's healthy and what's not.

When `/teamvault-status` surfaces a `DEGRADED` row and the next question is "why?" — run **`/teamvault-doctor`**. Doctor extends the read-only status with a three-layer diagnostic (Liveness / Structure / Data — including `/readyz`, plist shape, MCP-vs-sidecar path drift, recent_errors tail, audit-chain integrity), pairs each non-OK row with a numbered remediation (reindex / kickstart / build support bundle), and requires explicit confirmation before applying any fix — guide, not autopilot.

---

## 🧩 Packs: how compliance & ticket-linkage work

### 📦 What a pack is

A directory under `packs/<name>/` with a `PACK.yaml` declaring what it contributes:

```yaml
name: hipaa-reference
version: 0.1.0
description: HIPAA PHI detection
contributions:
  agents:
    - path: agents/hipaa-reviewer.md
  scrubbers:
    - type: regex
      file: scrubbers/phi_patterns.yaml
  reviewers:
    - agent: hipaa-reviewer
      mode: blocking   # or 'advisory'
```

Three contribution types in v0.0:

- **`agents`** — reviewer prompts (markdown) the runtime invokes during review
- **`scrubbers`** — regex pattern banks that run at publish-time (block PHI from entering KB) and at review-time (block PHI from entering PRs)
- **`reviewers`** — bindings of agent → mode (`advisory` flags but doesn't block; `blocking` fails the PR check)

### 🛡️ Pack: `hipaa-reference` (HIPAA PHI detection)

Ships in the master template as a starting set. Detects:
- MRN with prefix (`MRN:`, `Patient #`, `Pt#`, `Med Rec`)
- Bare MRN near patient-context keywords (Epic default 8-digit MRN)
- SSN in dashed / dotted / spaced / explicit forms
- NPI (10-digit Provider ID)
- DOB with explicit prefix
- Email addresses (PHI when associated with a patient)
- US phone numbers (PHI when associated with a patient)

**Mode: blocking.** Match = PR cannot merge until redacted.

**Limit you should know:** regex catches structured PHI. Names alongside conditions/medications is real PHI that regex CANNOT catch. The pack disclaims this in its reviewer body. You still need organizational HIPAA controls + human review.

### 🔗 Pack: `clickup-linkage` (ticket-trail check)

Ships in the master template. Confirms every PR description or diff includes a `clickup.com` URL. Useful for SOC 2 audit evidence — every code change traceable to a tracked work item.

**Mode: advisory.** Missing linkage = flagged but PR can still merge. Flip to `blocking` in your fork's `space.yaml` if you want enforcement.

### ❓ How does this work with Jira instead of ClickUp?

The same way. The principle is "pack declares what your team uses." For Jira, fork the `clickup-linkage` pack into `jira-linkage` in your team's space:

```yaml
# packs/jira-linkage/PACK.yaml
name: jira-linkage
version: 0.1.0
description: Confirms PRs reference a Jira ticket (e.g., PROJ-123 or atlassian.net URL)
contributions:
  agents:
    - path: agents/jira-linkage-reviewer.md
  reviewers:
    - agent: jira-linkage-reviewer
      mode: advisory
```

The reviewer agent body just changes the URL pattern (`atlassian.net/browse/<TICKET>` or `\b[A-Z]+-\d+\b`). Same structure, different regex. Enable it in your `space.yaml`:

```yaml
enabled_packs:
  - hipaa-reference
  - jira-linkage           # instead of clickup-linkage
```

The runtime doesn't care which one you enable — it loads whatever's in `enabled_packs`.

### 🧱 How to build your own pack

See `docs/CONTRIBUTING_PACKS.md` for the full contributor guide. Short version:

1. Make a directory `packs/your-pack-name/`
2. Write `PACK.yaml` declaring contributions
3. Write `agents/your-reviewer.md` — the reviewer agent body (markdown with frontmatter)
4. Optionally write `scrubbers/your-patterns.yaml` — regex pattern bank
5. Add the pack name to `space.yaml::enabled_packs[]`
6. Commit + push to your team space repo
7. ~60 seconds later, every dev's sidecar has your pack loaded

---

## 🔌 Workflow integration

This is the most important section. TeamVault's value isn't from being asked "vault_search this" once a week — it's from being woven into your existing development workflow so it gets consulted continuously without friction.

### ✨ The general pattern (recommended for everyone)

**Add a one-line instruction to your `~/.claude/CLAUDE.md` (personal global) or your project's `CLAUDE.md`:**

```markdown
## TeamVault knowledge base

If the TeamVault MCP server is registered (check with `vault_status`), call `vault_search` early in any task that involves:
- Prior team decisions ("how did we decide X?")
- Code patterns the team has used before
- Incident history / postmortems
- Compliance policies (HIPAA, SOC 2, etc.)
- Before implementing anything substantive, ask: "has the team done something like this before?"

Cite the source path of any KB entry you use in your response.
```

This is the **lowest-friction integration**. No new skill to remember; the agent proactively consults the KB whenever it's relevant. Works for vanilla Claude Code, Codex (via equivalent prompt), and any other host.

### 🎫 Pattern A: the maintainer's `/start-ticket` and `/review-ticket` skills

Your custom skills are excellent integration points because they fire at clear workflow moments (start of work, end of work). Add one step to each:

**In `~/.claude/skills/start-ticket/SKILL.md`** — early in the flow, before grounding in the codebase:

```markdown
### Pre-step: consult TeamVault KB

If `vault_status` confirms the sidecar is up, call `vault_search` with:
- The ticket's title as the query
- Any keywords from the acceptance criteria
- The repo / module name

Surface any relevant past decisions, patterns, or postmortems to me before I start grounding in the codebase. If the KB returns nothing relevant, say so and proceed.
```

**In `~/.claude/skills/review-ticket/SKILL.md`** — late in the flow, after acceptance-criteria scoring:

```markdown
### Pre-step: cross-check against KB patterns

Before running the reviewer panel, call `vault_search` for entries tagged `pattern` or `decision` that relate to the diff's domain. Surface any conflict between the diff and a documented team pattern as part of the reviewer's "scope drift" findings.
```

You do NOT need a new bridging skill. You're already running a skill at the right moment; just add the KB check as a step.

### 🤖 Pattern B: Teams using OMC

OMC (Oh-My-Claude-Code) has multiple lifecycle stages. TeamVault wires in via OMC's `companyContext` integration surface.

For each OMC stage that benefits from team knowledge, add a KB-check step:

- **`deep-interview` Phase 4 (grounding):** call `vault_search` for the user's stated requirement; surface conflicts between requirement and prior team decisions before generating questions
- **`autopilot` Phase 0 (planning):** call `vault_search` for the planned approach; if a similar approach was tried before, surface the lessons-learned entry
- **`ralph` per-iteration:** call `vault_search` for the file/module being modified; surface any pattern/postmortem entries about it

The cleanest implementation: a small wrapper in the OMC user's CLAUDE.md instructions saying:

```markdown
When using OMC, before any stage that produces specs, plans, or substantive code changes, call `vault_search` with the relevant query and incorporate findings. Skip if `vault_status` says the sidecar is down — never block on KB unavailability.
```

### 🧰 Pattern C: Vanilla Claude Code (no custom skills)

Default to **Pattern (general)** above — the CLAUDE.md instruction does the work. Users don't need to remember anything; the agent consults the KB when relevant.

### 🔄 Pattern D: Codex / other hosts

Same idea, different file. Codex reads its own system prompt configuration; add an equivalent KB-aware instruction. The MCP tool is the same — `vault_search` works from any host that registers the TeamVault MCP server.

### 💡 My honest take on bridging skills

You asked whether to build skills that bridge TeamVault and existing workflows. My honest opinion:

**Default = CLAUDE.md instruction.** Cheapest, broadest reach, works for everyone. No new commands to remember. The agent decides when the KB is relevant.

**Add skill-level steps to YOUR existing skills** (`/start-ticket`, `/review-ticket`) when you want guaranteed KB consultation at specific workflow moments. This is the "I know this skill fires at the right time, so make it KB-aware" pattern.

**Don't build a separate `/kb-check` bridging skill.** It adds a command users must remember and invoke. Failure mode: they forget; the KB doesn't get used. The CLAUDE.md instruction is implicit; the existing-skill patch is automatic; both beat "remember to invoke this every time."

The only exception: a `/teamvault-context` skill that explicitly fetches "what does the team know about X" can be useful when the user wants to be deliberate — e.g., before a planning session or stakeholder review. Worth shipping as v0.1 because it's cheap, but not the primary integration mechanism.

---

## 🎯 Your responsibility

TeamVault is a substrate. It does work. But it doesn't do these things, and treating it like it does will hurt your team:

### ❌ What TeamVault does NOT do

1. **TeamVault is NOT a HIPAA compliance certification.** The `hipaa-reference` pack is one layer of defense. You still need: BAA arrangements with all third parties (GitHub, AI providers, anyone touching your data), organizational HIPAA Security Rule controls, periodic manual audits, and a real compliance officer. See `LICENSE` for the formal disclaimer.

2. **TeamVault does not catch all PHI.** Regex catches structured patterns (MRN, SSN, NPI, DOB, email, phone). It cannot catch unstructured PHI — patient names alongside conditions, free-text descriptions of cases. Human review is still required.

3. **TeamVault does not enforce that you publish everything important.** If your team makes a decision and doesn't publish it, the KB doesn't know. Publish hygiene is a team discipline, not a product feature.

4. **TeamVault does not migrate your existing knowledge.** Existing Notion pages, Confluence docs, internal wikis — none of it auto-imports. You bring relevant entries over manually (or in v0.2+ via importer packs that don't yet exist).

5. **TeamVault does not centralize across teams by default.** Each "space" (team) has its own KB. Cross-team search is a v0.1 feature (`vault_search_all_spaces`). For now, you see your team's KB.

6. **TeamVault does not replace your code review.** The pack runtime is one signal in your PR flow. Human review, Code Rabbit, CI tests — all still required.

### ✅ What you ARE responsible for

- **Telling your team to publish.** Without entries, the KB is empty. The first 4-6 weeks are seeding; after that it compounds.
- **Reviewing pack updates.** Pack changes in `packs/*/` require CODEOWNERS review (configure your team's `compliance-leads` group in the space repo's `CODEOWNERS`). Don't merge HIPAA pack changes without compliance lead approval.
- **Maintaining your fork.** Pull updates from the master template (`tin-io/teamvault`) periodically. Security patches to the sidecar will live there.
- **Customizing patterns for your stack.** The reference HIPAA pack uses generic patterns. Add your team's Epic / Cerner / Allscripts-specific MRN formats. Don't trust the defaults blindly.
- **Educating your team.** TeamVault is a tool; adoption is a behavior change. Write a one-page workflow narrative for your team and walk through it together in the first week.

---

## 🔄 Upstream sync — pulling improvements from `tin-io/teamvault` into your team's fork

Over time the master template evolves: sidecar bug fixes, new diagnostic skills, refreshed reference packs, doc updates. Your team's fork should periodically pull those improvements **without losing your KB entries, your `space.yaml` customizations, your `repos.yaml` binds, or your custom pack patterns**.

### What is and isn't yours

| Layer | Paths | On sync |
|---|---|---|
| **Substrate (upstream owns)** | `sidecar/`, `.github/workflows/`, `.claude/skills/teamvault-{setup,status,publish,review,doctor}/`, `docs/`, `README.md`, `SETUP_PROMPT.md`, `LICENSE` | **Pull from upstream** |
| **Reference pack defaults** | `packs/{hipaa-reference,clickup-linkage,jira-linkage}/PACK.yaml` + `agents/*.md` (when not customized) | Pull with review |
| **Team-owned (yours forever)** | `space.yaml`, `repos.yaml`, `kb/entries/**`, custom packs, customized pack scrubbers/agents | **Never pulled** |

### Pattern A — targeted-path checkout (recommended today)

Deterministic, auditable, never touches team-owned files because we never include them in the path list.

```bash
cd ~/teamvault-<your-space>

# One-time: register upstream
git remote add upstream https://github.com/tin-io/teamvault
git remote -v

# Every sync (working tree must be clean first):
git fetch upstream
git status

git checkout upstream/main -- \
  sidecar/ docs/ .github/ \
  .claude/skills/teamvault-setup/ \
  .claude/skills/teamvault-status/ \
  .claude/skills/teamvault-publish/ \
  .claude/skills/teamvault-review/ \
  .claude/skills/teamvault-doctor/ \
  README.md SETUP_PROMPT.md LICENSE

git diff --staged   # review BEFORE committing
git commit -m "upstream sync: <upstream SHA or tag>"
launchctl kickstart -k gui/$(id -u)/dev.teamvault.sidecar
/teamvault-doctor   # confirm everything's still healthy post-sync
```

If `/teamvault-doctor` flags issues post-sync: `git reset --hard HEAD~1` + kickstart again to roll back, then file an upstream issue.

### Pattern B — `/teamvault-upstream-sync` skill (v0.2 roadmap; ROADMAP P2.14)

Not shipped yet. When it lands: detects upstream delta, applies substrate paths automatically, prompts for reference-pack changes, runs sandbox tests, supports rollback. Use Pattern A for now.

### 🔓 Alternative: fork-free clone (for orgs that need to obscure the upstream relationship)

Most teams fork `tin-io/teamvault` into their org via GitHub's fork button. Some teams can't or won't — and that's a first-class supported path. Reasons we've heard:

- **Compliance posture.** "Our repo metadata can't advertise a fork relationship pointing at an external repo."
- **Org policy.** Some orgs prohibit GitHub-side fork relationships to repos outside the org.
- **Brand / signaling.** "We don't want our space repo to read as 'a fork of someone else's project.'"

These are real reasons, not edge cases. The pattern is: create a new empty repo in your org, push the master template contents into it, and treat it as your space — no GitHub fork relationship, but everything else (substrate sync, KB sharing, MCP, packs) works identically.

#### What's kept vs. what's lost

| | Fork-based (GitHub fork) | Fork-free (push to new empty repo) |
|---|---|---|
| Substrate code (`sidecar/`, skills, packs) | ✓ | ✓ |
| Your KB entries, `space.yaml`, `repos.yaml`, custom packs | ✓ | ✓ |
| Full git commit history (same SHAs as upstream) | ✓ | ✓ |
| Sidecar pull-loop + push-on-publish (`vault_publish`) | ✓ | ✓ |
| MCP tools, packs, pre-commit hook | ✓ | ✓ |
| GitHub "X commits behind upstream" UI | ✓ | ✗ |
| `gh repo sync` | ✓ | ✗ |
| `git fetch upstream` + `git merge` / Pattern A targeted checkout | ✓ | ✓ (after one-time `git remote add upstream`) |

The only thing lost is the GitHub-side fork relationship — which affects the web UI and `gh repo sync`, but does NOT affect raw git fetch/pull/merge. Upstream sync works identically; you just register `upstream` as a regular git remote.

#### Setup from scratch — fork-free, one dev does this once

```bash
# 1. Create a new empty repo in your org via the GitHub UI (no README, no .gitignore, nothing)
#    e.g., https://github.com/<your-org>/teamvault-<your-team>

# 2. Clone the master template to a temp dir
git clone https://github.com/tin-io/teamvault.git /tmp/teamvault-master
cd /tmp/teamvault-master

# 3. Repoint origin at your new empty repo and push
git remote set-url origin https://github.com/<your-org>/teamvault-<your-team>.git
git push -u origin main

# 4. Move the working tree into the canonical location
mv /tmp/teamvault-master ~/teamvault-<your-space>
cd ~/teamvault-<your-space>

# 5. Add upstream remote (the master template) for future syncs
git remote add upstream https://github.com/tin-io/teamvault.git
git remote -v   # confirm: origin = your new repo; upstream = tin-io/teamvault

# 6. Run the targeted-path sync (Pattern A) to bring your fork-free copy up to upstream HEAD
git fetch upstream
git checkout upstream/main -- \
  sidecar/ docs/ .github/ \
  .claude/skills/teamvault-setup/ \
  .claude/skills/teamvault-status/ \
  .claude/skills/teamvault-publish/ \
  .claude/skills/teamvault-review/ \
  .claude/skills/teamvault-doctor/ \
  README.md SETUP_PROMPT.md LICENSE
git diff --staged
git commit -m "chore(sync): upstream $(git rev-parse --short upstream/main)"
git push   # to your new origin

# 7. Every other dev on your team clones your new repo (NOT the master template), then adds upstream on their own machine
#    See the next subsection for the three commands each teammate runs
```

From here, every dev runs `/teamvault-setup` against the new repo URL — the setup skill doesn't care whether the space is a GitHub fork or a fork-free clone; it just clones whatever URL you give it.

#### Recovery flow — you already pushed to a new empty repo and want upstream sync

If your team did the "push to new empty repo" path before reading this section (welcome — this is exactly the situation that prompted this doc), here's the three-command recovery. Run this on **one** dev's machine; everyone else just `git pull`s from origin afterward.

```bash
cd ~/teamvault-<your-space>

# 1. Confirm origin points at your new repo
git remote -v

# 2. Add upstream — the master template
git remote add upstream https://github.com/tin-io/teamvault.git

# 3. Fetch and inspect the upstream delta
git fetch upstream
git log --oneline HEAD..upstream/main | head -20
```

If step 3 shows commits, run the same Pattern A targeted-path checkout above (the substrate paths list never includes `kb/`, `space.yaml`, `repos.yaml`, or customized pack files — so team-owned content is untouched), then commit and `git push` to your new origin. Every other dev pulls from origin and they're current.

#### Per-clone caveat — `upstream` is a per-developer git config

The `upstream` remote is a local-only git remote, stored in each clone's `.git/config`. It does NOT sync via `git push` — every dev needs to add it once on their own machine the first time they want to inspect upstream (`git fetch upstream`, `git log HEAD..upstream/main`).

In practice:
- **Only ONE dev per team needs to RUN the sync** (the targeted-path checkout + commit + push).
- **Every dev who wants to inspect upstream locally** (`git log HEAD..upstream/main`) needs `git remote add upstream https://github.com/tin-io/teamvault.git` on their machine. Two seconds, one-time.
- Once the syncing dev pushes the commit to origin, every other dev's `git pull` brings in the substrate updates without needing `upstream` configured at all.

#### Coming soon: native handling in `/teamvault-upstream-sync`

The forthcoming `/teamvault-upstream-sync` skill (ROADMAP P2.14) handles the fork-free case natively. Its first pre-flight check is "is the `upstream` remote registered?" — if not, it prompts:

> Your space doesn't have an `upstream` remote. If your team is using a fork-free clone (pushed substrate to a new empty repo), I can add `https://github.com/tin-io/teamvault.git` as the upstream now. Add it? [Y/n]

After that one-time prompt, fork-free teams get the same `/teamvault-upstream-sync` UX as forked teams — no special-casing, no documentation divergence.

### Anti-patterns

- ❌ **`git merge upstream/main` (untargeted).** Conflicts on `space.yaml` (your kingdoms / packs choice vs upstream defaults), `repos.yaml` (your binds vs empty), and any customized pack files. Devs unfamiliar with git conflict resolution can silently clobber team config.
- ❌ **"Hey agent, update this fork from master."** Non-deterministic; no clean diff; no audit trail. For HIPAA-adjacent teams the audit answer "the agent did it" isn't acceptable.
- ❌ **Pulling reference packs blindly.** If your team customized `packs/hipaa-reference/scrubbers/*.yaml` for your specific PHI patterns, an upstream sync of that file overwrites them. Either skip `packs/` from the path list or review the diff carefully.

### Watch-outs

- **Upstream file moves** (rare). Targeted checkout creates the new file but doesn't delete the old. After sync, scan for duplicates: `find sidecar -type f | sort`. If duplicates exist, `git rm` the old paths.
- **Team-modified substrate code.** If your team modified `sidecar/` directly, targeted checkout clobbers those changes. Teams that modify the substrate should send upstream PRs, not maintain a fork.
- **Schema breaking changes at v0.x bumps.** Watch upstream release notes; future schema additions may require manual `space.yaml` edits.

---

## 🧰 Managing skills — installing, distributing, updating

TeamVault distributes three classes of skills. Different classes live in different places and update via different flows.

### The three classes

| Class | Examples | Lives in | Visible from |
|---|---|---|---|
| **Substrate skills** (talk to the sidecar) | `/teamvault-setup`, `/teamvault-publish`, `/teamvault-status`, `/teamvault-review`, `/teamvault-doctor` | Today: space dir `~/teamvault-<space>/.claude/skills/`. Recommended: also user-global `~/.claude/skills/` so they work from any directory. | The space dir today; everywhere after the workaround below |
| **Project workflow skills** | `/pr-push`, `/pr-review`, `/pr-fix`, `/pr-pipeline` (also `code-structure` as a tailorable example) | Per-project `<project>/.claude/skills/` + committed to project repo | Only the project they're deployed in |
| **Team-custom skills** (your team's additions) | e.g. `/title21-clinical-publish` | Space fork as source of truth → deployed to user-global OR per-project by intent | Depends on which class you put it in |

### Substrate-skills gap + workaround (until v0.1.5)

`teamvault-setup` deploys `pr-*` into your bound project (§7.5) but does **NOT** copy `teamvault-*` into user-global. That means slash commands like `/teamvault-doctor` only work from inside the space dir — not from your project repo. The MCP tools (`vault_search` etc.) DO work everywhere because MCP is registered with `--scope user`.

**Today's workaround** — run this after install to make TeamVault slash commands available from any directory:

```bash
mkdir -p ~/.claude/skills
for s in teamvault-publish teamvault-status teamvault-review teamvault-doctor; do
  cp -r ~/teamvault-<your-space>/.claude/skills/$s ~/.claude/skills/$s
done
```

Re-run after every upstream sync to keep the global copies current.

**v0.1.5 roadmap:** `teamvault-setup` §7.6 will auto-deploy these to user-global on install; subsequent upstream-sync invocations refresh them.

### Project workflow skills (PR flow) — status quo is right

§7.5 of `teamvault-setup` asks during install: *"Deploy TeamVault's PR workflow skills into this project? [Y/n]"* Saying yes copies them from the space fork into `<this-project>/.claude/skills/` AND commits them to the project repo.

**Why commit to the project repo?** Teammates who clone the project (and don't have TeamVault installed) still get the skills via git. The PR flow becomes part of the project, not gated on a TeamVault install.

**Deploying to additional projects:** `cd <other-project>` and re-invoke `/teamvault-setup` from there. It'll skip the install steps (already installed) and just run the §7.5 deploy.

**Pulling pr-* updates into projects after upstream sync:** `cp -r ~/teamvault-<your-space>/.claude/skills/pr-*` into each project where they're deployed, then commit + push.

### Adding a team-custom skill — the lifecycle

Say your team writes `/title21-clinical-publish` — a thin wrapper around TeamVault publish that adds clinical-context tagging.

**1. Author writes the skill in the space fork:**

```bash
cd ~/teamvault-<your-space>
mkdir -p .claude/skills/title21-clinical-publish
# write SKILL.md inside that dir
git add .claude/skills/title21-clinical-publish
git commit -m "feat(skill): /title21-clinical-publish for clinical KB entries"
git push
```

**2. Teammates pull from the space fork, then deploy by intent:**

```bash
cd ~/teamvault-<your-space>
git pull

# Substrate-style (visible everywhere):
cp -r .claude/skills/title21-clinical-publish ~/.claude/skills/

# OR project-style (embedded in a specific project's workflow):
cd <target-project>
cp -r ~/teamvault-<your-space>/.claude/skills/title21-clinical-publish .claude/skills/
git add .claude/skills/title21-clinical-publish
git commit -m "deploy skill: title21-clinical-publish"
```

**3. Updates:** author edits in the space fork → commits → pushes → teammates pull → re-run the deploy step. (v0.1.5+: a `/teamvault-deploy-skills` skill will automate the sync from space fork → user-global / per-project.)

### Anti-patterns

- ❌ **Distributing skills via Slack/email.** Manual file-shipping → drift between teammates. The space fork is the canonical source; pulls keep teammates in sync.
- ❌ **Editing user-global copies directly.** They're deployment *targets*, not sources. Edit in the space fork, commit, push, redeploy.
- ❌ **Forgetting to redeploy after upstream sync.** `teamvault-*` copies in `~/.claude/skills/` go stale when the space fork pulls upstream. Until v0.1.5 ships the auto-deploy, manually re-copy.
- ❌ **Same skill in BOTH user-global AND a project's `.claude/skills/`.** Claude Code resolves project-local first, silently shadowing the user-global copy. Pick one location per skill.

---

## 🎉 Frictionless adoption — recommendations

You asked for ideas on making this as low-friction as possible. Here's the prioritized list:

### 🥇 Tier 1: Do these in the first week

1. **Pre-install on attendee laptops before any demo.** The 2.5 GB torch install is the #1 friction. If devs walk into a demo with TeamVault already pip-installed, the rest is 30 seconds.

2. **Pre-seed the team's space repo with `repos.yaml` + 5-10 KB entries.** A first-time installer hitting an empty KB feels like the tool doesn't work. A first-time installer hitting "your team already documented X" feels like value.

3. **Add the one-line CLAUDE.md instruction** (see workflow integration above). Without it, agents only consult the KB when explicitly asked. With it, the KB gets consulted continuously and naturally.

4. **Patch your existing skills** (`/start-ticket`, `/review-ticket`, or your team's equivalents) with KB-check steps. This makes integration AUTOMATIC at the workflow moments where knowledge matters most.

### 🥈 Tier 2: Reduces friction in week 2-4

5. **Ship 3-4 KB entry templates** under `kb/entries/_template-*.md`:
   - `_template-decision.md` — title, decision, why, alternatives considered, related entries
   - `_template-postmortem.md` — summary, impact, root cause, what we changed
   - `_template-pattern.md` — name, when to use, when to skip, example
   - `_template-onboarding-note.md` — for new-hire context

6. **Provide a `/teamvault-publish-decision` shortcut skill** that loads the decision template, asks the user for the fields, fills them in, calls `vault_publish`. Reduces "I want to publish but I don't know what to write" friction.

7. **Add a Friday-afternoon prompt** (calendar reminder or a cron-fired Claude prompt) asking "Publish anything from this week?" Adoption compounds when publishing becomes habitual.

### 🥉 Tier 3: Roadmap (v0.1.5+, sized in ROADMAP.md)

8. **Pre-baked wheelhouse** — ship platform-specific `pip download` artifacts in the master template so install drops from 10 min to ~30s.

9. **Importers** — Notion-to-TeamVault, Confluence-to-TeamVault. One-time bulk migration of existing institutional memory.

10. **A `/teamvault-context` skill** for power users who want to deliberately fetch "what does the team know about X" before a planning session.

11. **`/teamvault-doctor` (beyond `/teamvault-status`)** — proactive health checks, not just reporting. Detect "your sidecar version is N versions behind master" and offer to upgrade.

### 🚨 What I'd NOT recommend (anti-patterns)

- **Don't gate adoption on perfection.** Ship the basics, let teams customize. The reference packs are 80% — that's good enough to start; teams add the last 20% themselves.
- **Don't require everyone to publish constantly.** Aim for "the right person publishes the right thing" — your tech lead publishes architecture decisions, your compliance lead publishes policy clarifications. Random publishing-for-publishing's-sake creates noise.
- **Don't make pack changes need a 5-person PR review.** The HIPAA pack should require compliance-lead review. Everything else can be 1 reviewer. CODEOWNERS-heavy = friction.
- **Don't try to be the system of record.** ClickUp is your tracker, your code repo is your code source-of-truth, TeamVault is the KNOWLEDGE layer. Stay in that lane.

---

## 🛠️ Troubleshooting

See `docs/TROUBLESHOOTING.md` — full failure-mode runbook covering: sidecar down/wedged/crashes, MCP tools missing, search misses, publish blocked/lost, GHA module errors, false-positive blocks, stale git sync, demo-day recoveries.

Most common issues, in order of frequency:

1. **`vault_*` tools missing in Claude Code** → you didn't restart Claude Code after `claude mcp add`. `/quit` and relaunch.
2. **`vault_search` returns nothing** → reindex hasn't run, or sidecar wasn't pointed at your space. Run `vault_status` to confirm, then `curl -X POST .../reindex`.
3. **Publish fails with "Content blocked by pack scrubber"** → HIPAA pack matched a PHI pattern in your content (working as designed). Redact and retry.
4. **GHA `teamvault-review` fails with `ModuleNotFoundError`** → your space repo isn't a fork of the master template (which has `sidecar/` at root). The workflow expects sidecar at the checkout root.

---

## 📖 Glossary

- **Space** — One team's TeamVault instance. A fork of `tin-io/teamvault` (or your own master template) that the team customizes and uses. Cloned to `~/teamvault-<name>/` per developer.
- **KB entry** — A markdown file in `kb/entries/*.md` with YAML frontmatter. The unit of knowledge.
- **Pack** — A directory under `packs/<name>/` declaring extensions: reviewer agents, scrubber pattern banks, ingest guards (v0.1+).
- **Sidecar** — The local Python process (FastAPI on `localhost:8100`) that watches your space clone, re-indexes on git pull, and exposes the MCP endpoint. One per Mac.
- **MCP** — Model Context Protocol. The Anthropic protocol that lets Claude Code (or Codex) call tools exposed by an external server. TeamVault's MCP server exposes `vault_search`, `vault_publish`, `vault_status`.
- **Bind** — Telling the sidecar that a specific project repo "belongs to" a specific space. Editable via `repos.yaml` in the team space repo.
- **Master template** — The canonical `tin-io/teamvault` repo. Your team forks it.
- **Workspace** — A config variant within a space (e.g., `prod` vs `staging` for an engineering team). v0.0 ships only the default workspace; v0.1+ adds first-class workspace switching.
- **Compliance space** — A space with `compliance: true` in `space.yaml`. Disables pack auto-deploy (changes require explicit `/teamvault-apply-pack-update` acknowledgement) and enables fail-closed scrubber behavior.

---

## 👉 Where to go next

After you've installed and used TeamVault for a week:

- **Want to extend it?** Read `docs/CONTRIBUTING_PACKS.md` — three-tier governance model, pack contributor checklist, PACK.yaml schema with v0.1 extension preview.
- **Want to know what's coming?** Read `docs/ROADMAP.md` — P0/P1/P2/P3 tiered deferral list with sizing, plus recommended 4-6 week sequencing.
- **Want to understand the architecture?** Read `docs/ARCHITECTURE.md` (the canonical architecture doc) + `docs/KB-FOUNDATIONS.md` (the underlying KB pattern catalog this builds on) + `docs/CONTRACTS.md` (exact HTTP/MCP/pack specs).
- **Want to share what you've learned?** Open a PR against `tin-io/teamvault` adding to this user guide. The audience above is broader than just your team.

---

End of user guide. Welcome to TeamVault.
