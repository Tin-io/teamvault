# 🏗️ TeamVault — Architecture

> ✨ **The canonical architecture document.** What TeamVault is, how it's shaped, what each piece does, and what's load-bearing vs. extensible. For exact HTTP/MCP/pack contracts see [CONTRACTS.md](CONTRACTS.md); for the universal KB pattern catalog see [KB-FOUNDATIONS.md](KB-FOUNDATIONS.md); for the deferral list see [ROADMAP.md](ROADMAP.md); for the product vision and strategy see [STRATEGY.md](STRATEGY.md).

<p align="center">
  <img src="https://img.shields.io/badge/scope-architecture-7c3aed?style=flat-square" alt="Scope: architecture">
  <img src="https://img.shields.io/badge/audience-implementers%20%2B%20pack%20authors-555?style=flat-square" alt="Audience: implementers + pack authors">
</p>

---

## 1. What TeamVault is

TeamVault is a **bidirectional knowledge substrate for human ↔ agent collaboration**. It gives a group of developers — a company, a team, two people on a side project, or one person across many of their own repos — a persistent, semantically-searchable knowledge base AND a shared, PR-reviewable place to define the packs, agents, scrubbers, and review skills they use together.

Same git substrate. Two access patterns: **agents query via MCP; humans browse via GitHub.**

Each developer's machine runs a single local sidecar. The sidecar watches one or more cloned **space** repositories, pulls updates every ~60s, and exposes an MCP endpoint any agentic harness can use (Claude Code today; Codex and others through host adapters). Knowledge entries, pack customizations, and shared agents propagate to every member of a space via standard git. Code review is the compliance gate.

TeamVault makes no opinionated distinction between "team" and "personal" use. A space with one member behaves identically to a space with fifty. Tier, governance, and policy come from `space.yaml::compliance`, CODEOWNERS, and workspaces — not from baked-in semantics.

---

## 2. Core concepts

| Term | Meaning |
|------|---------|
| **Master template** | The canonical TeamVault repo (this one). Forked (or used-as-template) to create a new space. Contains sidecar code, reference packs, the setup skill, and a single meta-template KB entry. |
| **Space** | A forked clone of the master template, customized for a particular context. Owns its KB, packs, workspaces, agents, member-repo registry, and (in v0.0) a snapshot of the sidecar binary. Synced via git among its members. |
| **Project repo** | A regular code repository the developer works in. Binds to a space via that space's `repos.yaml` — **not** via any artifact inside the project repo itself. |
| **Workspace** (a.k.a. **variant**) | An optional config variant *inside* a space. Multiple workspaces share the space's KB but can have different pack tunings. Hidden behind a `default` workspace when the space doesn't need variants. The rename to "variant" is roadmapped (P2.6). |
| **Pack** | A pluggable bundle (agents, scrubbers, ingest guards, config schema) that contributes to TeamVault's runtime behavior. Packs are PR-reviewed in the space repo. The `hipaa-reference` pack contributes a PHI scrubber + reviewer; `clickup-linkage` / `jira-linkage` packs check ticket linkage on PRs. |
| **Host adapter** | A small piece of code per agentic harness that translates TeamVault's canonical formats into what that host expects (Claude Code drops agents into `~/.claude/agents/`; Codex would have its own conventions). v0.0 ships only the Claude Code adapter. |
| **Sidecar** | The single long-running process per machine. Watches all installed spaces, indexes their KBs, routes MCP queries by cwd, applies host-adapter changes on pull. |
| **Pack runtime** | The orchestration layer inside the sidecar. Discovers `PACK.yaml` files, loads enabled packs (snapshotted at invocation), fans out reviewers + scrubbers, synthesizes verdicts. |
| **Per-space isolation** | A **routing** simplification, not a security control. Two spaces on the same machine do not share KB or pack state. Egress invariants (e.g., scrubbers on cross-space writes) are enforced separately when any installed space declares `compliance: true`. |

