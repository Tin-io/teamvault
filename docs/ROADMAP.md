# 🗺️ TeamVault v0.1 — Roadmap

> ✨ Structured deferral list from the v0.0 build. Each item is sized + tagged + sourced so post-v0.0 planning is mechanical.

<p align="center">
  <img src="https://img.shields.io/badge/status-planning-orange?style=flat-square" alt="Status: planning">
  <img src="https://img.shields.io/badge/P0%3A%204%20%C2%B7%20P1%3A%207%20%C2%B7%20P2%2B%3A%206-555?style=flat-square" alt="Tier counts">
</p>

## 🏷️ Tags
- 🛡️ **[HIPAA]** — touches HIPAA Security Rule controls or pack-compliance guarantees
- 🧰 **[DX]** — developer experience surface
- 🦾 **[OPS]** — sidecar reliability / observability
- 🔢 **[IR]** — information retrieval quality
- 📦 **[OSS]** — public OSS launch readiness
- 🏗️ **[ARCH]** — architecture / abstraction

## 📚 Sourced from
- Adversarial review feedback (Security, DX, Code critics)
- 8-reviewer round-table review (R1-R8) with recalibration appendix
- Install dry-run sub-agent feedback
- The v0.0 build's "DOES NOT ship" deferral inventory
- Gap-coverage pass from the V2 review digest

## 🎯 Priority tiers
- 🚨 **P0** — must ship before broader v1 OSS launch
- ⚡ **P1** — high value within first 4 weeks post-v0.0
- 📌 **P2** — solid v0.2 candidates
- 💡 **P3** — long-tail polish

---

## ✅ Shipped after v0.0 (reconciled 2026-06-20)

These were built post-base-v0.0 and merged into `main` (commit `7c68bbe`), but the tiers below were authored *before* that — so several items are marked DONE inline. Reconciled 2026-06-20 against what actually shipped.

- **P0.1 — Audit log** ✅ (`sidecar/audit.py`; JSONL + SHA-256 tamper-evident hash chain).
- **P1.5 — Contextual retrieval prefixes** ✅ (static variant, `sidecar/ingest.py`; LLM-generated variant still pending).
- **Pack `knowledge_topics`** ✅ (PACK.yaml schema + loader; was not previously roadmapped).
- **`vault_packs` / `vault_cite` / `vault_query_log` MCP tools + `/packs` `/cite` `/query_log` endpoints** ✅ (the search→cite→audit loop; was not previously roadmapped).

---

## 🚨 P0 — Compliance & demo follow-through

### ✅ P0.1 — Audit log (HIPAA §164.312(b)) — SHIPPED (post-v0.0) [HIPAA] [SIZE: M ~6h]

Source: Sec critic F2.

Sidecar emits a structured JSONL audit log per space at `${TEAMVAULT_HOME}/<space>/audit.log` covering every meaningful action: KB read (via search), publish attempt + verdict, pack deploy, settings patch.

