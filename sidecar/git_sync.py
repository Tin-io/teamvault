"""TeamVault sidecar — background git sync.

Polls space remote on a fixed interval. Fast-forward-only semantics with a
halt mechanism: when sync hits a state that needs human acknowledgement
(upstream history rewrote, dirty working tree), set a halt flag so the loop
stops hammering the same error every cycle. The user clears it via
`POST /confirm-rewind` (exposed by `/teamvault-confirm-rewind` skill).

Failure classes
---------------
- auth        → actionable hint (`gh auth refresh ...`), no halt (transient)
- non-ff      → halt + actionable error (explicit acknowledgement required)
- dirty-tree  → halt + actionable error (user must commit/stash first)
- timeout     → no halt (transient network condition)
- generic git → no halt

State surfaced to `/healthz`
----------------------------
`on_sync_state(space_name, SyncResult)` callback fires after every cycle.
The app uses it to update `SpaceState.last_pull` / `last_error` /
`halted_reason` so the per-space sync state is visible without git_sync
sharing mutable state with app.py.
"""
from __future__ import annotations

import logging
import subprocess
import threading
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable

from sidecar import config

# Namespaced under `teamvault.sidecar.*` so records flow through the handlers
# attached in logging_setup.setup_logging() (JSON file + stderr + recent_errors).
log = logging.getLogger("teamvault.sidecar.git_sync")

_thread: threading.Thread | None = None
_stop = threading.Event()

# Per-space halt flag. Keyed by space name. When set, _sync_once short-circuits
# until cleared via clear_halt(). Module-level so it persists across loop ticks
# without forcing app.py to share mutable state.
_halted: dict[str, str] = {}


@dataclass
class SyncResult:
    """One sync cycle's outcome — passed to the on_sync_state callback.

    `last_pull` is set to the ISO timestamp of every *successful* cycle (incl.
    the no-op same-SHA case). On failure it's None so the existing last_pull
    is preserved.

    `halt` being non-None signals the app that this space has entered a
    halted state — the same string also lands in `error` so /healthz surfaces
    it as the current sync error.
    """

    ok: bool
    last_pull: str | None = None
    error: str | None = None
    halt: str | None = None


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


# Substrings that mark a git stderr as a *credential-missing* auth failure.
# Standard HTTPS prompt-disabled and SSH publickey-rejected patterns. The fix
# for these is the canonical "refresh your credentials" advice.
_AUTH_FAIL_MARKERS_CREDENTIAL = (
    "could not read Username",
    "could not read Password",
    "Permission denied (publickey)",
    "Could not read from remote repository",
    "Authentication failed",
    "fatal: Authentication",
    "remote: Invalid username or password",
)

# Substrings that mark a git stderr as a *repo-hidden* failure — i.e. GitHub
# returned a 404 because the active credentials don't have access to the
# private repo (GitHub deliberately 404s instead of 403'ing private repos to
# avoid leaking existence). The most common cause on multi-account macOS
# setups: gh-credential-helper resolves to the wrong active gh user.
# Surfaced by dogfood 2026-06-22 — see kb entry b1-personal-fork-ssh-pivot.
_AUTH_FAIL_MARKERS_REPO_HIDDEN = (
    "Repository not found",
    "fatal: repository '",
)

_AUTH_HINT_CREDENTIAL = "git auth failed — run `gh auth refresh -h github.com -s repo` and retry"

_AUTH_HINT_REPO_HIDDEN = (
    "git access failed (remote returned 404 — repo hidden or no read access). "
    "Common multi-account cause on macOS: gh-credential-helper resolved to the wrong gh user. "
    "Try, in order: (1) verify `git remote -v` matches the expected repo; "
    "(2) `gh auth status` then `gh auth switch -u <repo-owner>` if multi-account; "
    "(3) switch origin to SSH: `git remote set-url origin git@github.com:OWNER/REPO.git` "
    "(most durable for multi-account users)."
)


def _detect_auth_failure(stderr: str) -> str | None:
    """Classify a git stderr against known auth-failure patterns.

    Returns the appropriate hint message if stderr matches a known pattern;
    None if no pattern matches. Repo-hidden patterns take precedence over
    credential-missing patterns since they're a more specific diagnosis.
    """
    if any(m in stderr for m in _AUTH_FAIL_MARKERS_REPO_HIDDEN):
        return _AUTH_HINT_REPO_HIDDEN
    if any(m in stderr for m in _AUTH_FAIL_MARKERS_CREDENTIAL):
        return _AUTH_HINT_CREDENTIAL
    return None


def _run_git(space_root: Path, args: list[str], timeout_s: int) -> tuple[bool, str]:
    """Run a git command in the space root with a hard timeout.

    Returns (ok, stderr-or-error-message). ok=True iff returncode 0.
    """
    try:
        result = subprocess.run(
            ["git", "-C", str(space_root), *args],
            capture_output=True,
            text=True,
            timeout=timeout_s,
        )
    except subprocess.TimeoutExpired:
        return False, f"git {args[0]} timed out after {timeout_s}s"
    except FileNotFoundError:
        return False, "git executable not found in PATH"
    if result.returncode != 0:
        return False, (result.stderr or result.stdout or "").strip()
    return True, ""


def clear_halt(space_name: str) -> bool:
    """Clear the halt flag for a space. Returns True if a flag was cleared."""
    return _halted.pop(space_name, None) is not None


