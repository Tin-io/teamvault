# 📋 Autonomous Build Methodology

> ✨ Distilled from the TeamVault POC v0.0 build (Fri 2026-06-12 → Sun 2026-06-14): a bounded ~24h autonomous run that produced a working end-to-end POC + comprehensive handoff, supervised by an hourly watchdog cron, with parallel sub-agent fan-out at phase boundaries. This document is the reusable methodology so the pattern survives the next time you need it.

<p align="center">
  <img src="https://img.shields.io/badge/scope-methodology-555?style=flat-square" alt="Scope: methodology">
  <img src="https://img.shields.io/badge/source-v0.0%20build%20distillation-7c3aed?style=flat-square" alt="Source: v0.0 build distillation">
</p>

## 🎯 When to use this pattern

Use it when **all four** of these are true:

1. **Bounded time window** with a clear start and end. Sabbath, conference travel, weekend, scheduled vacation. Not "indefinitely."
2. **Clear scope** that can be frozen in a one-page contract. If the scope is "explore," this pattern fights you.
3. **No interactive feedback expected** during the window. If you can be paged, the supervision overhead isn't worth it.
4. **A definite handoff target** — someone (often future you) reads the result cold and decides next steps.

Do NOT use it for: exploratory research, design exercises where the path is unclear, anything where the answer to "what does done look like?" is genuinely unknown going in. Those benefit from interactive iteration, not autonomous build.

## 🧱 Preconditions

Before going autonomous, you need:

- A repo (or willingness to create one) that the build agent owns
- A sandbox directory the agent can mutate freely (e.g., `~/Projects/test-omc/`)
- A push policy you've explicitly decided on (branches only, no `main`, no force push)
- A clearly-stated set of files/directories the agent will NEVER touch (`~/.claude/`, `~/Library/LaunchAgents/`, real user state)
- An understanding of how to spawn sub-agents and schedule cron jobs in your tooling

If any of these are missing, fix them first.

## 🏗️ The 4-layer resilience architecture

```
┌───────────────────────────────────────────────────────────────┐
│  Primary builder (continuous session)                         │
│  - Works the spec, commits to wip/* branches                  │
│  - Reads JOURNAL.md to know where to pick up                  │
│  - Writes JOURNAL.md after each meaningful action             │
└────────────────────┬──────────────────────────────────────────┘
                     │
                     ↓ writes to
                     │
┌───────────────────────────────────────────────────────────────┐
│  JOURNAL.md — durable shared brain                            │
│  - Append-only, newest entries at TOP                         │
│  - Structured fields: STATUS, LAST ACTION, NEXT ACTION, etc.  │
│  - Source of truth for build state                            │
│  - Survives session compression / death                       │
└────────────────────┬──────────────────────────────────────────┘
                     │
                     ↓ read by
                     │
┌───────────────────────────────────────────────────────────────┐
│  Hourly watchdog (cron, fresh context each fire)              │
│  - Reads JOURNAL.md + runs `git log` + `git status`           │
│  - Categorizes: HEALTHY / SLOWING / STALLED / WEDGED          │
│  - Report-only by default — appends a watchdog entry          │
│  - Promotes to RECOVERY MODE only if 2 consecutive WEDGED     │
│    AND top builder entry is IN_PROGRESS or BLOCKED            │
└────────────────────┬──────────────────────────────────────────┘
                     │
                     ↓ at phase boundaries
                     │
┌───────────────────────────────────────────────────────────────┐
│  Sub-agent fan-out (parallel, on separate worktrees)          │
│  - Adversarial reviewers (security / DX / code-quality)       │
│  - Install dry-run simulators                                 │
│  - Stretch features on their own branches                     │
│  - Return structured verdicts the primary builder integrates  │
└───────────────────────────────────────────────────────────────┘
```

Each layer has a single job. The primary builder is the only one that writes code. The journal is the only thing that's durable across context boundaries. The watchdog is read-only except in extreme recovery. Sub-agents work in isolated worktrees so their git ops don't race.

## 🔧 Phase 0: Setup (before going autonomous)

> ⚠️ This is the most important phase. Skipping or rushing it is the most common failure mode.

### 📐 0.1 Write the frozen build contract

A one-page markdown doc with:

