"""TeamVault sidecar — FastAPI HTTP API.

Endpoints
---------
- GET  /healthz    status + version + per-space sync state
- GET  /packs      enabled packs + their knowledge_topics + mode_summary
- POST /search     hybrid BM25 + vector + RRF search (returns query_id)
- POST /publish    write a KB entry, commit, push, reindex
- POST /reindex    force reindex of a space
- POST /review     pack-runtime fan-out on a diff
- POST /cite       record which KB entries informed (or didn't inform) a decision
- GET  /query_log  read filtered audit-log rows + chain_ok

Run
---
$ uvicorn sidecar.app:app --port ${TEAMVAULT_PORT:-8100}
"""
from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field

from sidecar import config

app = FastAPI(
    title="TeamVault Sidecar",
    description="Local-first knowledge substrate with hybrid retrieval.",
    version=config.VERSION,
)


# ---------------------------------------------------------------------------
# In-memory state (v0.0: single-space; multi-space is v0.1)
# ---------------------------------------------------------------------------


class SpaceState(BaseModel):
    name: str
    last_pull: str | None = None  # ISO 8601 UTC
    last_error: str | None = None


_spaces: dict[str, SpaceState] = {}


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def get_space(name: str) -> SpaceState:
    if name not in _spaces:
        raise HTTPException(status_code=404, detail=f"space not registered: {name}")
    return _spaces[name]


# ---------------------------------------------------------------------------
# Models
# ---------------------------------------------------------------------------


class SearchRequest(BaseModel):
    query: str
    top_k: int = Field(default=10, ge=1, le=100)
    space: str | None = None
    # Free-text statement of what the caller is trying to decide or accomplish.
    # Recorded verbatim in the audit log for retrospective review. v0.1+ contract.
    purpose: str | None = None


class SearchHit(BaseModel):
    path: str
    chunk: str
    score: float
    metadata: dict[str, Any] = Field(default_factory=dict)


class SearchResponse(BaseModel):
    # 32-char lowercase hex (uuid4().hex). Used to bind a follow-up vault_cite
    # to this search, closing the search → cite audit loop.
    query_id: str
    results: list[SearchHit]


class PublishRequest(BaseModel):
    space: str
    slug: str
    content: str
    frontmatter: dict[str, Any] = Field(default_factory=dict)


class PublishResponse(BaseModel):
    path: str
    committed: bool
    pushed: bool
    error: str | None = None


class ReindexRequest(BaseModel):
    space: str


class ReindexResponse(BaseModel):
    indexed: int
    skipped: int
    errors: int


class ReviewRequest(BaseModel):
    space: str
    diff: str


class ReviewerVerdict(BaseModel):
    pack: str
    agent: str
    mode: str  # "advisory" | "blocking"
    pass_or_fail: str  # "pass" | "fail"
    message: str


class ReviewResponse(BaseModel):
    overall: str  # "pass" | "block"
    individual: list[ReviewerVerdict]


class PackInfo(BaseModel):
    name: str
    version: str
    description: str
    knowledge_topics: list[str] = Field(default_factory=list)
    mode_summary: str  # "blocking" | "advisory" | "none"


class PacksResponse(BaseModel):
    space: str
    packs: list[PackInfo]


class CiteRequest(BaseModel):
    space: str
    query_id: str  # UUID returned by a prior /search
    paths_used: list[str] = Field(default_factory=list)  # empty = "nothing useful"
    note: str | None = None


class CiteResponse(BaseModel):
    recorded: bool


class QueryLogRow(BaseModel):
    ts: str
    action: str
    metadata: dict[str, Any] = Field(default_factory=dict)


class QueryLogResponse(BaseModel):
    rows: list[QueryLogRow]
    # True if audit.verify_chain over the FULL log (not the filtered slice)
    # returns ok. Surfaces tamper detection to the consumer.
    chain_ok: bool


# Default action whitelist for /query_log if no explicit filter is provided.
_DEFAULT_LOG_ACTIONS: tuple[str, ...] = ("search", "cite", "publish", "publish_blocked")


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------


@app.get("/healthz")
def healthz() -> dict[str, Any]:
    """Liveness probe + per-space sync state. Always returns 200 if the app is up."""
    return {
        "status": "ok",
        "version": config.VERSION,
        "config": config.summary(),
        "spaces": [s.model_dump() for s in _spaces.values()],
    }


