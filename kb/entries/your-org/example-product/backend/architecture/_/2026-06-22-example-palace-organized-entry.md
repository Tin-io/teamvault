---
created: 2026-06-22T00:00:00Z
source: template
confidence: 1.0
author: tin-io/teamvault
decision_type: pattern

# Light Palace taxonomy. v0.1.5+ /teamvault-publish auto-fills kingdom/palace/wing
# from the publishing repo's repos.yaml entry. In v0.1.x, set them manually.
kingdom: your-org
palace: example-product
wing: backend
hall: architecture
room: _

tunnels:
  - 2026-06-16-meta-how-to-write-a-kb-entry

tags:
  - sample
  - template
  - palace-organized
---

# Sample: a Palace-organized KB entry

## What this is

A throwaway sample showing the **canonical path + frontmatter mirroring** for a project-bound entry. The meta entry at `kb/entries/tin-io/teamvault/_/meta/_/2026-06-16-meta-how-to-write-a-kb-entry.md` documents what each frontmatter field means and when to use each `decision_type`; this entry just lives at a real Light Palace path so the structure is visible in the `kb/entries/` directory tree.

Fork the master template, drop your team's real entries at the equivalent path for your project, then `git rm` this sample once you've internalized the shape.

## Path ↔ frontmatter mirroring

This entry's filesystem path is:

```
kb/entries/your-org/example-product/backend/architecture/_/2026-06-22-example-palace-organized-entry.md
           kingdom  palace          wing    hall         room   slug
```

…and the frontmatter at the top of this file mirrors it level-for-level. In v0.1.5+ the publish flow auto-fills `kingdom/palace/wing` from the binding repo's `repos.yaml` entry; until then, set them by hand to keep path + frontmatter in sync.

## `_` for skipped levels

This entry uses `_` for `room` — common when an entry fits a hall but doesn't fit a more specific room yet. Any level can be skipped with `_`; trailing levels can be omitted entirely.

## Related

- `kb/entries/tin-io/teamvault/_/meta/_/2026-06-16-meta-how-to-write-a-kb-entry.md` — frontmatter field reference + decision-type catalog
- `docs/KB-FOUNDATIONS.md` — canonical Mem Palace taxonomy + converged retrieval-pattern background
- `docs/STRATEGY.md` "Memory Palace" section — where Palace fits in the v0.2+ roadmap