- **Scope statement** (1 sentence)
- **What ships in v0.0** (cheap + load-bearing — list explicitly)
- **What does NOT ship** (defer list — defending against scope creep)
- **Day-1 file tree** (concrete: what directories exist, what files in each)
- **Safety rails** (forbidden operations, sandbox env vars)
- **Phases** (Phase 1 / 2 / 3 with target hours and deliverables)
- **DEVIATION protocol** — if the agent finds the contract is wrong, write a `DEVIATION:` line in JOURNAL rather than silently changing course

Example: the frozen contract used in this codebase's original autonomous v0.0 build (since removed from the tree post-build; the methodology pattern remains).

The contract is **frozen** the moment you go autonomous. The agent reads it, never edits it. Deviations are documented in JOURNAL, never made silently.

### 📝 0.2 Write the durable journal seed

`.build/JOURNAL.md` with:

- A header explaining the build's purpose, target end time, contract reference
- The "Recovery protocol" (what to do if you see BLOCKED/WEDGED at top)
- The "Entry format" (so future agents write consistently)
- `## Entries (newest first)` marker
- One STARTING entry describing what's about to happen

Example: `.build/JOURNAL.md` from this build.

Entries follow this exact format:

```
## YYYY-MM-DDTHH:MM:SS — <agent role> — <phase>
**STATUS:** STARTING | IN_PROGRESS | COMPLETED | BLOCKED | RECOVERING | WEDGED
**LAST ACTION:** what was just done
**NEXT ACTION:** what to do next
**DECISIONS:** any architectural/scope decisions during this session
**KNOWN ISSUES:** open problems
**FILES TOUCHED:** which files changed
**COMMIT:** git SHA if committed
```

The journal is the **single source of truth for build state**. Every meaningful action gets an entry. If a fresh agent reads only the top entry, they know exactly where things stand and what to do next.

### 🔌 0.3 Write the integration contracts (if you'll fan out sub-agents)

An integration-contracts file (conventionally `CONTRACTS.md`) declares interfaces:

- HTTP API shapes
- File ownership map (which sub-agent owns which files — prevents conflicts)
- Schema definitions (PACK.yaml, space.yaml, etc.)
- Sandbox env vars
- Contract-change protocol

Example: the integration-contracts file used in this codebase's original build (since promoted to `docs/CONTRACTS.md` as a reference doc).

If you're solo-building (no sub-agents), skip this. If you're fanning out, this is what makes parallel work possible without integration hell.

### 🩺 0.4 Schedule the watchdog cron

The watchdog is a fresh-context agent that fires hourly and reads JOURNAL.md. Its prompt is the same every fire. It writes one entry to JOURNAL.md per fire. It does NOT modify code.

Cron expression: `17 * * * *` (off-:00 to avoid fleet collisions).

Watchdog prompt template:

```
You are the build WATCHDOG. Fresh context, no prior session memory.
You are a HEALTH MONITOR, not a builder, UNLESS the build has been wedged >2h.

Read these files in this order:
1. <path>/.build/JOURNAL.md (durable build state; newest entries at top)
2. <path>/docs/<CONTRACT>.md (build contract; reference only)

Then run parallel checks (Bash):
- git log --oneline -10
- git branch -a
- git status -sb
- stat -f "%Sm" <path>/.build/JOURNAL.md
- find <path>/<source-dir> -name "*.<ext>" -mmin -60 | wc -l
- date

Categorize:
- HEALTHY: commits within last 90 min, OR top journal entry IN_PROGRESS within 60 min
- SLOWING: no commits in 90-120 min but journal updated within 60 min
- STALLED: no commits in 2+ hours AND journal unchanged in 90+ min
- WEDGED: no commits in 3+ hours AND journal unchanged in 2+ hours AND top journal entry shows IN_PROGRESS or BLOCKED

Append a new entry at the TOP of JOURNAL.md (Edit tool, insert after "## Entries (newest first)" line) with this format:

## YYYY-MM-DDTHH:MM:SS — watchdog — hourly-check
**STATUS:** HEALTHY | SLOWING | STALLED | WEDGED
**LAST ACTION:** Read journal + ran checks. <summary>
**OBSERVATIONS:** Last commit at <ts>; last journal update at <ts>; current branch is <branch>; <N> source files modified in last hour
**RECOMMENDATION:** (HEALTHY/SLOWING: "continue"; STALLED: "next builder should consider pivoting"; WEDGED: "next watchdog promotes to recovery-builder")
**WATCHDOG NOTE:** Any anomalies

DO NOT modify any code/docs. JOURNAL.md is the only writable file.

EXCEPTION — RECOVERY MODE: If you see TWO consecutive WEDGED entries in the last 3 hours, switch mode and become the recovery-builder.

Be terse — under 200 words.
```

