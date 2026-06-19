---
name: jira-comment-conventions
description: Reference document for any agent about to compose a Jira comment, description, or AC edit. Captures the team's posting conventions (TLDR-first, minimal @-mentions, "For Claude" sections, no deflection, codebase-grounded). NOT auto-invoked by the runtime — reference from your skills (e.g., your `/start-ticket`, `/review-ticket`, OMC stages) or your CLAUDE.md so it loads before any Jira write.
---

# Jira Comment Conventions

If you're an agent about to call `mcp__mcp-atlassian__jira_add_comment` or any other Jira write tool (status transitions excepted — those are content-free), read this first. These conventions were agreed by the team and are load-bearing for ticket signal quality.

## The five rules

### 1. TLDR at the top

Every AI-authored Jira comment opens with a TLDR line. No walls of text — if a human can't skim it in ten seconds, rewrite it.

```
TLDR: <one sentence — what happened or what's the ask>

<optional: 1-3 supporting bullets>

<optional: detail block under "Detail:" header for those who want it>
```

The TLDR is the load-bearing element. Most readers stop after it. Make it count.

### 2. @-mention only when a specific person needs to act, respond, or decide

Mentions are signals — they lose value when used for routine status, audit findings, parking notes, or "FYI" comments. **Default to no mention.** A comment without one still lives in the ticket's audit trail for anyone who later opens it.

Add a mention when:
- The ticket creator needs questions answered
- A recent interactor needs to respond
- A specific decision is required from a named person

Lean fewer; expand if signal is being missed. Calibration is ongoing.

### 3. "For Claude" / "For agents" sections

When content in a ticket or comment is meant for AI consumption (implementation specs, agent directives, parsing guidance), label it `For Claude:` or `For agents:` so humans know to skip it. When reading a ticket, prioritize these sections as authoritative for implementation — but never assume humans have read them.

### 4. Don't deflect

Never close or push back on a ticket by saying "that functionality is already there." If a stakeholder or PM couldn't find it, the ticket is real — surface the underlying gap (missing UX, missing user guide, terminology mismatch) and propose a fix.

### 5. Ground tickets in the codebase, not just Jira

When creating or refining tickets, read the relevant code, the repo's glossary, and the user guide first. Match the repo's terminology exactly. If the ticket says "the settings page" but the code calls it `<UserPreferences/>` at `/account/preferences`, use the code's terminology in your comment and gently surface the mismatch.

## Good vs bad examples

### Status update

**Bad** (routine status with unnecessary mention):
> @the-author Implementation complete, all AC satisfied, 12/12 tests pass.

**Good** (no mention; TLDR + supporting bullets):
> TLDR: Implementation complete. 12/12 tests pass; all AC satisfied.
>
> - AC #1: see src/foo.ts:42
> - AC #2: see src/bar.ts:88
> - Test coverage: tests/foo.test.ts + tests/bar.test.ts

### FYI comment

**Bad** (mention for FYI):
> @the-author FYI we landed PROJ-123.

**Good**: no comment at all. The merge itself is the signal; Jira's status transition tracks it.

### Decision needed

**Good** (mention because a decision is genuinely needed):
> TLDR: AC #3 is ambiguous on retry policy. Need a call.
>
> @the-author — the spec says "handle transient failures gracefully" but doesn't specify retry policy. Two options:
>
> 1. Retry with exponential backoff up to 30s, then fail-fast (matches /tasks pattern)
> 2. Fail-fast immediately, let caller retry (matches /briefing pattern)
>
> I'd lean (1) for consistency with the more recent pattern, but it's your call. Will proceed once you choose.

### Deflection

**Bad** (deflects an apparent duplicate):
> TLDR: This is already implemented in `/admin/settings`. Closing as duplicate.

**Good** (acknowledges the gap underneath):
> TLDR: The functionality exists at `/admin/settings`, but the request shape suggests it's not discoverable. Proposing a follow-up.
>
> The user's described flow ("I clicked Profile → couldn't find it") tells us the navigation isn't obvious. Three options:
>
> 1. Add a Settings link to the Profile page sidebar (smallest change)
> 2. Rename "Admin" → "Account & Admin" so non-admin users notice
> 3. Add a search box to the main nav (largest change, fixes a class of similar issues)
>
> Recommending (1) as the immediate fix; (3) as a follow-up ticket if discovery friction keeps surfacing.

