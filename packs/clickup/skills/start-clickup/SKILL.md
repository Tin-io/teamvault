---
name: start-clickup
description: Start work on a ClickUp ticket. Fetches the ticket + dependencies, scores AC clarity, runs a short interview if AC are under-specified, transitions the ticket to In Progress (with explicit approval), searches the TeamVault KB for relevant prior decisions, and walks the agent through the full implement → review → publish → PR → DoD report flow. Stack assumption — ClickUp source of truth, OMC harness (optional), TeamVault KB. Use when the user says "/start-clickup TASK-ID", "start ClickUp ticket X", "what does X say and how should we approach it".
args: "[clickup-task-id] (required — bare task ID or full clickup.com URL)"
allowed-tools: Bash, Read, Grep, Glob, Write, Edit, AskUserQuestion, Agent, Skill
---

# Start ClickUp Ticket

Companion to `/new-clickup` (creates) and `/review-clickup` (grades diff vs AC). This skill is the **start** of the lifecycle: fetch the ticket, ground it, decide it's clear enough to act on, transition it to In Progress, and set the stage for implementation.

Sister Jira skill: `/start-ticket`. This is the ClickUp analog with the same shape but adapted for ClickUp's task model + the OMC+TeamVault stack.

## Inputs

Argument string at `$ARGUMENTS`.

- **Task ID** (e.g., `86baegfym`) or **full URL** (e.g., `https://app.clickup.com/t/86baegfym`) — extract the bare ID.
- **Empty** — surface a recoverable error: ask the user to pass the task ID. Don't try to list candidates yet (v2 may add that).

## Protocol

### Step 1 — Parse arg + fetch ticket

Extract bare task ID. Strip URL wrapping if present (`https://app.clickup.com/t/<id>` → `<id>`).

Call `mcp__clickup__clickup_get_task`:

- `task_id: "<id>"`
- `include: ["description", "dependencies", "linked_tasks", "checklists"]`
- `expand_statuses: true`

Read the ticket end-to-end. Note `available_statuses` — you need the exact strings for "in progress" and "complete" later (commonly lowercase but verify per-list).

### Step 2 — Fetch dependencies (one hop only)

For each task listed under `blocked_by` (and optionally `linked_tasks`), call `mcp__clickup__clickup_get_task` with the minimal include set. Cap at 6 linked tickets; if more, list the rest by ID without fetching. **Do not recurse** — one hop is enough for context.

For each dependency: capture its summary, status, and any KB references it has published (look for `vault_publish` mentions in the body or in comments tagged `For Claude:`).

### Step 3 — Read product context

Read the current repo's top-level docs: `PRD.md`, `README.md`, `CLAUDE.md`, `docs/STRATEGY.md` (if present). Look for a `For Claude:` or `For agents:` section in the ticket body — those are the canonical implementation references when present.

### Step 4 — Score AC clarity + interview if needed

Extract the acceptance criteria from the ticket body (bulleted lists, "AC:" or "Definition of Done" sections, checklist items). For each AC bullet, check:

- ☑ Has a verifiable predicate (something observable — "shows X", "returns Y")
- ☑ Names the file / component / route / endpoint scope explicitly
- ☑ Addresses at least one obvious edge case (empty input, error state)
- ☑ Implies a test expectation, even loosely

Count bullets meeting ≥3 of 4 criteria. `r = met / total`:

- `r ≥ 0.8` → score = **high** → skip interview
- `r ≥ 0.5` → score = **medium** → short interview (≤3 questions)
- `r < 0.5` → score = **low** → full interview (≤5 questions)

**Interview rules (when triggered):**

- **One round only.** Batch into a single `AskUserQuestion` call.
- **Questions must be generative, not confirmatory.** Phrase as *"I plan to verify X by Y. Correct, or refine?"* — not *"do you want X?"*
- **Don't ask things grounding step 3 already answered.** State the inference and confirm it.
- Capture answers as `clarifications` for downstream use.

### Step 5 — Search the TeamVault KB

Before committing to any algorithm or convention decision, call `mcp__teamvault__vault_search` for prior team conventions on the topic. Use the ticket's key nouns as the query; set `purpose:` to a one-liner explaining the decision you're about to make. Don't reinvent decisions the team has already made.

If results are relevant, `mcp__teamvault__vault_cite` afterward with the paths you actually used (closes the search → decision audit loop). Empty `paths_used` is valid — records "we searched, nothing was useful."

### Step 6 — Transition to In Progress (explicit approval gate)

Use `AskUserQuestion`: *"Move `<task-id>` (`<summary>`) to 'in progress' in ClickUp?"* — options:

1. **Yes (Recommended)** — fires the transition.
2. **Not yet** — skip; user transitions manually later.

If Yes: `mcp__clickup__clickup_update_task` with `task_id: "<id>"` and `status: "<exact in-progress string from available_statuses>"`. Do this BEFORE writing files — signals to the team that work is live.

