"""TeamVault sidecar — hybrid search.

BM25 (SQLite FTS5) + Vector (LanceDB) → Reciprocal Rank Fusion → top-K.

P1.6 — temporal decay + access-count resistance applied to the fused score
before the top_k slice. `created` from frontmatter drives the decay; per-chunk
access counts persist in a side table in the same fts.db and are incremented
for every hit that makes it into the returned results.
"""
from __future__ import annotations

import logging
import math
import sqlite3
from datetime import date, datetime, timezone
from typing import Any

from sidecar import ingest


log = logging.getLogger("teamvault.sidecar.search")

RRF_K = 60

# Temporal decay constants — pattern per docs/ROADMAP.md::P1.6, KB-FOUNDATIONS pattern #4.
DECAY_FRESH_DAYS = 30        # ≤ this age in days → multiplier 1.0
DECAY_FLOOR_DAYS = 365       # ≥ this age in days → multiplier DECAY_FLOOR
DECAY_FLOOR = 0.5            # asymptotic floor at DECAY_FLOOR_DAYS+
ACCESS_BOOST_COEFFICIENT = 0.07   # 0 accesses → 1.0; 5 → ~1.13; 20 → ~1.21; 100 → ~1.32

# Audit-log tag for the current scoring regime. Derived from the constants so
# any change to decay/boost parameters auto-updates the string — retrospectives
# comparing audit-log entries across a parameter bump can detect the regime
# shift without anyone remembering to bump a literal.
SCORING_VERSION = (
    f"p1.6:fresh={DECAY_FRESH_DAYS}d,"
    f"floor={DECAY_FLOOR_DAYS}d@{DECAY_FLOOR},"
    f"boost={ACCESS_BOOST_COEFFICIENT}"
)


def decay_multiplier(age_days: float | None) -> float:
    """Temporal decay multiplier from age in days.

    1.0× when age ≤ DECAY_FRESH_DAYS; linear interpolation to DECAY_FLOOR at
    DECAY_FLOOR_DAYS; clamped to DECAY_FLOOR for older entries. Missing or
    invalid ages (None) get 1.0 — never penalize an entry for missing metadata.
    Future-dated entries (negative age) also get 1.0 — likely clock skew, not
    reason to demote.
    """
    if age_days is None or age_days <= DECAY_FRESH_DAYS:
        return 1.0
    if age_days >= DECAY_FLOOR_DAYS:
        return DECAY_FLOOR
    span = DECAY_FLOOR_DAYS - DECAY_FRESH_DAYS
    return 1.0 - (1.0 - DECAY_FLOOR) * (age_days - DECAY_FRESH_DAYS) / span


def access_boost(count: int) -> float:
    """Mild boost from access count. ``1 + c·log(1+count)``. Bounded growth so
    a very popular chunk can't dominate purely on count, but a frequently-used
    chunk resists decay enough to keep it visible past 30d.
    """
    if count <= 0:
        return 1.0
    return 1.0 + ACCESS_BOOST_COEFFICIENT * math.log(1 + count)


def _chunk_age_days(meta: dict[str, Any]) -> float | None:
    """Extract age in days from a frontmatter dict's ``created`` field.

    Accepts datetime / date / ISO-8601 string. Returns None for missing or
    unparseable values (caller should treat as no decay).
    """
    if not meta:
        return None
    raw = meta.get("created")
    if raw is None:
        return None
    now = datetime.now(timezone.utc)
    created_dt: datetime | None = None
    if isinstance(raw, datetime):
        created_dt = raw if raw.tzinfo else raw.replace(tzinfo=timezone.utc)
    elif isinstance(raw, date):
        # plain date → midnight UTC of that day
        created_dt = datetime(raw.year, raw.month, raw.day, tzinfo=timezone.utc)
    else:
        s = str(raw).strip()
        if not s:
            return None
        # Try full ISO-8601 first, then YYYY-MM-DD only.
        try:
            # Python 3.11+ handles trailing 'Z' in fromisoformat; older needs replace.
            created_dt = datetime.fromisoformat(s.replace("Z", "+00:00"))
            if created_dt.tzinfo is None:
                created_dt = created_dt.replace(tzinfo=timezone.utc)
        except ValueError:
            try:
                d = date.fromisoformat(s[:10])
                created_dt = datetime(d.year, d.month, d.day, tzinfo=timezone.utc)
            except ValueError:
                return None
    if created_dt is None:
        return None
    return (now - created_dt).total_seconds() / 86400.0


def _ensure_access_counts_table(conn: sqlite3.Connection) -> None:
    """Idempotent table creation. Called at the top of any access-count read
    or write so the search path doesn't depend on ingest having run first.
    """
    conn.execute(
        "CREATE TABLE IF NOT EXISTS access_counts("
        "content_hash TEXT PRIMARY KEY, "
        "count INTEGER NOT NULL DEFAULT 0, "
        "last_accessed TEXT)"
    )


