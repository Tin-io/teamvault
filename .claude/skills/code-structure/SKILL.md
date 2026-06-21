---
name: code-structure
description: TeamVault-specific architectural reference — where new endpoints / MCP tools / audit actions / pack reviewers / KB entries belong, which existing utilities to reuse, when to extract a helper vs inline. Auto-loads when discussing where new code goes in the teamvault codebase, when reviewing diffs against architectural conventions, or when deciding whether to extract shared logic. Reference-only — no tools, no state changes.
---

# code-structure

Architectural conventions for the TeamVault codebase. Use as a checklist when adding new code OR reviewing a diff that adds new code.

> **Reference skill — example.** Pure markdown guidance, auto-loaded when the description matches. Other projects should write their OWN `code-structure` tailored to THEIR conventions; this one is teamvault-specific and ships as an example of the pattern.

## Where new code goes — by layer

| Adding... | Where | Notes |
|---|---|---|
| HTTP endpoint | `sidecar/app.py` | Pydantic request + response models. `/cite` is a good template — small, audited, has both HTTP + MCP shape. |
| MCP tool | `sidecar/mcp_server.py` | Name `vault_<noun>`. Mirror the HTTP shape — same request fields, same response. |
| Audit action | `sidecar/audit.py` | Add to the `Action` Literal BEFORE first use site. Write entries via `append_audit_entry`. |
| Pack reviewer | `packs/<name>/agents/<name>-reviewer.md` | Update `PACK.yaml::contributions.reviewers`. The .md file IS the agent prompt. |
| Pack scrubber | `packs/<name>/scrubbers/<name>-scrubber.md` | Same shape as reviewers. Runs at publish-time on entry content. |
| KB entry | `kb/entries/YYYY-MM-DD-<slug>-<short-suffix>.md` | Frontmatter holds metadata. See `kb/entries/2026-06-16-meta-how-to-write-a-kb-entry.md` for the canonical template. |
| Sidecar script | `sidecar/scripts/<name>.py` | Must be importable via `python -m sidecar.scripts.<name>`. Add docstring + CLI entry point. |
| Skill | `.claude/skills/<name>/SKILL.md` | Frontmatter `name:` + `description:` required. See existing skills for body conventions. |

## Existing utilities — use these, don't reinvent

Before writing a helper, check whether one of these already does what you need:

- **Audit log** — `sidecar.audit.append_audit_entry(action, **fields)`. Chain-hashed, tamper-evident. Required for any action that should be auditable.
- **Pack runtime fan-out** — `pack_runtime.fan_out_review(diff)` and `fan_out_scrub(content)`. Runs all enabled pack reviewers/scrubbers, returns aggregated verdict.
- **Space resolution** — `sidecar.app._resolve_space_root(space_name)`. Turns a space name into its on-disk path.
- **Git sync** — `sidecar.git_sync`. Handles pull/push for space repos. Don't shell out to `git` from new sidecar code.
- **Ingest pipeline** — `sidecar.ingest`. Markdown → chunks → BM25 + vector indices. Triggered on git sync.
- **Search** — `sidecar.search.search(query, k, space)`. Hybrid retrieval with RRF fusion. Don't add a second search path.

## When to extract a helper

Three signals — ALL must be present:

1. **Used in 2+ places, both already needing it** (not "I might use this elsewhere later")
2. **Does ONE thing with a clear name** (if you can't name it in 3 words, the abstraction isn't right)
3. **Callers are conceptually the same** (not "they happen to look similar but mean different things")

## When NOT to extract a helper

- Single caller
- "I might use this later" (YAGNI)
- Callers do conceptually different things even if the code looks similar
- The helper would obscure what the caller is doing

Three similar lines IS better than a premature abstraction.

## Patterns for new packs

Copy `packs/hipaa-reference/` as the template — it has the most complete shape:
- `PACK.yaml` with full frontmatter (`name`, `version`, `description`, `contributions`, `knowledge_topics`)
- Reviewer agent (`agents/hipaa-reviewer.md`)
- Scrubber agent (`scrubbers/hipaa-scrubber.md`)

If your pack only contributes reviewers (no scrubbers), copy `packs/clickup-linkage/` or `packs/jira-linkage/` — those are simpler.

## Patterns for new sidecar endpoints

1. Define Pydantic `<Action>Request` + `<Action>Response` models
2. Implement the endpoint with `@app.post("/path", response_model=<Action>Response)`
3. Call `append_audit_entry` if the action is auditable
4. Add a parallel MCP tool in `sidecar/mcp_server.py` named `vault_<noun>` with the same shape
5. Document in `docs/CONTRACTS.md`
6. Smoke-test inline with FastAPI `TestClient` in a `.build/test_*.py` script

## Patterns for new KB entries

Lead with the conclusion. Use frontmatter for metadata, not the body. Keep entries scoped to one decision/finding/pattern — split if you're tempted to use multiple H2s for unrelated topics. See the meta-template entry.

## Anti-patterns to flag in reviews

- Direct shell-out to `git` from new sidecar code (use `git_sync` instead)
- New search path that bypasses `sidecar.search` (breaks hybrid retrieval semantics)
- Audit actions written outside `append_audit_entry` (breaks the chain)
- Pack contributions referenced in unfrozen state (must snapshot at invocation start — see `pack_runtime`)
- Skills that mutate state without an explicit `## Permission boundary` section in the SKILL body