Per global CLAUDE.md rules, every ClickUp write requires explicit approval. The `AskUserQuestion` satisfies that.

### Step 7 — Execute the implementation

The work loop:

1. Read the relevant code (files identified in Step 3 grounding + KB hits from Step 5).
2. Write the deliverables per the ticket's AC + Step 4 clarifications.
3. **Before publishing any decision to the KB**, if you're about to write a non-trivial decision doc, invoke `oh-my-claudecode:critic` (via Agent tool with `subagent_type: oh-my-claudecode:critic`) on it. Adversarial review prevents weak choices from entering the KB as canonical.
4. After implementation, run the review chain:
   - `/verify` (or `oh-my-claudecode:verify` if OMC is loaded) — confirm tests collect, stubs import, fixtures parse
   - `/code-review` on the full diff
   - `/teamvault-review` on the diff (runs pack-runtime scrubbers + linkage check)
5. `/remember` (or `oh-my-claudecode:remember`) — capture session-local decisions in project memory for cheap recall next session.

### Step 8 — Publish to the TeamVault KB

`mcp__teamvault__vault_publish` (or `/teamvault-publish`) per the ticket's KB requirements. Prefer individual short docs for non-obvious judgment calls — they're cheaper for `vault_search` to surface than one mega-doc.

When the entry's frontmatter would carry `kingdom/palace/wing` per the Light Palace convention, set them in the body for now (v0.1.x `vault_publish` doesn't auto-fill from `repos.yaml` — auto-fill is v0.1.5+).

### Step 9 — Branch + PR (explicit approval gates)

Use the branch name from the ticket's `For Claude:` section if present, else use a slug from the ticket summary (`feat/<task-id>-<short-slug>`).

**Do NOT push or open a PR without Reuven's explicit approval.** Show the diff and the review-chain outputs first. After approval, push and open the PR using the project's PR conventions (see `pr-push` skill if available).

The diff also gets re-reviewed by the pack runtime if `/teamvault-review` runs on it (the ClickUp linkage advisory will warn if the PR doesn't reference the ClickUp ticket — add the URL to the PR body).

### Step 10 — Report back in ClickUp (explicit approval gate)

Use `AskUserQuestion`: *"Post a Definition-of-Done summary as a comment on `<task-id>`?"* — Yes / Skip.

If Yes: `mcp__clickup__clickup_create_comment` with:
- `entity_type: "task"`
- `entity_id: "<task-id>"`
- `body:` formatted per the user's conventions (TLDR at top; bullets covering AC satisfied / open / KB published / PR link)

Per global CLAUDE.md rules, ClickUp content writes need explicit approval — `AskUserQuestion` satisfies that.

### Step 11 — Transition to Complete (explicit approval gate)

ONLY after Reuven's approval (PR merged where applicable, or final report acknowledged). Use `AskUserQuestion`: *"Move `<task-id>` to 'complete' in ClickUp?"* — Yes / Skip.

If Yes: `mcp__clickup__clickup_update_task` with `task_id: "<id>"` and `status: "<exact complete string from available_statuses>"`. **Don't self-close** — wait for the gate.

## On blockers

If you hit a blocker mid-flight: drop a comment on the ticket via `mcp__clickup__clickup_create_comment` (gated on `AskUserQuestion` — explicit approval per global rules). Stay on `in progress` status — don't bounce back to `to do`.

## Safety rules

- **Every ClickUp write requires explicit `AskUserQuestion` approval.** Status transitions (Steps 6, 11), comments (Steps 10, blocker case), task edits. Global CLAUDE.md rule.
- **Every git write requires explicit user approval.** Commits, pushes, PR creation. Don't auto-commit even after the review chain passes — surface the diff and the verdicts and ASK.
- **Don't push to production / main.** Per Merkos org rules: PRs target staging (or the project's documented default), not main/production.
- **Don't auto-add `@`-mentions in ClickUp comments unless someone specifically needs to act, respond, or decide.** Convention from the user's Jira conventions; mirror it here.
- **OMC is optional.** The existing `/start-clickup` slash command (now superseded by this skill) hard-required OMC. This skill treats OMC as optional — if available, use the OMC variants (`oh-my-claudecode:verify`, `:code-reviewer`, `:critic`, `:remember`); if not, use the project's equivalent built-ins (`/verify`, `/code-review`, etc.). Surface the choice once at the start.

## Out of scope (future versions)

- **Background dispatch + monitor** (mirroring `/start-ticket`'s Step 8/10 dispatch/Monitor architecture). Phase 2.
- **Multi-repo grounding.** Single-repo flow only in v1.
- **Auto-detection of in-flight tickets when args is empty.** Add when there's a clear "list candidate tickets" UX.
- **ClickUp checklist sync** — auto-update checklist items as AC are satisfied. Defer until the workflow's settled.