def _read_access_counts(space: str, hashes: list[str]) -> dict[str, int]:
    """Bulk lookup of access counts for a set of content hashes.

    Returns {hash: count}; absent hashes default to 0 at the call site.
    Returns {} early if the fts.db file hasn't been created yet (no ingest
    has run) — first-search semantics: no recorded accesses.

    Concurrency note: this read can race with a parallel
    ``_increment_access_counts`` call against the same fts.db. The window
    is benign: the UPSERT is atomic, so no count is ever lost; the only
    cost is that a concurrent search might score against a slightly stale
    count (off by 1, possibly more under contention). This shifts the
    *order* of two near-equal hits by a tiny boost — never enough to
    promote a low-RRF, never-accessed chunk over a high-RRF recent one.
    """
    if not hashes:
        return {}
    hash_list = list(hashes)
    fts_path = ingest._fts_db_path(space)
    if not fts_path.exists():
        return {}
    conn = sqlite3.connect(fts_path, timeout=30.0)
    try:
        _ensure_access_counts_table(conn)
        placeholders = ",".join("?" for _ in hash_list)
        rows = conn.execute(
            f"SELECT content_hash, count FROM access_counts WHERE content_hash IN ({placeholders})",
            hash_list,
        ).fetchall()
    finally:
        conn.close()
    return {h: c for h, c in rows}


def _increment_access_counts(space: str, hashes: list[str]) -> None:
    """Bump access_count + last_accessed for each hash. Idempotent per call
    (one bump per hash); concurrent calls each get their own bump.
    """
    if not hashes:
        return
    hash_list = list(hashes)
    fts_path = ingest._fts_db_path(space)
    # Don't materialize an empty fts.db just for access counts; if ingest
    # hasn't run, there's nothing to rank against either.
    if not fts_path.exists():
        return
    now_iso = datetime.now(timezone.utc).isoformat()
    conn = sqlite3.connect(fts_path, timeout=30.0)
    try:
        _ensure_access_counts_table(conn)
        # ON CONFLICT UPSERT: insert with count=1 OR bump existing count by 1.
        conn.executemany(
            "INSERT INTO access_counts(content_hash, count, last_accessed) "
            "VALUES (?, 1, ?) "
            "ON CONFLICT(content_hash) DO UPDATE SET "
            "count = count + 1, last_accessed = excluded.last_accessed",
            [(h, now_iso) for h in hash_list],
        )
        conn.commit()
    finally:
        conn.close()


def _fts_search(space: str, query: str, top_k: int) -> list[dict[str, Any]]:
    fts_path = ingest._fts_db_path(space)
    if not fts_path.exists():
        return []
    conn = sqlite3.connect(fts_path)
    try:
        # FTS5 MATCH on raw query; fall back to LIKE if MATCH errors on reserved chars
        try:
            rows = conn.execute(
                """
                SELECT content_hash, entry_path, chunk_index, text, bm25(chunks) AS s
                FROM chunks
                WHERE chunks MATCH ?
                ORDER BY bm25(chunks)
                LIMIT ?
                """,
                (query, top_k),
            ).fetchall()
        except sqlite3.OperationalError:
            rows = conn.execute(
                """
                SELECT content_hash, entry_path, chunk_index, text, 0.0
                FROM chunks
                WHERE text LIKE ?
                LIMIT ?
                """,
                (f"%{query}%", top_k),
            ).fetchall()
    finally:
        conn.close()
    return [
        {"content_hash": r[0], "entry_path": r[1], "chunk_index": r[2], "text": r[3], "bm25_score": r[4]}
        for r in rows
    ]


def _vector_search(space: str, query: str, top_k: int) -> list[dict[str, Any]]:
    import lancedb
    import numpy as np

    db = lancedb.connect(str(ingest._vault_db_path(space)))
    if "chunks" not in db.table_names():
        return []
    table = db.open_table("chunks")

    model = ingest.get_model()
    # encode([str]) returns a stable-shaped 2D array regardless of model version.
    vec = np.asarray(
        model.encode([f"search_query: {query}"], normalize_embeddings=True, show_progress_bar=False)
    ).reshape(-1).tolist()

    rows = table.search(vec).limit(top_k).to_list()
    return rows


