---
name: pr-pipeline
description: Stage 3 conductor for the PR review pipeline — orchestrates /pr-review → /pr-fix → /pr-review loop with iter cap, state file, and per-repo permission profile. Usually invoked by a detached background process (`gh pr checks --watch && claude --print '/pr-pipeline <N>'`). NEVER auto-merges. Stage 3 sketch — expected to be rewritten after Stage 1 + 2 manual usage reveals what the conductor actually needs.
---

# pr-pipeline

The conductor that turns the manual `/pr-push → /pr-review → /pr-fix` chain into a loop that runs unattended until the PR is clean or hits the iteration cap.

> **Stage 3 sketch.** Written as a canonical seed before Stage 1 + 2 manual usage of the underlying skills. Expect rewrites once we have evidence of what the conductor actually needs to do. Don't follow this skill literally without confirming the underlying skills have stabilized.

## When to use

- Invoked by a detached background process after `gh pr checks --watch` completes (Stage 3 wiring)
- Manually re-invoked on a PR mid-pipeline to resume after interruption

## When NOT to use

- Stage 1 — the underlying skills haven't been validated manually yet. Use `/pr-review` and `/pr-fix` directly.
- For repos whose permission profile in `~/.pr-pipeline-config.yaml` doesn't grant `fix-branch` + `draft-pr`
- For autonomous merge scenarios (this skill NEVER merges; it stops at clean state for human review)

## Configuration

`~/.pr-pipeline-config.yaml`:
```yaml
repos:
  org/repo:
    permissions: [read, comment, fix-branch, draft-pr]
    push_default: draft   # or non-draft
max_iterations: 5
per_pr_token_budget: 100000
```

`~/.pr-pipeline-state.json`:
```json
{
  "org/repo:42": {
    "iter": 2,
    "status": "active",
    "last_sha": "abc...",
    "last_check": "2026-06-21T18:00:00Z"
  }
}
```

## Flow

### 1. Resolve target + load state

```bash
PR=$1
REPO=$(gh repo view --json nameWithOwner -q .nameWithOwner)
STATE=$(jq ".\"${REPO}:${PR}\" // {}" ~/.pr-pipeline-state.json)
ITER=$(echo "$STATE" | jq -r '.iter // 0')
```

### 2. Check iter cap

```bash
MAX_ITER=$(yq .max_iterations ~/.pr-pipeline-config.yaml)
if [ "$ITER" -ge "$MAX_ITER" ]; then
    # mark state as 'aborted', log, exit
    exit 0
fi
```

### 3. Check repo permissions

```bash
PERMS=$(yq ".repos[\"$REPO\"].permissions[]" ~/.pr-pipeline-config.yaml)
echo "$PERMS" | grep -q "fix-branch" || { echo "permission denied"; exit 1; }
```

### 4. Invoke /pr-review behavior inline

Skills don't cleanly call other skills — this skill INLINES the `/pr-review` flow (Claude reads `/pr-review`'s SKILL.md and executes its steps). Findings come back as a structured list.

### 5. Termination check

If no BLOCKER findings AND all required CI green: mark state `clean`, exit. Notify the user (log to `~/Library/Logs/pr-pipeline.log`).

### 6. Otherwise: invoke /pr-fix on the highest-priority finding

Inline `/pr-fix`'s flow on the top blocker. Opens a draft fix-PR. Capture the new PR number.

### 7. Spawn next-iteration watcher

```bash
NEW_FIX_PR=<from step 6>
nohup bash -c "
    timeout 30m gh pr checks $NEW_FIX_PR --watch && \
    cd $(pwd) && \
    claude --print --prompt '/pr-pipeline $PR'
" >> ~/Library/Logs/pr-pipeline.log 2>&1 &
```

Watch the FIX PR's CI (to ensure the fix doesn't itself break), then re-invoke `/pr-pipeline` against the ORIGINAL PR for the next iteration. `timeout 30m` prevents indefinite hangs on stuck CI.

### 8. Update state

```bash
jq ".\"${REPO}:${PR}\" = {iter: $((ITER + 1)), status: \"active\", last_sha: \"$NEW_HEAD\", last_check: \"$(date -Iseconds)\"}" \
    ~/.pr-pipeline-state.json > ~/.pr-pipeline-state.json.tmp \
    && mv ~/.pr-pipeline-state.json.tmp ~/.pr-pipeline-state.json
```

## Permission boundary

NEVER auto-merges fix PRs. NEVER auto-merges the original PR. NEVER pushes outside the `fix-pr-*` branch pattern. NEVER bypasses the iter cap.

## What this skill explicitly does NOT decide

- Whether the original PR's fixes are correct enough to merge — that's a human reviewing the fix-PR
- Whether to run additional reviewers — that's the underlying `/pr-review` skill
- How to format findings — that's `/pr-review`'s contract
- How to construct fix patches — that's `/pr-fix`'s contract

This skill is ONLY: state management + iter capping + permission gating + chain triggering.
