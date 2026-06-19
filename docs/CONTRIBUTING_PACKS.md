# 🧩 Contributing Packs to TeamVault

> ✨ Targeting v0.1 — this doc seeds the contributor surface for the OSS launch. v0.0 ships only the two reference packs from the master template; this is the path the ecosystem will take.

<p align="center">
  <img src="https://img.shields.io/badge/status-v0.1%20prep-orange?style=flat-square" alt="Status: v0.1 prep">
  <img src="https://img.shields.io/badge/scope-pack%20contributors-blue?style=flat-square" alt="Scope: pack contributors">
</p>

## ✨ Why packs

TeamVault's value is its substrate (markdown KB + sidecar + MCP) + its extensibility via **packs**. Packs declare what a team cares about: PHI patterns, ticket linkage, security checks, naming conventions. The core runtime knows nothing about specific compliance regimes — teams compose by enabling the packs that match their world.

A pack is a directory under `packs/<name>/` with a `PACK.yaml` declaring its contributions.

## 📦 What a pack can contribute

In v0.0:

| Contribution | Type | When it runs |
|---|---|---|
| 🤖 `agents` | Markdown reviewer prompts | At review time (currently regex-based; v0.1 LLM-spawned per reviewer) |
| 🧼 `scrubbers` | YAML regex pattern banks | At publish time (block on match) AND at review time (block via reviewer) |
| 🛡️ `reviewers` | Bindings of agent → mode | At review time, per pack |

In v0.1+ (planned):

| Contribution | Type | When |
|---|---|---|
| 🚧 `ingest_guards` | Pre-ingest filters (path + content predicates) | Before chunking, in the ingest pipeline |
| 🔄 `transformers` | Pack-specific content transformers (e.g., Granola meeting transcript → structured chunks) | Between parse and chunk |
| 🔧 `settings_patches` | Host-specific config patches | At pack deploy time, scoped to the host adapter |
| 📐 `config_schemas` | JSON Schema for pack-level config | At pack load (validation only) |

## 🏛️ Three tiers (governance model)

1. 🥇 **Core packs** ship in the master template `tin-io/teamvault/packs/`. Maintainer-maintained. Narrow set. Currently:
   - `hipaa-reference` — example reference, NOT a complete HIPAA control. See LICENSE disclaimer.
   - `clickup-linkage` — advisory ticket-linkage check.

2. 🥈 **Official reference packs** live in separate repos under `tin-io/teamvault-pack-<name>` (or wherever the maintainer blesses). Versioned independently, registered in a top-level `packs.registry.json` in the master template.

3. 🥉 **Community packs** live anywhere on GitHub. Discovered via a `packs.registry.json` PR flow in the master template. Bar for inclusion: PACK.yaml validates, no obviously malicious code, follows the contributor checklist below.

## 🛤️ Path to contribute a new pack

### 🎯 1. Decide the tier

If you're solving for your team only: keep it in your team's space fork. No upstream contribution needed.

If you're solving for a category of teams (e.g., PCI-DSS, SOC 2, GDPR, a specific vendor integration): consider proposing it as an official reference pack. Open an issue at `tin-io/teamvault` describing the use case and the pack design.

### 🗂️ 2. Repo conventions

Pack repos under the official-reference tier name themselves `tin-io/teamvault-pack-<name>`. Inside:

```
PACK.yaml              # contributions declaration
README.md              # what this pack does + how to enable + disclaimer
LICENSE                # MIT for v0.0 (Apache 2.0 considered for v0.1+)
agents/<name>.md       # reviewer agent prompts
scrubbers/<name>.yaml  # regex pattern banks (if any)
config_schema.json     # optional JSON Schema for pack config
CHANGELOG.md
```

Community packs follow the same conventions but live wherever.

### 📐 3. PACK.yaml format (v0.0)

```yaml
name: <kebab-case-pack-name>
version: <semver>           # please follow semver for the registry
description: >
  One sentence on what this pack does. Mention if it's advisory or blocking
  by default.
knowledge_topics:           # optional (v0.1+); kebab-case domain names
  - <topic-1>
  - <topic-2>
contributions:
  agents:
    - path: agents/<reviewer-name>.md
  scrubbers:
    - type: regex
      file: scrubbers/<patterns>.yaml
  reviewers:
    - agent: <reviewer-name>     # matches agents[*].path basename without .md
      mode: advisory             # or blocking
```

**About `knowledge_topics`** (v0.1+):

> `knowledge_topics` is the whitelist the agent uses to decide when to query
> the KB for prior art. It is NOT enforcement (no scrubber runs against it);
> it is *the team's declaration of which domains they've accumulated KB on*.
> If unsure whether to add a topic, prefer omitting — the agent's
> demand-side instinct covers anything not declared.