---

## 3. Distribution model

```
┌─ master template (this repo) ──────────────────────────────┐
│  - sidecar/          FastAPI sidecar + MCP shim           │
│  - .claude/skills/   setup, publish, review, status       │
│  - packs/            reference packs                      │
│  - kb/               one meta-template entry              │
│  - repos.yaml        empty; teams fill on bind            │
│  - space.yaml        template metadata                    │
│  - README.md         + LICENSE                            │
└────────────┬───────────────────────────────────────────────┘
             │ "Use this template" or git fork
             ▼
   ┌──────────────────────────────────────────────────────────┐
   │ <your-org>/teamvault-<space>                            │
   │  Each fork is a "space" — fully owned by the team.      │
   └────────────┬─────────────────────────────────────────────┘
                │ each member clones each space they belong to
                ▼
   ┌─ a developer's machine ──────────────────────────────────┐
   │  ~/teamvault-<space>/        (one clone per installed   │
   │  ~/teamvault-<other-space>/  space)                     │
   │                                                          │
   │  ~/.teamvault/                                           │
   │     registry.json   (all installed spaces)               │
   │     <space>/                                             │
   │        vault.lance  (per-space vector index)             │
   │        fts.db       (per-space text index)               │
   │        audit.log    (per-space JSONL audit chain)        │
   │     logs/                                                │
   └──────────────────────────────────────────────────────────┘
```

The master template is the only upstream actively maintained. Teams don't "install TeamVault" via a package manager — they fork the template. The fork is their copy. Upstream improvements (sidecar fixes, new reference packs) reach teams when they choose to merge from upstream. v0.1+ adds `/teamvault-upstream-sync` to mechanize this; v0.2 splits the sidecar to a versioned pip package (ROADMAP P2.2).

---

## 4. Per-machine topology

**One sidecar process per machine**, multi-space-aware.

- Listens on `localhost:8100` (configurable via `TEAMVAULT_PORT`).
- Maintains an in-memory registry of installed spaces, populated from `~/.teamvault/registry.json`.
- For each space: tracks last-pull, last-error, `last_indexed_commit_sha`. Schedules `git fetch && git pull --ff-only` every ~60s, with per-space jitter ± 10s to avoid thundering-herd on shared repos.
- On pull, runs path-dispatched handlers (see §6).
- Pulls are **guarded**: dirty working tree → skip + surface; non-fast-forward → refuse + set `space.last_error` and pause that space until acknowledged via `/teamvault-confirm-rewind` (v0.1).
- Per-space pull errors trigger exponential backoff (60s → 5m → 30m → 1h cap).

### Query routing

When the host (Claude Code) calls an MCP tool on the sidecar, the sidecar:

1. Inspects the calling session's working directory.
2. Runs `git -C <cwd> remote get-url origin` to find the remote URL.
3. Looks up the remote URL across every installed space's `repos.yaml`.
4. Resolves the matching space + workspace.
5. Routes the query (KB search, pack lookups) against that space's data.

If the cwd's remote doesn't match any installed space's registry, the sidecar returns a clear "this repo is not bound to any TeamVault space; run `/teamvault-bind <space>` to bind it" — never guessing.

The `_context` MCP tool (v0.1) exposes the resolved `{active_space, active_variant, resolved_via}` so agents and humans can debug routing.

---

## 5. Space repo layout

