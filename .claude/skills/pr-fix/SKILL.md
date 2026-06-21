---
name: pr-fix
description: Create a DRAFT fix branch off an open PR's HEAD, apply a specific fix for a finding surfaced by /pr-review, draft commit + PR messages, and open the fix-PR. Use when /pr-review surfaced a blocker with a clear suggested patch and you want a separate audit trail for the fix (rather than modifying the original PR branch). ALWAYS opens DRAFT; NEVER auto-merges.
---

# pr-fix

Apply a single fix from a `/pr-review` finding via a separate draft fix-PR. Keeps the original PR untouched; gives a reviewable diff for the fix in isolation.

## When to use

- `/pr-review` surfaced a BLOCKER finding with a clear suggested patch
- You want a separate audit trail for the fix (not bundled into the original PR's history)
- The fix is non-trivial enough to warrant its own diff

## When NOT to use

- Trivial 1–2 line fixes — just commit to the original PR branch directly
- Findings without a clear suggested patch — make the fix manually instead
- When you don't have permission to push branches to the repo
- For autonomous loop scenarios in Stage 1 (this skill is manual until Stage 3)

## Preconditions

```bash
gh auth status
PR=$1
[ -n "$PR" ] || { echo "usage: /pr-fix <PR_NUMBER>"; exit 1; }
gh pr view "$PR" --json number > /dev/null  # PR must exist

REPO=$(gh repo view --json nameWithOwner -q .nameWithOwner)
PERMS=$(yq ".repos[\"$REPO\"].permissions[]" ~/.pr-pipeline-config.yaml 2>/dev/null)
echo "$PERMS" | grep -q "fix-branch" \
    || { echo "this repo doesn't permit fix-branch creation in ~/.pr-pipeline-config.yaml"; exit 1; }
```

## Flow

### 1. Fetch original PR metadata

```bash
ORIG_HEAD=$(gh pr view "$PR" --json headRefOid -q .headRefOid)
ORIG_BASE=$(gh pr view "$PR" --json baseRefName -q .baseRefName)
ORIG_TITLE=$(gh pr view "$PR" --json title -q .title)
```

### 2. Create the fix branch

Increment seq based on existing `fix-pr-<N>-*` branches:

```bash
SEQ=$(git branch -a | grep -c "fix-pr-${PR}-" || echo 0)
SEQ=$((SEQ + 1))
FIX_BRANCH="fix-pr-${PR}-${SEQ}"

git fetch origin "pull/${PR}/head:${FIX_BRANCH}"
git checkout "$FIX_BRANCH"
```

### 3. Apply the patch

The finding from `/pr-review` provides:
- `file` — target file
- `line` — approximate location
- `suggested_patch` — unified diff snippet

Apply via Edit tools (NOT a raw `patch` command — verify the change reads correctly in context). Read the file, make the targeted edit, save.

### 4. Lint locally (project-dependent)

If the project has a known lint command (`make lint`, `npm run lint`, `ruff check`, etc.), run it on the changed file. If lint fails: STOP and surface the failure. Don't push a fix that breaks lint.

### 5. Commit

```bash
git add -- "<changed-file>"
git commit -m "$(cat <<EOF
fix: <one-line-summary-of-finding>

Addresses #${PR} — <finding-rule>

<finding-explanation>
EOF
)"
```

### 6. Push the fix branch

```bash
git push -u origin "$FIX_BRANCH"
```

### 7. Open the DRAFT fix PR

```bash
PR_BODY=$(cat <<EOF
## Summary
- Fixes finding from #${PR}: <finding-rule>

## Original review excerpt
> <finding-explanation>

## Test plan
- [ ] CI passes on this fix branch
- [ ] After merge, re-run /pr-review on #${PR} to confirm finding cleared

## Linked PR
#${PR}
EOF
)

gh pr create \
    --draft \
    --base "$ORIG_BASE" \
    --head "$FIX_BRANCH" \
    --title "Fix #${PR}: <summary>" \
    --body "$PR_BODY"
```

### 8. (Optional) TeamVault — publish fix pattern

If TeamVault-bound, publish the pattern so future reviews surface it:

```
vault_publish(
    slug="fix-pattern-<short-rule-slug>-$(date +%Y-%m-%d)",
    content="When we encounter <pattern>, the fix is <approach>. See PR #${PR} (fixed in #${FIX_PR}).",
    tags=["fix-pattern", "<finding-rule>"]
)
```

### 9. Confirm

Show user:
- Fix-PR URL (draft)
- Original PR URL
- Suggested next: review the fix-PR diff before un-drafting

## Stage 3 (future)

A `--pipeline` flag will, after the fix-PR's CI completes, automatically invoke `/pr-review` against the ORIGINAL PR to confirm the finding cleared. Not active in Stage 1.

## Permission boundary

ALWAYS opens as DRAFT. NEVER non-draft (override requires manually editing the gh command). NEVER auto-merges — that's a human's call. NEVER force-pushes. NEVER pushes to the original PR's branch (only to its own `fix-pr-*` branch).
