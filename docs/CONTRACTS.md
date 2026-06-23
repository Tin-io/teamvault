# 📐 TeamVault — Reference: API + MCP + Pack contract + env vars

> ✨ **Reference document.** Exact HTTP/MCP/pack contracts and runtime env vars. For the conceptual model and how the pieces fit together, see [ARCHITECTURE.md](ARCHITECTURE.md). For deferred items see [ROADMAP.md](ROADMAP.md).

<p align="center">
  <img src="https://img.shields.io/badge/scope-reference-555?style=flat-square" alt="Scope: reference">
  <img src="https://img.shields.io/badge/audience-integrators%20%2B%20pack%20authors-7c3aed?style=flat-square" alt="Audience: integrators + pack authors">
</p>

---

## Sidecar HTTP API (`sidecar/app.py`)

Base URL: `http://localhost:${TEAMVAULT_PORT:-8100}`.

### `GET /healthz`

Liveness probe — always returns 200 if the app process is up.

```json
{
  "status": "ok",
  "version": "0.0.1",
  "config": {"home": "...", "port": 8100, "space_root": "...", "dry_run": false},
  "spaces": [
    {"name": "<space>", "last_pull": "<iso8601 | null>", "last_error": "<str | null>", "last_indexed": "<iso8601 | null>", "halted_reason": "<str | null>"}
  ],
  "recent_errors": {
    "<space>": [{"ts": "<iso8601>", "level": "warning|error", "message": "<str>", "logger": "<str>"}],
    "__sidecar__": [{"ts": "...", "level": "warning", "message": "git_sync failed to start: ..."}]
  }
}
```

`recent_errors` (added in P1.4) is an in-memory tail of the last 5 WARNING+ records per space. Unscoped records (emitted before a space is registered, e.g. startup errors) bucket under `__sidecar__`.

`last_pull` (added in P1.1) is the ISO timestamp of the last *successful* `git_sync` cycle for the space — includes the no-op same-SHA case, not just cycles that actually pulled new commits. Null until the first successful cycle completes (≤ one `git_sync` interval after sidecar start).

`halted_reason` (added in P1.1) is non-null when `git_sync` has halted on a state requiring human acknowledgement: upstream history rewrote (force-push) or local working tree dirty. The loop short-circuits subsequent cycles until cleared via `POST /confirm-rewind`. `last_error` mirrors `halted_reason` while halted.

The `compliance` field (P0.7) reports the machine-wide egress posture. Under `strict` the listed invariants apply to every space the sidecar serves, not just the compliance space — see "Compliance posture" below for the full contract.

```json
"compliance": {
  "posture": "strict | permissive",
  "local_embedding_only": true,
  "remote_inference_blocked": true,
  "cross_space_scrubbers": true,
  "strictest_regime_search_scrubbing": true,
  "compliance_true_spaces": ["<space>"]
}
```

### `GET /readyz`

Readiness probe distinct from `/healthz`. Returns 200 only when at least one space is registered AND has completed a reindex (`last_indexed` non-null) AND has no recorded `last_error`. Returns 503 with a structured `reason` otherwise. K8s liveness-vs-readiness pattern.

```json
// 200 ready
{"ready": true, "spaces": [{"name": "<space>", "last_pull": "...", "last_error": null, "last_indexed": "<iso8601>"}]}

// 503 not-ready — three possible reasons:
{"detail": {"ready": false, "reason": "no space registered"}}
{"detail": {"ready": false, "reason": "space(s) not yet indexed", "spaces": ["<space>"]}}
{"detail": {"ready": false, "reason": "space in error state", "errors": {"<space>": "<msg>"}}}
```

### `POST /search`

- **Request:** `{"query": "<str>", "top_k": 10, "space": "<str | null>"}`
- **Response:** `{"results": [{"path": "<rel-path>", "chunk": "<text>", "score": <float>, "metadata": {...}}]}`

### `POST /publish`

- **Request:** `{"space": "<str>", "slug": "<str>", "content": "<markdown>", "frontmatter": {...}}`
- **Response:** `{"path": "<rel-path>", "committed": <bool>, "pushed": <bool>, "error": "<str | null>"}`

### `POST /reindex`

- **Request:** `{"space": "<str>"}`
- **Response:** `{"indexed": <int>, "skipped": <int>, "errors": <int>}`

### `POST /review`

- **Request:** `{"space": "<str>", "diff": "<unified diff>"}`
- **Response:** `{"overall": "pass | block", "individual": [{"pack": "<str>", "agent": "<str>", "mode": "<str>", "pass_or_fail": "<str>", "message": "<str>"}]}`

### `POST /confirm-rewind`