```
<space>/
├── README.md                          team-authored; explains what the space is for
├── LICENSE                            inherited or team's choice
├── CODEOWNERS                         path-scoped ownership (see §10)
├── space.yaml                         space metadata (name, compliance, enabled_packs, auto_deploy)
├── repos.yaml                         member project repos, by git remote
│
├── kb/                                THE KNOWLEDGE BASE
│   └── entries/
│       └── YYYY-MM-DD-<slug>.md       markdown + YAML frontmatter
│
├── packs/                             EXTENSIBILITY — PR-reviewed
│   ├── hipaa-reference/               reference pack (fork or replace for production)
│   │   ├── PACK.yaml
│   │   ├── scrubbers/phi_patterns.yaml
│   │   └── agents/hipaa-reviewer.md
│   ├── clickup-linkage/
│   └── jira-linkage/
│
├── workspaces/                        OPTIONAL config variants (most spaces ship only `default`)
│   └── <variant>/config.yaml
│
├── .claude/skills/                    host-adapter artifacts for Claude Code
│   ├── teamvault-setup/SKILL.md
│   ├── teamvault-publish/SKILL.md
│   ├── teamvault-review/SKILL.md
│   └── teamvault-status/SKILL.md
│
├── .github/workflows/
│   └── teamvault-review.yml           PR-stage pack runtime (required check if compliance: true)
│
└── sidecar/                           v0.0: bundled inline · v0.1+: split out to pip package
    ├── app.py, ingest.py, search.py, pack_runtime.py, audit.py, ...
    └── requirements.txt
```

### Key files

**`space.yaml`** — space-level metadata.

```yaml
name: <space-name>
description: <one-liner>
compliance: false           # true → inverts auto_deploy; enforces stricter egress invariants
enabled_packs:
  - hipaa-reference
  - clickup-linkage
auto_deploy: true           # apply pulled pack updates within ~60s; forced false when compliance: true
```

**`repos.yaml`** — which project repos belong to this space, keyed by git remote.

```yaml
- remote: https://github.com/<your-org>/<project-repo>
  workspace: default
- remote: git@github.com:<your-org>/<another-repo>.git
  workspace: prod         # any variant defined under workspaces/
```

Remotes — not absolute paths — so the same `repos.yaml` works regardless of where each dev cloned the project locally.

**`PACK.yaml`** — pack contribution declaration.

```yaml
name: hipaa-reference
version: 0.1.0
description: HIPAA PHI detection reference pack.
contributions:
  agents:
    - path: agents/hipaa-reviewer.md
  scrubbers:
    - type: regex
      file: scrubbers/phi_patterns.yaml
  reviewers:
    - agent: hipaa-reviewer
      mode: blocking            # or advisory; v0.1+ adds veto
```

v0.1+ extensions to the contract — `ordering`, `mode: veto`, `on_error`, `depends_on`, `mutually_exclusive_with`, `timeout_s`, per-reviewer `token_budget` — are roadmapped in ROADMAP P2.4.

---

## 6. Sync semantics

The sidecar's job per pull cycle (default every 60s ± 10s jitter, per space):

1. `git fetch` with a 30s timeout; `GIT_TERMINAL_PROMPT=0` so auth prompts can't hang the loop.
2. Guard checks: dirty working tree → skip + surface; non-fast-forward → refuse + pause that space.
3. `git pull --ff-only`.
4. For each changed path, dispatch handlers:

| Changed path | Handler |
|---|---|
| `kb/**` | Re-embed changed files; update vault index. Deletions remove stale chunks by `(entry_path, content_sha256, chunk_index)`. |
| `packs/**` | Reload pack configs **transactionally** — validate in staging area, swap on success. On parse fail, keep prior valid config + log + surface to `/healthz`. |
| `workspaces/**` | Reload variant mappings. Routing tables updated for affected project repos. |
| `repos.yaml` | Rebuild routing table: cwd → git remote → (space, workspace). |
| `space.yaml` | Update space metadata in registry. Re-evaluate `compliance` and `auto_deploy`. |
| `.claude/skills/**` | Host adapter redeploys skills to `~/.claude/skills/` (namespaced; see §11). |

### Snapshot-on-invocation consistency

A `/teamvault-review` or `/teamvault-publish` invocation **pins pack reads to the commit SHA at invocation start**. Verdicts carry `pack_sha` in their metadata. Mid-invocation pulls cannot change which patterns a verdict ran against — load-bearing for audit reproducibility.

