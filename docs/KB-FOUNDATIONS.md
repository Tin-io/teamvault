# 📐 Knowledge Base Architecture — Overview

> 📐 **Reference document.** Generic distillation of the underlying KB pattern catalog (markdown-as-substrate, hybrid BM25+vector+RRF, contextual retrieval, paragraph chunking, temporal decay, content-hash dedup, Mem Palace taxonomy) that TeamVault's runtime implements. The catalog is broader than what v0.0 ships; the shipped subset is summarized in [ARCHITECTURE.md §10](ARCHITECTURE.md) (retrieval pipeline). User-facing entry point: [USER_GUIDE.md](USER_GUIDE.md).

> A generic, shareable distillation of the KB architecture that emerged through convergent evolution across several independent knowledge-base systems built for different audiences — personal institutional memory, autonomous coding agents, end-user content search, and debugging workflows.

**Audience:** Anyone designing, building, or evaluating a knowledge base — internally or for collaboration.
**Scope:** The architecture, the retrieval methodology, the taxonomy, and the decision framework. Project-agnostic.

---

## The convergence story (1 paragraph)

Between April and May 2026, five independent teams — each building knowledge bases for different audiences (personal institutional memory, autonomous coding agents, end-user content search, video transcripts, debugging workflows) — rejected framework-heavy approaches (Bedrock KB, MemPalace, S3 Vectors) and independently converged on the same custom retrieval architecture. The systems span local-first ($0/month) and AWS-hosted (~$0.03/month) implementations, but run the same methodology. The convergence is the validation: five teams optimizing for different problems arrived at the same pattern. This document captures that pattern, generically.

---

## Six core principles

1. **Markdown + YAML frontmatter is the source of truth — and it's rich enough to be its own data layer.** Git-tracked, reviewable, diffable. The substrate is the architecture; retrieval is one consumer of it. Other access patterns (browse, filter, traverse, exact-search) are equally valid and equally available.
2. **Indexes are disposable; the substrate is durable.** SQLite, LanceDB, pgvector are derivative artifacts — rebuildable from markdown in minutes. The implication: you can experiment freely with new access patterns (new embedding model, new fusion strategy, new graph algorithm) without ever risking the source of truth.
3. **Hybrid retrieval beats either alone.** Run text-search (BM25) and vector-search in parallel; fuse with Reciprocal Rank Fusion. Industry: 91% recall@10 hybrid vs. 78% vector-only.
4. **Contextual chunks ground meaning.** Prepend a 1-2 sentence document-level context to each chunk *before* embedding. Anthropic research: 35% retrieval-failure reduction alone, 67% combined with hybrid.
5. **Hierarchical taxonomy enables intentional cross-domain sharing.** Mem Palace structure (Kingdom → Palace → Wing → Hall → Room + tunnels for cross-references). Depth chosen per organizational complexity.
6. **Custom code over frameworks.** ~400-640 LOC of custom implementation matches or exceeds framework-based equivalents and avoids vendor lock-in.

---

## The data substrate — value before retrieval

The retrieval pipeline (described below) is the most visible part of the architecture, but it's not the architecture's strongest property. The strongest property is that the **data substrate beneath retrieval is independently valuable**, queryable through multiple access patterns without any ML round-trip. The pre-retrieval layers are listed here.

### Pre-retrieval layers

| Layer | What it is | What it enables (no ML needed) |
|---|---|---|
| **YAML frontmatter** | Structured metadata at the top of every doc (palace, wing, hall, tags, source, confidence, dates, repos, tunnels) | Direct SQL / jq / grep queries — filter by author, source, date, topic, confidence |
| **Hierarchical filesystem** | Directory tree = the taxonomy | Tree-browse navigation; file listings as a catalog; no index needed |
| **Tunnels + composes graphs** | Cross-reference edges in frontmatter + composition relationships between artifacts | Graph traversal, neighbor queries, importance ranking, community detection |
| **BM25 / FTS5 text index** | Pure keyword search | Exact-match queries without embedding cost or quality variance — critical for code, identifiers, error codes, fixed phrases |
| **Content-hash manifest** | SHA-256 ledger of every doc + chunk | Dedup, audit trail, idempotent re-ingest |
| **Provenance metadata** | `source`, `repos[]`, `created`, `last_validated`, `extracted_from` | Auditable lineage, freshness checks, filter-by-origin |
| **Curation signals** | `confidence` (0-100), drafts gate, privacy gate filtering | Quality routing without semantic ML |
| **Reinforcement counters** | `access_count`, `last_accessed_at`, dedup folding | Popularity surfaces without inference |
| **Contextual prefixes (ingest-time)** | LLM-generated 1-2 sentence document-level context, prepended to each chunk | Becomes durable enriched text — human-readable AND searchable via plain BM25 |

