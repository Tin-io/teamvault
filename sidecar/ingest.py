"""TeamVault sidecar — ingest pipeline.

scan kb/entries/*.md → parse frontmatter + body → chunk paragraph-bounded
(target 512 tokens ~= 2048 chars, 64 overlap ~= 256 chars) → embed via
Nomic Embed v1.5 768d → content-hash dedup → write LanceDB (vector) + SQLite FTS5 (text).

Idempotent: re-running is a no-op aside from re-hashing time.

v0.1 stretch — contextual retrieval prefixes
--------------------------------------------
Each chunk is prepended with a 1-2 sentence document-level context string
(title, entry_type, created_date, tags, short_summary) BEFORE embedding and
BEFORE writing to FTS5. This implements the static (no-LLM) variant per
``docs/ROADMAP.md::P1.5``. v0.1.5 will add an LLM-generated variant
(per-chunk Haiku call) as an opt-in.

NOTE: because the embedded/indexed text now includes the prefix, the
content-hash of every chunk changes. Existing v0.0 vault.db files will fully
reindex from scratch on first run with v0.1. That's expected and acceptable.
"""
from __future__ import annotations

import hashlib
import re
import sqlite3
import threading
from dataclasses import dataclass
from pathlib import Path
from typing import Iterator

from sidecar import config


_MODEL_NAME = "nomic-ai/nomic-embed-text-v1.5"
_EMBED_DIM = 768

# Chunking heuristic — char proxy for tokens (1 tok ~= 4 chars).
# v0.1 should move to tokenizer-true counts.
CHUNK_CHARS = 512 * 4    # 2048
OVERLAP_CHARS = 64 * 4   # 256


_model = None
_model_lock = threading.Lock()
_ingest_lock = threading.Lock()


def get_model():
    """Thread-safe lazy load of the Nomic Embed model. ~547MB download on first call."""
    global _model
    if _model is None:
        with _model_lock:
            if _model is None:
                from sentence_transformers import SentenceTransformer
                _model = SentenceTransformer(_MODEL_NAME, trust_remote_code=True)
    return _model


@dataclass
class Chunk:
    text: str
    entry_path: str
    chunk_index: int
    content_hash: str
    frontmatter: dict
    # v0.1 stretch: per-entry contextual prefix, prepended to ``text`` for
    # both embedding and FTS5 indexing. Computed once per entry in
    # ``chunk_entry`` and shared across all chunks of that entry.
    prefix: str = ""


# Maximum number of tags rendered in the static prefix. Keeps the prefix
# short enough that it doesn't dominate the chunk content during embedding.
_PREFIX_MAX_TAGS = 6
# Truncate the body-extracted short summary to this many characters before
# rolling back to a sentence boundary.
_PREFIX_SUMMARY_MAX_CHARS = 120


def _extract_h1_title(body: str) -> str | None:
    """Return the first markdown H1 (``# Title``) in body, or None."""
    for line in body.splitlines():
        line = line.strip()
        if line.startswith("# ") and not line.startswith("## "):
            return line[2:].strip() or None
    return None


def _strip_leading_h1(body: str) -> str:
    """Drop the first H1 line (and any leading blank lines) from body."""
    lines = body.splitlines()
    out: list[str] = []
    dropped = False
    for line in lines:
        if not dropped and line.strip().startswith("# ") and not line.strip().startswith("## "):
            dropped = True
            continue
        out.append(line)
    return "\n".join(out).lstrip()


def _short_summary(body: str, max_chars: int = _PREFIX_SUMMARY_MAX_CHARS) -> str:
    """Return the first ``max_chars`` of the body (post-H1) ending at a
    sentence boundary where possible. Markdown heading lines are dropped so
    the summary reads as prose, not section markers.
    """
    stripped = _strip_leading_h1(body)
    # Drop pure heading lines (## Heading, ### Heading, ...) — they add no
    # semantic value to the summary and look like noise in the prefix.
    prose_lines = [
        ln for ln in stripped.splitlines() if not re.match(r"^\s*#{1,6}\s+\S", ln)
    ]
    # Collapse markdown structure into a flowing single-line string so the
    # summary reads naturally inside the prefix.
    flat = re.sub(r"\s+", " ", "\n".join(prose_lines)).strip()
    if not flat:
        return ""
    if len(flat) <= max_chars:
        return flat
    window = flat[:max_chars]
    # Prefer the last sentence-ending punctuation inside the window.
    for sep in (". ", "! ", "? "):
        idx = window.rfind(sep)
        if idx >= int(max_chars * 0.5):
            return window[: idx + 1].strip()
    # Fall back to the last whitespace boundary.
    idx = window.rfind(" ")
    if idx >= int(max_chars * 0.5):
        return window[:idx].rstrip() + "…"
    return window.rstrip() + "…"


