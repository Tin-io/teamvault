"""Integration test for contextual retrieval prefixes (v0.1 stretch — P1.5).

Flow:
  1. Wipe the sandbox vault state (chunk hashes change in v0.1 — full
     reindex from scratch is expected and required).
  2. Force a /reindex which now uses ``make_context_prefix`` per entry.
  3. Run a handful of queries that should benefit specifically from the
     contextual prefix being embedded with each chunk:
       a. "the team's MRN policy" — should top-rank the MRN policy entry
          (matches the *title-level* "Team policy: MRN handling" via the
          prefix even though "the team" isn't in the body)
       b. "example domain pattern" — should top-rank the example workflow
          entry via the title + domain tag in the prefix
       c. a pure tag-only query ("example workflow") — should top-rank
          the matching entry via tags rendered into the prefix
  4. Assert the expected entry is top-1 for each query.

Prerequisites: sidecar running on $TEAMVAULT_PORT (default 18100) with
``TEAMVAULT_HOME=.../teamvault-sandbox/.teamvault-home`` and
``TEAMVAULT_SPACE_ROOT=.../teamvault-sandbox``.

The .teamvault-home directory is wiped at the start of this test because
the v0.1 chunk hashes are not compatible with v0.0 — see the module
docstring in ``sidecar/ingest.py`` for the rationale.
"""
from __future__ import annotations

import os
import shutil
import sys
from pathlib import Path

import httpx


PORT = int(os.environ.get("TEAMVAULT_PORT", "18100"))
SBX = Path(
    os.environ.get(
        "TEAMVAULT_SPACE_ROOT",
        "/tmp/teamvault-sandbox",
    )
)
HOME = Path(
    os.environ.get(
        "TEAMVAULT_HOME",
        "/tmp/teamvault-sandbox/.teamvault-home",
    )
)
SPACE = "teamvault-template"
URL = f"http://localhost:{PORT}"


# Each case: (query, expected entry-path filename substring, label)
CASES: list[tuple[str, str, str]] = [
    (
        "the team's MRN policy",
        "seed-team-policy-mrn-handling",
        "title-level match via prefix (the 'team policy' framing is in the title, not body)",
    ),
    (
        "example service patient-care workflow",
        "seed-pattern-example-workflow",
        "tag-driven match via prefix (patient-care, workflow, example tags)",
    ),
    (
        "example workflow export decision",
        "seed-decision-example-export",
        "tag-driven match via prefix (example, workflow, export)",
    ),
]


def _post(path: str, body: dict, timeout: float = 60.0) -> dict:
    r = httpx.post(f"{URL}{path}", json=body, timeout=timeout)
    r.raise_for_status()
    return r.json()


def _wipe_state() -> None:
    """Wipe the per-space state dir so the reindex is from-scratch.

    v0.1 changes the chunk content_hash to include the prefix; that means a
    v0.0 vault.lance is incompatible. Wipe & rebuild from kb/entries.
    """
    space_dir = HOME / SPACE
    if space_dir.exists():
        for child in ("vault.lance", "fts.db"):
            target = space_dir / child
            if target.exists():
                if target.is_dir():
                    shutil.rmtree(target)
                else:
                    target.unlink()
        print(f"  wiped vault.lance and fts.db under {space_dir}")
    else:
        print(f"  no state dir at {space_dir} (fresh)")


def _search(query: str, top_k: int = 5) -> list[dict]:
    return _post("/search", {"query": query, "top_k": top_k, "space": SPACE}, timeout=30)[
        "results"
    ]


def run() -> int:
    failures: list[str] = []

    print("[setup] Wiping sandbox vault state for v0.1 chunk-hash break...")
    _wipe_state()

    print("[setup] Triggering full reindex (uses contextual prefixes now)...")
    counts = _post("/reindex", {"space": SPACE}, timeout=180)
    print(f"  reindex: {counts}")
    if counts["errors"] > 0:
        failures.append(f"reindex errored ({counts['errors']})")

    print()
    for query, expected_substr, label in CASES:
        print(f"[query] {query!r}  — expect top-1 matches *{expected_substr}*")
        print(f"        ({label})")
        hits = _search(query, top_k=5)
        if not hits:
            print("        FAIL: no hits returned")
            failures.append(f"no hits for {query!r}")
            continue
        # Print the top 3 hits for diagnostics.
        for i, h in enumerate(hits[:3]):
            path = Path(h["path"]).name
            print(f"          {i + 1}. score={h['score']:.4f}  {path}")
        top_path = Path(hits[0]["path"]).name
        if expected_substr in top_path:
            print(f"        PASS: top-1 is {top_path}")
        else:
            print(f"        FAIL: top-1 is {top_path}, expected to contain {expected_substr!r}")
            failures.append(f"top-1 mismatch for {query!r}")
        print()

    if failures:
        print(f"\n{len(failures)} failure(s):")
        for f in failures:
            print(f"  - {f}")
        return 1
    print("\nAll contextual-prefix retrieval cases passed.")
    return 0


if __name__ == "__main__":
    sys.exit(run())