> ⚠️ **Caveat from this build:** `durable: true` was supposed to persist the cron to disk but the response said "session-only." It actually did fire hourly for 25+ hours, so either the response was misleading or it survived for other reasons. Verify behavior in your tooling.

### 🛡️ 0.5 Hard-code the safety rails

In your top-level instructions to the primary builder, name explicitly:

- **No push to `main`** — branches only
- **No force pushes**
- **No touch to real user state** (list paths)
- **No external network beyond X** (git push to your own repos, local model downloads, etc.)
- **No installs on the user's actual account** — sandbox via env-var redirection (`TEAMVAULT_HOME=<sandbox>`)

Stated once, held throughout. The builder treats these as hard constraints, not preferences.

## 🧱 Phase 1+: Execution

### 📋 1.1 Phase structure

Each phase has:

- **One clear goal** — "thin slice working end-to-end," "harden from critic findings," "polish + handoff"
- **A target time budget** (hours, not days)
- **An exit criterion** — what does "done" look like for this phase?
- **A push checkpoint** — `wip/v0.0-thin-slice`, `wip/v0.0-hardened`, etc.

Don't mix phases. Don't add new features in a hardening phase. Don't pile polish onto a thin slice. Clear phase boundaries = legible progress + clean revertability.

### ✂️ 1.2 The thin-slice rule

Phase 1 builds the entire flow end-to-end — ugly, minimal, but functional from edge to edge. Smoke test it before declaring complete. This proves the architecture works.

In this build: sidecar boots → ingest pipeline → hybrid search → MCP shim → setup skill → publish/review skills → GHA workflow → 3 seed KB entries. All in 6 hours. Pushed as `wip/v0.0-thin-slice`.

The temptation to "just clean this one thing up" before pushing the thin slice is strong. Resist it. Phase 2 is for cleaning.

### 🤖 1.3 Sub-agent fan-out at phase boundaries

Fan-out is only worth the overhead at phase boundaries. Mid-phase parallelism creates integration headaches that cost more than they save.

**Good fan-out moments:**
- After thin slice lands → 3 parallel adversarial critics (security, DX, code-quality)
- Before declaring done → install dry-run simulator + stretch features on separate branches
- For genuinely independent components at the start of a phase (sidecar + packs + skills)

**Bad fan-out moments:**
- During code that has integration dependencies — sub-agents can't see each other's in-flight work
- For "more of the same" (10 sub-agents writing similar tests is just slow)
- When the work needs to be sequenced (one builds on the next)

**The structured-verdict pattern for critics:**

```
ROLE: <Reviewer name>
VERDICT: APPROVE | APPROVE_WITH_CONCERNS | REQUEST_CHANGES | REJECT

EXECUTIVE SUMMARY (under 100 words):
<paragraph>

CRITICAL FINDINGS (must fix before X):
[F1] FILE:LINE — <observation> — <recommendation>
...

HIGH FINDINGS (should fix before X):
[F1] ...

MEDIUM / LOW:
[F1] ...

SINGLE BIGGEST CONCERN:
<one sentence>
```

This is mechanical to triage. You read 3 verdicts, dedupe findings across them, assign severity, fix the criticals + highs, defer the rest with documentation.

### 👀 1.4 Adversarial review before declaring done

Spawn critics with explicit "find weaknesses" charters, not "review this." A critic asked "give me feedback" produces noise. A critic asked "find the kill-shot — what would break this in production" produces signal.

In this build, the 3 critics surfaced 14 substantive findings (PHI regex gaps the builder missed, MCP registration path bug, launchd PYTHONPATH issue, ghost-chunks bug, etc.). The builder hadn't seen any of them.

Critic charters should be **out-of-scope explicit** too. "Don't flag the things in the deferral list. Don't flag style nits." Otherwise critics fill the output with low-signal noise.

### 🧪 1.5 Dress rehearsal as the confidence gate

Before claiming Phase 2 is done, run a test that exercises the actual demo flow end-to-end against fresh sandbox state.