Topic naming: kebab-case lowercase, alphanumeric + hyphens
(regex `^[a-z0-9]+(-[a-z0-9]+)*$`). Invalid topics are dropped from the
loaded list with a warning; the pack still loads. Missing field → empty
list (no behavior change). The agent reads the union of all enabled packs'
topics via `vault_packs()` at the start of substantive work.

### ✅ 4. PACK contribution checklist

Before opening a PR (against your pack repo or against the registry):

- [ ] `PACK.yaml` validates against the runtime contract (`docs/CONTRACTS.md` in the master template)
- [ ] All `scrubbers/*.yaml` patterns have descriptive `name` + `description` fields
- [ ] All reviewer agent markdowns have a `name` + `description` frontmatter, and the body explains what the reviewer flags + what NOT to flag
- [ ] The README clearly states whether the pack ships `advisory` or `blocking` by default
- [ ] If the pack handles compliance (HIPAA, PCI, SOC 2, etc.): the README disclaims that this is ONE layer of defense, not a complete control
- [ ] No code execution paths in v0.0 (regex only). v0.1 will introduce sandboxed code paths with a separate review process.
- [ ] License declared (MIT recommended unless wrapping a proprietary tool — then declare the wrapped tool's terms)

### 🧪 5. Test against the master template's sidecar

```bash
# In the master template repo with the sidecar venv set up
git clone <your-pack-repo> /tmp/test-pack
ln -s /tmp/test-pack ~/Projects/test-omc/teamvault-sandbox/packs/<your-pack-name>

# Add to sandbox space.yaml::enabled_packs
echo "  - <your-pack-name>" >> ~/Projects/test-omc/teamvault-sandbox/space.yaml

# Boot sidecar against sandbox
TEAMVAULT_HOME=~/Projects/test-omc/teamvault-sandbox/.teamvault-home \
TEAMVAULT_SPACE_ROOT=~/Projects/test-omc/teamvault-sandbox \
TEAMVAULT_PORT=18100 \
  .venv/bin/uvicorn sidecar.app:app --port 18100

# In another shell — verify it loads
curl -s -X POST http://localhost:18100/review -H 'Content-Type: application/json' \
  -d '{"space":"teamvault-template","diff":"+sample line to trigger pack"}'
```

If the response shows your pack's reviewer in the `individual[]` array, it's loading correctly.

### 🤝 6. Open a PR to the registry (for official reference tier)

When ready: open a PR to `tin-io/teamvault/packs.registry.json` (file to be created in v0.1) listing your pack:

```json
{
  "your-pack-name": {
    "repo": "https://github.com/<you>/teamvault-pack-<name>",
    "version": "0.1.0",
    "description": "...",
    "tier": "community"   // or "official"
  }
}
```

The maintainer reviews. Standard OSS review terms apply.

## ❌ What a pack should NOT do (v0.0)

- Execute arbitrary code (regex only)
- Make network calls (deferred to v0.1's `ingest_guards` for explicit network-allowed tools)
- Read or write files outside its own `packs/<name>/` directory
- Modify other packs

The runtime currently enforces these implicitly (no code execution surface), but v0.1's expanded contribution types will need explicit sandboxing.

## 🔢 Versioning + compatibility (v0.0 → v0.1)

The PACK.yaml schema is `v1`. v0.1 will introduce:

- `ordering` field on reviewer bindings (priority int)
- `depends_on` and `mutually_exclusive_with` for cross-pack relationships
- `timeout_s` per reviewer
- `mode: veto` for single-reviewer-blocks-all semantics
- `on_error: fail | skip | warn`
- A top-level `schema_version` field (1 → 2)

v0.0 packs WILL continue to load under v0.1 with their existing semantics — the new fields are additive.

## ⚠️ Disclaimer (compliance packs)

If your pack name or description suggests compliance (HIPAA, PCI, SOC 2, GDPR, FedRAMP, etc.), include a prominent disclaimer in the pack README and reviewer agent body:

> This pack provides defensive tooling for the [REGIME] regime. It is NOT a [REGIME]-compliance certification, audit substitute, or replacement for organizational controls. Teams using this pack must execute their own BAAs / DPAs / vendor agreements, maintain their own [REGIME] Security Rule / control implementations, and conduct periodic manual audits. The authors disclaim liability for compliance gaps in any specific deployment.

This protects both you and the user.

---

When in doubt: open a GitHub issue at `tin-io/teamvault` first. Pack design is the most consequential extension surface; getting alignment early saves rework.
