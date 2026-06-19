"""TeamVault sidecar — background git sync.

Polls space remote on a fixed interval. Fast-forward-only semantics:
  - skip if working tree dirty
  - refuse non-fast-forward (force-push detection deferred to v0.1's
    "refuse and require explicit confirm-rewind" flow)

v0.0 is single-space; multi-space is v0.1.
"""
from __future__ import annotations

import logging
import threading
from pathlib import Path

log = logging.getLogger("teamvault.git_sync")

_thread: threading.Thread | None = None
_stop = threading.Event()


def _sync_once(space_root: Path) -> tuple[bool, str | None]:
    """One sync cycle. Returns (ok, error_message)."""
    try:
        from git import Repo, GitCommandError
    except ImportError as e:
        return False, f"gitpython not installed: {e}"

    try:
        repo = Repo(space_root)
    except Exception as e:
        return False, f"not a git repo: {e}"

    if repo.is_dirty(untracked_files=False):
        return False, "local changes block sync; commit or stash"

    try:
        try:
            origin = repo.remotes.origin
        except (AttributeError, KeyError):
            return True, None  # no origin → nothing to sync
        origin.fetch()

        local_sha = repo.head.commit.hexsha
        try:
            remote_branch = origin.refs[repo.active_branch.name]
        except (KeyError, IndexError):
            return True, None  # no matching remote branch
        remote_sha = remote_branch.commit.hexsha

        if local_sha == remote_sha:
            return True, None

        merge_base = repo.merge_base(local_sha, remote_sha)
        if not merge_base or merge_base[0].hexsha != local_sha:
            return False, f"non-fast-forward upstream: local={local_sha[:8]} remote={remote_sha[:8]}"

        origin.pull(ff_only=True)
        return True, None
    except GitCommandError as e:
        return False, f"git error: {e}"
    except Exception as e:
        return False, f"unexpected sync error: {e}"


def _loop(space_root: Path, interval: int) -> None:
    log.info(f"git_sync loop started: space_root={space_root}, interval={interval}s")
    while not _stop.wait(interval):
        ok, err = _sync_once(space_root)
        if ok:
            log.debug("sync ok")
        else:
            log.warning(f"sync failed: {err}")


def start(space_root: Path, interval: int = 60) -> None:
    global _thread
    if _thread and _thread.is_alive():
        return
    _stop.clear()
    _thread = threading.Thread(target=_loop, args=(space_root, interval), daemon=True)
    _thread.start()


def stop() -> None:
    _stop.set()