Clear the `git_sync` halt flag for a space so the loop resumes. Invoked by the `/teamvault-confirm-rewind` skill after the user has resolved the underlying issue (committed/stashed local changes, or accepted the upstream rewrite).

- **Request:** `{"space": "<str>"}`
- **Response:** `{"cleared": <bool>, "space": "<str>"}` — `cleared` is true iff a halt flag was actually cleared (false = nothing was halted; idempotent no-op). Also zeros the `halted_reason` and `last_error` fields on the SpaceState so `/healthz` reflects the resume immediately without waiting for the next sync tick.

---

## MCP server (`sidecar/mcp_server.py`)

Tools exposed to any MCP host (each is an HTTP wrapper around the sidecar):

- `vault_search(query: str, top_k: int = 10, space: str | None = None, purpose: str | None = None) -> dict` — returns `{query_id, results: [...]}`; `query_id` threads through to a follow-up `vault_cite`
- `vault_publish(slug: str, content: str, tags: list[str] = []) -> dict`
- `vault_status() -> dict`
- `vault_packs(space: str | None = None) -> dict` — enabled packs + their `knowledge_topics` + per-pack `mode_summary` (`advisory` / `blocking` / `none`)
- `vault_cite(space: str, query_id: str, paths_used: list[str], note: str | None = None) -> dict` — record which KB entries informed (or didn't inform) a decision after a `vault_search`; closes the search → decision audit loop
- `vault_query_log(space: str | None = None, since: str | None = None, until: str | None = None, action: str | None = None, limit: int = 50) -> dict` — read filtered audit-log rows + `chain_ok` (audit hash-chain verification)

---

## Pack runtime contract (`sidecar/pack_runtime.py`)

### `PACK.yaml` schema

```yaml
name: <kebab-case>
version: <semver>
description: <one-line>
knowledge_topics: [<kebab-case>]   # optional; v0.1+ — domains the team has accumulated KB on
contributions:
  agents:
    - path: <relative path to .md file>
  scrubbers:
    - type: regex
      file: <relative path to .yaml file>
  reviewers:
    - agent: <basename of agents[*].path without .md>
      mode: advisory | blocking
  skills:                           # v0.2+ — pack-shipped Claude Code skills
    - path: <relative path to skill DIRECTORY containing SKILL.md>
```

**`skills:` field (v0.2+).** Each entry points to a skill directory (e.g., `skills/start-clickup/`) containing a `SKILL.md`. Pack-shipped skills are NOT executed by the sidecar runtime — they're manifested for `/teamvault-setup`'s §7.7 step to copy into `~/.claude/skills/` at install/upgrade time. This lets a pack be a self-contained domain capability bundle: enable one pack → get its scrubbers + reviewers + workflow skills together. The pack runtime drops skill entries with missing dirs / missing SKILL.md with a warning (pack still loads — skills are a manifest, not runtime-load-blocking).

v0.1+ extensions to the contract (per [ROADMAP.md::P2.4](ROADMAP.md)): `ordering`, `mode: veto`, `on_error: fail | skip | warn`, `depends_on`, `mutually_exclusive_with`, `timeout_s`, per-reviewer `token_budget`.

### Failure modes (P0.6)

The pack runtime can fail in several ways. v0.0 enumerates and tests these modes with **required block behavior for `compliance: true` spaces**. The runtime never silently fails open under `compliance: true`.

| Failure                  | When                                                                  | `compliance: true` | `compliance: false` |
|--------------------------|-----------------------------------------------------------------------|--------------------|---------------------|
| `missing_file`           | PACK.yaml references a scrubber YAML that doesn't exist, OR exists but isn't a regular file (e.g., a directory) | BLOCK | ADVISORY |
| `malformed_yaml`         | YAMLError or OSError loading PACK.yaml or a scrubber YAML             | BLOCK              | ADVISORY            |
| `degenerate_pack`        | PACK.yaml parses but has no `name:` field (empty / clobbered / blank) | BLOCK              | ADVISORY            |
| `unresolved_pack`        | `enabled_packs` entry matches no pack directory or PACK.yaml `name:`  | BLOCK              | ADVISORY            |
| `regex_compile`          | a pattern's regex doesn't compile (e.g., `[unclosed`)                 | BLOCK              | ADVISORY            |
| `oversize_input`         | input exceeds 10 MB UTF-8 (proxy for timeout / OOM)                   | BLOCK              | ADVISORY            |
| timeout / OOM (direct)   | Python `re` has no timeout; can't detect at runtime                   | deferred to v0.1 (proxied by oversize cap) | same |

Failures synthesize a verdict with `agent: "scrubber-health"`. On `compliance: true` spaces the synthetic verdict is `mode: blocking` and `overall = "block"`; on `compliance: false` spaces it's `mode: advisory` and `overall` stays `pass` (unless a real scrubber match also fires).

**Identifiers used in synthetic verdicts** (hyphenated to avoid markdown-bold rendering in PR comment tables): `scrubber-health` (agent), `space-yaml` (synthetic pack for space.yaml-level errors), `runtime` (synthetic pack for runtime errors like `oversize_input`).

**Malformed `space.yaml`:** PackRuntime presumes `compliance: true` (safe-mode) when space.yaml itself fails to parse — assuming `compliance: false` would silently downgrade enforcement on what may be a corrupted compliance space. The resulting `space-yaml` LoadError additionally carries `force_blocking=True`, so the verdict blocks regardless of how downstream code interprets the (unreadable) compliance flag.

**Enable-by-name and enable-by-directory both work.** `enabled_packs` entries are resolved against either the pack directory name OR the PACK.yaml `name:` field. An entry that matches neither produces an `unresolved_pack` LoadError — closing the silent-fail-open path where a typo in `enabled_packs` (or a forked pack with a renamed directory) would have disabled the scrubber.

**`fan_out_review` vs. `fan_out_scrub`:**
- `fan_out_review` (commit + PR gate) synthesizes the verdict directly.
- `fan_out_scrub` (used by `/publish` at write time) records `ScrubError`s on `runtime.scrub_errors` rather than synthesizing a verdict. `publish.py` inspects both `runtime.load_errors` and `runtime.scrub_errors` after the scrub call and **refuses publish under `compliance: true`** when either is non-empty. This closes the publish-path PHI leak that the previous "v0.0 silent skip on regex error" behavior allowed.

**Linkage checks** (clickup, jira-linkage) run regardless of oversize input — they're bounded regex against the diff and SOC 2 audit evidence depends on the linkage advisory row appearing in the verdict even when scrubber matching is aborted on oversize.

Tests: `.build/test_pack_runtime_failure_modes.py` covers the matrix.

### Pack discovery & loading

- Discovery glob: `${SPACE_ROOT}/packs/*/PACK.yaml`
- Enabled set: `space.yaml::enabled_packs[]` (list of pack names)
- **Load at invocation start, frozen for the session** (snapshot consistency — verdicts carry `pack_sha` for reproducibility)

### Python API

```python
@dataclass
class ReviewerVerdict:
    pack: str
    agent: str
    mode: Literal["advisory", "blocking"]
    pass_or_fail: Literal["pass", "fail"]
    message: str

@dataclass
class ReviewVerdict:
    overall: Literal["pass", "block"]
    individual: list[ReviewerVerdict]

class PackRuntime:
    def __init__(self, space_path: Path): ...
    def enabled_packs(self) -> list[Pack]: ...
    def fan_out_review(self, diff: str) -> ReviewVerdict: ...
    def fan_out_scrub(self, text: str) -> str: ...    # used by publish
```

---

## Skill SKILL.md format

Standard Claude frontmatter:

```yaml
---
name: <skill-name>
description: <when to invoke>
---
```

Body: markdown describing the flow. Skills call into the sidecar via the HTTP API or via the MCP tools.

---

## `space.yaml` schema

```yaml
name: <kebab-case>
description: <one-liner>
kingdoms: [<name>]          # Light Palace kingdoms (v0.1.x: documentation-only; v0.1.5+ adds soft validation — WARN at publish if entry's `kingdom` isn't here; never blocks)
compliance: <bool>          # if true, auto-deploy of packs is disabled and stricter egress invariants apply
enabled_packs: [<name>]
auto_deploy: <bool>         # default true; forced false when compliance: true
```

## `repos.yaml` schema

```yaml
- remote: <git URL>
  workspace: <variant name | "default">
  kingdom: <name>           # Light Palace kingdom (must match space.yaml::kingdoms)
  palace: <name>            # free-form — product / major system (Palace level 2)
  wing: <name>              # free-form — feature domain within the palace (Palace level 3)
- remote: ...
```

`kingdom/palace/wing` are documentation-only in v0.1.x. v0.1.5+ adds auto-fill: `/teamvault-publish` reads the publishing repo's entry from this file and fills `kingdom/palace/wing` into the new KB entry's frontmatter automatically. Today, set them by hand on each entry. See [docs/KB-FOUNDATIONS.md](KB-FOUNDATIONS.md) for the canonical Mem Palace taxonomy.

## KB entry path convention

```
kb/entries/<kingdom>/<palace>/<wing>/<hall>/<room>/YYYY-MM-DD-<slug>.md
```

Path mirrors the entry's `kingdom/palace/wing/hall/room` frontmatter exactly. Use `_` to skip any level; trailing levels can be omitted (drop `room` if the hall is granular enough). Tool-docs / unbound entries can use `_` for all levels: `kb/entries/_/_/_/_/_/<slug>.md`.

The sidecar's reindex walks `kb/entries/` recursively (`Path.rglob("*.md")`), so any depth works.

---

## Compliance posture (P0.7)

When ANY registered space has `compliance: true`, the sidecar enforces a **strict** egress posture machine-wide, not just within that space:

| Invariant                            | Meaning                                                                  | v0.0 enforcement                                  |
|--------------------------------------|--------------------------------------------------------------------------|---------------------------------------------------|
| `local_embedding_only`               | embedding model runs on-device, never hits a remote API                  | structural — Nomic via `sentence-transformers`    |
| `remote_inference_blocked`           | no LLM calls to external APIs from the sidecar                           | structural — reviewers are regex, no LLM in code  |
| `cross_space_scrubbers`              | search/publish content is run through the UNION of all compliance-true spaces' enabled packs, even when reading from a permissive space | enforced by `compliance.make_scrubber()` closure  |
| `strictest_regime_search_scrubbing`  | search results (`chunk`, `path`, `metadata` string values) are scrubbed by the same union before being returned | enforced in `search.hybrid_search`                |

Surfaced in `/healthz.compliance` at boot.

### Read-path defense — fail-closed semantics

The scrubbing pipeline is **fail-closed**: if the union scrubber cannot complete a scrub (broken regex, oversize input, pack runtime can't load), the affected field returns the sentinel `[SCRUB_UNAVAILABLE]` rather than unscrubbed text. A consumer seeing this in a search result knows the underlying content could not be safely scrubbed and should treat the field as redacted.

For metadata `bytes` values, the sentinel is `b"[REDACTED-BINARY]"` when the bytes can't be UTF-8 decoded (regex engines need text; opaque binary content is treated as a leak vector under strict posture).

### Per-query scrubber closure

`compliance.make_scrubber()` returns a **closure with a snapshot** of every compliance-true space's PackRuntime, loaded ONCE. The closure is called many times per query (per chunk, per metadata string) without re-instantiating PackRuntime. This avoids the 100+ PackRuntime-per-search self-DoS the naive per-call design would have caused, and closes the TOCTOU race where space.yaml could change mid-query.

### v0.0 single-space deployment — what's actually defended

The sidecar registers ONE space (via `TEAMVAULT_SPACE_ROOT`). The cross-space / strictest-regime semantics still kick in the moment that one space has `compliance: true` — the posture flips to `strict` and search-result scrubbing engages.

**Under v0.0 single-space with a broken pack in the compliance space:** the read-path defense disables (the union has no working members). Search/publish return `[SCRUB_UNAVAILABLE]` instead of unscrubbed content. The remaining defense layer is the **commit / PR gate** (`pack_runtime.fan_out_review` via P0.6) which still BLOCKS commit + publish under the same conditions. v0.1 adds true multi-space so the union has fallback members.

**Out of scope for v0.0:** multi-process binding (a space bound after sidecar boot is invisible until restart); `/healthz` posture caching (every probe re-reads space.yaml). Both tracked as v0.1 hardening.

### Malformed `space.yaml`

`_read_compliance` returns `True` (presume-strict / safe-mode) on YAML parse error — matches `PackRuntime._read_compliance` so the commit-gate and the read-path posture stay consistent under a broken config. Returning `False` would create a window where /healthz reports `permissive` (no scrubbing) while pack_runtime would block writes — easy to land in by accident with a half-saved space.yaml.

Tests: `.build/test_compliance_egress.py`.

## Runtime env vars

| Var | Default | Purpose |
|---|---|---|
| `TEAMVAULT_HOME` | `~/.teamvault/` | Root for sidecar runtime state. Override during dev/test. |
| `TEAMVAULT_PORT` | `8100` | Sidecar HTTP port. |
| `TEAMVAULT_SPACE_ROOT` | `~/teamvault-<space>/` | Path to the space clone the sidecar watches. |
| `TEAMVAULT_DRY_RUN` | unset | If set, skip git push (commit only). Use for tests. |
| `TEAMVAULT_GIT_TIMEOUT_S` | `30` | Hard timeout (seconds) for `git fetch` / `git pull` in the `git_sync` loop. |

---

*For the conceptual model see [ARCHITECTURE.md](ARCHITECTURE.md). For the deferral list see [ROADMAP.md](ROADMAP.md). For user-facing install/usage see [USER_GUIDE.md](USER_GUIDE.md).*