In this build: `.build/test_dress_rehearsal.py` ran the 4 demo beats sequentially (publish + search round-trip, PHI PR review blocks, new pattern propagates, advisory→blocking via PACK.yaml). All 4 passed. That gate gave 95% confidence the demo would land.

If the dress rehearsal fails, you go back. You don't ship.

### 🌿 1.6 Git worktrees for parallel branch work

When 2+ sub-agents work on separate branches concurrently, give each its own `git worktree`:

```bash
git worktree add ../<project>-wt-<feature> -b wip/v0.1-stretch-<feature> wip/v0.0-hardened
git worktree add ../<project>-wt-<other>  -b wip/v0.1-stretch-<other>  wip/v0.0-hardened
```

Each sub-agent operates exclusively in its own worktree. No git index races. Each commits + pushes to its own branch. The primary builder integrates findings into HANDOFF when they return.

Symlink the venv across worktrees so they share installed deps:

```bash
ln -sf <main-worktree>/.venv <stretch-worktree>/.venv
```

### 🏷️ 1.7 Continuous git commits + branch checkpoints

Commit every meaningful chunk of work (every 30-90 min). Push to `wip/*` branches at phase milestones, not main.

Branch checkpoints from this build:
- `wip/v0.0-thin-slice` — Phase 1 end-to-end working
- `wip/v0.0-hardened` — Phase 2 + 3 + bonus + docs (current demo head)
- `wip/v0.1-stretch-audit-log` — optional stretch
- `wip/v0.1-stretch-contextual-prefixes` — optional stretch

The maintainer can compare any pair, merge any subset, drop any single branch — all without losing the others.

## 📦 Phase N: Handoff

The handoff documents are written DURING the build (not just at the end). They mature as the build progresses, but the structure is established Phase 0.

### 📚 Document hierarchy

Each doc has one audience and one job:

| Doc | Audience | Job |
|---|---|---|
| 📦 `HANDOFF.md` (repo root) | You returning | "Read me first." TL;DR, branch table, top-3 things to do, code reading guide |
| 📐 frozen contract doc | Build agent | What ships in this slice vs. defers |
| 📝 `.build/JOURNAL.md` | Anyone resuming | Full audit trail of decisions |
| 🗺️ `docs/ROADMAP.md` | Post-build planner | Structured P0/P1/P2/P3 deferral list with sizing |
| 🛠️ `docs/TROUBLESHOOTING.md` | End user / customer | Symptom → check → fix runbook |
| 📋 `docs/<DEMO>_WORKFLOW.md` | Customer team | One-page workflow narrative |
| 🤝 `docs/CONTRIBUTING_*.md` | Future contributors | OSS contribution surface |

Don't conflate audiences. A customer-facing workflow doc doesn't repeat what's in TROUBLESHOOTING. The internal POC doesn't try to be a user-facing README. Each doc earns its existence by serving exactly one audience.

### 📦 HANDOFF.md structure

This is the doc the human reads cold. Structure it ruthlessly for skimming:

1. **TL;DR status** (1 paragraph) — ready / not ready, with reasoning
2. **What works end-to-end** (bullet list with verification)
3. **Three items YOU must do** (numbered, concrete, sized)
4. **Branch table** (every branch + commit + one-line purpose)
5. **Demo flow** (or equivalent: the canonical use case, with timing)
6. **Pre-call checklist** (or equivalent: action items)
7. **What's deferred to v0.1** (pointer to ROADMAP)
8. **Code reading guide** (file tree with one-line annotations)
9. **How to run the software yourself** (concrete bash recipe)
10. **How the build worked** (autonomous mode + safety rails honored)
11. **Open questions for you** (numbered, each answerable in 1 sentence)

## 🧰 Methods catalog (recipes)

These are the small reusable patterns. Each is 1-3 paragraphs because that's all they need.

### 📐 M1. Frozen contract + DEVIATION protocol

The build agent reads the frozen contract at start and never edits it. If the agent finds the contract is wrong, impossible, or contradictory, it does NOT silently change course. It writes a `DEVIATION: <what changed and why>` line in JOURNAL.md and picks a defensible default.

Why it works: scope drift is the #1 failure mode of long autonomous runs. The contract makes drift detectable. DEVIATION lines make drift legible.

### 🧠 M2. Journal as durable shared brain

