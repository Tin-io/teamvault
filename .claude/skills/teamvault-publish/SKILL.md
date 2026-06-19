---
name: teamvault-publish
description: Publish a knowledge-base entry to the team's TeamVault space. Use when the user wants to record a decision, postmortem, finding, team policy, or note for the whole team to find later. The sidecar commits and pushes the entry; pack scrubbers run first.
---

# TeamVault Publish

Write a new entry to the team's TeamVault KB. The sidecar handles markdown commit + push + reindex. Pack scrubbers (HIPAA PHI etc.) run before write — if they match, the entry is rejected and you must fix it.

## When to use

- User says "publish this to the KB", "save this for the team", "remember this", "record this decision"
- After a meeting where decisions were made
- After resolving an incident — postmortem material
- When the user expresses a team policy they want others to find

## When NOT to use

- One-off personal notes (those go in personal notes, not the team KB)
- Code itself (commit to the project repo, not the KB)
- Anything the user marks confidential or "don't share"

## Flow

### 1. Gather material

Identify what to publish from the conversation:

- **slug** (kebab-case): short identifier — e.g., `mrn-handling-policy`, `deploy-incident-2026-06-15`, `decision-clickup-board`
- **content**: the markdown body
- **tags** (optional): list of topic tags

If the slug/content isn't clear, ask the user once.

### 2. Compose frontmatter

Defaults set by sidecar: `created`, `source`, `confidence`. You can add:

- `author`: who decided / authored (string)
- `participants`: who else was involved (list)
- `decision_type`: `policy` | `decision` | `postmortem` | `pattern` | `constraint`
- `links`: related entries, ClickUp/Jira tickets, PR URLs

### 3. Call the MCP tool

```
vault_publish(slug="<slug>", content="<markdown>", tags=["<tag>", ...])
```

### 4. Confirm

Show the user:
- The file path the entry was written to
- Whether the commit succeeded
- Whether the push succeeded (or dry-run skip)
- Any pack scrubber rejection

If scrubber rejected, the response tells you which patterns matched. Help the user redact and retry.

### 5. Searchability check (optional)

Within ~10 seconds after publish, the entry should be searchable. Confirm:

```
vault_search(query="<part of the entry>")
```

## Common errors

- **"Space root not found"**: Sidecar wasn't told which space to publish to. Check `vault_status()` for registered spaces.
- **"Content blocked by pack scrubber"**: A pack's regex matched a sensitive pattern (PHI, secret, etc.). The response message names which pattern. Redact and retry.
- **"committed locally; push failed"**: Entry is on local disk in the space clone but didn't reach the team's remote. Causes: network, auth, branch protection. Surface the underlying error.