Required fields per entry:
- `ts` (ISO 8601 UTC)
- `actor` (user identifier — initially `local-user`, post-OIDC the real principal)
- `action` (one of `search` / `publish` / `pack-deploy` / `reindex`)
- `path` (relative path the action touched, when applicable)
- `space`, `workspace`
- `host_session_id` (Claude Code session UUID; the host can pass this through MCP env)
- `hash_prev` (SHA-256 of the previous entry's full JSONL line — append-only tamper-evident chain)

Retention: 6 years documented (HIPAA §164.530(j)(2)). Rotation deferred.

Surface in `/teamvault-status`.

### 🛡️ P0.2 — Pre-commit + pre-receive scrubber hooks [HIPAA] [SIZE: S ~2h]

Source: Sec critic F3.

Close the "dev edits `kb/` directly, bypassing `/teamvault-publish`" leak path. Two hooks:

- **Pre-commit hook** (installed by `teamvault-setup`): runs the pack scrubbers against staged `kb/**` content before commit. Match → commit refused with the pattern name.
- **Pre-receive GHA workflow** (added to the master template): server-side check on `kb/**` paths in any PR. Required status if compliance: true. Match → PR cannot merge.

Pack runtime can be reused as-is.

### 📜 P0.3 — Liability disclaimer + legal review [HIPAA] [OSS] [SIZE: S ~legal review time]

Source: Sec critic F9, R6 F4.

Have a lawyer review the LICENSE disclaimer language + the HIPAA reviewer agent's body language. The current text is best-effort; a real review before public OSS launch protects the maintainer personally.

### 📦 P0.4 — Move `hipaa-reference` pack to its own repo [HIPAA] [OSS] [SIZE: S ~2h]

Source: Sec critic F9, R6 F4, R8 F12.

Move `packs/hipaa-reference/` to `tin-io/teamvault-pack-hipaa-reference`. Reference it from the master template's `packs.registry.json` (P1 below). Reduces the optics of "TeamVault ships HIPAA compliance" and broadens the master template's positioning.

---

## ⚡ P1 — Reliability & demo polish

### 🦾 P1.1 — `git_sync` UX hardening [OPS] [SIZE: M ~4h]

Source: Code critic F6 (already wired in Phase 2), Sec critic F10, R3 F1+F4.

- Surface `git_sync` state in `/healthz` (currently `last_pull` is always null)
- On non-fast-forward upstream: `space.last_error = "upstream history rewrote — run /teamvault-confirm-rewind to acknowledge"` and stop pulling
- On dirty working tree: same pattern, surface clearly
- `git fetch`/`pull` timeout (30s) — currently can hang indefinitely
- Surface auth failures with `gh auth refresh` suggestion

### 🩺 P1.2 — `/teamvault-doctor` [DX] [OPS] [SIZE: S ~2h]

Source: R7 F1, DX critic.

Beyond `/teamvault-status` (read-only diagnostic shipped in v0.0). Doctor runs deeper checks + offers remediation:
- Verify launchd plist matches expected shape
- Verify `claude mcp list | grep teamvault` matches the active sidecar path
- Probe sentence-transformers cache exists and is non-empty
- Probe disk free
- Bundle logs + registry + config into a tarball for support

### 🧰 P1.3 — Pre-baked wheelhouse [DX] [SIZE: M ~3h]

Source: DX critic F3, dress rehearsal observation.

The 2.5GB torch + 547MB Nomic install is the slowest step. Pre-bake:
- Master template ships a `make warm-cache` target that downloads platform-specific wheels into `wheelhouse/`
- Setup skill offers `--use-wheelhouse` path: `pip install --find-links=$WHEELHOUSE --no-index -r requirements.txt`
- Cuts demo-install time from 10-15 min to ~30s

Caveat: platform-specific (arm64 vs x86_64); need separate wheelhouses or use `pip download --platform`.

### 📝 P1.4 — Structured logs + rotation [OPS] [SIZE: S ~2h]

Source: R7 F3.

`~/.teamvault/logs/sidecar.log` JSON-per-line. Daily rotation, 7-day retention. Per-space sub-loggers. Surface in `/teamvault-status` (last 5 errors per space).

### 🐧 P1.8 — Linux native install (systemd user unit) [DX] [OPS] [SIZE: S ~2-3h]

Source: USER_GUIDE.md / TROUBLESHOOTING.md OS-support commitment.

v0.0 ships only the macOS install path (launchd plist via `launchctl bootstrap`). Linux users can run the runtime as-is (pure Python; all deps have Linux wheels) but have no documented install recipe.

**Deliverables:**
- OS-detecting variant of `.claude/skills/teamvault-setup/SKILL.md` — branches on `uname -s`: macOS = launchd plist; Linux = systemd user unit at `~/.config/systemd/user/teamvault-sidecar.service`.
- Unit file generation + `systemctl --user enable --now teamvault-sidecar` for boot persistence.
- Path translations: `~/.teamvault/logs/` stays the same; supervisor logs go to `journalctl --user -u teamvault-sidecar`.
- TROUBLESHOOTING.md Linux section with `systemctl --user status` substitutions (already partially scaffolded in the v0.0 OS-scope note).
- Remove "v0.0 = Mac only" notes from USER_GUIDE.md, TROUBLESHOOTING.md once tested.

**Why first (before Windows):** Linux is the lowest-friction OS to add — bash setup script stays as-is; only the supervisor + path lines change. ~30 lines of skill rewrite. Doubles addressable surface (many developer machines run Linux).

---

## 🔢 P1 — IR quality

### ✅ P1.5 — Contextual retrieval prefixes — SHIPPED (static; LLM-gen pending) [IR] [SIZE: M ~4h]

Source: R2 F1, Anthropic research (35% recall improvement standalone, 67% with hybrid).

Before embedding a chunk, prepend a 1-2 sentence document-level context to the chunk text. Two implementations:

- **Static**: prepend `f"From '{title}' ({entry_type}, {created_date}). Tags: {tags}."` — cheap, no LLM call
- **LLM-generated**: per-chunk Haiku call to generate the prefix at ingest time — better quality, ~$0.03 per 1k entries (autonomous-coding KB precedent)

v0.1.0 ships static, v0.1.5 adds LLM-generated as an opt-in.

### ⏳ P1.6 — Temporal decay [IR] [SIZE: S ~2h]

Source: R2 F3, KB-FOUNDATIONS.md pattern #4.

Add a `created_at` field to chunk metadata (already in frontmatter; just pipe through to score). Score multiplier: 1.0× for ≤30 days, linear decay to 0.5× floor at 365 days. Access-count resistance via `access_count` counter incremented on each retrieval.

### 🔍 P1.7 — `vault_search_all_spaces` MCP tool [IR] [SIZE: S ~2h]

Source: R2 F5.

For power users with 5+ spaces. Fan-out per-space search, merge with each hit labeled by space. Default behavior remains cwd-routed; this is an opt-in tool.

---

## 📌 P2 — Architecture & ecosystem

### 📦 P2.1 — `packs.registry.json` + tiered governance [OSS] [SIZE: M ~4h]

Source: R6 F2, F11.

Master template ships `packs.registry.json` listing blessed packs by URL + version. Three tiers documented in `docs/CONTRIBUTING_PACKS.md`. Setup skill `--use-registry` mode pulls additional packs at install time.

### 🧱 P2.2 — Split distribution: binary package + config template [OSS] [SIZE: L ~8h]

Source: R6 F1, F8.

Currently the master template bundles sidecar code + config + packs. Backstage/dbt pattern: publish sidecar as a versioned pip package (or Homebrew bottle), master template is config-only with `.teamvault/bin/version` pinning. Upgrade story becomes `pip install --upgrade teamvault-sidecar==<v>`.

### 🏗️ P2.3 — Host adapter abstraction + Codex stub [ARCH] [SIZE: M ~4h]

Source: R1 F3, F8.

Define a `*.tv.md` canonical agent format. Per-host adapter translates. Ship stub Codex adapter (no real Codex integration; just the protocol) to validate the abstraction. R1 explicitly recommended this BEFORE shipping `.tv.md` formalism.

### 📐 P2.4 — Pack contribution contract extensions [ARCH] [SIZE: M ~4h]

Source: R1 F1.

Add to PACK.yaml schema:
- `ordering` (priority int or before/after list)
- `mode: veto` (single reviewer can fail verdict)
- `on_error: fail | skip | warn`
- `depends_on: [pack-name]`
- `mutually_exclusive_with: [pack-name]`
- `timeout_s` per reviewer
- Per-reviewer token budget (R1 F7)

### 🤖 P2.5 — `/discover` cross-repo agent comms (skeleton) [ARCH] [SIZE: L ~6h]

Source: R1 F5, OMC analysis flagged this as the maintainer's load-bearing differentiator.

Define the message format, board location (per-space `discover/` dir), addressing model, durability, cross-space sends. Ship a skeleton implementation; iterate based on real cross-team use.

---

## 🧰 P2 — DX & onboarding

### 🔤 P2.6 — Rename "workspace" → "variant" [DX] [SIZE: S ~2h]

Source: R4 F2.

`workspace` is overloaded (VS Code, npm, Yarn, GitHub Actions, AWS, JetBrains). Rename to `variant` in `space.yaml` schema, glossary, and skill docs. Migration shim: read both names for one release, then drop `workspace`.

### 🔗 P2.7 — Local-bind "tentative" mode [DX] [SIZE: S ~2h]

Source: R8 F3, DX critic F4, recalibration N2.

`/teamvault-bind-now` skips the PR ceremony for local quick-bind. Sidecar treats the local-but-not-yet-merged binding as valid on the binding dev's machine only (marked pending) until merge. Other devs still see "unbound."

### 👉 P2.8 — Guided first-run walkthrough [DX] [SIZE: M ~3h]

Source: R4 F11.

After install completes, the setup skill walks the dev through: (a) clone, (b) bind first repo, (c) publish first entry, (d) search for it. Each step has a "did this work?" confirmation. Reduces the first-session error rate.

---

## 🌐 P2 — Distribution & cross-platform

### 🐳 P2.9 — Containerized distribution (Docker image, parallel install path) [DIST] [OPS] [OSS] [SIZE: L ~12-16h]

Source: maintainer question + tradeoff analysis in conversation transcript.

**Strategic question:** should TeamVault's primary install path become Docker, replacing the per-OS native install (launchd on Mac, systemd on Linux, Service/scheduled task on Windows)?

**What Docker would solve:**
- **OS portability** — one image runs on Mac, Linux, Windows (via Docker Desktop). Eliminates the three-way native install split.
- **Install-time torch pain** — pre-bake `torch` (~2.5GB) and the Nomic model (~547MB) into the image. First-run drops from ~10 min to ~30s. (The single biggest install friction in v0.0.)
- **Reproducibility** — every dev runs the same binary. No "works on my machine."
- **Supervisor unification** — `docker run --restart=unless-stopped` replaces launchd / systemd / Windows Service. One command, three OSes.
- **Sandboxing** — container can't touch host `~/.claude/`, `~/Library/`, `~/.ssh`, etc. unless explicitly mounted. The `TEAMVAULT_HOME` safety rails become natural rather than discipline-based.

**What Docker does NOT solve / would introduce:**
- **MCP shim cannot be containerized.** Claude Code launches `python -m sidecar.mcp_server` as a stdio subprocess. The shim has to run natively as a Claude Code child process. Only the FastAPI sidecar gets containerized; the shim stays native and talks to the container over HTTP (which `mcp_server.py` already does — minimal change).
- **Git credentials mounting** — the sidecar pulls every 60s, requiring SSH key or PAT access. Bind-mounting `~/.ssh` or `~/.config/gh` into the container is doable but adds setup complexity the current pip install doesn't have.
- **Filesystem perf on Mac/Windows** — Docker Desktop bind-mounts are slow for many small file ops. Re-indexing a 1k+ entry KB notices the latency. Mitigable with Docker volumes (instead of bind mounts) but loses "edit files locally" semantics.
- **Resource footprint** — Docker Desktop is 4-8GB RAM on Mac. Devs already running heavy container stacks notice. Adds friction for users without Docker installed.
- **No database to Dockerize.** TeamVault uses SQLite FTS5 + LanceDB, both file-based. There's no PostgreSQL / Redis server. Only the FastAPI sidecar would be containerized.

**Three paths:**

- **Path A — Docker as primary install method.** README becomes `docker run --rm -v ./teamvault-<space>:/space -p 8100:8100 ghcr.io/tin-io/teamvault-sidecar:0.2`. Eliminates OS-specific install paths entirely. Tradeoff: hard dependency on Docker Desktop.
- **Path B — Docker as parallel install option (recommended).** Native install stays primary through v0.1; Docker image ships as a parallel option in v0.2. README offers both. Measure adoption; decide by v0.3.
- **Path C — Skip Docker, fix friction differently.** Address torch install with ONNX/GGUF embedding (P1.3 wheelhouse). Native install per OS (P1.8 Linux + P2.10 Windows). Tradeoff: maintain three OS install paths indefinitely.

**Recommended sequencing (Path B):**
- v0.1 ships native Linux install (P1.8). Doubles addressable surface at low risk.
- v0.2 ships parallel Docker image — pre-baked Nomic model, `host.docker.internal` for MCP shim → sidecar, documented mount points for `~/.ssh` and the space clone.
- v0.3 decides based on adoption data: make Docker primary (deprecate native) OR keep both.

**Sizing breakdown for v0.2 image:**
- Dockerfile + multi-stage build (separate "model-bake" stage to enable layer caching) — ~3h
- Nomic model pre-bake + image size optimization — ~2h
- Git credentials mount strategy + docs (SSH agent forwarding vs PAT env var) — ~2h
- CI/CD for `ghcr.io/tin-io/teamvault-sidecar` (multi-arch: `linux/amd64` + `linux/arm64`) — ~3h
- MCP shim adaptation to point at container endpoint via `host.docker.internal` — ~2h
- USER_GUIDE Docker section + test on 3 OSes (Mac arm64, Linux amd64, Windows) — ~4h

**Open questions:**
- Should the image bundle Claude Code too, or stay sidecar-only? Sidecar-only is simpler; bundling Claude Code is a v0.3+ consideration if "one container, everything works" becomes the marketing point.
- Versioning policy — bump on every sidecar change, or only when the HTTP API contract changes? Recommend: bump on contract changes only; tag `latest` floating.
- Multi-arch from day one, or arm64-first? Mac M-series + Linux ARM are early-adopter platforms; amd64 is broader. Recommend multi-arch from v0.2.0 to avoid migration pain later.

**Why not now (v0.0):** native pip install works; runtime is already OS-agnostic; committing to Docker primary without seeing early adopters' Docker readiness is premature. The launchd path ships first. Don't redesign the install story before any real adoption data.

### 🪟 P2.10 — Windows native install (Service or scheduled task + PowerShell setup) [DX] [OPS] [SIZE: M ~4-8h]

Source: USER_GUIDE.md / TROUBLESHOOTING.md OS-support commitment.

**Deliverables:**
- Windows-detecting variant of `teamvault-setup` skill (PowerShell, not bash).
- Choice between `New-Service` Windows Service or Task Scheduler scheduled task for the supervisor (latter is lower-privilege; recommend default).
- Path translations: `~/.teamvault/` → `%USERPROFILE%\.teamvault\` (or `%APPDATA%\teamvault\` for stricter convention).
- Test on Windows 11 with Claude Code installed.
- Update USER_GUIDE.md, TROUBLESHOOTING.md with Windows sections (remove v0.2 placeholder).

**Why second (after Linux):** larger lift than Linux (bash → PowerShell port + Windows Service / scheduled task is more involved than systemd unit). Narrower expected addressable surface among early adopters. Workaround in v0.0/v0.1: Windows users can run TeamVault inside WSL (Linux subsystem) once P1.8 ships.

**Composes with P2.9 (Docker):** if both land in v0.2, Windows users get TWO install paths simultaneously — native (PowerShell) or Docker. The Path B sequencing in P2.9 accounts for this; expect Docker to be more popular on Windows because Docker Desktop's WSL2 backend handles many of the supervisor concerns natively.

---

## 💡 P3 — Long-tail

- **Multi-space sidecar** (R3): cwd → space resolution for power users with N spaces. (POC deferred)
- **Re-ranker** (R2 F2): cross-encoder pass after RRF, top 50 → top 10. Quality win, latency cost.
- **Mem Palace hierarchy** (KB-FOUNDATIONS.md): Kingdom/Palace/Wing/Hall/Room/Tunnels taxonomy. Heavy lift for v0.2+.
- **Telemetry opt-in** (R7 F8): how does the maintainer hear about field failures without paging?
- **Tests on the master template repo's CI**: pytest + GHA pipeline. POC has integration tests under `.build/` but they're sidecar-running, not CI-friendly.
- **Documentation site**: GitHub Pages or similar to replace `docs/*.md` for OSS users.
- **Settings sync mechanism beyond git** (R8): for v2+ if git pull every 60s becomes the limiting factor.
- **Naming change** (R6 F3): "TeamVault" → ??? if the vault connotation issue becomes a real problem.

---

## 📋 Recommended sequencing (4-6 weeks)

**Week 1 (first-team bedding-in):**
- P0.1 audit log (skeleton enough to satisfy a §164.312(b) question)
- P0.2 pre-commit hooks (close the kb/ direct-edit leak)
- P1.1 git_sync UX hardening (early ops issues surface here)

**Week 2 (second design partner):**
- P0.3 legal review (parallel)
- P0.4 hipaa-reference repo split (separation is cheap once you decide)
- P1.5 contextual prefixes (visible retrieval quality lift)

**Weeks 3-4 (broader OSS prep):**
- P2.1 packs.registry.json (sets the contributor surface)
- P2.2 split distribution (load-bearing for OSS)
- P1.3 wheelhouse (visible install lift)

**Week 5-6 (v0.2 milestone):**
- P2.5 /discover skeleton
- P2.3 Codex adapter stub
- P2.4 pack contract extensions

---

## 🧩 Gaps from V2 review (folded in 2026-06-16)

A second pass over `ARCHITECTURE_V2_REVIEW.md` against this roadmap surfaced architectural items that weren't yet captured. Folding them in here so the roadmap is complete.

### 🛡️ P0 additions (compliance hardening)

- **P0.5 — Snapshot-on-invocation pack-SHA pinning [HIPAA] [ARCH] [SIZE: S ~2h]** — `/teamvault-review` and `/teamvault-publish` already snapshot pack reads at invocation start (POC). Harden: emit `pack_sha` in every verdict's metadata and in the audit log, so reproducibility is bit-exact and a verdict can be re-run later against the same commit.
- **P0.6 — Fail-closed contract enumeration [HIPAA] [SIZE: S ~3h]** — Document and test every scrubber failure mode (malformed YAML, missing file, regex compile error, timeout, OOM). Each gets a required block behavior for `compliance: true` spaces. Land integration tests for the full matrix.
- **P0.7 — Data-egress invariants for compliance spaces [HIPAA] [SIZE: S ~3h]** — When ANY installed space declares `compliance: true`, enforce machine-wide: embedding model is local-only, no remote inference calls, cross-space scrubbers run on writes, cross-space search results scrubbed to the strictest regime. Surface in `/healthz` at boot.
- **P0.8 — Breach-response runbook [HIPAA] [SIZE: S ~legal+dev]** — `BREACH_RUNBOOK.md`: BFG / `git filter-repo` recipe to scrub a leaked entry from history; GitHub support template; BAA notification clock; pack-SHA forensics. Co-authored with legal review (P0.3).
- **P0.9 — CODEOWNERS hardening for compliance spaces [HIPAA] [OPS] [SIZE: S ~1h]** — Document and template a GitHub branch ruleset for `compliance: true` spaces: min-2-reviewers, admin bypass disabled, compliance-leads rotation policy. Treat any admin bypass as a break-glass audit event.

### ⚡ P1 additions (reliability + observability)

- **P1.9 — `_context` MCP tool [DX] [SIZE: S ~1h]** — Returns `{active_space, active_variant, resolved_via}`. Every other MCP tool response embeds the resolved space. Removes a class of "which space did this come from?" support tickets.
- **P1.10 — Retrieval observability [IR] [OPS] [SIZE: M ~4h]** — `retrieval.log.jsonl` per query: input, BM25 + vector top-K, RRF fusion, decay multipliers, final ranks. `/teamvault-debug-search` replays a query against the log for "why did THAT rank where it did?" debugging.
- **P1.11 — Resource budget enforcement [OPS] [SIZE: M ~3h]** — RSS < 1GB steady-state target; embedding batch size cap (env: `TEAMVAULT_EMBED_BATCH`); max 2 concurrent space pulls; file-watcher debounce ≥ 2s; pre-flight disk-free check (<2GB free → refuse reindex). Document in TROUBLESHOOTING.
- **P1.12 — Pull jitter + per-space exponential backoff [OPS] [SIZE: S ~2h]** — Per-space ± 10s pull jitter (avoid thundering herd on shared remotes). Backoff schedule 60s → 5m → 30m → 1h cap on consecutive errors. `space.last_error` carries reason + next-attempt time. Soft scaling-limit guidance documented at N=10 spaces.
- **P1.13 — `/healthz` + `/readyz` + PID-lockfile [OPS] [SIZE: S ~2h]** — `/readyz` reports startup completion separately from liveness. PID-lockfile (`~/.teamvault/sidecar.pid` via `flock`) prevents two sidecar processes contending on the same indexes. Atomic JSON writes for `registry.json`. Graceful-shutdown marker on clean exit.
- **P1.14 — Transactional pack reload + CI pack linter [OPS] [ARCH] [SIZE: M ~4h]** — Validate pulled pack changes in a staging area; swap atomically on success; on parse failure, keep prior valid config + log + surface to `/healthz`. Ship `teamvault-pack-lint.yml` GHA pack linter to run on PR in space repos before any pack change merges.
- **P1.15 — Slug-collision behavior + worktree-based publish [DX] [OPS] [SIZE: S ~2h]** — On publish-time slug collision: append content-addressed suffix. On `git push` rejected: pull-rebase-retry with backoff. Run the publish in a separate worktree so it can't race with the indexer's working tree.
- **P1.16 — `/teamvault-cost` skill [DX] [SIZE: S ~2h]** — Per-invocation cumulative token spend across pack reviewers. Useful both for cost awareness and for tuning per-reviewer token budgets (P2.4).
- **P1.17 — Embedding model pinned per space in `vault.lance` header [IR] [OPS] [SIZE: S ~2h]** — Record embedding model name + version in the vector DB header. Cross-space merge or model bump refuses unless explicit. Migration story is P2.

### 📌 P2 additions (ecosystem + scale)

- **P2.11 — Frontmatter schema extension [IR] [SIZE: S ~2h]** — Add `entry_type` (controlled vocab; generalizes `decision_type`), `superseded_by`, `related_entries[]`. Drives graph-style traversal in v0.2+.
- **P2.12 — `get_company_context({query})` MCP tool [ARCH] [SIZE: M ~3h]** — Substrate-under-harness positioning. Lets OMC and similar harnesses pull team context without knowing about TeamVault internals. Returns scrubbed, scoped, ranked KB chunks for an arbitrary prompt-time query.
- **P2.13 — `/teamvault-pack-upgrade` skill + version-drift audit logging [HIPAA] [OPS] [SIZE: M ~3h]** — Skill: pull upstream pack diff → PR. Sidecar: notify when a pack is N versions behind upstream. For compliance packs: version drift is itself an audit event.
- **P2.14 — `/teamvault-upstream-sync` skill + master-template-vs-fork docs [DX] [OSS] [SIZE: M ~3h]** — Skill: merge from upstream master template with rebase + conflict prompts. Docs: clarify "use template, not fork" path; document adding upstream remote manually; document the upgrade story.
- **P2.15 — Host-adapter alias generation [DX] [SIZE: S ~2h]** — Makes `@hipaa-reviewer` in `<space>` territory resolve to `<space>--hipaa-reviewer` on disk so the ugly namespaced filenames don't reach the user.
- **P2.16 — Embedding-model upgrade migration [IR] [OPS] [SIZE: M ~4h]** — When the master template bumps the embedding model, spaces need a documented migration: reindex from scratch, validate top-K parity, swap. Schema-version field in `vault.lance` header gates the migration.
- **P2.17 — KB partitioning `YYYY/MM/` at scale [OPS] [SIZE: S ~2h]** — At ~5k+ entries APFS performance on a flat `kb/entries/` directory degrades. Document the migration path: `kb/entries/YYYY/MM/<slug>.md`. Backward-compat: indexer reads both layouts.
- **P2.18 — GOVERNANCE.md + bus-factor mitigation [OSS] [SIZE: S ~legal+dev]** — Before broader OSS launch: governance model, maintainer rotation, how to fork the master template, how decisions get made. Mitigates the "one-person project" risk.
- **P2.19 — Code-signing / notarization of sidecar binary [OPS] [OSS] [SIZE: M ~4h]** — macOS Gatekeeper: notarize the sidecar binary so users don't have to right-click → Open. Required for OSS distribution at scale.

### 💡 P3 additions (long-tail)

- **macOS major-upgrade plist-reset recovery** — macOS major upgrades sometimes nuke `~/Library/LaunchAgents/` entries. Document the rebuild path; add `/teamvault-doctor` (P1.2) detection.
- **Agent name namespacing in frontmatter** — In addition to disk namespacing (P2.15), record the source space in the deployed agent's frontmatter so audits can prove provenance.
- **`_context` retrieval-debug round-trip** — Pair the `_context` MCP tool with `/teamvault-debug-search` so an agent can answer "why did THIS come back?" introspectively.

### 🛑 Architectural open questions (parked, not roadmapped)

Folded into [ARCHITECTURE.md §19](ARCHITECTURE.md). Not roadmap items because they're decisions, not deliverables. Re-evaluate when the deliverables above force a choice.

---

When `git log --oneline` on `main` falls behind by N commits, refresh this file.
