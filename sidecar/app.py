"""TeamVault sidecar — FastAPI HTTP API.

Endpoints
---------
- GET  /healthz          status + version + per-space sync state
- GET  /readyz           K8s-style readiness (200 only when serving usefully)
- GET  /packs            enabled packs + their knowledge_topics + mode_summary
- POST /search           hybrid BM25 + vector + RRF search (returns query_id)
- POST /publish          write a KB entry, commit, push, reindex
- POST /reindex          force reindex of a space
- POST /review           pack-runtime fan-out on a diff
- POST /cite             record which KB entries informed (or didn't inform) a decision
- GET  /query_log        read filtered audit-log rows + chain_ok
- POST /confirm-rewind   clear the git_sync halt flag for a space

Run
---
$ uvicorn sidecar.app:app --port ${TEAMVAULT_PORT:-8100}
"""
from __future__ import annotations

import fcntl
import logging
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field

from sidecar import config
from sidecar import logging_setup

# Module logger. Handlers attached in setup_logging() during _startup() —
# at module-import time the logger has no handlers, so any pre-startup
# records are silently dropped (which is fine; nothing logs at import).
log = logging.getLogger("teamvault.sidecar")

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
    last_pull: str | None = None  # ISO 8601 UTC — last successful git_sync poll
    last_error: str | None = None  # Last git_sync error; cleared on success
    # Set to the ISO timestamp of the last successful reindex. /readyz uses
    # this to signal readiness (distinct from /healthz, which signals only
    # process liveness — the K8s liveness-vs-readiness pattern).
    last_indexed: str | None = None
    # Non-null when git_sync has halted on a state requiring human acknowledgement
    # (upstream history rewrote, dirty working tree). Cleared by POST /confirm-rewind.
    halted_reason: str | None = None


_spaces: dict[str, SpaceState] = {}

# Holds the sidecar PID lockfile descriptor for the process lifetime.
# Closing the fd releases the flock and allows another sidecar to start.
# Module-level so the GC doesn't reclaim it after _acquire_pid_lock() returns.
_PID_LOCK_FD: Any = None


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


class ConfirmRewindRequest(BaseModel):
    space: str


class ConfirmRewindResponse(BaseModel):
    cleared: bool  # True iff a halt flag was actually cleared
    space: str


# Default action whitelist for /query_log if no explicit filter is provided.
_DEFAULT_LOG_ACTIONS: tuple[str, ...] = ("search", "cite", "publish", "publish_blocked")


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------


@app.get("/healthz")
def healthz() -> dict[str, Any]:
    """Liveness probe + per-space sync state. Always returns 200 if the app is up.

    `recent_errors` is the in-memory tail of the last 5 WARNING+ log records
    per space (plus a `__sidecar__` bucket for pre-space-aware errors).

    `compliance` (P0.7): machine-wide egress posture. When ANY registered
    space has `compliance: true`, posture flips to `strict` and the listed
    invariants apply machine-wide (cross-space scrubbers, strictest-regime
    search scrubbing). See `sidecar/compliance.py` for the contract.
    """
    from sidecar import compliance

    return {
        "status": "ok",
        "version": config.VERSION,
        "config": config.summary(),
        "spaces": [s.model_dump() for s in _spaces.values()],
        "recent_errors": logging_setup.all_recent_errors(),
        "compliance": compliance.egress_invariants(),
    }


@app.get("/readyz")
def readyz() -> dict[str, Any]:
    """Readiness probe — distinct from /healthz.

    Returns 200 only when the sidecar can actually serve useful search results:
    at least one space is registered AND has completed a reindex AND has no
    recorded error. Returns 503 with `reason` otherwise.

    Use /healthz to ask "is the process up?"; use /readyz to ask "will a
    search return useful results?" — the K8s liveness-vs-readiness pattern.
    """
    if not _spaces:
        raise HTTPException(
            status_code=503,
            detail={"ready": False, "reason": "no space registered"},
        )
    not_indexed = [s.name for s in _spaces.values() if not s.last_indexed]
    if not_indexed:
        raise HTTPException(
            status_code=503,
            detail={
                "ready": False,
                "reason": "space(s) not yet indexed",
                "spaces": not_indexed,
            },
        )
    errored = {s.name: s.last_error for s in _spaces.values() if s.last_error}
    if errored:
        raise HTTPException(
            status_code=503,
            detail={
                "ready": False,
                "reason": "space in error state",
                "errors": errored,
            },
        )
    return {"ready": True, "spaces": [s.model_dump() for s in _spaces.values()]}


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
                # P1.6: scores are RRF × temporal-decay × access-boost.
                # Tag is derived from the current DECAY_*/BOOST constants so
                # retrospectives across a parameter bump can detect the
                # regime shift without anyone updating a literal here.
                "scoring_version": search_mod.SCORING_VERSION,
            },
        )
    except Exception as e:
        log.warning("audit.record(search) failed: %s", e, extra={"space": space_name})
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
        log.warning("audit.record(publish) failed: %s", e, extra={"space": req.space})
    return PublishResponse(**result)


