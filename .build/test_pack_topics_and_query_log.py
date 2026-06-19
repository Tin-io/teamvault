"""Acceptance test for Part 3: pack topics + query usage log.

Source: PLAN-2026-06-16-pack-knowledge-topics-and-query-log.md::Acceptance criteria.

Flow
----
  1. Wipe audit log for the sandbox space.
  2. GET /packs — assert hipaa-reference returns knowledge_topics containing
     both 'hipaa' and 'safe-harbor'.
  3. POST /search with purpose="deciding config rotation for example-service", top_k=3
     — assert response has UUID4-shape query_id and results list.
  4. POST /cite with that query_id, non-empty paths_used, note
     — expect 200, recorded=true.
  5. POST /cite with paths_used=[] (nothing useful)
     — expect 200, recorded=true.
  6. GET /query_log?limit=10 — assert ≥3 rows (1 search + 2 cites);
     chain_ok=true; cite rows' metadata.query_id == search row's
     metadata.query_id.
  7. Tamper: flip a byte in a middle entry. GET /query_log — assert
     chain_ok=false.

Backward-compat note: the existing .build/test_audit_log.py and
.build/test_mcp_e2e.py must still pass independently.

Run against the sandbox sidecar:
  TEAMVAULT_HOME=/tmp/teamvault-sandbox/.teamvault-home \\
  TEAMVAULT_SPACE_ROOT=/tmp/teamvault-sandbox \\
  TEAMVAULT_PORT=18100 \\
  python .build/test_pack_topics_and_query_log.py
"""
from __future__ import annotations

import json
import os
import re
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

# uuid4().hex shape: 32 lowercase hex chars.
UUID_HEX_RE = re.compile(r"^[a-f0-9]{32}$")


def wipe_log() -> None:
    if AUDIT_LOG.exists():
        AUDIT_LOG.unlink()


