---
created: 2026-06-16T22:00:00Z
source: template
confidence: 1.0
author: tin-io/teamvault
decision_type: meta

# Light Palace taxonomy — this entry is tool meta-documentation, so it lives
# under tin-io/teamvault (publishing org / product) with hall=meta. In v0.1.5+
# /teamvault-publish auto-fills kingdom/palace/wing from the publishing repo's
# repos.yaml entry; until then, set them manually so path + frontmatter mirror.
kingdom: tin-io
palace: teamvault
wing: _
hall: meta
room: _

tunnels: []

tags:
  - meta
  - format
  - template
  - how-to
---

# Meta: How to write a TeamVault KB entry

## What this is

This entry IS the format. To write your own KB entry, copy this file's structure — the frontmatter at the top, the heading layout below, the cross-reference pattern at the end. Notice what each piece does, then replace the content.

This file ships in the master template as a format reference. Once your team has real entries to look at, feel free to `git rm` it.

## The frontmatter (annotated)

Every KB entry starts with a YAML frontmatter block delimited by `---` lines. Required fields:

```yaml
created: <ISO 8601 UTC timestamp>     # e.g., 2026-06-16T22:00:00Z
source: <provenance>                  # seed | manual | autopublish | template
confidence: <0.0–1.0>                 # how confident is the author?
author: <name | team handle>
decision_type: <see types below>

# Light Palace taxonomy. v0.1.x: set manually. v0.1.5+: auto-filled from the
# publishing repo's repos.yaml entry. Path mirrors frontmatter:
#   kb/entries/<kingdom>/<palace>/<wing>/<hall>/<room>/<slug>.md
# See docs/KB-FOUNDATIONS.md for the full taxonomy reference.
kingdom: <from space.yaml::kingdoms>  # e.g., your-org
palace: <product / major system>      # free-form (emerges from use)
wing: <feature domain>                # free-form
hall: <knowledge type>                # free-form — architecture, conventions, lessons, debugging, meta, …
room: <specific topic>                # free-form; use `_` to skip

tunnels:                              # cross-references — slugs of related entries
  - <slug-of-related-entry>

tags:
  - <topic>
  - <another-topic>
```

Planned in v0.1.5+ (use these fields today; auto-fill + soft validation ship then):

- `kingdom`, `palace`, `wing` — auto-filled by `/teamvault-publish` from the binding repo's `repos.yaml` entry. Until v0.1.5 set them manually so the path mirrors frontmatter.
- Soft validation: WARN at publish if `kingdom` isn't in `space.yaml::kingdoms`. Never blocks.

Planned in v0.2+ (do NOT use yet):

- `entry_type` — generalizes `decision_type` to a controlled vocabulary
- `superseded_by` — filename of an entry that replaces this one
- `related_entries` — list of filenames for explicit graph edges (different from `tunnels`, which are inside the Palace taxonomy)

The frontmatter is BOTH human-readable metadata AND structured data the sidecar indexes. It feeds the `vault_search` text index (BM25), participates in vector embeddings (because tags + title get prepended into the contextual prefix), and surfaces in retrieval results so an agent knows what kind of entry it just read.

## Decision types (when to use each)

| Type | Use when… |
|------|-----------|
| **decision** | A choice was made. "We decided X because Y." Concrete, action-oriented. |
| **pattern** | A repeatable solution emerged. "When X happens, do Y. We've seen this work N times." |
| **postmortem** | Something broke. Include incident summary, root cause, what changed, what we'd do differently. |
| **policy** | A team rule. "Don't commit secrets to the repo." Often references regulations or BAAs. |
| **meta** | Documentation about how to use TeamVault itself — like this entry. |

## Body sections (typical layout)

Adapt these to fit the content. Not every entry needs every section.

### Context / Decision / Summary (the lede)

The thing. What was decided, what pattern emerged, what happened. One short paragraph.

### Why

The reasoning. Future readers ask "why did we do this?" — answer here. This is the most-load-bearing section because it's the part that doesn't decay: the decision may change, but knowing *why* the old one was made shapes whether to change it.

### What changed / Rules / Impact

The concrete consequences. What's now different. Bullets work well here.

### Open

Loose ends, follow-ups, or "we'll revisit on <date>." Optional.

### Related

Cross-references to other KB entries by plain filename. Example:

```markdown
## Related

- `2026-07-01-decision-something-else.md` — the decision this one depends on
- `2026-06-20-postmortem-related-incident.md` — the incident that motivated this
```

Don't use double-bracket `[[wiki-link]]` syntax — TeamVault doesn't parse it. Plain filename references read fine to humans and the search index treats them as ordinary tokens.

## Filename convention

```
kb/entries/<kingdom>/<palace>/<wing>/<hall>/<room>/YYYY-MM-DD-<slug>.md
```

The path mirrors the entry's `kingdom/palace/wing/hall/room` frontmatter level-for-level. Use `_` for any level you want to skip; trailing levels can be omitted entirely (drop `room` if the hall is granular enough).

- **v0.1.x:** set the path + frontmatter manually so they mirror.
- **v0.1.5+:** `/teamvault-publish` auto-fills `kingdom/palace/wing` from the binding repo's `repos.yaml` entry; you only specify `hall/room/tunnels` (and the slug).

### Examples

- **Project entry** at `kb/entries/your-org/example-product/backend/architecture/_/2026-06-22-example-palace-organized-entry.md` — worked example in the master template.
- **Tool meta-docs** (like this entry) live under the publishing org's kingdom: this entry's own path is `kb/entries/tin-io/teamvault/_/meta/_/2026-06-16-meta-how-to-write-a-kb-entry.md`.
- **Entries from an unbound repo** can use `_` for all levels until the team's structure emerges: `kb/entries/_/_/_/_/_/<slug>.md`. `/teamvault-publish` will WARN that the publishing repo has no Palace binding but won't block.

### Common rules

- `YYYY-MM-DD` is the entry's creation date (matches the `created` frontmatter field's date).
- `<slug>` is kebab-case, describes the topic. Keep it short (3–6 words).
- `/teamvault-publish` may append a content hash (`-<8-char-hex>.md`) to prevent slug collisions across teams that publish on the same day.

## How to publish

Use the slash command:

```
/teamvault-publish
```

Or ask the agent: "publish this to the KB — title '<title>', decision_type pattern, related to topic X."

The pack-runtime scrubbers run before the entry is written. If they catch PHI / secrets / patterns your team has banned (via `compliance: true` packs), the publish is refused and the entry never lands in the repo. Otherwise it's committed to `kb/entries/`, pushed, and re-indexed by every team member's sidecar within ~60 seconds.

## Why this entry exists

A fresh fork of the master template starts with an empty KB. That's bad for two reasons:

1. **First-search UX.** A dev's first `vault_search` returns "no results," which feels like the tool is broken even though it's working correctly.
2. **No format reference.** New entries are easier to write when there's a concrete example to pattern-match against.

This entry solves both: the indexer has something to chew on, and a human writing their first real entry can open this file and copy the shape.

## Related

(none — this is the template entry. Your future entries should list related filenames here.)