@app.post("/reindex", response_model=ReindexResponse)
def reindex_endpoint(req: ReindexRequest) -> ReindexResponse:
    from sidecar import ingest

    counts = ingest.reindex_space(req.space)
    # Mark readiness: any non-erroring reindex flips /readyz to 200 for this space.
    if req.space in _spaces and counts.get("errors", 0) == 0:
        _spaces[req.space].last_indexed = _now_iso()
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
        log.warning("audit.record(reindex) failed: %s", e, extra={"space": req.space})
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
        log.warning("audit.record(cite) failed: %s", e, extra={"space": req.space})
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


@app.post("/confirm-rewind", response_model=ConfirmRewindResponse)
def confirm_rewind_endpoint(req: ConfirmRewindRequest) -> ConfirmRewindResponse:
    """Clear the git_sync halt flag for a space so the loop resumes.

    Set by `_sync_once` when it hits a state requiring human acknowledgement
    (upstream history rewrote, dirty working tree). The corresponding skill
    (`/teamvault-confirm-rewind`) invokes this after the user resolves the
    underlying issue (committed/stashed local changes, or accepted the
    upstream rewrite). Clears both the in-memory halt flag and the
    `halted_reason` / `last_error` fields on the SpaceState so /healthz
    reflects the resume immediately without waiting for the next sync tick.
    """
    from sidecar import git_sync

    cleared = git_sync.clear_halt(req.space)
    if req.space in _spaces:
        _spaces[req.space].halted_reason = None
        _spaces[req.space].last_error = None
    return ConfirmRewindResponse(cleared=cleared, space=req.space)


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


def _acquire_pid_lock() -> None:
    """Take the sidecar PID lock — prevents two sidecars contending on the same indexes.

    Uses `fcntl.flock` (advisory, Unix). If the lock is held, another sidecar
    process is alive; refuse to start with a clear error and exit non-zero so
    launchd / the user notice instead of silently fighting another sidecar
    over the same indexes and audit log.

    Lockfile path: `$TEAMVAULT_HOME/sidecar.pid`. Single global lock (not
    per-space) because the runtime is currently single-process.
    """
    global _PID_LOCK_FD
    config.TEAMVAULT_HOME.mkdir(parents=True, exist_ok=True)
    pid_path = config.TEAMVAULT_HOME / "sidecar.pid"
    # Open in "a+" (read-write, NO truncate) so the existing PID is still
    # readable when the flock fails. "w" mode would truncate the file before
    # the flock attempt and the error message would say "<empty>".
    fd = open(pid_path, "a+")
    try:
        fcntl.flock(fd.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError:
        try:
            fd.seek(0)
            existing_pid = fd.read().strip() or "<empty>"
        except Exception:
            existing_pid = "<unreadable>"
        sys.stderr.write(
            "ERROR: another TeamVault sidecar is already running.\n"
            f"  PID lockfile: {pid_path}\n"
            f"  PID inside:   {existing_pid}\n"
            "  Find the live process with `launchctl list | grep teamvault`,\n"
            "  then restart cleanly with\n"
            "  `launchctl kickstart -k gui/$(id -u)/dev.teamvault.sidecar`.\n"
            "  Exiting.\n"
        )
        sys.exit(1)
    # We own the lock — safe to truncate and write our PID.
    fd.seek(0)
    fd.truncate()
    fd.write(f"{os.getpid()}\n")
    fd.flush()
    _PID_LOCK_FD = fd


@app.on_event("startup")
def _startup() -> None:
    _acquire_pid_lock()
    logging_setup.setup_logging()
    log.info("sidecar starting (pid=%d, port=%d)", os.getpid(), config.TEAMVAULT_PORT)
    if config.TEAMVAULT_SPACE_ROOT and config.TEAMVAULT_SPACE_ROOT.exists():
        _register_space_from_yaml(config.TEAMVAULT_SPACE_ROOT)
        # Kick off the background git_sync loop for the registered space.
        try:
            from sidecar import git_sync

            # Single-space v0.0 — the only registered space is the one we just
            # read from space.yaml. Pass its name + a callback that mirrors
            # SyncResult into _spaces so /healthz surfaces last_pull /
            # last_error / halted_reason without git_sync touching app state
            # directly.
            registered = next(iter(_spaces), None)
            if registered:
                git_sync.start(
                    config.TEAMVAULT_SPACE_ROOT,
                    space_name=registered,
                    interval=60,
                    on_sync_state=_apply_sync_state,
                )
        except Exception as e:
            # Don't crash sidecar boot on git_sync setup error; log it instead.
            log.warning("git_sync failed to start: %s", e)


def _apply_sync_state(space_name: str, result: Any) -> None:
    """Mirror a git_sync SyncResult into SpaceState for /healthz surfacing.

    Lives in app.py (not git_sync.py) so git_sync stays free of any direct
    reference to _spaces / SpaceState. The `result: Any` type-hint avoids
    importing SyncResult at module scope (lazy-import keeps the startup
    dependency arrow one-way: app → git_sync, never the reverse).
    """
    if space_name not in _spaces:
        return
    st = _spaces[space_name]
    if result.last_pull:
        st.last_pull = result.last_pull
    st.last_error = result.error
    st.halted_reason = result.halt