def make_context_prefix(frontmatter: dict, body: str, *, fallback_title: str | None = None) -> str:
    """Build a 1-2 sentence document-level context prefix.

    Static (no-LLM) template — v0.1.0 ships this; v0.1.5 will add an
    LLM-generated variant. Inputs are the entry's parsed frontmatter dict
    and the entry body. ``fallback_title`` is used when no H1 is present
    (typically the filename stem).

    Output shape::

        From "{title}" ({entry_type}, {created}). Tags: {tags_csv}. {short_summary}

    Each field has a sane fallback so a malformed or empty entry still
    produces a valid (if minimal) prefix.
    """
    fm = frontmatter or {}

    title = _extract_h1_title(body or "") or (fallback_title or "untitled")
    entry_type = str(fm.get("decision_type") or "entry").strip() or "entry"

    created_raw = fm.get("created")
    if created_raw is None:
        created = "unknown date"
    else:
        # Accept datetime, date, or string; render as YYYY-MM-DD.
        try:
            from datetime import date, datetime

            if isinstance(created_raw, datetime):
                created = created_raw.date().isoformat()
            elif isinstance(created_raw, date):
                created = created_raw.isoformat()
            else:
                created = str(created_raw)[:10]
        except Exception:
            created = str(created_raw)[:10]

    raw_tags = fm.get("tags") or []
    if isinstance(raw_tags, str):
        raw_tags = [raw_tags]
    try:
        tag_list = [str(t).strip() for t in raw_tags if str(t).strip()]
    except TypeError:
        tag_list = []
    tag_list = tag_list[:_PREFIX_MAX_TAGS]
    tags_csv = ", ".join(tag_list) if tag_list else "none"

    summary = _short_summary(body or "")

    head = f'From "{title}" ({entry_type}, {created}). Tags: {tags_csv}.'
    if summary:
        return f"{head} {summary}"
    return head


def _split_long_para(para: str, max_chars: int) -> list[str]:
    """Hard-split a single paragraph exceeding max_chars on sentence/whitespace boundaries.
    Falls back to char-bounded slices if no good boundary exists.
    """
    if len(para) <= max_chars:
        return [para]
    pieces: list[str] = []
    remaining = para
    while len(remaining) > max_chars:
        # Prefer breaking at sentence/whitespace within last 20% of the window
        window_lo = int(max_chars * 0.8)
        slice_ = remaining[:max_chars]
        break_at = max(slice_.rfind(". ", window_lo), slice_.rfind("\n", window_lo), slice_.rfind(" ", window_lo))
        if break_at <= 0:
            break_at = max_chars
        pieces.append(remaining[:break_at].rstrip())
        remaining = remaining[break_at:].lstrip()
    if remaining:
        pieces.append(remaining)
    return pieces


def paragraph_chunk(body: str, max_chars: int = CHUNK_CHARS, overlap: int = OVERLAP_CHARS) -> Iterator[str]:
    """Split at \\n\\n, merge paragraphs up to max_chars, with overlap between chunks.
    Hard-splits a single paragraph exceeding max_chars on sentence/whitespace boundaries.
    """
    raw_paras = [p.strip() for p in body.split("\n\n") if p.strip()]
    paras: list[str] = []
    for p in raw_paras:
        paras.extend(_split_long_para(p, max_chars))

    current: list[str] = []
    cur_len = 0

    def emit_and_reset() -> tuple[str, list[str], int]:
        chunk = "\n\n".join(current)
        tail: list[str] = []
        tail_len = 0
        for tp in reversed(current):
            cost = len(tp) + 2
            if tail_len + cost > overlap:
                break
            tail.insert(0, tp)
            tail_len += cost
        return chunk, tail, sum(len(t) + 2 for t in tail)

    out: list[str] = []
    for p in paras:
        cost = len(p) + 2
        if cur_len + cost > max_chars and current:
            chunk, current, cur_len = emit_and_reset()
            out.append(chunk)
        current.append(p)
        cur_len += cost
    if current:
        out.append("\n\n".join(current))
    return iter(out)