### Content-addressed ingestion

Chunks are identified by `(entry_path, content_sha256, chunk_index)`. This gives:
- **Dedup** — same `content_sha256` → skip re-embed
- **Delete idempotency** — removing an entry deletes its chunks deterministically
- **Force-push survivability** — history rewrites produce different `content_sha256` → next reindex sees stale rows and removes them
- **Frontmatter-only edit skip** — if only frontmatter changes, body-based chunks keep their `content_sha256` and are not re-embedded

### Local-only spaces

A space repo with no configured `origin` remote is treated as local-only. The sidecar still watches the working tree for filesystem changes and re-indexes, but skips the git pull. This makes purely-personal spaces (a private vault never pushed to a remote) first-class without special-casing.

### Branch policy

v0.0 syncs from a fixed default branch (`main`). No branch switching. If a team wants a "staging" variant, they create a separate space repo.

---

## 7. Project repos contain zero TeamVault artifacts

A deliberate inviolable rule.

- No `.claude/teamvault.yaml`, no `.teamvault/`, no marker files inside project repos.
- Binding to a space is declared exclusively in the space repo's `repos.yaml`, keyed by git remote URL.
- The sidecar resolves cwd → git remote → space lookup at query time.

**Why.** The sidecar's sync model is "watch ONE thing (the space repo) and pull every 60s." If config also lived in project repos, a dev might be on a feature branch missing the latest config, or working in a project repo whose default branch hasn't been pulled recently — and the active config would silently differ from intent. Keeping everything in the space repo gives the sidecar exactly one watch point per space, with deterministic semantics.

A consequence: until a project repo's git remote is added to a space's `repos.yaml` (and that change is merged + synced), MCP queries from inside that project repo return "unbound." The fix is `/teamvault-bind <space>` (see §12).

An optional `.teamvault-hint` file at the project root is allowed for discoverability (v0.1+); `repos.yaml` remains canonical.

---

## 8. Workspaces (variants)

Optional **config variants inside a space**. They share the space's KB but can carry different pack tunings.

| Property | Behavior |
|---|---|
| KB | Shared with the rest of the space — workspaces do NOT partition KB. |
| Packs enabled | Can differ per workspace. Most commonly: same packs, different config. |
| Pack config | Workspace config overrides pack-level defaults at the leaf level. |
| Project repo assignment | Each entry in `repos.yaml` declares its workspace; defaults to `default` if omitted. |
| Visibility | Spaces that need only one config ship with a `default` workspace and never mention the concept to users. Workspaces become visible only when the team needs variants. |

**When to use a workspace vs. a separate pack.** Use a workspace override when the *same questions* need *different answers* (e.g., per-environment pattern overrides). Use distinct packs when the *questions themselves* are different (a pack reviewing UX correctness is conceptually unrelated to a pack reviewing data-handling).

---

## 9. Packs and the pack runtime

A pack contributes one or more of: **reviewer agents**, **scrubbers** (called by `/teamvault-publish` before KB writes and by the PR-stage GHA), **ingest guards** (called by the sidecar before files enter the vault), **settings patches**, and a **config schema**.

**Pack-extensibility is the central runtime contract.** Core skills are **runtimes** that discover and invoke pack contributions:

- `/teamvault-review` loads its enabled packs (frozen-at-invocation), runs each pack's reviewers in parallel, and synthesizes a single verdict (`pass | block`). A single `blocking` reviewer failing causes overall `block`; `advisory` reviewers surface findings without blocking. v0.1+ adds `veto` (one reviewer can fail the verdict regardless of others).
- `/teamvault-publish` runs every pack's scrubbers in declared order before committing the new KB entry. A scrubber match refuses the publish.
- **PR-stage GHA workflow (`.github/workflows/teamvault-review.yml`)** fires on every pull request: it runs the same pack runtime against the PR's diff, posts a structured verdict comment, and sets a required-status check that **blocks merge** if any `blocking` pack fails. Hardened against fork-PR shell injection via an `if: head.repo.full_name == github.repository` guard.

