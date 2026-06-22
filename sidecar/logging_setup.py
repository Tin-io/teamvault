"""TeamVault sidecar logging — JSON-per-line, daily rotation, per-space tail.

Logger hierarchy
----------------
`teamvault.sidecar` is the root sidecar logger. Module-level callers grab a
bare Logger (`logging.getLogger("teamvault.sidecar")`); for per-space scoping
on a single log call, pass `extra={"space": space_name}` to `.warning(...)`.
The JSON formatter and the recent-errors handler both honor that field.

Handler chain (attached by `setup_logging()` once during startup)
----------------------------------------------------------------
- TimedRotatingFileHandler at `~/.teamvault/logs/sidecar.log`
  (rolls at UTC midnight, keeps 7 days). JSON-per-line.
- StreamHandler to stderr (WARNING+). JSON-per-line; launchd captures stderr
  to `~/.teamvault/logs/sidecar.err.log`.
- RecentErrorsHandler — in-memory ring buffer of the last 5 WARNING+ records
  per space, surfaced via `/healthz`'s `recent_errors` field.

Usage
-----
    # Once, at sidecar startup (idempotent):
    logging_setup.setup_logging()

    # Anywhere else (per-call space tagging via `extra`):
    import logging
    log = logging.getLogger("teamvault.sidecar")
    log.warning("something failed: %s", err, extra={"space": "myspace"})
"""
from __future__ import annotations

import json
import logging
import logging.handlers
import sys
from collections import defaultdict, deque
from datetime import datetime, timezone
from typing import Any

from sidecar import config


# Per-space ring buffer of WARNING+ records. The "__sidecar__" key holds
# records emitted outside of any space scope (e.g., startup errors).
_RECENT_ERRORS: dict[str, deque] = defaultdict(lambda: deque(maxlen=5))


class JsonFormatter(logging.Formatter):
    """One JSON object per line.

    Stable keys: `ts` (ISO 8601 UTC), `level`, `logger`, `message`.
    Optional keys: `space` (when caller passes `extra={"space": ...}`), `exc`
    (when `record.exc_info` is set).
    """

    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, Any] = {
            "ts": datetime.fromtimestamp(record.created, tz=timezone.utc).isoformat(),
            "level": record.levelname.lower(),
            "logger": record.name,
            "message": record.getMessage(),
        }
        space = getattr(record, "space", None)
        if space:
            payload["space"] = space
        if record.exc_info:
            payload["exc"] = self.formatException(record.exc_info)
        return json.dumps(payload, separators=(",", ":"))


class RecentErrorsHandler(logging.Handler):
    """In-memory tail of the last 5 WARNING+ records per space.

    Drops INFO/DEBUG. Records without a `space` extra are filed under
    `__sidecar__` so pre-space-aware startup errors don't get lost.
    """

    def emit(self, record: logging.LogRecord) -> None:
        if record.levelno < logging.WARNING:
            return
        space = getattr(record, "space", None) or "__sidecar__"
        _RECENT_ERRORS[space].append(
            {
                "ts": datetime.fromtimestamp(record.created, tz=timezone.utc).isoformat(),
                "level": record.levelname.lower(),
                "message": record.getMessage(),
                "logger": record.name,
            }
        )


def recent_errors_for(space: str) -> list[dict[str, Any]]:
    """Return the last 5 WARNING+ records for a single space (oldest first)."""
    return list(_RECENT_ERRORS.get(space, []))


def all_recent_errors() -> dict[str, list[dict[str, Any]]]:
    """Return the per-space recent-errors map for /healthz surfacing.

    Includes the `__sidecar__` key for records emitted outside any space scope.
    """
    return {s: list(records) for s, records in _RECENT_ERRORS.items()}


_LOGGING_INITIALIZED = False


def setup_logging() -> None:
    """Attach handlers to `teamvault.sidecar`. Idempotent on repeat calls."""
    global _LOGGING_INITIALIZED
    if _LOGGING_INITIALIZED:
        return

    root = logging.getLogger("teamvault.sidecar")
    root.setLevel(logging.INFO)
    root.propagate = False

    log_dir = config.TEAMVAULT_HOME / "logs"
    log_dir.mkdir(parents=True, exist_ok=True)
    log_path = log_dir / "sidecar.log"

    fmt = JsonFormatter()

    file_handler = logging.handlers.TimedRotatingFileHandler(
        log_path, when="midnight", backupCount=7, utc=True
    )
    file_handler.setLevel(logging.INFO)
    file_handler.setFormatter(fmt)
    root.addHandler(file_handler)

    # Stderr → launchd captures to sidecar.err.log. WARNING+ only so the
    # process stderr stays readable during interactive runs.
    stderr_handler = logging.StreamHandler(sys.stderr)
    stderr_handler.setLevel(logging.WARNING)
    stderr_handler.setFormatter(fmt)
    root.addHandler(stderr_handler)

    # /healthz tail.
    root.addHandler(RecentErrorsHandler())

    _LOGGING_INITIALIZED = True
