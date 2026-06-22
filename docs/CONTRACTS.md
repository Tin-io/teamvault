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
    {"name": "<space>", "last_pull": "<iso8601 | null>", "last_error": "<str | null>", "last_indexed": "<iso8601 | null>"}
  ],
  "recent_errors": {
    "<space>": [{"ts": "<iso8601>", "level": "warning|error", "message": "<str>", "logger": "<str>"}],
    "__sidecar__": [{"ts": "...", "level": "warning", "message": "git_sync failed to start: ..."}]
  }
}
```

`recent_errors` (added in P1.4) is an in-memory tail of the last 5 WARNING+ records per space. Unscoped records (emitted before a space is registered, e.g. startup errors) bucket under `__sidecar__`.

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
contributions:
  agents:
    - path: <relative path to .md file>
  scrubbers:
    - type: regex
      file: <relative path to .yaml file>
  reviewers:
    - agent: <basename of agents[*].path without .md>
      mode: advisory | blocking
```

v0.1+ extensions to the contract (per [ROADMAP.md::P2.4](ROADMAP.md)): `ordering`, `mode: veto`, `on_error: fail | skip | warn`, `depends_on`, `mutually_exclusive_with`, `timeout_s`, per-reviewer `token_budget`.

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

## Runtime env vars

| Var | Default | Purpose |
|---|---|---|
| `TEAMVAULT_HOME` | `~/.teamvault/` | Root for sidecar runtime state. Override during dev/test. |
| `TEAMVAULT_PORT` | `8100` | Sidecar HTTP port. |
| `TEAMVAULT_SPACE_ROOT` | `~/teamvault-<space>/` | Path to the space clone the sidecar watches. |
| `TEAMVAULT_DRY_RUN` | unset | If set, skip git push (commit only). Use for tests. |

---

*For the conceptual model see [ARCHITECTURE.md](ARCHITECTURE.md). For the deferral list see [ROADMAP.md](ROADMAP.md). For user-facing install/usage see [USER_GUIDE.md](USER_GUIDE.md).*