Packs themselves contain only declarations and content — they don't ship orchestration logic. The runtimes own the orchestration.

### Per-workspace override

A pack ships base configuration; workspaces override at the leaf level. The pack's agent reads its resolved (base + override) config at invocation time.

### Compliance review on pack changes

Pack content lives in the space repo at `packs/`. CODEOWNERS routes all changes to `packs/**` to the team's compliance reviewers. A new scrubber pattern doesn't ship until the compliance lead approves the PR.

### Fail-closed contract

If a scrubber fails to load (malformed YAML, missing file, regex compile error), `/teamvault-publish` and `/teamvault-review` **block** in `compliance: true` spaces. Non-compliance spaces may fall back to `advisory` with a clear warning. The full failure-mode matrix and required block behaviors are enumerated in [`CONTRACTS.md`](CONTRACTS.md).

### Auto-deploy semantics

By default, the host adapter redeploys pack contributions on every relevant pull. For spaces marked `compliance: true`, the sidecar surfaces "new pack version available — run `/teamvault-apply-pack-update` to apply" and waits for explicit acknowledgement before swapping the live agent. **The compliance flag inverts auto-deploy.**

### Data-egress invariants

When **any installed space** declares `compliance: true`, the sidecar enforces stricter egress for all spaces on that machine:

- Embedding model MUST be local (no remote inference calls).
- Scrubbers MUST run on every cross-space write path.
- Cross-space search results MUST be scrubbed to the most-conservative regime of any participating space.

Documented at boot in `/healthz`.

---

## 10. The KB substrate — markdown, hybrid retrieval, chunking

The knowledge base is **markdown files with YAML frontmatter, git-tracked**. The sidecar maintains derivative indexes that are disposable — wipe `~/.teamvault/<space>/` and the next reindex rebuilds them in minutes.

### Frontmatter schema (v0.0 + planned extensions)

```yaml
---
created: 2026-06-16T10:00:00Z         # required (also drives temporal decay in v0.1)
source: seed                          # provenance: seed | manual | autopublish | template
confidence: 0.9                       # 0.0–1.0 curation signal
author: <name or team>
decision_type: decision               # decision | pattern | postmortem | policy | meta
tags: [<topic>]
# v0.1 planned extensions:
# entry_type:    <controlled vocab>   # generalizes decision_type
# superseded_by: <other-entry.md>     # explicit versioning across entries
# related_entries: [<other.md>]       # explicit graph edges
---
```

### The retrieval pipeline (v0.0)

```
1. CHUNK     paragraph-bounded, 512 tokens, 64 overlap
2. PREFIX    static doc-level context (title + tags + type) prepended pre-embed
3. EMBED     Nomic Embed v1.5 (768d, local)
4. INDEX     LanceDB (vector, HNSW) + SQLite FTS5 (BM25, porter stemmer)
5. QUERY     both indexes in parallel — same query, two paths
6. FUSE      Reciprocal Rank Fusion (RRF, k=60)
7. RE-RANK   temporal decay (v0.1+) — linear 1.0× ≤30d → 0.5× floor at 365d
```

The universal pattern catalog and design principles behind this pipeline are in [KB-FOUNDATIONS.md](KB-FOUNDATIONS.md).

### Embedding model is pinned per space

`vault.lance` carries a header with the embedding model name + version. Cross-space merge or schema migration on model bump is rejected unless explicit. The migration path is roadmapped (P2 — embedding-model upgrade).

### Retrieval observability (v0.1+)

A per-query `retrieval.log.jsonl` records the search input, BM25 + vector top-K, RRF fusion, decay multipliers, and final ranks. `/teamvault-debug-search` replays a query against the log so a maintainer can debug why a specific result ranked where it did.

---

