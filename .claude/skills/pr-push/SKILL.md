---
name: pr-push
description: Push the current branch and open a structured PR (Summary, Test plan). Use when the user says "push a PR", "open a pull request", "create a PR for this branch", or has finished work on a feature branch ready for review. Manual invocation = explicit authorization to push and open. For pre-PR pack checks, run /teamvault-review first. For post-creation review of the opened PR, use /pr-review.
---

# pr-push

Open a pull request from the current branch with a consistent body template. Manual; user-invoked; one PR per invocation.

## When to use

- User says "push a PR" / "open a pull request" / "PR this branch"
- A feature branch is ready for review
- The user has finished a unit of work and wants to share it

## When NOT to use

- For draft commits not yet ready for review (commit normally first)
- When the user hasn't committed their work to a branch yet
- For pushing additional commits to a branch already open in a PR — just `git push` instead

## Preconditions

```bash
gh auth status                          # must be authed
git rev-parse --git-dir > /dev/null     # must be in a git repo
CURRENT=$(git branch --show-current)
[ -n "$CURRENT" ] || { echo "detached HEAD"; exit 1; }
git diff --quiet || echo "WARN: working tree dirty — commit or stash first"
```

## Flow

### 1. Resolve the base branch

Per Merkos org convention (from global CLAUDE.md): `staging` for `merkos-302/*` repos, default branch otherwise.

```bash
REMOTE_URL=$(git remote get-url origin)
if echo "$REMOTE_URL" | grep -q "merkos-302/"; then
    BASE=staging
else
    BASE=$(gh repo view --json defaultBranchRef -q .defaultBranchRef.name)
fi
```

Confirm with the user if the repo's convention is ambiguous.

### 1a. Refuse if you're on a protected/base branch

A PR needs a feature branch to come from. STOP if the user is sitting on
any of: the resolved base, the repo's default branch, or any commonly
protected name. Tell them to create a feature branch first.

```bash
PROTECTED=("$BASE" main master staging production develop release)
for P in "${PROTECTED[@]}"; do
    if [ "$CURRENT" = "$P" ]; then
        echo "ERROR: refusing to PR from protected branch '$CURRENT'."
        echo "Create a feature branch first:"
        echo "  git checkout -b feat/<short-description>"
        echo "Then commit your changes there and re-run /pr-push."
        exit 1
    fi
done

if [ "$CURRENT" = "$BASE" ]; then
    echo "ERROR: current ($CURRENT) equals base ($BASE); nothing to PR."
    exit 1
fi
```

If the protected check passes, proceed.

### 2. Push the branch

```bash
git push -u origin "$CURRENT"
```

If push fails (e.g., remote ahead), surface the error and stop. NEVER force-push without explicit user permission.

### 3. Gather PR content

From the conversation context, derive:
- **Title** — short, descriptive, ≤72 chars
- **Summary bullets** — 1–3 bullets, what changed and why
- **Test plan steps** — concrete verification actions

If anything is unclear, ask the user once before proceeding.

### 4. Render the PR body

```markdown
## Summary
- <bullet 1>
- <bullet 2>

## Test plan
- [ ] <step>
- [ ] <step>
```

The first Summary bullet doubles as the TLDR; no separate TLDR header needed.

### 5. Choose draft vs non-draft

Read per-repo config:

```bash
REPO=$(gh repo view --json nameWithOwner -q .nameWithOwner)
PUSH_DEFAULT=$(yq ".repos[\"$REPO\"].push_default // \"draft\"" ~/.pr-pipeline-config.yaml 2>/dev/null || echo draft)
```

Unknown repos default to `draft`. CLI flag `--ready` overrides to non-draft; `--draft` forces draft regardless of config.

### 6. (Optional) TeamVault pre-flight pack check

If the repo is bound to TeamVault (sidecar `/healthz` responds OK and the repo's remote is in some space's `repos.yaml`):

```bash
DIFF=$(git diff "origin/$BASE...HEAD")
curl -s -X POST "http://localhost:${TEAMVAULT_PORT:-8100}/review" \
    -H 'Content-Type: application/json' \
    -d "$(jq -n --arg space "$SPACE" --arg diff "$DIFF" '{space: $space, diff: $diff}')"
```

If any pack reviewer returns `BLOCK`, surface the failures and STOP. Do not open the PR until the user has addressed them or explicitly overridden.

### 7. Open the PR

```bash
DRAFT_FLAG=""
[ "$PUSH_DEFAULT" = "draft" ] && DRAFT_FLAG="--draft"

gh pr create $DRAFT_FLAG \
    --base "$BASE" \
    --head "$CURRENT" \
    --title "$TITLE" \
    --body-file <(echo "$PR_BODY")
```

Capture the returned PR number.

### 8. (Optional) TeamVault publish — log the in-flight PR

If TeamVault-bound, publish a lightweight KB entry so the team can search for in-flight work:

```
vault_publish(
    slug="pr-opened-$(date +%Y-%m-%d)-${PR_NUMBER}",
    content="PR #${PR_NUMBER}: ${TITLE}\n\n${PR_BODY}",
    tags=["pr", "in-flight"]
)
```

### 9. Confirm to user

Show:
- PR URL
- Whether opened as draft or ready
- Suggested next: `/pr-review ${PR_NUMBER}` after CI completes

## Stage 3 (future — not yet wired)

A `--pipeline` flag will spawn a detached background CI watcher that invokes `/pr-review --pipeline` when CI completes. Not active in Stage 1.

## Permission boundary

This skill pushes branches and creates PRs. Invoking it manually IS your explicit approval for that invocation. The skill NEVER force-pushes, NEVER pushes directly to a base branch, and NEVER opens PRs without user-confirmed title + body content.
