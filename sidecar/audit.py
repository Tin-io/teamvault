"""TeamVault audit log — JSONL with tamper-evident hash chain.

HIPAA §164.312(b) integrity control. Each entry includes hash_prev which is
the SHA-256 of the entire previous JSONL line. Tampering with any prior
entry breaks the chain, detectable by re-walking from genesis.

Append-only. 6-year retention documented (HIPAA §164.530(j)(2));
rotation deferred to v0.2.

Storage
-------
    ${TEAMVAULT_HOME}/<space>/audit.log

Format (one JSON object per line, separators=(",", ":") for stable output)
    {"ts": "...", "space": "...", "workspace": "...", "action": "...",
     "actor": "...", "path": "...", "host_session_id": "...",
     "metadata": {...}, "hash_prev": "<sha256-hex>"}

The first entry's hash_prev is "0" * 64 (GENESIS_HASH). Each subsequent
entry's hash_prev is the SHA-256 of the previous JSONL line including its
trailing "\\n".
"""
from __future__ import annotations

import hashlib
import json
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Literal

from sidecar import config

# Controlled vocabulary for `action`.
Action = Literal["search", "publish", "publish_blocked", "pack_deploy", "reindex", "cite"]

GENESIS_HASH = "0" * 64  # 64-char hex zero = no previous line

# Module-level lock — the sidecar serves concurrent requests; the audit log
# must serialize so the hash chain stays consistent.
_lock = threading.Lock()

# Field order for stable serialization. json.dumps preserves dict insertion
# order in Python 3.7+, so we build the entry in this exact order.
_FIELD_ORDER = (
    "ts",
    "space",
    "workspace",
    "action",
    "actor",
    "path",
    "host_session_id",
    "metadata",
    "hash_prev",
)


def _audit_path(space: str, home: Path | None = None) -> Path:
    """Return the audit log path for a space.

    Ensures the per-space state dir exists via config.ensure_state_dirs().
    When `home` is provided it overrides the default TEAMVAULT_HOME.
    """
    if home is None:
        # Use the default location under TEAMVAULT_HOME via config.
        config.ensure_state_dirs(space)
        return config.TEAMVAULT_HOME / space / "audit.log"
    # Caller passed an explicit home — honor it directly and ensure the dir.
    space_dir = home / space
    space_dir.mkdir(parents=True, exist_ok=True)
    (space_dir / "logs").mkdir(exist_ok=True)
    return space_dir / "audit.log"


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _last_hash(p: Path) -> str:
    """SHA-256 of the last line in the audit log (including its trailing newline),
    or GENESIS_HASH if the log is empty or missing.

    Reads the file in binary mode to compute the hash over the exact bytes
    that were written — necessary for chain verification to be byte-stable.
    """
    if not p.exists():
        return GENESIS_HASH
    data = p.read_bytes()
    if not data:
        return GENESIS_HASH
    # Find the start of the last non-empty line. Each appended record ends in
    # b"\n", so the file ends with b"\n" if any records exist.
    # We want the hash of "the last full line, including its newline".
    if data.endswith(b"\n"):
        # Drop the trailing newline to find the prior boundary.
        prior_boundary = data.rfind(b"\n", 0, len(data) - 1)
        last_line = data[prior_boundary + 1 :]  # includes trailing \n
    else:
        # No trailing newline — treat the tail as a partial/last line.
        prior_boundary = data.rfind(b"\n")
        last_line = data[prior_boundary + 1 :]
        if not last_line.endswith(b"\n"):
            last_line = last_line + b"\n"  # normalize for hash stability
    return hashlib.sha256(last_line).hexdigest()


def record(
    *,
    space: str,
    action: Action,
    actor: str = "local-user",
    path: str | None = None,
    workspace: str | None = None,
    host_session_id: str | None = None,
    metadata: dict | None = None,
    home: Path | None = None,
) -> dict:
    """Append a structured audit entry to the space's log.

    Thread-safe: serialized via the module-level lock so concurrent sidecar
    requests don't race on the hash chain.

    Returns the full entry dict that was written (with the computed hash_prev).
    """
    entry = {
        "ts": _now_iso(),
        "space": space,
        "workspace": workspace,
        "action": action,
        "actor": actor,
        "path": path,
        "host_session_id": host_session_id,
        "metadata": metadata or {},
        # hash_prev filled inside the lock so chain is consistent.
        "hash_prev": GENESIS_HASH,
    }

    with _lock:
        p = _audit_path(space, home=home)
        entry["hash_prev"] = _last_hash(p)
        # Stable serialization: compact separators, fixed field order.
        ordered = {k: entry[k] for k in _FIELD_ORDER}
        line = json.dumps(ordered, separators=(",", ":"), ensure_ascii=False)
        # Append the line with a trailing newline. Open in binary append to
        # avoid any platform newline translation.
        with p.open("ab") as f:
            f.write(line.encode("utf-8") + b"\n")
        return ordered


def verify_chain(
    space: str, home: Path | None = None
) -> tuple[bool, int, int | None]:
    """Walk the chain from genesis.

    Returns
    -------
    (ok, entries_checked, error_line_index)
        ok               True if every link verifies (or file is empty/missing).
        entries_checked  Number of entries successfully walked.
        error_line_index 0-based line number of the first bad entry, or None.
    """
    p = _audit_path(space, home=home)
    if not p.exists():
        return True, 0, None

    data = p.read_bytes()
    if not data:
        return True, 0, None

    expected_prev = GENESIS_HASH
    checked = 0
    # Split keeping trailing newlines so the hash is over the exact bytes
    # written (line + b"\n").
    lines: list[bytes] = []
    start = 0
    for i, b in enumerate(data):
        if b == 0x0A:  # '\n'
            lines.append(data[start : i + 1])
            start = i + 1
    if start < len(data):
        # Trailing partial line (no newline) — append as-is. The hash of the
        # previous "real" line still includes its own newline, so this won't
        # match what a follower would compute, but we still parse it.
        lines.append(data[start:])

    for idx, raw in enumerate(lines):
        # Parse the JSON content (strip any trailing newline for json.loads).
        try:
            text = raw.decode("utf-8")
            entry = json.loads(text)
        except (UnicodeDecodeError, json.JSONDecodeError):
            return False, checked, idx
        if entry.get("hash_prev") != expected_prev:
            return False, checked, idx
        # Compute the hash of THIS line (as written, with its trailing \n)
        # for the next iteration to verify against.
        expected_prev = hashlib.sha256(raw).hexdigest()
        checked += 1

    return True, checked, None