@app.post("/search", response_model=SearchResponse)
def search_endpoint(req: SearchRequest) -> SearchResponse:
    # Lazy import so /healthz works even if retrieval deps fail to load.
    import uuid

    from sidecar import search as search_mod

    space_name = req.space or _default_space_name()
    # query_id generated BEFORE search so it can be threaded into both the
    # audit record and the response. Lets the caller bind a follow-up
    # vault_cite to this search.
    query_id = uuid.uuid4().hex
    hits = search_mod.hybrid_search(
        query=req.query,
        top_k=req.top_k,
        space=space_name,
    )
    # Audit: record the KB read. Lazy import so /healthz stays clean.
    try:
        from sidecar import audit

        audit.record(
            space=space_name,
            action="search",
            metadata={
                "query": req.query,
                "purpose": req.purpose,
                "top_k": req.top_k,
                "result_count": len(hits),
                "query_id": query_id,
                "paths_returned": [h.get("path") for h in hits],
                "top_scores": [round(float(h.get("score", 0.0)), 4) for h in hits],
            },
        )
    except Exception as e:
        print(f"warning: audit.record(search) failed: {e}")
    return SearchResponse(
        query_id=query_id,
        results=[SearchHit(**h) for h in hits],
    )


@app.post("/publish", response_model=PublishResponse)
def publish_endpoint(req: PublishRequest) -> PublishResponse:
    from sidecar import publish as publish_mod

    result = publish_mod.publish_entry(
        space=req.space,
        slug=req.slug,
        content=req.content,
        frontmatter=req.frontmatter,
    )
    # Audit: a scrubber match returns a scrubber error string with no commit.
    try:
        from sidecar import audit

        err = result.get("error") or ""
        scrubber_blocked = (
            not result.get("committed")
            and "Content blocked by pack scrubber" in err
        )
        if scrubber_blocked:
            audit.record(
                space=req.space,
                action="publish_blocked",
                path=result.get("path") or req.slug,
                metadata={"slug": req.slug, "error": err},
            )
        else:
            audit.record(
                space=req.space,
                action="publish",
                path=result.get("path") or req.slug,
                metadata={
                    "slug": req.slug,
                    "committed": bool(result.get("committed")),
                    "pushed": bool(result.get("pushed")),
                    "error": err or None,
                },
            )
    except Exception as e:
        print(f"warning: audit.record(publish) failed: {e}")
    return PublishResponse(**result)


@app.post("/reindex", response_model=ReindexResponse)
def reindex_endpoint(req: ReindexRequest) -> ReindexResponse:
    from sidecar import ingest

    counts = ingest.reindex_space(req.space)
    try:
        from sidecar import audit

        audit.record(
            space=req.space,
            action="reindex",
            metadata={
                "indexed": counts.get("indexed", 0),
                "skipped": counts.get("skipped", 0),
                "errors": counts.get("errors", 0),
            },
        )
    except Exception as e:
        print(f"warning: audit.record(reindex) failed: {e}")
    return ReindexResponse(**counts)


@app.post("/review", response_model=ReviewResponse)
def review_endpoint(req: ReviewRequest) -> ReviewResponse:
    from sidecar import pack_runtime

    verdict = pack_runtime.run_review(space=req.space, diff=req.diff)
    return ReviewResponse(**verdict)


@app.get("/packs", response_model=PacksResponse)
def packs_endpoint(space: str | None = None) -> PacksResponse:
    """Enabled packs + their `knowledge_topics` + overall `mode_summary`.

    Read-only introspection on data already in version control (PACK.yaml +
    space.yaml). No audit entry — nothing here changes state or reveals
    anything not already visible in git.

    The agent uses this at the start of substantive work to learn which
    knowledge domains the team has accumulated KB on, then targets
    `vault_search` accordingly.
    """
    from sidecar import pack_runtime

    space_name = space or _default_space_name()
    space_root = _resolve_space_root(space_name)
    rt = pack_runtime.PackRuntime(space_root)

    out: list[PackInfo] = []
    for p in rt.packs:
        modes = {r.mode for r in p.reviewers}
        if "blocking" in modes:
            summary = "blocking"
        elif modes:
            summary = "advisory"
        else:
            summary = "none"
        out.append(
            PackInfo(
                name=p.name,
                version=p.version,
                description=p.description,
                knowledge_topics=list(p.knowledge_topics),
                mode_summary=summary,
            )
        )
    return PacksResponse(space=space_name, packs=out)


@app.post("/cite", response_model=CiteResponse)
def cite_endpoint(req: CiteRequest) -> CiteResponse:
    """Record which KB entries informed (or didn't inform) a decision after a search.

    `paths_used=[]` is valid and records "we searched, nothing was useful." No
    validation that `query_id` exists in a prior search row — dangling cites
    are valid signals (e.g., when the search log was rotated). The reviewer
    joins on `query_id` post-hoc.
    """
    try:
        from sidecar import audit

        audit.record(
            space=req.space,
            action="cite",
            metadata={
                "query_id": req.query_id,
                "paths_used": list(req.paths_used),
                "note": req.note,
            },
        )
        return CiteResponse(recorded=True)
    except Exception as e:
        print(f"warning: audit.record(cite) failed: {e}")
        return CiteResponse(recorded=False)