def is_halted(space_name: str) -> str | None:
    """Return the halt reason for the space, or None if not halted."""
    return _halted.get(space_name)


def _sync_once(
    space_root: Path,
    space_name: str,
    timeout_s: int,
) -> SyncResult:
    """One sync cycle. Returns SyncResult capturing ok/last_pull/error/halt."""

    # Halt short-circuit. Re-emit the halt so the callback can keep
    # `halted_reason` populated even after a sidecar restart cleared the
    # in-memory _halted dict (the next post-restart tick will run through the
    # normal path and re-halt if the condition still applies).
    halt = _halted.get(space_name)
    if halt:
        return SyncResult(ok=False, error=halt, halt=halt)

    try:
        from git import Repo
    except ImportError as e:
        return SyncResult(ok=False, error=f"gitpython not installed: {e}")

    try:
        repo = Repo(space_root)
    except Exception as e:
        return SyncResult(ok=False, error=f"not a git repo: {e}")

    if repo.is_dirty(untracked_files=False):
        reason = (
            "local changes block sync — commit or stash, "
            "then run /teamvault-confirm-rewind"
        )
        _halted[space_name] = reason
        log.warning("dirty working tree — halted", extra={"space": space_name})
        return SyncResult(ok=False, error=reason, halt=reason)

    try:
        origin = repo.remotes.origin
    except (AttributeError, KeyError):
        return SyncResult(ok=True, last_pull=_now_iso())  # no origin → nothing to sync

    ok, stderr = _run_git(space_root, ["fetch", "origin"], timeout_s)
    if not ok:
        hint = _detect_auth_failure(stderr)
        if hint:
            log.warning(hint, extra={"space": space_name})
            return SyncResult(ok=False, error=hint)
        log.warning("git fetch failed: %s", stderr, extra={"space": space_name})
        return SyncResult(ok=False, error=f"git fetch failed: {stderr}")

    try:
        local_sha = repo.head.commit.hexsha
        try:
            remote_branch = origin.refs[repo.active_branch.name]
        except (KeyError, IndexError):
            return SyncResult(ok=True, last_pull=_now_iso())  # no matching remote branch
        remote_sha = remote_branch.commit.hexsha
    except Exception as e:
        return SyncResult(ok=False, error=f"sha comparison failed: {e}")

    if local_sha == remote_sha:
        return SyncResult(ok=True, last_pull=_now_iso())

    try:
        merge_base = repo.merge_base(local_sha, remote_sha)
    except Exception as e:
        return SyncResult(ok=False, error=f"merge-base check failed: {e}")

    if not merge_base or merge_base[0].hexsha != local_sha:
        reason = "upstream history rewrote — run /teamvault-confirm-rewind to acknowledge"
        _halted[space_name] = reason
        log.warning(
            "non-fast-forward upstream (local=%s remote=%s) — halted",
            local_sha[:8],
            remote_sha[:8],
            extra={"space": space_name},
        )
        return SyncResult(ok=False, error=reason, halt=reason)

    ok, stderr = _run_git(space_root, ["pull", "--ff-only", "origin"], timeout_s)
    if not ok:
        hint = _detect_auth_failure(stderr)
        if hint:
            log.warning(hint, extra={"space": space_name})
            return SyncResult(ok=False, error=hint)
        log.warning("git pull failed: %s", stderr, extra={"space": space_name})
        return SyncResult(ok=False, error=f"git pull failed: {stderr}")

    return SyncResult(ok=True, last_pull=_now_iso())


def _loop(
    space_root: Path,
    space_name: str,
    interval: int,
    timeout_s: int,
    on_sync_state: Callable[[str, SyncResult], None] | None,
) -> None:
    log.info(
        "git_sync loop started: space=%s root=%s interval=%ds timeout=%ds",
        space_name,
        space_root,
        interval,
        timeout_s,
        extra={"space": space_name},
    )
    while not _stop.wait(interval):
        result = _sync_once(space_root, space_name, timeout_s)
        if result.ok:
            log.debug("sync ok", extra={"space": space_name})
        if on_sync_state:
            try:
                on_sync_state(space_name, result)
            except Exception as e:
                log.warning(
                    "on_sync_state callback failed: %s",
                    e,
                    extra={"space": space_name},
                )


def start(
    space_root: Path,
    space_name: str,
    interval: int = 60,
    timeout_s: int | None = None,
    on_sync_state: Callable[[str, SyncResult], None] | None = None,
) -> None:
    """Start the background sync loop. Idempotent if a loop is already alive.

    `timeout_s` defaults to `config.TEAMVAULT_GIT_TIMEOUT_S`.
    `on_sync_state(space_name, SyncResult)` is invoked after every cycle so
    the app can update its in-memory SpaceState (last_pull / last_error /
    halted_reason). Optional — leave None if the caller doesn't care.
    """
    global _thread
    if _thread and _thread.is_alive():
        return
    effective_timeout = timeout_s if timeout_s is not None else config.TEAMVAULT_GIT_TIMEOUT_S
    _stop.clear()
    _thread = threading.Thread(
        target=_loop,
        args=(space_root, space_name, interval, effective_timeout, on_sync_state),
        daemon=True,
    )
    _thread.start()


def stop() -> None:
    _stop.set()
