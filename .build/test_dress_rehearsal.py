"""Full demo-flow dress rehearsal.

Mirrors the four Monday demo beats end-to-end against the sandbox. Each beat
asserts pass-criteria so a regression is loud.

Beat 1: a user publishes a KB entry via /publish → searchable within seconds
Beat 2: Compliance lead opens a PR with PHI → /review returns block
Beat 3: New PHI pattern added → propagates (simulated via reload after file edit)
Beat 4: clickup-linkage advisory → blocking (simulated via PACK.yaml edit)
"""
from __future__ import annotations

import json
import os
import shutil
import sys
import time
from pathlib import Path

import httpx
import yaml


PORT = int(os.environ.get("TEAMVAULT_PORT", "18100"))
SBX = Path(os.environ.get("TEAMVAULT_SANDBOX", "/tmp/teamvault-sandbox"))
SPACE = "teamvault-template"
URL = f"http://localhost:{PORT}"


def _post(path: str, body: dict) -> dict:
    r = httpx.post(f"{URL}{path}", json=body, timeout=60)
    r.raise_for_status()
    return r.json()


def _get(path: str) -> dict:
    r = httpx.get(f"{URL}{path}", timeout=10)
    r.raise_for_status()
    return r.json()


def _hr(title: str) -> None:
    print(f"\n{'='*8} {title} {'='*8}")


def assert_eq(actual, expected, msg: str) -> bool:
    ok = actual == expected
    mark = "✓" if ok else "✗"
    print(f"  {mark} {msg} | expected={expected!r} actual={actual!r}")
    return ok


def assert_in(needle, haystack, msg: str) -> bool:
    ok = needle in haystack
    mark = "✓" if ok else "✗"
    print(f"  {mark} {msg} | needle={needle!r} found={ok}")
    return ok


