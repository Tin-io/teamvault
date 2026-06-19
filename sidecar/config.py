"""TeamVault sidecar configuration.

All runtime paths derive from `TEAMVAULT_HOME`. Defaults are user-friendly;
dev/test environments redirect via env vars so the real user account is
never touched.

Env vars:
    TEAMVAULT_HOME       Root for sidecar state. Default ~/.teamvault/
    TEAMVAULT_PORT       HTTP port for the sidecar. Default 8100
    TEAMVAULT_SPACE_ROOT Path to the space clone the sidecar watches.
                         If unset, sidecar boots in standby (only /healthz works).
    TEAMVAULT_DRY_RUN    If truthy, skip git push on publish. Used in tests.
"""
from __future__ import annotations

import os
from pathlib import Path


VERSION = "0.0.1"


def _expand(path_str: str) -> Path:
    return Path(os.path.expanduser(path_str)).resolve()


def _bool_env(name: str) -> bool:
    val = os.environ.get(name, "").strip().lower()
    return val in ("1", "true", "yes", "on")


TEAMVAULT_HOME: Path = _expand(os.environ.get("TEAMVAULT_HOME", "~/.teamvault"))
TEAMVAULT_PORT: int = int(os.environ.get("TEAMVAULT_PORT", "8100"))

_space_root_env = os.environ.get("TEAMVAULT_SPACE_ROOT")
TEAMVAULT_SPACE_ROOT: Path | None = _expand(_space_root_env) if _space_root_env else None

TEAMVAULT_DRY_RUN: bool = _bool_env("TEAMVAULT_DRY_RUN")


def space_state_path(space_name: str) -> Path:
    """Return the per-space state dir under TEAMVAULT_HOME."""
    return TEAMVAULT_HOME / space_name


def ensure_state_dirs(space_name: str) -> Path:
    """Create the per-space state tree. Idempotent. Returns the space path."""
    p = space_state_path(space_name)
    p.mkdir(parents=True, exist_ok=True)
    (p / "logs").mkdir(exist_ok=True)
    return p


def summary() -> dict:
    """Diagnostic dump of the current config — used by /healthz."""
    return {
        "version": VERSION,
        "home": str(TEAMVAULT_HOME),
        "port": TEAMVAULT_PORT,
        "space_root": str(TEAMVAULT_SPACE_ROOT) if TEAMVAULT_SPACE_ROOT else None,
        "dry_run": TEAMVAULT_DRY_RUN,
    }