## 11. Host-agnostic design

TeamVault's intent is to support any agentic harness that speaks MCP. v0.0 ships only the Claude Code adapter; v0.2+ adds Codex (ROADMAP P2.3).

### Canonical formats

- **Agents (v0.0):** `packs/<pack>/agents/*.md` — standard markdown with frontmatter. A canonical `*.tv.md` superset was considered and deferred; v0.0 keeps the Claude Code-native format and the v1 abstraction is described in P2.3.
- **Skills (v0.0):** `.claude/skills/*/SKILL.md` (Claude Code format).
- **Settings:** `config/settings/<host>.<format>` — per-host. Each adapter only reads its own file; no cross-host merge.

### Host adapter responsibility

The active host adapter:
- Translates canonical artifacts into the host's expected format.
- Deploys artifacts into the host's directory (Claude Code: `~/.claude/agents/`, `~/.claude/skills/`).
- Applies settings patches to the host's settings file.
- Runs on every sync that touches `packs/`, `.claude/`, or `config/settings/`.

### Agent namespacing on disk

When two spaces both enable a `hipaa-reference` pack, both would try to deploy `hipaa-reviewer.md` into the shared agent directory. Collision is real.

**Adopted convention:** namespace by space name when deploying. The agent in space `<space>` lands at `~/.claude/agents/<space>--hipaa-reviewer.md`. The host-adapter alias generator (v0.1+) makes `@hipaa-reviewer` in `<space>` territory resolve to `<space>--hipaa-reviewer` so the ugly filenames don't reach the user.

---

## 12. Bind flow

Adding a project repo to a space is a state change that affects every dev on the team. It deserves the same PR-review hygiene as any other space change.

`/teamvault-bind <space>` flow (run from inside a project repo):

1. Resolve the project repo's git remote.
2. `cd ~/teamvault-<space>`, checkout a new branch `bind/<repo-slug>`.
3. Edit `repos.yaml` to add the new entry (default workspace `default` unless the dev specifies one).
4. Commit.
5. `gh pr create` with a title like `Bind repo: <slug>` and a summary.
6. Report the PR URL to the dev.

Until the PR merges and the sidecar pulls the change, the project repo is unbound — MCP queries from inside it return the "not bound to any space" message. The sidecar pokes a refresh immediately after the binding dev merges, so they don't wait for the next 60s tick.

**`/teamvault-bind-now` (v0.1+, P2.7):** Local-tentative mode for demo / quick-bind. The sidecar treats the local-but-not-yet-merged binding as valid **on the binding dev's machine only** (marked `pending`) until the PR merges; other devs still see unbound.

---

## 13. CODEOWNERS — recommended pattern

```
# packs/** and compliance-sensitive config → compliance-reviewed
packs/**                @<your-org>/compliance-leads
space.yaml              @<your-org>/compliance-leads

# Skills + sidecar code (from master template) → platform-reviewed
.claude/skills/**       @<your-org>/platform-leads
sidecar/**              @<your-org>/platform-leads

# repos.yaml — bind/unbind events, low-stakes
repos.yaml              @<your-org>/anyone

# kb/ entries — direct push allowed for non-compliance spaces
# (omitted from CODEOWNERS = no required reviewer)
# kb/**                 (intentionally unowned)
```

The principle: **knowledge entries land freely, binding is lightweight, packs and config are gated.**

For `compliance: true` spaces, harden further with a GitHub branch ruleset (not just CODEOWNERS):
- min-2-reviewers
- admin bypass disabled (any admin bypass is a break-glass audit event)
- compliance-leads team rotation policy documented

---

## 14. Setup and install

Repeatable per space — devs run setup once per space they install.

