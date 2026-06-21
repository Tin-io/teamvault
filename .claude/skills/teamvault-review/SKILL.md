---
name: teamvault-review
description: Run the TeamVault pack-runtime check on a LOCAL diff (working directory, branch, or any git range). Loads all enabled packs from the bound space, fans out their reviewer contributions, and produces a verdict (pass | block) with per-reviewer details. Use REPEATEDLY during development — before commits, before opening a PR, after pulling — to verify pack scrubbers + reviewers pass. Fast, deterministic, regex-based. For reviewing an ALREADY-OPENED PR by number with general code-quality checks + CI status, use /pr-review instead.
---

# TeamVault Review

Run the pack-extensible review runtime on a unified diff. Each enabled pack's reviewer agents are loaded, run, and their verdicts synthesized into a single PASS or BLOCK outcome.

## When to use

- User says "run a TeamVault review" / "check this diff"
- Before opening a PR in a bound project repo
- When debugging why a GHA PR check failed

## When NOT to use

- For non-pack-runtime reviews (e.g., generic code style — use your normal review behavior)
- On untracked working-directory changes that aren't ready for review

## Flow

### 1. Capture the diff

The user is in a project repo. Get the unified diff for the changes being reviewed:

```bash
git diff origin/<base>...HEAD
```

(Default base: `main` or `staging` per repo convention. Ask if unclear.)

### 2. Send to the sidecar

```
POST http://localhost:${TEAMVAULT_PORT:-8100}/review
{
  "space": "<space>",
  "diff": "<unified diff>"
}
```

### 3. Render the verdict

The response has:

```json
{
  "overall": "pass" | "block",
  "individual": [
    {"pack": "...", "agent": "...", "mode": "advisory|blocking", "pass_or_fail": "pass|fail", "message": "..."}
  ]
}
```

Format for the user as a markdown table or grouped list. Highlight `block` outcomes prominently.

### 4. Explain failures

If `overall: block`:
- Name the specific reviewer(s) that failed
- Show the message (often includes the matched pattern names)
- Suggest concrete next actions (redact PHI, link a ticket, etc.)

Advisory failures should be surfaced but not block. Note them and the rationale.

### 5. (Optional) Smoke-publish the verdict

If the user wants to save the verdict to the KB for audit trail:

```
vault_publish(
  slug="review-verdict-<short-sha>",
  content="<rendered verdict>",
  tags=["review", "pack-runtime"]
)
```

(This pattern is useful for compliance-flagged spaces where every review verdict should be auditable.)

## Pack-runtime behavior

- Discovery: `${SPACE_ROOT}/packs/*/PACK.yaml`
- Enabled set: `space.yaml::enabled_packs`
- Snapshot consistency: packs loaded once at invocation start, frozen for the call
- v0.0: reviewers are regex passes over added diff lines (cheap, fast)
- v0.1: reviewers will be spawned as real LLM agents per pack (more accurate)

See `docs/CONTRACTS.md` for the formal pack runtime contract.
