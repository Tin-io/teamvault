---
name: pr-review
description: Comprehensive review of an OPEN pull request — fetches diff + CI status, runs general code-quality checklist, optionally posts findings as PR review comments. For TeamVault-bound repos, also aggregates pack-runtime verdicts. Use AFTER a PR exists, when investigating CI failures, or when the user references a PR number. For pre-commit / pre-PR LOCAL pack checks, use /teamvault-review instead.
---

# pr-review

Review an open pull request against a project-specific checklist, CI status, and (when applicable) TeamVault pack reviewers. Produces structured findings the user can post as review comments.

## When to use

- User says "review this PR" / "review PR #N" / "what's wrong with my PR"
- After a PR has been opened, especially after CI completes
- When CI fails and you want a holistic look at what's broken

## When NOT to use

- Pre-commit / pre-PR pack checks on a LOCAL diff → use `/teamvault-review`
- General "look at this code" with no PR in scope → just ask Claude directly
- When the PR doesn't exist yet → use `/pr-push` first

## Preconditions

```bash
gh auth status
git rev-parse --git-dir > /dev/null
```

## Flow

### 1. Resolve target PR

```bash
if [ -n "$1" ]; then
    PR=$1
else
    PR=$(gh pr view --json number -q .number 2>/dev/null) \
        || { echo "no PR for current branch; pass a PR number"; exit 1; }
fi
```

### 2. Fetch PR metadata + diff + CI

```bash
gh pr view "$PR" --json title,body,baseRefName,headRefName,headRefOid,files,additions,deletions
gh pr diff "$PR"
gh pr checks "$PR" --required 2>/dev/null || gh pr checks "$PR"
```

### 3. (TeamVault repos) Aggregate pack verdicts

Detect binding:

```bash
curl -sf "http://localhost:${TEAMVAULT_PORT:-8100}/healthz" >/dev/null && BOUND=1 || BOUND=0
```

If bound, POST the diff to `/review`:

```
POST http://localhost:${TEAMVAULT_PORT:-8100}/review
{
    "space": "<derived from vault_status or /healthz>",
    "diff": "<diff from step 2>"
}
```

Capture verdict per pack.

### 4. (Optional) Surface relevant KB context

If TeamVault-bound, search for prior decisions on the changed files:

```
vault_search(query="<top changed file names + summary of diff>", k=5)
```

If hits, include them as advisory context the review takes into account.

### 5. Run the general checklist

Walk the diff against these dimensions. For each finding capture: file, line, dimension, severity (`blocker | warn | info`), explanation, suggested patch.

- **Correctness** — off-by-one, null/undefined, error handling at boundaries, race conditions, resource leaks
- **Security** — unsanitized input reaching shell/SQL/HTML, hardcoded secrets, auth/authz on new endpoints, OWASP top 10
- **Tests** — does the diff add/modify code paths without coverage? Are existing tests deleted without justification?
- **Convention adherence** — matches surrounding code style (verify by reading 2–3 nearby files, not by assumption)
- **Naming** — misleading names, abbreviations that hurt readability
- **Scope creep** — unrelated changes bundled in (refactors + features in one PR)
- **Comments** — WHY-comments missing for non-obvious code; WHAT-comments that duplicate the code

The reference skill `/code-structure` (if present in the repo) auto-loads architectural rules that further inform "is this code in the right place?" findings.

### 6. Add CI status as a finding

If any required check failed, emit a synthetic finding:

```
{
    file: ".github/workflows/...",
    line: 0,
    dimension: "ci",
    severity: "blocker",
    explanation: "Required CI check '<name>' failed: <conclusion>",
    suggested_patch: "<gh run view --log-failed snippet>"
}
```

### 7. Aggregate

Merge: pack verdicts + general findings + CI findings. Group by file. Order by severity (blocker first).

### 8. Offer actions

Ask the user:
1. **Post as PR review comments** — `gh pr review "$PR" --comment --body-file <(...)`
2. **Save to /tmp/pr-review-${PR}.md** for later
3. **Skip** — just print

Default: ask. If `--post` flag was passed, do (1) without asking.

### 9. (TeamVault) Cite any KB entries used

If step 4 surfaced entries that informed any finding:

```
vault_cite(
    query_id="<from search response>",
    paths_used=["<used entries>"],
    note="informed review of PR #${PR}"
)
```

## Output format

```
PR #42: <title>
Base: <base> ← Head: <head> (<sha>)
Files: <N>, +<add>/-<del>

=== CI ===
  ✅ check-1
  ❌ check-2 (required)

=== Pack reviewers (teamvault) ===
  hipaa-reference: PASS
  jira-linkage:    BLOCK — no ticket link in title

=== Findings (5) ===
  BLOCKER  sidecar/app.py:142  correctness
    Unhandled None when space lookup misses
    Suggested patch: <unified diff>

  WARN     sidecar/app.py:38   naming
    'do_stuff' is vague; suggest 'render_response_template'
  ...

Action? [1=post / 2=save / 3=skip]
```

## Stage 3 (future)

A `--pipeline` flag will route blocker findings to `/pr-fix` automatically. Not active in Stage 1.

## Permission boundary

Pure read until step 8. Posting PR comments requires explicit confirmation (or `--post` flag). NEVER edits files, NEVER pushes, NEVER opens/closes PRs.