@app.get("/query_log", response_model=QueryLogResponse)
def query_log_endpoint(
    space: str | None = None,
    since: str | None = None,
    until: str | None = None,
    action: str | None = None,
    limit: int = 50,
) -> QueryLogResponse:
    """Read filtered audit-log rows for retrospectives + orientation.

    Filters
    -------
    - `since` / `until`: ISO 8601 timestamps (lex compare; ISO 8601 sorts correctly).
    - `action`: comma-separated whitelist. Defaults to
      `search,cite,publish,publish_blocked`.
    - `limit`: capped at 500; default 50. Keeps the tail (most recent rows).

    `chain_ok` runs `audit.verify_chain` over the FULL log (not the filtered
    slice) so the agent sees "your view is filtered but the underlying log is
    consistent." If False, treat the rows as suspect.

    Read-only; no audit entry (would create unbounded recursion).
    """
    import json

    from sidecar import audit

    space_name = space or _default_space_name()
    capped_limit = max(0, min(int(limit), 500))
    if action:
        action_set = {a.strip() for a in action.split(",") if a.strip()}
    else:
        action_set = set(_DEFAULT_LOG_ACTIONS)

    # Verify chain on the full log regardless of filters.
    chain_ok, _, _ = audit.verify_chain(space_name)

    log_path = config.TEAMVAULT_HOME / space_name / "audit.log"
    if not log_path.exists():
        return QueryLogResponse(rows=[], chain_ok=chain_ok)

    rows: list[QueryLogRow] = []
    for raw_line in log_path.read_text().splitlines():
        if not raw_line.strip():
            continue
        try:
            entry = json.loads(raw_line)
        except json.JSONDecodeError:
            # Tampered / truncated line — chain_ok will already be False.
            continue
        if entry.get("action") not in action_set:
            continue
        ts = entry.get("ts") or ""
        if since and ts < since:
            continue
        if until and ts > until:
            continue
        rows.append(
            QueryLogRow(
                ts=ts,
                action=entry.get("action", ""),
                metadata=entry.get("metadata") or {},
            )
        )

    # Keep the most-recent `capped_limit` rows (file order is chronological).
    if capped_limit > 0:
        rows = rows[-capped_limit:]
    else:
        rows = []

    return QueryLogResponse(rows=rows, chain_ok=chain_ok)


# ---------------------------------------------------------------------------
# Startup
# ---------------------------------------------------------------------------


def _default_space_name() -> str:
    if not _spaces:
        raise HTTPException(
            status_code=503,
            detail="No space registered. Set TEAMVAULT_SPACE_ROOT and ensure space.yaml exists.",
        )
    return next(iter(_spaces))


def _resolve_space_root(space: str) -> Path:
    """Resolve the filesystem root for a space clone.

    Prefers `TEAMVAULT_SPACE_ROOT` when set + present on disk (dev / test /
    multi-space-via-env). Falls back to the per-Mac convention
    `~/teamvault-{space}` used by the setup skill.
    """
    if config.TEAMVAULT_SPACE_ROOT and config.TEAMVAULT_SPACE_ROOT.exists():
        return config.TEAMVAULT_SPACE_ROOT
    return Path.home() / f"teamvault-{space}"


def _register_space_from_yaml(space_root: Path) -> None:
    """Read space.yaml in the space clone root, register the space."""
    import yaml

    yaml_path = space_root / "space.yaml"
    if not yaml_path.exists():
        # No space.yaml yet — that's fine for first boot; just don't register.
        return
    try:
        doc = yaml.safe_load(yaml_path.read_text()) or {}
    except yaml.YAMLError as e:
        # Don't crash the sidecar on bad YAML — log via space's last_error.
        name = "default"
        _spaces[name] = SpaceState(name=name, last_error=f"space.yaml parse error: {e}")
        return
    name = doc.get("name") or "default"
    _spaces[name] = SpaceState(name=name)
    config.ensure_state_dirs(name)


@app.on_event("startup")
def _startup() -> None:
    if config.TEAMVAULT_SPACE_ROOT and config.TEAMVAULT_SPACE_ROOT.exists():
        _register_space_from_yaml(config.TEAMVAULT_SPACE_ROOT)
        # Kick off the background git_sync loop for the registered space.
        try:
            from sidecar import git_sync

            git_sync.start(config.TEAMVAULT_SPACE_ROOT, interval=60)
        except Exception as e:
            # Don't crash sidecar boot on git_sync setup error; just log.
            print(f"warning: git_sync failed to start: {e}")