Newest entries at top. Structured fields. Every meaningful action gets an entry. Any agent (primary, watchdog, sub-agent, future you) reads the top entry and knows exactly where things stand.

Why it works: surviving context compression / session death is what makes long runs possible. JOURNAL.md is the only state that persists across all agent boundaries.

### 🩺 M3. Watchdog cron with strict recovery exception

Hourly fresh-context agent. Report-only by default. Recovery exception fires ONLY when (a) 2 consecutive WEDGED entries AND (b) top builder entry is IN_PROGRESS or BLOCKED.

Why the exception is so narrow: false positives on recovery are catastrophic — a recovery agent that promotes itself when the builder is correctly idle will invent unwanted work.

### 👀 M4. Adversarial critic fan-out

3-5 critics with diverse perspectives (security, DX, code-quality, OSS-strategy, etc.) running in parallel. Each gets an EXPLICIT charter with focus areas + out-of-scope + anchoring questions. Structured-verdict output format (severity-tagged findings) makes mechanical triage possible.

Why it works: critics with "find weaknesses" framing surface things the builder missed. Diversity of perspective catches things any single critic would miss. Structured output is dedupe-friendly.

### 🧪 M5. Dress rehearsal as confidence gate

End-to-end test that exercises the actual production flow against fresh sandbox state. NOT unit tests, NOT smoke tests. The actual flow the user will see.

Why it works: passing unit tests proves the code compiles. Passing dress rehearsal proves the demo lands.

### 🌿 M6. Git worktrees for parallel branch sub-agents

`git worktree add` creates an isolated checkout of a branch in a separate directory. Two sub-agents can each work in their own worktree without git index races. Each commits + pushes to its own branch.

Why it works: sub-agents share my cwd by default. Worktrees give each its own working tree without sharing `.git/HEAD`.

### 🧪 M7. Sandbox via env-var redirection

`TEAMVAULT_HOME` / `TEAMVAULT_SPACE_ROOT` env vars redirect runtime state into a sandbox directory. Production default `~/.teamvault/` is never touched during dev/test.

Why it works: testing the real install path without polluting the user's real account is otherwise impossible.

### 🏷️ M8. Branch-checkpoint sequence

Push to `wip/v0.0-<phase>` after each phase milestone. Never merge to main during the build. The user reviews the sequence and decides what merges where.

Why it works: gives the user a comparable, revertable history. Lets them pick any subset.

### 🐍 M9. Lazy imports in app code

The web app's main entry point lazy-imports heavy modules inside request handlers, not at top of file. A broken module doesn't kill the whole app — only the endpoint that imports it.

Why it works: keeps the health-check endpoint always functional, which keeps the watchdog accurate.

### 🗺️ M10. Defer aggressively, document carefully

Aggressive deferrals → ROADMAP.md with P0/P1/P2/P3 tiers, sizing, and source attribution. Nothing silently dropped. Every "we didn't do X" has a structured entry the user can act on later.

Why it works: scope discipline that doesn't lose information. The user trusts the build's "complete" claim because they can see the deferral list.

## ❌ Anti-patterns (what didn't work)

### ❌ A1. Over-engineering audit trails

Early in this build I appended a "recalibration appendix" to a review doc when a simpler in-place edit + footnote would have served. The user pushed back: "I'm not sure why you're saving this stuff there." Lesson: audit trails are for compliance docs / regulatory filings, not working consultation outputs. Consolidate when you can.

### ❌ A2. Approximate timestamps in journal entries

I used wall-clock-approximate times that drifted from actual `date` output. The watchdog noticed and flagged it. Cost is small but smells unprofessional. Use `date` output literally.

### ❌ A3. Bash heredocs with embedded JSON

My first PHI test wrote a bash loop with embedded JSON containing `\n` escapes. The JSON parser choked. Wasted time. Lesson: when the work is structured-data manipulation, write it in Python. Use bash for orchestration only.

### ❌ A4. Sub-agent cwd sharing

Sub-agents share my cwd by default. If they `cd` into a working dir, that affects subsequent tool calls. Use `git -C <path>` and worktrees instead of `cd` in sub-agent prompts.

### ❌ A5. Watchdog labeling rules don't cover "idle by design"