```
Adding a new space to a machine:

1. git clone <space-repo-url> ~/teamvault-<space>
2. cd ~/teamvault-<space>
3. claude → /teamvault-setup
   → reads SETUP_PROMPT.md / SKILL.md
   → reads space.yaml for metadata
   → pip install sidecar dependencies (~2.5GB torch, ~547MB Nomic on first run)
   → if this is the FIRST space installed:
        copies sidecar/ → ~/.teamvault/sidecar/   (v0.0; v0.1+ uses pip package)
        creates launchd plist for the sidecar on port 8100
        registers Claude Code MCP entry via `claude mcp add --scope user`
   → else (sidecar already running):
        sidecar adds this clone path to ~/.teamvault/registry.json
        sidecar starts watching it (pull every 60s, index kb/, load packs)
   → adapter deploys this space's agents (namespaced) to ~/.claude/agents/
   → adapter applies settings patch
   → prints summary: space registered, sidecar port, slash commands available
```

Per-space install is lightweight — adding the 5th space is `clone + run setup`. No new sidecar process; the running sidecar starts watching another clone.

---

## 15. Audit and observability

The sidecar emits structured signals so any compliance regime can be evidenced:

- **JSONL audit log** at `${TEAMVAULT_HOME}/<space>/audit.log`. Append-only, tamper-evident via SHA-256 hash chain (`hash_prev` field on each entry). Fields: `ts, actor, action, path, space, workspace, host_session_id, pack_sha, hash_prev`. Verify via `sidecar.audit.verify_chain(<space>)`. Retention is documented per space; the compliance regime adopted (HIPAA, SOC 2, etc.) declares the actual retention requirement.
- **Structured JSON logs** at `~/.teamvault/logs/sidecar.log` (v0.1+, P1.4) with daily rotation, 7-day retention, per-space sub-loggers.
- **`/healthz`** returns `{status, version, spaces: [{name, last_pull, last_error, last_indexed_commit_sha, last_audit_hash}]}`.
- **`/readyz`** (v0.1+) reports startup completion separately from liveness.
- **`/teamvault-status`** slash command surfaces a human-readable diagnostic.
- **`/teamvault-doctor`** (v0.1+, P1.2) deeper diagnostic with remediation suggestions and a tarball-for-support bundler.
- **PID-lockfile** (`~/.teamvault/sidecar.pid` with `flock`) prevents two sidecar processes from contending on the same indexes.

---

## 16. What ships in v0.0 vs. what's roadmapped

v0.0 is the demo POC. The structured deferral list is in [ROADMAP.md](ROADMAP.md). Below is the architectural summary.

### Shipped in v0.0

- One sidecar per machine, multi-space-aware
- Hybrid BM25 + vector + RRF retrieval over markdown
- Static contextual prefixes prepended pre-embed
- Pack runtime with `advisory | blocking` modes; snapshot-on-invocation consistency
- Reference packs: `hipaa-reference`, `clickup-linkage`, `jira-linkage`
- Claude Code host adapter (skills: setup, publish, review, status)
- GHA PR-stage workflow (`teamvault-review.yml`)
- JSONL audit log with hash-chain (HIPAA §164.312(b) skeleton)
- Content-hash dedup; stale-row deletion on reindex
- macOS launchd supervisor

### Deferred to v0.1+

See [ROADMAP.md](ROADMAP.md) for the full structured list. Highest-priority architectural items:

- Hardened `git_sync` UX (non-FF acknowledgement, dirty-tree surface, timeouts, jitter, backoff) — P1.1
- `/teamvault-doctor` + structured logs + rotation — P1.2, P1.4
- Pre-baked wheelhouse — P1.3
- Temporal decay; multi-space search — P1.6, P1.7
- Linux (P1.8), Windows (P2.10), Docker (P2.9) install paths
- `packs.registry.json` + tiered governance — P2.1
- Sidecar split: separate pip package + config template — P2.2
- Host adapter abstraction + Codex stub — P2.3
- Pack contract extensions (`ordering`, `mode: veto`, `on_error`, `depends_on`, `mutually_exclusive_with`, `timeout_s`, per-reviewer token budget) — P2.4
- `/agent-board` cross-repo agent comms skeleton — P2.5
- Workspace → variant rename — P2.6
- New gap-coverage items surfaced by V2 review (see ROADMAP "Gaps from V2 review") — fail-closed enumeration, data-egress invariants, breach-response runbook, `_context` MCP tool, retrieval observability, embedding-model migration, host-adapter alias gen, `/teamvault-cost`, `/teamvault-pack-upgrade`, `/teamvault-upstream-sync`, `get_company_context`, GOVERNANCE.md, KB partitioning at scale, code-signing, plist-reset recovery