### Concrete queries you can answer without embeddings

```
- "All architecture decisions modified in the last 30 days"
   → frontmatter SQL: `hall=architecture AND last_validated >= 2026-05`

- "Everything that references both `auth` and `payments`"
   → tunnel join across tag dimensions

- "Which lessons came from debugging sessions in 2026-Q1?"
   → source + temporal filter on frontmatter

- "What's the most-accessed entry in `discover-layer`?"
   → access_count sort, scoped by wing

- "Have I already ingested this PDF?"
   → SHA-256 lookup on the content-hash manifest
```

Each query hits a different pre-retrieval layer. None invoke an embedding model. They run in milliseconds against structured data.

### Composability — adopt any subset

The architecture is a **stack of independent layers**. A consumer can adopt any subset and get value at each step:

```
frontmatter + hierarchy           → metadata-driven navigation + audit
+ FTS5 / tsvector                 → keyword search
+ manifests + dedup               → catalog + quality control
+ curation gates                  → trust signals
+ tunnels + composes              → graph queries
+ vector store                    → semantic search
+ RRF fusion                      → hybrid retrieval
+ RAG synthesis                   → generated answers
```

Each layer is independently shippable. You don't have to commit to the whole stack — start with the substrate, layer on what your use case demands.

---

## The Mem Palace taxonomy

A 5-level hierarchy plus cross-reference edges. Depth is chosen per use case — flat wings work for personal KBs; the full stack fits multi-product organizations.

| Level | Purpose | Example |
|---|---|---|
| **Kingdom** | Top-level organizational container | "your-org" |
| **Palace** | One per product or major system | "web-app", "billing-service", "mobile-app" |
| **Wing** | Feature domain within a palace | "auth", "search", "deployment" |
| **Hall** | Knowledge type | "architecture", "conventions", "lessons", "debugging", "resolution" |
| **Room** | Specific topic | "auth-relay-timeout", "cloudfront-oac-policy" |
| **Tunnels** | Cross-references between rooms | Tags linking related rooms across wings/palaces |

**Depth matrix:**

| System type | Recommended depth |
|---|---|
| Personal knowledge base | Wings only (flat) |
| Single-product organizational KB | Wing/hall/room |
| Multi-product organization | Full Kingdom/palace/wing/hall/room |
| Cross-org reference (this doc) | Variable — palace per partner org |

**Tunnels in practice:** an entry about "SDK version alignment breaks the web client" lives in `web-app/client-sdk/lessons` but tunnels to `design-system`, `infrastructure` (npm publishing), and `conventions` (semver policy). Structural location is one; semantic neighbors are many.

---

## The retrieval methodology — seven steps

```
1. CHUNK     at paragraph boundaries (450-512 tokens), with 10-15% overlap
2. PREFIX    each chunk with 1-2 sentence document-level context
3. EMBED     the prefixed chunk (Nomic, Titan, or equivalent)
4. INDEX     into a vector store + parallel text index (BM25)
5. QUERY     both indexes in parallel — same query, two paths
6. FUSE      via Reciprocal Rank Fusion (RRF, k=60)
7. RE-RANK   by temporal decay + multi-scope relevance (optional)
```

**Key formulas:**

- **RRF:** `score = 1/(k + rank_bm25) + 1/(k + rank_vector)` where k=60. Alpha=0.5 for balanced; alpha=0.6 for spoken/prose-heavy.
- **Temporal decay:** Linear from 1.0× (≤30 days) to 0.5× floor at 365 days, with access-count resistance (frequently-accessed docs decay slower).
- **Multi-scope relevance:** Junction table `(document_id, wing, relevance_score)`. A document can belong to multiple wings with different relevance per wing.

Each step is independent. Drop the ones your use case doesn't need.

---

## Pattern catalog (10 patterns)

Each pattern is independently adoptable. Apply the ones your scale and use case require.