The SLOWING/STALLED/WEDGED rules assume work-in-progress. Once the build is complete and the human is offline, the rules generate increasingly alarming labels for a state that's correct. I pre-empted with a watchdog note ("recovery is NOT warranted because top builder entry is COMPLETED, not IN_PROGRESS") and the watchdog correctly held its position for 20+ hours. For future builds: add an explicit IDLE_COMPLETE label to the categorization rules.

### ❌ A6. Misleading tool responses

`CronCreate` with `durable: true` returned "session-only" in its response, but in practice the cron fired hourly for 25+ hours across multiple sessions. The response was misleading; the behavior was correct. Lesson: verify behavior empirically; don't trust tool response text alone for long-running guarantees.

### ❌ A7. Padding hour estimates

I padded effort estimates by ~50% (nervousness disguised as caution). The maintainer called it out. Real work was 8-12h of focused build, not the 18-24h I'd projected. Trust your actual velocity; don't pad to feel safe.

## 📑 Templates

### 📐 Template: frozen build contract

```markdown
# <Project> POC v0.0 — Build Contract

> Status: Build contract for autonomous <window-name> build, <start> → <end>.
> Audience: Any build agent picking up the work. <Owner> reviews on return.
> North Star: <one-sentence success criterion>.

## Scope discipline
v0.0 is the demo POC. NOT v0.1 (public OSS), NOT production. Make <event> work, leave clear breadcrumbs for v0.1 polish.

## What ships in v0.0
- <item 1, cheap + load-bearing>
- <item 2>
...

## What does NOT ship (deferred to v0.1+)
<item> · <item> · <item>

## Sandbox & safety rails
- All runtime state goes to `${SANDBOX_HOME}`. During dev/test: `<env var>=<sandbox>`. Default `<real path>` is UNTOUCHED.
- No push to `main`. Branches only.
- No force pushes.
- No modifying <list of real user state paths>.
- No outbound network beyond <whitelist>.

## Day-1 file tree
<concrete file tree>

## Build phases
### Phase 1 — <name> (~Nh)
<what ships>. Push to `wip/v0.0-<phase>`.

### Phase 2 — <name> (~Nh)
<what ships>. Push to `wip/v0.0-<phase>`.

### Phase 3 — <name> (~Nh)
<what ships>. Push to `wip/v0.0-<phase>`.

## DEVIATION protocol
If the build agent finds the contract is wrong / impossible / contradictory, do NOT silently change course. Write a `DEVIATION: <what changed and why>` line in JOURNAL.md and pick a defensible default. <Owner> decides on return.
```

### 📝 Template: JOURNAL.md seed

```markdown
# <Project> Autonomous Build — Journal

> Started: <date>
> Target: <end>
> Mode: Autonomous build (<owner> offline for <reason>)
> Contract: `<frozen-contract>.md` — frozen spec; deviations require `DEVIATION:` lines.
> Integration contracts: `<integration-contracts>.md` — interfaces between sub-agents

## How to read this file
This is the durable shared brain. Every agent reads at start, writes back the new state.
Order: newest entries at the TOP. Resuming = read top entry, understand state, take next action.

## Entry format
[as documented above]

## Recovery protocol
If you see BLOCKED or WEDGED at top: read entry, understand block, pivot if possible. Document the pivot. If watchdog detects WEDGED >2h with no recovery, watchdog becomes new primary builder.

If you inherit a COMPLETED phase: advance to next phase per the frozen contract.

---

## Entries (newest first)

## <ISO timestamp> — primary-builder — phase-1
**STATUS:** STARTING
**LAST ACTION:** <what>
**NEXT ACTION:** <what>
**DECISIONS:** <any>
**KNOWN ISSUES:** <any>
**FILES TOUCHED:** <list>
**COMMIT:** <SHA or pending>
```

### 📦 Template: HANDOFF.md skeleton

```markdown
# <Project> v0.0 — <Window-name> Build Handoff

> For <owner> on return <date>.
> Build window: <start> → ongoing.
> Demo / event: <date> with <audience>.
> You read this first — it's the cold-start summary.

---

## TL;DR — Status
**READY / NOT-READY** with <count> remaining items to verify yourself.

What works end-to-end (smoke-tested):
- <bullet>
- <bullet>

**N items YOU must do before <event>:**
1. <concrete action>
2. <concrete action>
3. <concrete action>

---

## Branches on <remote>
| Branch | What |
|---|---|
| `main` | <state> |
| `wip/v0.0-*` | <state> |

---

## <Event> flow (canonical use case)
| Min | Beat |
|---|---|
| 0-N | <step> |

### Pre-event checklist
- [ ] <item>

---

## What's deferred (see ROADMAP.md)
<quick summary; full detail in ROADMAP>

---

## Code reading guide
<file tree with one-line annotations>

---

## To run the software yourself
<concrete bash recipe>

---

## How I worked autonomously
- Primary builder: <approach>
- Durable brain: `.build/JOURNAL.md`
- Watchdog: hourly cron
- Sub-agents: <when used>

### Hard guarantees held
- <list>

---

## Open questions for you
1. <question answerable in 1 sentence>
2. <question>
```