---

## 17. What TeamVault is NOT

- **NOT a certified compliance system** for any regime. The `hipaa-reference` pack is one *layer* — you still need BAAs with all third parties, organizational controls, periodic manual audits, and a real compliance officer. See [LICENSE](../LICENSE) for the disclaimer.
- **NOT a substitute for code review.** The pack runtime is one signal in your PR flow. Human review still required.
- **NOT a vendor product.** v0.0 is reference architecture. Bug ↔ fix loop is community-driven.
- **NOT a centralized service.** Each space is fully owned by its team; no cross-team central server.
- **NOT a security boundary.** Per-space isolation is routing convenience, not a sandbox.

---

## 18. Design lineage

- **A personal knowledge vault** — the single-developer precursor. Established the sidecar / MemPalace / single-writer invariants.
- **The multi-system KB convergence pattern** — distilled in [KB-FOUNDATIONS.md](KB-FOUNDATIONS.md). The hybrid BM25+vector+RRF + paragraph chunking + content-hash dedup + frontmatter-as-substrate pattern came from there.
- **Anthropic's contextual retrieval research** — informs the contextual-prefix path (35% recall lift standalone, 67% combined with hybrid).
- **Backstage / dbt distribution pattern** — informs the v0.2+ binary-package-plus-config-template split (ROADMAP P2.2).

The methodology that produced this codebase is documented in [AUTONOMOUS_BUILD_METHODOLOGY.md](AUTONOMOUS_BUILD_METHODOLOGY.md).

---

## 19. Open architectural questions

These were raised in the V2 review and remain open. Pinning them here keeps the architecture honest about what isn't yet settled.

1. **Subsume the personal vault?** TeamVault's "1-member space" subsumes the personal-KB use case. Keep a standalone personal vault separate or consolidate?
2. **Cross-space query.** When a shared library is bound to two spaces, what does `vault_search` do? Both? Pick one? Surface via `_context`?
3. **Two spaces both shipping the same pack.** Same `hipaa-reviewer` agent in two spaces — does `/teamvault-review` invoke both in a repo bound to only one?
4. **Settings-patch conflict resolution across hosts.** Once a second host adapter ships (Codex), overlapping keys in `config/settings/*.json` need a documented rule.
5. **Pack version compatibility across runtime versions.** Independently versioned packs vs. runtime version skew. Compatibility matrix not yet specified.
6. **`/teamvault-publish` push identity.** Each dev as themselves vs. a service account. Affects audit-log fidelity.
7. **`/teamvault-unpublish` UX.** Deletion path unspecified for the v0.0 publish flow.
8. **Brand.** "TeamVault" carries a security-vault connotation; rename window may still be open.
9. **First-installed-wins sidecar coupling.** The running binary comes from the first space installed; mismatches are surfaced via `/teamvault-status`. Should a `/teamvault-sidecar-switch <space>` skill be required?
10. **Multi-bound project repos.** A library bound to spaces A and B — does the binding dev's `/teamvault-search` see both? Both is the obvious answer; semantics around conflicting pack policies are not.

---

*This is the canonical architecture doc. [CONTRACTS.md](CONTRACTS.md) has exact HTTP/MCP/pack contract specs; [ROADMAP.md](ROADMAP.md) is the structured deferral list. See [README.md](../README.md) for the documentation map.*
