# packs/jira-linkage

Advisory pack for teams using Jira on `atlassian.net`. Two contributions:

| File | Purpose | Runtime behavior |
|---|---|---|
| `agents/jira-linkage-reviewer.md` | PR linkage check — confirms every PR references a Jira ticket | Runtime-invoked by `/teamvault-review` and the GHA workflow (advisory by default) |
| `agents/jira-comment-conventions.md` | Reference document capturing the team's Jira posting rules (TLDR, mentions, "For Claude", no deflection, codebase-grounded) | NOT auto-invoked — referenced from your skills (your `/start-ticket`, `/review-ticket`, OMC stages) or your CLAUDE.md |

## What this pack does

1. **PR linkage check (advisory).** Confirms every PR's diff includes a Jira ticket reference (URL or bare ID like `PROJ-123`). Useful for SOC 2 evidence — every change traceable to a tracked work item. Flip to `blocking` in your fork to enforce.

2. **Jira posting conventions (reference).** Captures the team's Jira hygiene rules with templates and good/bad examples. Any agent about to write to Jira reads this first.

## Enable in your space

In your space's `space.yaml`:

```yaml
enabled_packs:
  - hipaa-reference
  - jira-linkage         # add this
```

Commit and push to your team space repo. Within ~60s every developer's sidecar has the pack loaded.

## (Optional but recommended) CLAUDE.md addition

Add to `~/.claude/CLAUDE.md` (personal global) or your project's `CLAUDE.md`:

```markdown
## Before any Jira write
If TeamVault has the jira-linkage pack installed, read
`~/teamvault-<space>/packs/jira-linkage/agents/jira-comment-conventions.md`
before composing any Jira comment, description, or AC edit.
```

This makes conventions consultation implicit — no command to remember; the agent loads them when relevant.

## Integration with your `/start-ticket` and `/review-ticket`

Your existing skills handle the workflow; the pack supplies conventions + a linkage check at the right moments.

**Suggested skill edits:**

In `~/.claude/skills/review-ticket/SKILL.md` Step 9 (the closing TLDR comment to Jira) — add a pre-step:

```markdown
### Step 8.5 — Load Jira conventions before composing
Read `~/teamvault-<space>/packs/jira-linkage/agents/jira-comment-conventions.md`
and apply the "review summary" template in Step 9.
```

The PR linkage check (the reviewer agent) fires automatically via the GHA workflow once the pack is enabled in `space.yaml` — no skill edit needed.

## Integration with OMC

Same CLAUDE.md addition above. OMC stages that produce Jira writes (status updates, completion summaries) pick up the conventions naturally.

## Project key flexibility

The runtime's linkage check uses a broad regex (`[A-Z][A-Z0-9_]+-\d{1,6}`) that matches `PROJ-123`, `ENG-567`, `OPS-89`, etc. Teams with multiple project keys or non-standard formats can fork the pack and tighten the regex in `sidecar/pack_runtime.py` (the `jira-linkage` branch in `fan_out_review`).

## Limits (v0.0)

- Runtime only sees diff text. PR description body (via `${{ github.event.pull_request.body }}` in GHA context) is NOT yet plumbed — v0.1 fix. Workaround: include the ticket ID in the branch name (a `feature/PROJ-XXX-<slug>` convention satisfies this naturally).
- Default mode is `advisory` (flag without blocking). Flip to `blocking` in your fork if your team wants enforcement.
- Does NOT validate that the matched ID actually exists in Jira (no MCP call). Presence-only check.
- The conventions doc is a one-time read into agent context per session. If a long session has many Jira writes, the agent should re-read between batches to refresh — the doc is small enough that this is cheap.

## Provenance

Conventions: the maintainer's team, per global CLAUDE.md.
Pack author: the maintainer via TeamVault build agent.