### 👀 Template: Sub-agent critic charter

```
You are <Critic role>. You are one of N reviewers running in parallel; blind to other reviewers' work so independent disagreement surfaces.

Persona: <experience profile>

Read in this order:
1. <contract>
2. <files in priority order>

Focus areas:
- <specific thing to look at>
- <specific thing>

Out of scope (other reviewers own these):
- <thing>

Anchoring questions (take a position):
1. <question>
2. <question>

Output format — exact structure:

ROLE: <name>
VERDICT: APPROVE | APPROVE_WITH_CONCERNS | REQUEST_CHANGES | REJECT
EXECUTIVE SUMMARY (under 100 words): <paragraph>
CRITICAL FINDINGS: [F1] FILE:LINE — observation — recommendation
HIGH FINDINGS: ...
MEDIUM / LOW: ...
SINGLE BIGGEST CONCERN: <sentence>

Cap at ~10 findings total. Quality over quantity. Be specific (file:line). If the code is solid for v0.0, say so.
```

## 💡 Concluding heuristics

- **Defer with documentation > push for completeness.** Every deferral in `ROADMAP.md` is a tracked item, not a forgotten one.
- **Honest about uncertainty > performatively confident.** HANDOFF.md says "not runtime-tested against real ~/.claude" because it isn't. The reader trusts what the build says is true because the build is honest about what it doesn't know.
- **The frozen contract is the only authority.** No matter how clever the in-flight idea, if it deviates from the contract, it gets a DEVIATION line, not silent execution.
- **Sub-agents are workers, the journal is the manager.** Sub-agents don't see each other's state. They see the journal. The journal coordinates them.
- **Pre-empt the watchdog's confused states.** If you know the build will reach a state the watchdog's rules don't cleanly cover (like "complete + idle"), write a watchdog note about it before the state arrives.
- **The dress rehearsal is the gate.** If it passes, ship. If it fails, fix. No shipping on hope.

---

## 🗃️ The TeamVault POC build as the worked example

If you want to re-read this methodology against the actual artifacts it produced:

| Layer | Artifact in this repo |
|---|---|
| 📐 Frozen contract | wherever you wrote it (e.g., `docs/CONTRACT.md`) |
| 📝 Durable journal | `.build/JOURNAL.md` |
| 🔌 Integration contracts | wherever you wrote them (e.g., `docs/CONTRACTS.md`) |
| 🧱 Phase 1 thin slice | branch `wip/v0.0-thin-slice` |
| 👀 Adversarial critics | (3 sub-agent runs in the conversation transcript) |
| 🛡️ Phase 2 hardening | branch `wip/v0.0-hardened` (Phase 2 commit) |
| 🧪 Dress rehearsal | `.build/test_dress_rehearsal.py` |
| 🩺 Install dry-run | (sub-agent run in transcript) |
| 🌿 Stretch sub-agents on worktrees | branches `wip/v0.1-stretch-{audit-log, contextual-prefixes}` |
| 📦 Handoff doc | `HANDOFF.md` (repo root) |
| 🛠️ Customer-facing runbook | `docs/TROUBLESHOOTING.md` |
| 📋 Customer-facing narrative | (lives in each team's fork — kept out of the master template) |
| 🗺️ Structured deferral list | `docs/ROADMAP.md` |
| 🤝 OSS contributor surface | `docs/CONTRIBUTING_PACKS.md` |

The build window: Fri 2026-06-12 ~20:00 EDT → Sat 2026-06-13 ~21:30 EDT (~25 hours from setup to handoff). Real focused build time: ~8 hours. The rest was watchdog firings, polish, and stretch features.

Reuse this methodology when the next bounded autonomous window comes up. It works.