def _rrf_fuse(bm25_hits: list[dict], vec_hits: list[dict], k: int = RRF_K):
    """RRF fusion. Vector hits carry richer metadata (frontmatter_yaml), so when both
    paths see the same content_hash we prefer the vector row as the representative.
    """
    scores: dict[str, float] = {}
    rep: dict[str, dict] = {}
    for rank, hit in enumerate(bm25_hits):
        h = hit["content_hash"]
        scores[h] = scores.get(h, 0.0) + 1.0 / (k + rank + 1)
        rep.setdefault(h, hit)  # only fill if no vector rep yet
    for rank, hit in enumerate(vec_hits):
        h = hit["content_hash"]
        scores[h] = scores.get(h, 0.0) + 1.0 / (k + rank + 1)
        # Always prefer vector representative (carries frontmatter_yaml + full row)
        rep[h] = hit
    return sorted(((h, s, rep[h]) for h, s in scores.items()), key=lambda x: -x[1])


def hybrid_search(query: str, top_k: int, space: str) -> list[dict[str, Any]]:
    """Hybrid BM25 + vector search with RRF fusion.

    P1.6 (ranking): apply ``decay_multiplier(age_days) * access_boost(count)``
    to every fused candidate BEFORE the top_k slice, so a recent or
    frequently-accessed older chunk can outrank a higher-RRF stale one.
    Access counts are incremented for the returned top_k after scoring (the
    write happens before scrubbing so the counter reflects what was actually
    delivered to the caller, even if scrubbing redacts the visible text).

    P0.7 (egress): under strict compliance posture, scrub `chunk`, `path`,
    and string values in `metadata` through a UNION-scrubber snapshot built
    ONCE per query. Path is included because slug-derived paths embed
    identifying info (e.g., `kb/entries/<kingdom>/<palace>/.../<slug>.md` —
    a slug derived from PHI content leaks PHI via the path even when the
    content is redacted).

    Defense-in-depth: chunks SHOULD have been scrubbed at publish time
    (via publish.py's pack-runtime call). Anything that escaped that scrub
    (manual git commit bypassing /teamvault-publish, stale pre-pack
    content) gets caught here.

    Fail-closed: if the scrubber pipeline cannot complete (broken pack,
    oversize input, etc.), the affected field returns the sentinel
    `[SCRUB_UNAVAILABLE]` rather than unscrubbed text.
    """
    import yaml

    from sidecar import compliance as compliance_mod

    bm25 = _fts_search(space, query, top_k * 2)
    vec = _vector_search(space, query, top_k * 2)
    fused = _rrf_fuse(bm25, vec)

    # ---- P1.6: apply temporal decay + access boost to fused candidates ----
    # Parse frontmatter once per candidate; cache so scrubbing loop can reuse.
    candidate_meta: dict[str, dict[str, Any]] = {}
    for content_hash, _score, rep in fused:
        meta: dict[str, Any] = {}
        if "frontmatter_yaml" in rep and rep["frontmatter_yaml"]:
            try:
                meta = yaml.safe_load(rep["frontmatter_yaml"]) or {}
            except yaml.YAMLError:
                pass
        candidate_meta[content_hash] = meta

    counts = _read_access_counts(space, [h for h, _, _ in fused])
    adjusted: list[tuple[str, float, dict[str, Any]]] = []
    for content_hash, rrf_score, rep in fused:
        age = _chunk_age_days(candidate_meta[content_hash])
        decay = decay_multiplier(age)
        boost = access_boost(counts.get(content_hash, 0))
        adjusted.append((content_hash, rrf_score * decay * boost, rep))
    adjusted.sort(key=lambda x: -x[1])
    final_hits = adjusted[:top_k]

    # ---- Bump access counters for what we're about to return ----
    # Done BEFORE scrubbing so the counter reflects delivery, not display.
    # Wrapped in try/except so a counter-write failure (disk-full, db-locked)
    # never takes down /search — counters are advisory, ranking already
    # happened. Surfaced as a warning so /teamvault-doctor and recent_errors
    # pick it up. (Finding #1 from /code-review, this PR.)
    try:
        _increment_access_counts(space, [h for h, _, _ in final_hits])
    except Exception as e:  # noqa: BLE001 — never let counter writes fail /search
        log.warning(
            "access_counts increment failed (n=%d): %s",
            len(final_hits),
            e,
            extra={"space": space},
        )

    # ---- P0.7: scrub for egress ----
    # Snapshot the scrubber once per query. Under permissive posture this
    # is the identity closure; under strict it carries a PackRuntime
    # snapshot so per-chunk + per-metadata-string calls don't re-instantiate.
    scrubber = compliance_mod.make_scrubber()

    results: list[dict[str, Any]] = []
    for content_hash, score, rep in final_hits:
        chunk = scrubber(rep.get("text", ""))
        path = scrubber(rep.get("entry_path", ""))
        meta = compliance_mod.scrub_metadata(candidate_meta[content_hash], scrubber)

        results.append(
            {
                "path": path,
                "chunk": chunk,
                "score": float(score),
                "metadata": meta,
            }
        )
    return results