def chunk_entry(path: Path) -> list[Chunk]:
    import frontmatter

    post = frontmatter.load(str(path))
    fm = dict(post.metadata or {})
    body = post.content or ""
    # Compute the entry-level prefix once per file; every chunk of this entry
    # shares the same prefix.
    prefix = make_context_prefix(fm, body, fallback_title=path.stem)
    chunks: list[Chunk] = []
    for idx, text in enumerate(paragraph_chunk(body)):
        # Content-hash incorporates the prefix so an entry's title/tags/type
        # changing (which alters the prefix) invalidates cached chunks and
        # forces re-embedding. This is also why v0.0 → v0.1 triggers a full
        # reindex.
        hash_input = f"{prefix}\n\n{text}".encode("utf-8")
        h = hashlib.sha256(hash_input).hexdigest()
        chunks.append(
            Chunk(
                text=text,
                entry_path=str(path),
                chunk_index=idx,
                content_hash=h,
                frontmatter=fm,
                prefix=prefix,
            )
        )
    return chunks


# ---------- Storage ----------


def _space_root(space: str) -> Path:
    if config.TEAMVAULT_SPACE_ROOT and config.TEAMVAULT_SPACE_ROOT.exists():
        return config.TEAMVAULT_SPACE_ROOT
    candidate = Path.home() / f"teamvault-{space}"
    if candidate.exists():
        return candidate
    raise FileNotFoundError(f"Space root not found for {space!r}. Set TEAMVAULT_SPACE_ROOT.")


def _vault_db_path(space: str) -> Path:
    return config.ensure_state_dirs(space) / "vault.lance"


def _fts_db_path(space: str) -> Path:
    return config.ensure_state_dirs(space) / "fts.db"


def _open_fts(space: str) -> sqlite3.Connection:
    conn = sqlite3.connect(_fts_db_path(space), timeout=30.0)
    # WAL: concurrent readers + writer; required when /search and /publish run together.
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA synchronous=NORMAL")
    conn.executescript(
        """
        CREATE VIRTUAL TABLE IF NOT EXISTS chunks
        USING fts5(content_hash UNINDEXED, entry_path UNINDEXED, chunk_index UNINDEXED,
                   text, tokenize='porter unicode61');
        CREATE TABLE IF NOT EXISTS hashes(content_hash TEXT PRIMARY KEY);
        """
    )
    return conn


def _ensure_vector_table(db):
    import pyarrow as pa

    if "chunks" in db.table_names():
        return db.open_table("chunks")
    schema = pa.schema(
        [
            pa.field("content_hash", pa.string()),
            pa.field("entry_path", pa.string()),
            pa.field("chunk_index", pa.int32()),
            pa.field("text", pa.string()),
            pa.field("frontmatter_yaml", pa.string()),
            pa.field("vector", pa.list_(pa.float32(), _EMBED_DIM)),
        ]
    )
    return db.create_table("chunks", schema=schema)


