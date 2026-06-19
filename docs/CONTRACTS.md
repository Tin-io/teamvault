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

```json
{
  "status": "ok",
  "version": "0.0.1",
  "spaces": [
    {"name": "<space>", "last_pull": "<iso8601 | null>", "last_error": "<str | null>"}
  ]
}
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

- `vault_search(query: str, top_k: int = 10) -> list[dict]`
- `vault_publish(slug: str, content: str, tags: list[str] = []) -> dict`
- `vault_status() -> dict`

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
compliance: <bool>          # if true, auto-deploy of packs is disabled and stricter egress invariants apply
enabled_packs: [<name>]
auto_deploy: <bool>         # default true; forced false when compliance: true
```

## `repos.yaml` schema

```yaml
- remote: <git URL>
  workspace: <variant name | "default">
- remote: ...
```

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
