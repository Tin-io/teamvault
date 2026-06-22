---
name: new-clickup
description: Draft and (with explicit approval) create a new ClickUp ticket via mcp__clickup__clickup_create_task, formatted to the user's conventions — TLDR at the top, `For Claude:` / `For agents:` sections labeled for AI consumption, `@`-mentions only when someone specifically needs to act, grounded in the codebase rather than just paraphrasing the request. Sister skill to `/start-clickup` (works *on* an existing ClickUp ticket) and `/review-clickup` (grades a diff against a ticket's AC). Supports `--batch <yaml-file>` for bulk creation (roadmap migration, backlog import).
args: "[free-text description of the ticket idea] (optional — if empty, prompts for intent) — OR — --batch <path-to-yaml> for bulk creation"
allowed-tools: Bash, Read, Grep, Glob, Write, AskUserQuestion
---

# New ClickUp Ticket

Companion to `/start-clickup` and `/review-clickup`. Where those work on an existing ticket, `/new-clickup` produces a well-formatted new one and (with explicit approval) creates it via the ClickUp MCP.

Mirrors the shape of `/new-ticket` (Jira analog) — same conventions baked in, but adapted for ClickUp's task model (workspace → space → folder → list → task; per-list status taxonomy; tags instead of labels; auto-generated alphanumeric task IDs).

## The five conventions (canonical — apply on every ticket)

1. **TLDR at the top.** The first line of the description is `**TLDR:**` followed by a one-sentence summary. Skimmable in ten seconds; no walls of text above it.
2. **`@`-mention only when a specific person needs to act, respond, or decide.** Default to no mention. The ticket lives in the audit trail without one. ClickUp `@`-mentions render as direct notifications — they're high-signal. Add a mention when the reporter needs questions answered, a stakeholder needs to weigh in on a fork-in-the-road decision, or a specific approver is gating the work.
3. **`For Claude:` / `For agents:` sections** label content meant for AI consumption. Place these toward the end of the description, under a horizontal rule, so humans know to skip. Use when there's implementation guidance, file paths, repo grounding, or anything else a human reader doesn't need but a future `/start-clickup` run will.
4. **Don't deflect.** Never frame a ticket as "this already exists — closing." If someone couldn't find the functionality, the ticket is real. Surface the underlying gap (missing UX surface, missing user guide, terminology mismatch) and write the ticket to fix that, not to dismiss the requester.
5. **Ground in the codebase, not just the request.** Before writing, read the relevant code, the repo's glossary, and the user guide. Match the repo's terminology exactly — don't invent new names for things that already have names.

Precedence: if a repo's `CLAUDE.md` has ClickUp instructions covering any of the above, those override globally. Where the repo is silent, the above stands.

## Inputs

Argument string at `$ARGUMENTS`.