def reindex_space(space: str) -> dict[str, int]:
    """Full reindex of a space.

    - Idempotent on unchanged content (content-hash dedup).
    - DELETES stale rows whose entry_path no longer exists, so edits/republishes
      don't leave ghost chunks pointing at old file states.
    - Serialized by a process-level lock to avoid SQLite/LanceDB races between
      concurrent publish/search/reindex calls.
    """
    import lancedb
    import yaml

    space_root = _space_root(space)
    entries_dir = space_root / "kb" / "entries"
    if not entries_dir.exists():
        return {"indexed": 0, "skipped": 0, "errors": 0}

    with _ingest_lock:
        fts = _open_fts(space)
        lance = lancedb.connect(str(_vault_db_path(space)))
        table = _ensure_vector_table(lance)

        # ---- Discover current set of entries + chunk hashes ----
        current_paths: set[str] = set()
        current_hashes: set[str] = set()
        path_chunks: dict[Path, list[Chunk]] = {}
        errors = 0
        for path in sorted(entries_dir.rglob("*.md")):
            try:
                chunks = chunk_entry(path)
                current_paths.add(str(path))
                for c in chunks:
                    current_hashes.add(c.content_hash)
                path_chunks[path] = chunks
            except Exception as e:
                errors += 1
                print(f"ingest error on {path}: {e}")

        # ---- Delete stale rows (entries removed from disk or chunks replaced) ----
        existing_hash_to_path = {
            row[0]: row[1]
            for row in fts.execute("SELECT content_hash, entry_path FROM chunks").fetchall()
        }
        stale = [h for h, p in existing_hash_to_path.items() if h not in current_hashes or p not in current_paths]
        if stale:
            placeholders = ",".join("?" for _ in stale)
            fts.execute(f"DELETE FROM chunks WHERE content_hash IN ({placeholders})", stale)
            fts.execute(f"DELETE FROM hashes WHERE content_hash IN ({placeholders})", stale)
            fts.commit()
            try:
                hash_list = ", ".join(f"'{h}'" for h in stale)
                table.delete(f"content_hash IN ({hash_list})")
            except Exception as del_err:
                print(f"lancedb delete error (non-fatal): {del_err}")

        # ---- Embed + index new chunks ----
        existing_after = {row[0] for row in fts.execute("SELECT content_hash FROM hashes").fetchall()}
        new_chunks: list[Chunk] = []
        skipped = 0
        for chunks in path_chunks.values():
            for c in chunks:
                if c.content_hash in existing_after:
                    skipped += 1
                else:
                    new_chunks.append(c)

        if new_chunks:
            model = get_model()
            # v0.1 stretch: contextual retrieval. Prepend each chunk's per-entry
            # prefix BEFORE the Nomic ``search_document:`` instruction so the
            # embedding sees document-level context (title/type/tags/summary)
            # plus the chunk content together. Anthropic reports +35% recall
            # standalone, +67% combined with hybrid (which we already ship).
            texts = [
                f"search_document: {c.prefix}\n\n{c.text}" if c.prefix else f"search_document: {c.text}"
                for c in new_chunks
            ]
            vectors = model.encode(texts, normalize_embeddings=True, show_progress_bar=False)

            for c in new_chunks:
                # FTS5 also indexes the prefix so keyword queries against the
                # title / tag terms hit even when the chunk body lacks them
                # (e.g. a question framed around a tag word). We keep a single
                # ``text`` column rather than adding a ``prefix`` column so
                # bm25() ranking treats prefix + body as one document, which is
                # what we want for contextual retrieval.
                fts_text = f"{c.prefix}\n\n{c.text}" if c.prefix else c.text
                fts.execute(
                    "INSERT INTO chunks(content_hash, entry_path, chunk_index, text) VALUES (?, ?, ?, ?)",
                    (c.content_hash, c.entry_path, c.chunk_index, fts_text),
                )
                fts.execute("INSERT INTO hashes(content_hash) VALUES (?)", (c.content_hash,))
            fts.commit()

            rows = []
            for i, c in enumerate(new_chunks):
                # Store prefix+body in the vector table's ``text`` field too so
                # that search hits surface the same enriched text users saw at
                # embed time. The plain chunk body is still recoverable by
                # splitting on the two-newline boundary if a downstream caller
                # needs it.
                stored_text = f"{c.prefix}\n\n{c.text}" if c.prefix else c.text
                rows.append(
                    {
                        "content_hash": c.content_hash,
                        "entry_path": c.entry_path,
                        "chunk_index": c.chunk_index,
                        "text": stored_text,
                        "frontmatter_yaml": yaml.safe_dump(c.frontmatter, sort_keys=True),
                        "vector": vectors[i].tolist(),
                    }
                )
            table.add(rows)

        fts.close()
        return {"indexed": len(new_chunks), "skipped": skipped, "errors": errors}