### For-Claude marker

**Good** (mixed human + agent content, clearly delineated):
> TLDR: Updated AC #2 to clarify the empty-state edge case.
>
> The visible change for humans is the new bullet under "Acceptance Criteria."
>
> For Claude: The new bullet specifies that the API returns `null` rather than `[]` so downstream filters can distinguish "no data yet" from "data, but empty result." Update the type signature in `src/api/handler.ts` accordingly.

## Templates

### Status comment (mid-implementation)

```
TLDR: <phase> complete. <next phase> starting.

<1-2 bullets only if material — surprising find, decision made, scope change. Otherwise omit the body. Silence is fine.>
```

### Clarification comment (when you need a decision)

```
TLDR: <one sentence stating the open question>

@<person if a specific decision is needed; omit if not>

Context: <why this came up — 1-2 sentences>

Options:
1. <option A> — <implication>
2. <option B> — <implication>

I'd lean <X> because <reason>, but it's your call.
```

### Review summary (end-of-flow, from `/review-ticket` Step 9)

```
TLDR: /review-ticket — <M>/<N> AC satisfied, <K> findings (<X> blocking).

- AC coverage: <list satisfied verbatim>
- Outstanding: <list unmet AC verbatim>
- Top finding: <one line>

Pre-implementation clarifications (captured at /start-ticket time):
- <clarification 1>
- <clarification 2>

Full review at `<repo>/.claude/active-ticket.md` (local).
```

### Ticket-correction request (when the ticket itself is wrong, not just incomplete)

```
TLDR: AC #<N> says <X> but the actual constraint in <file> is <Y>. Suggesting an edit.

The original AC implies <interpretation>. Reading <file:line>, the existing pattern is <Y>. Two ways forward:

1. Update the AC to match the existing code pattern (small)
2. Update the code to match the AC (larger scope; would need a separate ticket)

Recommending (1). Proposed AC edit:

> <verbatim new AC bullet>

Will await your call before either editing the ticket or starting implementation.
```

## What to NEVER do

- Don't post a comment to announce you read the ticket. The status transition + branch-cut already signal that.
- Don't post a comment to announce you started work. The transition to In Progress is the signal.
- Don't post a comment with no TLDR. If it doesn't have one, rewrite it.
- Don't @-mention in routine status comments.
- Don't deflect with "already implemented" (rule #4).
- Don't post unstructured wall-of-text. Two lines of TLDR + bullets beats three paragraphs of prose.
- Don't auto-post to Jira without explicit user approval. Jira writes need the same approval gate as `git push` per global rules.

## How to use this document

This file is reference content — not auto-invoked by the pack runtime. Wire it into the moments where Jira writes happen:

### For `/start-ticket` and `/review-ticket` skills (your pattern)

Add an early step to each skill that reads this file once into context. Example for `/review-ticket` Step 9 (the only step that actually posts to Jira):

```markdown
### Step 8.5 — Load Jira posting conventions

Before composing the closing TLDR comment in Step 9, read
`~/teamvault-<space-name>/packs/jira-linkage/agents/jira-comment-conventions.md`
and apply the "review summary" template.
```

### For OMC users

Same idea — any OMC stage that posts to Jira should read this first. Add to your CLAUDE.md:

```markdown
## Before any Jira write
If TeamVault has the jira-linkage pack installed, read
`~/teamvault-<space>/packs/jira-linkage/agents/jira-comment-conventions.md`
before composing any Jira comment, description, or AC edit.
```

### For vanilla Claude Code

Same CLAUDE.md addition. Or invoke explicitly: "Read the Jira conventions from teamvault before composing this comment."

## Provenance

These conventions came from team discussion. They live in this pack so they're shared across every developer's machine — change them in the team space repo's fork of this pack and within ~60s every agent on every team member's machine has the updated conventions. That's the point of the substrate.
