"""Verify the v0.1 stretch audit log (HIPAA §164.312(b)).

Flow
----
  1. Wipe any existing audit log for the sandbox space.
  2. POST /search → confirm an entry with action="search" is appended.
  3. POST /publish (clean content) → confirm action="publish" entry.
  4. POST /publish (PHI-laden content) → confirm action="publish_blocked".
  5. verify_chain() → expect (ok=True, N, None).
  6. Corrupt one middle entry → verify_chain() → expect (ok=False, error_index).

Run against the sandbox sidecar:
  TEAMVAULT_HOME=/tmp/teamvault-sandbox/.teamvault-home \
  TEAMVAULT_SPACE_ROOT=/tmp/teamvault-sandbox \
  TEAMVAULT_PORT=18100 \
  python .build/test_audit_log.py
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

import httpx


PORT = int(os.environ.get("TEAMVAULT_PORT", "18100"))
BASE = f"http://localhost:{PORT}"
SPACE = "teamvault-template"
HOME = Path(
    os.environ.get(
        "TEAMVAULT_HOME",
        "/tmp/teamvault-sandbox/.teamvault-home",
    )
).expanduser()
AUDIT_LOG = HOME / SPACE / "audit.log"


def wipe_log() -> None:
    if AUDIT_LOG.exists():
        AUDIT_LOG.unlink()


def read_entries() -> list[dict]:
    if not AUDIT_LOG.exists():
        return []
    return [
        json.loads(line)
        for line in AUDIT_LOG.read_text().splitlines()
        if line.strip()
    ]


def run() -> int:
    # Make the audit module importable so we can call verify_chain in-process.
    repo_root = Path(__file__).resolve().parent.parent
    sys.path.insert(0, str(repo_root))
    from sidecar import audit  # noqa: E402

    failures: list[str] = []

    print(f"[setup] sidecar: {BASE}")
    print(f"[setup] audit log: {AUDIT_LOG}")

    print("[1] Wipe existing audit log...")
    wipe_log()
    assert not AUDIT_LOG.exists()

    print("[2] POST /search → expect action=search entry...")
    r = httpx.post(
        f"{BASE}/search",
        json={"query": "mrn handling", "top_k": 3, "space": SPACE},
        timeout=30,
    )
    r.raise_for_status()
    entries = read_entries()
    if not entries or entries[-1]["action"] != "search":
        failures.append(
            f"expected last entry action=search, got {entries[-1] if entries else None}"
        )
    else:
        e = entries[-1]
        if e.get("metadata", {}).get("query") != "mrn handling":
            failures.append(f"search entry missing query metadata: {e}")
        if "result_count" not in e.get("metadata", {}):
            failures.append(f"search entry missing result_count: {e}")
        if e.get("hash_prev") != audit.GENESIS_HASH:
            failures.append(
                f"first entry hash_prev should be GENESIS_HASH, got {e.get('hash_prev')}"
            )
        print(f"    PASS: search recorded (hash_prev={e['hash_prev'][:12]}...)")

    print("[3] POST /publish (clean) → expect action=publish entry...")
    r = httpx.post(
        f"{BASE}/publish",
        json={
            "space": SPACE,
            "slug": "audit-log-test-clean",
            "content": "# Audit log test\n\nThis is a clean entry with no PHI.",
            "frontmatter": {"tags": ["test", "audit"]},
        },
        timeout=30,
    )
    r.raise_for_status()
    body = r.json()
    entries = read_entries()
    if not entries or entries[-1]["action"] != "publish":
        failures.append(
            f"expected last entry action=publish, got {entries[-1] if entries else None}"
        )
    else:
        e = entries[-1]
        if "path" not in e or not e["path"]:
            failures.append(f"publish entry missing path: {e}")
        print(f"    PASS: publish recorded (path={e.get('path')!r}, committed={body.get('committed')})")

    print("[4] POST /publish (PHI in body) → expect action=publish_blocked...")
    r = httpx.post(
        f"{BASE}/publish",
        json={
            "space": SPACE,
            "slug": "audit-log-test-phi",
            "content": "# Bad entry\n\nMRN: 12345678 should be blocked.",
            "frontmatter": {},
        },
        timeout=30,
    )
    r.raise_for_status()
    blocked_body = r.json()
    entries = read_entries()
    if not entries or entries[-1]["action"] != "publish_blocked":
        failures.append(
            f"expected last entry action=publish_blocked, got {entries[-1] if entries else None}; body={blocked_body}"
        )
    else:
        print(f"    PASS: publish_blocked recorded (error={blocked_body.get('error', '')[:60]!r})")

    print("[5] verify_chain() on intact log → expect (True, N>=3, None)...")
    ok, n, err_idx = audit.verify_chain(SPACE, home=HOME)
    if not (ok and n >= 3 and err_idx is None):
        failures.append(f"verify_chain on intact log: ok={ok} n={n} err_idx={err_idx}")
    else:
        print(f"    PASS: chain ok, {n} entries verified")

    print("[6] Corrupt a middle entry → verify_chain should return (False, idx)...")
    raw_lines = AUDIT_LOG.read_bytes().splitlines(keepends=True)
    if len(raw_lines) < 2:
        failures.append("need >=2 entries to test corruption; got fewer")
    else:
        target_idx = len(raw_lines) // 2  # middle entry (not the first)
        if target_idx == 0:
            target_idx = 1
        original = raw_lines[target_idx]
        tampered = json.loads(original)
        # Mutate a field without touching hash_prev — chain hash over the
        # tampered line will then mismatch what the NEXT entry recorded.
        tampered["metadata"] = {"tampered": True}
        # Preserve same field order on rewrite.
        new_line = (
            json.dumps(tampered, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
            + b"\n"
        )
        raw_lines[target_idx] = new_line
        AUDIT_LOG.write_bytes(b"".join(raw_lines))

        ok2, n2, err_idx2 = audit.verify_chain(SPACE, home=HOME)
        # The tampered line's hash_prev is still correct, but the NEXT entry's
        # hash_prev no longer matches the tampered line's hash, so we expect a
        # mismatch at target_idx + 1 (if it exists), else at target_idx.
        expected_err_at = target_idx + 1 if target_idx + 1 < len(raw_lines) else target_idx
        if ok2 or err_idx2 != expected_err_at:
            failures.append(
                f"verify_chain on corrupted log: expected ok=False, err_idx={expected_err_at}; "
                f"got ok={ok2} err_idx={err_idx2} n={n2}"
            )
        else:
            print(f"    PASS: chain break detected at entry {err_idx2} (after corruption at {target_idx})")

    print()
    if failures:
        print(f"FAIL ({len(failures)} failures):")
        for f in failures:
            print(f"  - {f}")
        return 1
    print("ALL PASS")
    return 0


if __name__ == "__main__":
    sys.exit(run())
