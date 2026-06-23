"""TeamVault sidecar — hybrid search.

BM25 (SQLite FTS5) + Vector (LanceDB) → Reciprocal Rank Fusion → top-K.
"""
from __future__ import annotations

import sqlite3
from typing import Any

from sidecar import ingest


RRF_K = 60


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

    P0.7: under strict compliance posture, scrub `chunk`, `path`, and string
    values in `metadata` through a UNION-scrubber snapshot built ONCE per
    query. Path is included because slug-derived paths embed identifying
    info (e.g., `kb/entries/<kingdom>/<palace>/.../<slug>.md` — a slug
    derived from PHI content leaks PHI via the path even when the content
    is redacted).

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

    # Snapshot the scrubber once per query. Under permissive posture this
    # is the identity closure; under strict it carries a PackRuntime
    # snapshot so per-chunk + per-metadata-string calls don't re-instantiate.
    scrubber = compliance_mod.make_scrubber()

    results: list[dict[str, Any]] = []
    for content_hash, score, rep in fused[:top_k]:
        meta: dict[str, Any] = {}
        if "frontmatter_yaml" in rep and rep["frontmatter_yaml"]:
            try:
                meta = yaml.safe_load(rep["frontmatter_yaml"]) or {}
            except yaml.YAMLError:
                pass

        chunk = scrubber(rep.get("text", ""))
        path = scrubber(rep.get("entry_path", ""))
        meta = compliance_mod.scrub_metadata(meta, scrubber)

        results.append(
            {
                "path": path,
                "chunk": chunk,
                "score": float(score),
                "metadata": meta,
            }
        )
    return results
