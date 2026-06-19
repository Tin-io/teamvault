"""Verify the stale-row deletion fix (code-quality critic F2 — ghost chunks).

Flow:
  1. Confirm sandbox is indexed (3 entries from seeds).
  2. Search for a unique marker known to be in the MRN-policy entry → expect hit.
  3. Delete the MRN-policy entry file from disk.
  4. Force reindex.
  5. Search for the same marker → expect NO hit (stale rows must have been deleted).
  6. Restore the entry from main repo and reindex → marker comes back.
"""
from __future__ import annotations

import os
import shutil
import sys
from pathlib import Path

import httpx


PORT = int(os.environ.get("TEAMVAULT_PORT", "18100"))
SBX = Path(os.environ.get("TEAMVAULT_SANDBOX", "/tmp/teamvault-sandbox"))
MAIN = Path(__file__).resolve().parent.parent
SPACE = "teamvault-template"
ENTRY_NAME = "2026-06-13-seed-team-policy-mrn-handling.md"
# Unique multi-word phrase known to be only in the MRN-policy entry
MARKER = "MRN format variations"


def search(query: str) -> list[dict]:
    r = httpx.post(
        f"http://localhost:{PORT}/search",
        json={"query": query, "top_k": 5, "space": SPACE},
        timeout=15,
    )
    r.raise_for_status()
    return r.json()["results"]


def reindex() -> dict:
    r = httpx.post(f"http://localhost:{PORT}/reindex", json={"space": SPACE}, timeout=120)
    r.raise_for_status()
    return r.json()


def run() -> int:
    failures = 0

    print("[1] Confirm marker present in indexed sandbox...")
    hits = search(MARKER)
    marker_hits = [h for h in hits if MARKER.lower() in h["chunk"].lower()]
    print(f"    initial hits with marker: {len(marker_hits)}")
    if not marker_hits:
        print("    FAIL: marker not found even before deletion — seed entry missing or unindexed")
        return 1

    print("[2] Delete the MRN-policy entry from sandbox disk...")
    entry_path = SBX / "kb" / "entries" / ENTRY_NAME
    if not entry_path.exists():
        print(f"    FAIL: expected entry not on disk: {entry_path}")
        return 1
    entry_path.unlink()

    print("[3] Trigger reindex...")
    counts = reindex()
    print(f"    {counts}")

    print("[4] Search for the marker again — expect NO hit chunks containing the marker phrase...")
    hits_after = search(MARKER)
    marker_hits_after = [h for h in hits_after if MARKER.lower() in h["chunk"].lower()]
    print(f"    post-delete hits with marker: {len(marker_hits_after)}")
    if marker_hits_after:
        print(f"    FAIL: stale chunk still surfaced — {[h['path'] for h in marker_hits_after]}")
        failures += 1
    else:
        print("    PASS: stale rows correctly deleted")

    print("[5] Restore entry from main repo and reindex...")
    shutil.copy(MAIN / "kb" / "entries" / ENTRY_NAME, entry_path)
    counts = reindex()
    print(f"    {counts}")
    hits_restore = search(MARKER)
    marker_hits_restore = [h for h in hits_restore if MARKER.lower() in h["chunk"].lower()]
    if not marker_hits_restore:
        print("    FAIL: restored entry not searchable")
        failures += 1
    else:
        print(f"    PASS: marker is searchable again ({len(marker_hits_restore)} hits)")

    return 0 if failures == 0 else 1


if __name__ == "__main__":
    sys.exit(run())