def run() -> int:
    failures: list[str] = []

    print(f"[setup] sidecar: {BASE}")
    print(f"[setup] audit log: {AUDIT_LOG}")

    print("[1] Wipe existing audit log...")
    wipe_log()
    assert not AUDIT_LOG.exists()

    print("[2] GET /packs — expect hipaa-reference with knowledge_topics...")
    r = httpx.get(f"{BASE}/packs", params={"space": SPACE}, timeout=10)
    r.raise_for_status()
    packs_body = r.json()
    by_name = {p["name"]: p for p in packs_body.get("packs", [])}
    hipaa = by_name.get("hipaa-reference")
    if not hipaa:
        failures.append(f"hipaa-reference not in /packs response: {packs_body}")
    else:
        topics = set(hipaa.get("knowledge_topics") or [])
        for required in ("hipaa", "safe-harbor"):
            if required not in topics:
                failures.append(
                    f"hipaa-reference knowledge_topics missing {required!r}: {topics}"
                )
        if not failures:
            print(
                f"    PASS: hipaa-reference topics include hipaa + safe-harbor "
                f"(mode_summary={hipaa.get('mode_summary')!r})"
            )

    print("[3] POST /search with purpose= — expect query_id + results...")
    r = httpx.post(
        f"{BASE}/search",
        json={
            "query": "config rotation policy",
            "top_k": 3,
            "space": SPACE,
            "purpose": "deciding config rotation for example-service",
        },
        timeout=30,
    )
    r.raise_for_status()
    search_body = r.json()
    query_id = search_body.get("query_id", "")
    if not UUID_HEX_RE.match(query_id):
        failures.append(f"query_id not UUID4 hex shape: {query_id!r}")
    elif "results" not in search_body or not isinstance(search_body["results"], list):
        failures.append(f"search response missing results list: {search_body}")
    else:
        print(
            f"    PASS: search returned query_id={query_id[:12]}... + "
            f"{len(search_body['results'])} results"
        )

    print("[4] POST /cite with non-empty paths_used — expect recorded=true...")
    r = httpx.post(
        f"{BASE}/cite",
        json={
            "space": SPACE,
            "query_id": query_id,
            "paths_used": [
                "kb/entries/2026-06-15-example-decision-a73b4000.md",
            ],
            "note": "applied a config-rotation policy from an example decision to example-service",
        },
        timeout=10,
    )
    r.raise_for_status()
    cite_body_1 = r.json()
    if not cite_body_1.get("recorded"):
        failures.append(f"first /cite did not record: {cite_body_1}")
    else:
        print("    PASS: first cite recorded")

    print("[5] POST /cite with paths_used=[] — expect recorded=true...")
    r = httpx.post(
        f"{BASE}/cite",
        json={
            "space": SPACE,
            "query_id": query_id,
            "paths_used": [],
            "note": "follow-up search; nothing additional was useful",
        },
        timeout=10,
    )
    r.raise_for_status()
    cite_body_2 = r.json()
    if not cite_body_2.get("recorded"):
        failures.append(f"empty /cite did not record: {cite_body_2}")
    else:
        print("    PASS: empty cite recorded")

    print("[6] GET /query_log?limit=10 — expect ≥3 rows, chain_ok=true, "
          "query_id matches across rows...")
    r = httpx.get(
        f"{BASE}/query_log",
        params={"space": SPACE, "limit": 10},
        timeout=10,
    )
    r.raise_for_status()
    log_body = r.json()
    rows = log_body.get("rows", [])
    if not log_body.get("chain_ok"):
        failures.append(f"chain_ok was false on intact log: {log_body}")
    if len(rows) < 3:
        failures.append(f"expected >=3 rows (1 search + 2 cites); got {len(rows)}: {rows}")
    else:
        # Find the search and cite rows; assert query_id matches across.
        search_rows = [r_ for r_ in rows if r_.get("action") == "search"]
        cite_rows = [r_ for r_ in rows if r_.get("action") == "cite"]
        if len(search_rows) < 1:
            failures.append(f"no search rows in /query_log: {rows}")
        elif len(cite_rows) < 2:
            failures.append(f"expected >=2 cite rows in /query_log: cite_rows={cite_rows}")
        else:
            search_qid = search_rows[-1].get("metadata", {}).get("query_id")
            if search_qid != query_id:
                failures.append(
                    f"search row query_id mismatch: row={search_qid!r} expected={query_id!r}"
                )
            for cr in cite_rows[-2:]:
                cr_qid = cr.get("metadata", {}).get("query_id")
                if cr_qid != query_id:
                    failures.append(
                        f"cite row query_id mismatch: row={cr_qid!r} expected={query_id!r}"
                    )
            if not failures:
                print(
                    f"    PASS: {len(rows)} rows, chain_ok=true, "
                    f"search.query_id == cite.query_id (={query_id[:12]}...)"
                )

    print("[7] Tamper test: flip a byte in a middle entry → expect chain_ok=false...")
    raw_lines = AUDIT_LOG.read_bytes().splitlines(keepends=True)
    if len(raw_lines) < 2:
        failures.append("need >=2 entries to test corruption; got fewer")
    else:
        target_idx = len(raw_lines) // 2
        if target_idx == 0:
            target_idx = 1
        original = raw_lines[target_idx]
        tampered = json.loads(original)
        tampered["metadata"] = {"tampered": True}
        new_line = (
            json.dumps(tampered, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
            + b"\n"
        )
        raw_lines[target_idx] = new_line
        AUDIT_LOG.write_bytes(b"".join(raw_lines))

        r = httpx.get(
            f"{BASE}/query_log",
            params={"space": SPACE, "limit": 10},
            timeout=10,
        )
        r.raise_for_status()
        tampered_body = r.json()
        if tampered_body.get("chain_ok"):
            failures.append(
                f"chain_ok stayed true after tamper at line {target_idx}: {tampered_body}"
            )
        else:
            print(f"    PASS: chain_ok=false after tamper at entry {target_idx}")

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