- **Free-text** — treat as the ticket intent. Drives Step 1 directly.
- **Empty** — Step 1 prompts the user.
- **`--batch <path>`** — bulk-create mode. See [§ Batch mode](#batch-mode) below.
- **Flags** — see below.

## Argument parsing

Parse `$ARGUMENTS` into:

- **`intent_text`** — everything that isn't a flag, joined back to a single string.
- **`flags`** — every token starting with `--`. Recognized:

| Flag | Effect |
|---|---|
| `--list <id>` | Pre-set the target ClickUp list ID. Skip the "which list?" question in Step 0. |
| `--tags foo,bar` | Pre-set tags (comma-separated). |
| `--priority urgent\|high\|normal\|low` | Default: normal. ClickUp uses these four levels. |
| `--mention @user` | Pre-declare an `@`-mention. Convention #2 still applies — Step 5 will reflect this back to confirm. |
| `--no-interview` | Skip Step 3's clarification interview even if intent is sparse. |
| `--draft-only` | Show the drafted ticket and stop. Don't even ask whether to create it. |
| `--batch <path>` | Bulk-create mode. See [§ Batch mode](#batch-mode). |

Unknown flags are an error — surface and stop.

## Protocol

### Step 0 — Resolve the target list

ClickUp's `clickup_create_task` requires a `list_id`. Skip if `--list` was passed.

Otherwise:
1. Check for a project-level default: read `<repo>/CLAUDE.md` for a `clickup_default_list:` line OR an env var `CLICKUP_DEFAULT_LIST`. If set, use it.
2. If no default: use `mcp__clickup__clickup_get_workspace_hierarchy` to fetch the workspace tree. Walk it: spaces → folders → lists. Use `mcp__clickup__clickup_get_folder` and `mcp__clickup__clickup_get_list` to descend as needed.
3. Present the available lists via `AskUserQuestion`. Cap at 4 options; the rest go behind an "Other / paste a list ID" free-text option.
4. **Optionally offer to persist the choice** as the project default: "Save this as the default list for this project? [Y/n]" — writes a `clickup_default_list: <id>` line into `<repo>/CLAUDE.md` under a `## ClickUp config` section (creates the section if needed).

Hold `list_id` as state.

### Step 1 — Capture intent

If `intent_text` is non-empty, treat it as the seed and proceed. If empty, use `AskUserQuestion` with a single free-text question: *"What's the ticket about? One or two sentences is plenty — I'll ground it in the codebase and draft the rest."*

After this step, you should have a 1–3 sentence intent statement to work from.

### Step 2 — Ground in the codebase (convention #5)

This is non-negotiable. A draft written from the request alone is the wrong artifact — it'll use the user's words for things the code already names differently, and it'll miss whether the functionality partially exists.

**2a — Identify candidate repos.** The current repo (the cwd where the skill was invoked) is the primary candidate. If the intent text mentions other repos by name, add them. Validate against `~/teamvault-personal/repos.yaml` if available — repos listed there are bound to the team's TeamVault space.

**2b — Grep for terminology.** Grep the candidate repos for the key nouns and phrases from the intent:

```bash
grep -rIl --include='*.ts' --include='*.tsx' --include='*.js' --include='*.jsx' \
     --include='*.py' --include='*.go' --include='*.md' \
     --exclude-dir=node_modules --exclude-dir=.next --exclude-dir=dist --exclude-dir=build \
     -- '<token>' <repo-root>
```

The goal is to learn two things:

- **What does the codebase call the thing?** If the user says "discover feed" and the code says "DiscoverSurface", the ticket should use `DiscoverSurface` (with the user's phrasing as a parenthetical aid).
- **Does the functionality already exist, even partially?** This feeds convention #4 — if it does, don't deflect; figure out *why* the user couldn't find it and write the ticket to close that gap.

**2c — Check glossary / user guide if present.** Look for any of:
- `GLOSSARY.md`, `docs/GLOSSARY.md`
- `README.md`'s terminology section
- `docs/user-guide/`, `USER_GUIDE.md`
- `CLAUDE.md` (repo-level — may have terminology guidance)

Read what's relevant. Match the canonical names exactly in the draft.

**2d — Search the TeamVault KB.** Call `mcp__teamvault__vault_search` with the key nouns; set `purpose:` to "checking for prior team decisions related to this new ticket". Surface relevant hits. Future `/start-clickup` runs on this ticket will benefit if the KB-search context is included in the `For Claude:` section.

**2e — Search for existing related tickets.** Use `mcp__clickup__clickup_search` (or `mcp__clickup__clickup_filter_tasks` if you need filtering by list/status) with the key noun. Goal: surface anything already filed in the same area. If a strong match exists:

- **The existing ticket covers it** → don't create a duplicate. Surface the existing ticket to the user, ask: "this looks like `<task-id>` — want to comment there instead, or is your ticket scoped differently?" Per convention #4, never just close-out the user with "already filed"; if they want to add detail to the existing one, draft a comment for it instead.
- **Partial overlap** → still draft the new ticket, but include a "Related" section that links to the existing ticket(s) with a one-line note on the boundary.
- **No overlap** → proceed cleanly.

Hold the grounding results as state for Steps 3 and 5.

### Step 3 — Interview if intent is sparse

Conditional. Skip if:
- `--no-interview` was set.
- Intent text is already specific enough to produce concrete AC.
- Step 2 produced strong inferences for all open questions.

Otherwise, run **one** bounded round. Same rules as `/start-clickup`'s Step 4:

- **One round only.** Batch into a single `AskUserQuestion` call. Up to 4 questions.
- **Questions must be generative, not confirmatory.** Phrase as *"I plan to scope this as X based on Y. Confirm or refine?"* — not *"do you want X?"*
- **Don't ask things grounding already answered.**
- **Don't ask style preferences Claude can decide.**

Capture answers as clarifications to fold into the draft.

### Step 4 — Decide the `@`-mention (convention #2)

Default: **no mention.** Add only if:
- A specific person needs to answer a question before work can start
- A specific person needs to approve a decision the ticket records
- The ticket creator needs the work assigned to a specific person (set `assignees`; no body mention required)
- `--mention @user` was explicitly passed — reflect this back in Step 5 for confirmation

If tempted to add a mention "for visibility" or "as an FYI" — don't.

### Step 5 — Draft the ticket

Compose the draft in this exact shape. Each section is optional unless marked **required**.

```
TITLE (required):
<imperative, ≤80 chars — "Add lastSyncedAt to feed_sources admin view", not "lastSyncedAt feature">

DESCRIPTION:

**TLDR:** <one sentence — required, convention #1>

## Context
<2–4 sentences on why this is being filed. If Step 2e surfaced existing related tickets, name them here in a "Related" sub-list. If the functionality already partially exists, say so explicitly per convention #4 — don't pretend it doesn't.>

## Acceptance criteria
- [ ] <verifiable predicate — observable, scoped, edge-case aware>
- [ ] ...

## Out of scope
<one or two bullets, only if scope ambiguity surfaced in Step 3. Otherwise omit.>

---

**For Claude:** (convention #3 — omit entirely if no AI-relevant guidance)

<implementation grounding — file paths discovered in Step 2, repo it lives in, conventions to follow, terminology aliases. This is where you put "the user calls this 'discover feed' but the code calls it 'DiscoverSurface'" so a future `/start-clickup` run resolves it cleanly. Also include any KB-search hits worth re-checking.>

TAGS: <list>
PRIORITY: <urgent | high | normal | low>
LIST: <list_id from Step 0>
ASSIGNEES: <if set, else leave for triage>
@-MENTION IN BODY: <none | @user at <line> — convention #2 says default none>
RELATED TICKETS: <task-id> (from Step 2e, if any)
```

**Formatting rules:**
- ClickUp renders Markdown in descriptions — same syntax as Jira's flavor (`**bold**`, `_italic_`, `## heading`, `- bullet`, `[link](url)`, fenced code blocks).
- AC bullets use `- [ ]` syntax — ClickUp renders these as a checklist if the list is configured for checklists. Some lists need explicit checklist creation via `mcp__clickup__clickup_get_task` post-create + checklist API; for v1, embed as markdown checklist in the description.
- Inline `code` for identifiers.
- The horizontal rule (`---`) separates human-facing content from `For Claude:` / `For agents:` sections.

**What NOT to do:**
- Don't write more than 3–4 sentences of context. Walls of text fail convention #1's spirit.
- Don't repeat the TLDR in the Context section.
- Don't include implementation grunt-work in the human-facing section.
- Don't add a mention "for visibility."
- Don't write "this should be straightforward" or "shouldn't take long."

### Step 6 — Show the draft and gate on approval

Surface the entire draft to the user in a single message. Lead with:

```
Draft for new ClickUp ticket (NOT yet posted — your call):

[full draft from Step 5]
```

Then use `AskUserQuestion` with options (in order):

1. **Create it (Recommended)** — calls `mcp__clickup__clickup_create_task` with the draft as-is.
2. **Refine** — let the user describe what to change; loop back into Step 5 with the feedback.
3. **Save draft locally and don't post** — write the draft to a path the user specifies (default `~/Desktop/clickup-ticket-draft-<short-slug>.md`).
4. **Cancel** — drop the draft entirely.

If `--draft-only` was set, skip the AskUserQuestion and stop after surfacing the draft.

**This is the explicit-approval gate** the global `CLAUDE.md` ClickUp/Jira rules require. Writes only happen on option 1.

### Step 7 — Create the ticket

If the user chose "Create it":

1. Assemble the payload for `mcp__clickup__clickup_create_task`:
   - `name`: title (required)
   - `list_id`: from Step 0 (required)
   - `description`: full draft body (markdown)
   - `tags`: list (optional)
   - `priority`: numeric mapping — ClickUp uses 1=urgent, 2=high, 3=normal, 4=low
   - `assignees`: list of user IDs (optional — needs lookup via `mcp__clickup__clickup_get_workspace_members` or `mcp__clickup__clickup_find_member_by_name` if user gave a name)
2. Call `mcp__clickup__clickup_create_task`.
3. On success, surface the result inline:

   ```
   Created `<task-id>` — <title>
   URL: https://app.clickup.com/t/<task-id>

   Next:
   - /start-clickup <task-id> — start work now
   - View on ClickUp: <url>
   ```

4. If the draft includes a "Related" section pointing at existing tickets, ask whether to add a ClickUp task dependency link via `mcp__clickup__clickup_add_task_dependency`. This is another write; gate on `AskUserQuestion` per global rules.

5. **Do not auto-post a "Created by Claude" comment** to the new ticket. The ticket history shows you created it; an extra comment is noise.

### Step 8 — Don't transition

This skill creates the ticket. It does NOT transition it or start work on it. If the user wants to start immediately, that's `/start-clickup <task-id>` — a separate explicit action.

The default fresh state for a created ticket ("to do" on most lists) is the right starting point. Don't move it.

## Batch mode

For bulk creation (roadmap migration, backlog import) use `--batch <path-to-yaml>`. The YAML file is a list of ticket specs:

```yaml
- title: "P0.2 — pre-commit + pre-receive scrubber hooks"
  description: |
    **TLDR:** Closes the "dev edits kb/ directly, bypassing /teamvault-publish" PHI leak path.

    ## Acceptance criteria
    - [ ] pre-commit hook installed by teamvault-setup §...
    - [ ] pre-receive GHA workflow in the master template
    ...
  tags: [v0.1.x, compliance, scrubbers]
  priority: 2   # high
  list_id: <as-default-or-explicit>

- title: "..."
  ...
```

Flow:

1. Parse the YAML. Validate that each entry has at least `title` and either `list_id` (per-entry) or the run was invoked with `--list` (provides the default).
2. **Show the full batch as a summary table** (title + priority + tag count) — no per-ticket draft expansion.
3. **One `AskUserQuestion` gate** for the entire batch: *"Create all `<N>` tickets? [Yes / Show one full draft for review / Cancel]"*
4. On approval, iterate: for each spec, call `mcp__clickup__clickup_create_task`. Collect created `task_id`s.
5. After all creates: surface a results table (`<task-id>` | title | URL) and ask whether to write a `BATCH-MIGRATION.md` summary file locally.
6. **NEVER** auto-post comments to the created tickets — same rule as single-ticket Step 7.

**For the TeamVault roadmap migration specifically:** the YAML can be hand-authored from `docs/ROADMAP.md`, OR a future helper (`/migrate-roadmap-to-clickup`) could parse ROADMAP.md → YAML automatically. For v1, hand-author or use a one-off python script to generate.

## Safety rules

- **Writes need explicit approval each time.** The Step 6 `AskUserQuestion` is the gate. Per global CLAUDE.md, ClickUp writes are treated the same as Jira writes (and git commits) — explicit per-invocation OK. Batch mode collapses N gates into 1, but it's still an explicit gate.
- **Don't deflect.** Convention #4. If Step 2e finds an existing ticket, present it as a fork (comment on existing? or scope the new one differently?).
- **Don't invent terminology.** Convention #5.
- **No silent `@`-mention.** Convention #2. The draft shown in Step 6 explicitly lists `@-MENTION IN BODY:` so the user sees what (if anything) will be tagged.
- **One ticket per invocation** in interactive mode. If the user describes multiple distinct pieces of work, surface that and ask whether to split. Use batch mode for genuine bulk-create.
- **No auto-transition** post-create. `/start-clickup` is the explicit "begin work" gate.

## Out of scope (future versions)

- **`/edit-clickup`** for modifying an existing ticket's description / AC. Distinct skill — similar conventions, but the diff/approval flow is different.
- **`/new-clickup-comment`** for posting comments to existing tickets in convention-compliant form (TLDR + minimal mention).
- **Cross-link to GitHub.** When the new ticket implies code work in a specific repo, optionally create a placeholder GitHub issue and bi-directional link.
- **Templates per task type.** Bug tickets want a "steps to repro / expected / actual" template; spike tickets want a "questions to answer / done when" template.
- **Helper `/migrate-roadmap-to-clickup`** that parses `docs/ROADMAP.md` into the batch-mode YAML format automatically.
- **Persist `assignees` lookup cache** — repeated `clickup_find_member_by_name` calls are slow; cache to a local file scoped to the workspace.