| # | Pattern | Essence | Apply when |
|---|---|---|---|
| 1 | **Hybrid BM25 + Vector + RRF** | Two parallel search paths fused with RRF | Any KB with mixed keyword + conceptual queries |
| 2 | **Contextual retrieval** | Prepend doc-level context to each chunk before embedding | Whenever chunks < full doc; especially small chunks |
| 3 | **Paragraph chunking** | Split at `\n\n`; 450-512 tok; 10-15% overlap | Docs > ~500 tokens needing precise paragraph retrieval |
| 4 | **Temporal decay** | Recent ranks higher; access-count resists decay | KBs where freshness matters (debugging, decisions) |
| 5 | **Multi-scope relevance** | One doc, multiple wings, per-wing weights | Cross-cutting knowledge across domains |
| 6 | **Content-hash dedup** | SHA-256 on full text; skip if already indexed | Any automated ingest where the same doc might be processed twice |
| 7 | **Progressive multi-layer retrieval** | Search scoped first, fall back to broader scope | Multi-domain KBs where most queries target a specific area |
| 8 | **Palace metadata hierarchy** | Kingdom/Palace/Wing/Hall/Room | Multi-product organizations with shared & distinct knowledge |
| 9 | **Content-type-aware RRF weighting** | Tune alpha per content type | Mixed content (code vs. prose vs. spoken word) |
| 10 | **RAG synthesis** | LLM generates sourced answers from results | User-facing search where consumer wants an answer, not a list |

---

## Pattern selection matrix

Read across a row for each pattern; read down a column for your constraints.

| Pattern | Scale <1K | Scale 1K-100K | Scale >100K | Code/config | Prose | Spoken | Local-first | AWS | High freshness | Multi-domain |
|---|:-:|:-:|:-:|:-:|:-:|:-:|:-:|:-:|:-:|:-:|
| 1. Hybrid + RRF | Rec | **Req** | **Req** | **Req** | Rec | Rec | Rec | Rec | — | — |
| 2. Contextual prefix | Opt | Rec | **Req** | Rec | Rec | **Req** | Rec | Rec | — | — |
| 3. Paragraph chunking | Skip | Rec | **Req** | Rec | Rec | **Req** | Rec | Rec | — | — |
| 4. Temporal decay | Opt | Rec | Rec | Rec | Skip | Skip | Rec | Rec | **Req** | — |
| 5. Multi-scope | Skip | Opt | Rec | Opt | Opt | Opt | Opt | Opt | — | **Req** |
| 6. Hash dedup | Opt | Rec | **Req** | Rec | Rec | Rec | Rec | Rec | — | — |
| 7. Progressive | Skip | Opt | Rec | Opt | Opt | Opt | Opt | Opt | — | Rec |
| 8. Palace hierarchy | Skip | Opt | Opt | Opt | Opt | Skip | Opt | Opt | — | **Req** |
| 9. Content-type RRF | Skip | Opt | Opt | Skip | Skip | **Req** | Opt | Opt | — | Opt |
| 10. RAG synthesis | Opt | Rec | Rec | Opt | Rec | Rec | Opt | Rec | — | — |

**Key:** **Req** = required · Rec = recommended · Opt = optional · Skip = adds complexity without benefit · — = not relevant

**Worked example.** "I'm building a local-first KB for 200 debugging docs across multiple product domains, where freshness matters." → Hybrid+RRF (Rec), contextual prefix (Opt), temporal decay (**Req**), multi-scope (**Req**), palace hierarchy (**Req**), dedup (Opt). Skip chunking and progressive retrieval at this scale.

---

## Two reference implementations

Both run the same retrieval methodology. Pick based on operational shape, not architecture.

| Aspect | Local-first | AWS-hosted |
|---|---|---|
| **Vector store** | LanceDB (file-based, HNSW) | pgvector on RDS (1024-dim, HNSW) |
| **Embedding model** | Nomic Embed v1.5 (local, 768-dim) | Amazon Titan Embed v2 (Bedrock, 1024-dim) |
| **Text search** | SQLite FTS5 (BM25 + porter stemmer) | PostgreSQL tsvector + ts_rank_cd |
| **LLM (for prefixes / RAG)** | `claude -p` via subscription | Bedrock Haiku |
| **Transport** | FastMCP (local stdio) | API Gateway + Lambda + MCP wrapper |
| **Distribution** | git pull → rebuild local indexes | Centralized DB; clients hit API |
| **Source of truth** | Markdown in git | Markdown in git |
| **Cost** | $0/month | ~$0.03-5/month |
| **Use when** | Per-user/per-dev tools, offline-ok, $0 ops | Shared multi-user state, non-CLI clients (mobile, web), centralized analytics |