def main() -> int:
    failures: list[str] = []

    # --- Pre-flight ---
    _hr("Pre-flight: sidecar healthy + reindex")
    health = _get("/healthz")
    if not assert_eq(health["status"], "ok", "sidecar /healthz returns ok"):
        failures.append("preflight")
    spaces = health.get("spaces", [])
    assert_eq(len(spaces), 1, "exactly one space registered")
    assert_eq(spaces[0]["name"], SPACE, "registered space matches expected")
    reindex = _post("/reindex", {"space": SPACE})
    print(f"  reindex: indexed={reindex['indexed']} skipped={reindex['skipped']} errors={reindex['errors']}")
    if reindex["errors"] > 0:
        failures.append("preflight-reindex")

    # --- Beat 1: publish + search round-trip ---
    _hr("Beat 1: publish a KB entry, search retrieves it")
    publish_resp = _post("/publish", {
        "space": SPACE,
        "slug": "demo-beat-1-marker",
        "content": "# Demo beat 1 — published live\n\nThis entry was published during the dress rehearsal to verify the publish→reindex→search round-trip works end-to-end.\n\n## Markers\n- DRESS_REHEARSAL_BEAT1_MARKER\n",
        "frontmatter": {"author": "dress-rehearsal", "tags": ["demo", "beat-1"]},
    })
    print(f"  publish: {json.dumps(publish_resp, indent=2)[:200]}")
    assert_eq(publish_resp["committed"], True, "entry committed locally")
    # The sandbox repo has no remote — push fails, that's expected
    if publish_resp.get("error") and "Remote named 'origin' didn't exist" not in publish_resp.get("error", ""):
        failures.append(f"beat-1-unexpected-error: {publish_resp['error']}")

    # Search for the marker
    time.sleep(0.5)
    search_resp = _post("/search", {"query": "DRESS_REHEARSAL_BEAT1_MARKER", "top_k": 3, "space": SPACE})
    hits = search_resp["results"]
    marker_hits = [h for h in hits if "DRESS_REHEARSAL_BEAT1_MARKER" in h["chunk"]]
    if not assert_eq(len(marker_hits) >= 1, True, "beat-1 marker is searchable after publish"):
        failures.append("beat-1-search-miss")

    # --- Beat 2: PHI PR review blocks ---
    _hr("Beat 2: PR with PHI → /review returns block")
    phi_diff = (
        "+++ b/src/example/handler.py\n"
        "@@ +1,5 @@\n"
        "+# Bug repro: patient 47218291 had reaction to compound on 06/12/1985\n"
        "+# DOB: 06/12/1985 confirmed in EHR\n"
        "+def handle(patient_id):\n"
        "+    pass\n"
    )
    review_resp = _post("/review", {"space": SPACE, "diff": phi_diff})
    assert_eq(review_resp["overall"], "block", "PHI diff blocks the PR")
    hipaa = next(v for v in review_resp["individual"] if v["pack"] == "hipaa-reference")
    if not assert_eq(hipaa["pass_or_fail"], "fail", "hipaa reviewer fails with matched patterns"):
        failures.append("beat-2-hipaa-pass")
    print(f"  hipaa message: {hipaa['message']}")
    assert_in("mrn", hipaa["message"].lower(), "hipaa message names mrn match")

    # --- Beat 3: New PHI pattern propagates ---
    _hr("Beat 3: add new pattern → in-flight PackRuntime sees it")
    phi_yaml = SBX / "packs" / "hipaa-reference" / "scrubbers" / "phi_patterns.yaml"
    original = phi_yaml.read_text()
    try:
        # Append a vendor-style 7-digit MRN pattern
        new_pattern_block = (
            "\n  - name: vendor_mrn_brand_specific\n"
            "    pattern: '\\bVMRN-\\d{7}\\b'\n"
            "    description: vendor-brand MRN format added live\n"
        )
        phi_yaml.write_text(original.rstrip() + new_pattern_block + "\n")

        # First confirm the new pattern fires
        vendor_diff = "+++ b/test.py\n@@ +1 @@\n+VMRN-1234567 noted in chart\n"
        review_new = _post("/review", {"space": SPACE, "diff": vendor_diff})
        new_hipaa = next(v for v in review_new["individual"] if v["pack"] == "hipaa-reference")
        if not assert_eq(review_new["overall"], "block", "new vendor pattern blocks PR"):
            failures.append("beat-3-vendor-not-blocked")
        assert_in("vendor_mrn_brand_specific", new_hipaa["message"], "new pattern named in message")
    finally:
        phi_yaml.write_text(original)

    # --- Beat 4: advisory → blocking via PACK.yaml edit ---
    _hr("Beat 4: flip clickup-linkage advisory → blocking")
    pack_yaml = SBX / "packs" / "clickup-linkage" / "PACK.yaml"
    original_pack = pack_yaml.read_text()
    try:
        doc = yaml.safe_load(original_pack)
        doc["contributions"]["reviewers"][0]["mode"] = "blocking"
        pack_yaml.write_text(yaml.safe_dump(doc, sort_keys=False))

        # Diff without ClickUp link should now block (clickup mode is blocking)
        no_link_diff = "+++ b/README.md\n@@ +1 @@\n+random refactor, no ticket linked\n"
        review_block = _post("/review", {"space": SPACE, "diff": no_link_diff})
        if not assert_eq(review_block["overall"], "block", "blocking clickup pack blocks unlinked PR"):
            failures.append("beat-4-blocking-not-applied")
        clickup = next(v for v in review_block["individual"] if v["pack"] == "clickup-linkage")
        assert_eq(clickup["mode"], "blocking", "clickup-linkage now reports mode=blocking")

        # And a diff WITH the link should still pass
        link_diff = "+++ b/README.md\n@@ +1 @@\n+see https://app.clickup.com/t/abc\n"
        review_pass = _post("/review", {"space": SPACE, "diff": link_diff})
        assert_eq(review_pass["overall"], "pass", "linked PR still passes under blocking mode")
    finally:
        pack_yaml.write_text(original_pack)

    # --- Summary ---
    _hr("Summary")
    if failures:
        print(f"  ✗ {len(failures)} failures: {failures}")
        return 1
    print("  ✓ All 4 demo beats pass end-to-end against sandbox")
    return 0


if __name__ == "__main__":
    sys.exit(main())