The migration path between them is bounded: markdown source doesn't change; only the index backend swaps. Plan local-first; promote to hosted only when the operational shape demands it.

---

## How the validated systems vary

All of these systems share the architecture above. They differ in scale, content type, deployment, and depth — captured here at a glance:

| System | Audience | Stack | Distinctive choices |
|---|---|---|---|
| **Personal vault** | Single user (institutional memory) | LanceDB + SQLite FTS5 + Nomic, local | Flat wings (no full palace stack); 500+ docs; steady monthly growth |
| **Autonomous-coding KB** | Coding agents | pgvector + Titan + Bedrock Haiku, AWS | Wing/hall/room; Haiku-generated prefixes; progressive retrieval designed |
| **Content-search API** | End users (content discovery) | pgvector + Titan + tsvector, AWS | Full-doc embedding (no chunking); RAG synthesis via SSE; permission-aware |
| **Transcript-search pipeline** | End users (video search) | Inherits the content-search stack + pipeline-side Haiku prefixes | 4-way RRF (content+transcript × FT+semantic); 0.6 alpha for spoken word |
| **Debugging KB** | Cross-team debuggers | Local-first, recommended LanceDB+FTS5 | Introduces the Kingdom layer; multi-product hierarchy |
| **Cross-repo developer KB** | Coding agent sessions | Same as the personal-vault stack, local-first | Multi-palace taxonomy; per-dev drafts with privacy-gated extraction; git-distributed |

The architecture flexes to fit the audience. The methodology is the same.

---

## Why custom over frameworks

Three frameworks were evaluated and rejected across multiple teams:

1. **Bedrock Knowledge Bases** — $44/month base cost, opinionated chunking incompatible with multi-domain hierarchies, hard to extend with custom fusion.
2. **S3 Vectors** — 2 KB metadata limit blocks the rich frontmatter (palace/wing/hall/room/tunnels) that hierarchical retrieval depends on.
3. **MemPalace library** — Over-abstraction; ChromaDB lock-in; protocol surface didn't fit hybrid retrieval needs.

Each team independently chose ~400-640 LOC of custom code over framework dependencies. The patterns above are simple enough that "custom" is cheaper than learning a framework's quirks — and produces a system that fits the domain rather than vice versa.

---

## When this architecture fits (and doesn't)

| Fit | Skip — use something else |
|---|---|
| Hybrid keyword + semantic search needs | Pure semantic only (vector-only suffices) |
| Markdown / structured-text source | Binary / multimedia as primary source |
| ~100 to ~10M documents | Web-scale (>100M) — use a search platform like OpenSearch/Elastic |
| Multi-domain knowledge | Single flat domain (simple tagging works) |
| MCP-accessible from agents | Pure human-search-UI only (no agent consumers planned) |
| Self-managed infrastructure ok | Need a fully-managed SaaS (then accept the cost/lock-in tradeoff) |

---

## Validated by

This architecture is validated by production deployment or active development across:

- **The personal vault** — production, 500+ documents, months of operation
- **The autonomous-coding KB** — MVP shipped, an agent in production using it
- **The content-search API** — production search API serving end users
- **The transcript-search pipeline** — bulk ingestion in progress
- **The cross-repo developer KB** — planning complete (the newest system; the rest are reference)
- **The debugging KB** — planning complete, implementation pending

The convergent validation across these systems (independent teams, different audiences, same patterns) is the strongest argument for the architecture.

---

## Living document

This is a distilled, shareable overview of patterns validated across multiple independent systems — generic enough to adopt in any project.

Update this overview when:
- A new pattern emerges and proves itself in two or more systems
- A reference implementation choice changes meaningfully (e.g., new embedding model becomes standard)
- The "when to use" guidance shifts based on production experience

For ongoing-state details (who's shipped what), maintain the master reference rather than this overview.

---

*Distilled from the master reference and from cross-system planning artifacts. Free to share.*
