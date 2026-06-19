"""Verify the expanded PHI pattern bank catches realistic example edge cases that the
original (Phase 1) bank missed. Requires sidecar running on $TEAMVAULT_PORT.

Each case constructs a unified diff with `+` lines containing the PHI variant and
verifies the hipaa-reference reviewer returns pass_or_fail=fail with overall=block.
"""
from __future__ import annotations

import json
import os
import sys

import httpx


PORT = int(os.environ.get("TEAMVAULT_PORT", "18100"))
URL = f"http://localhost:{PORT}/review"


CASES = [
    # (label, +diff line, expected_block?)
    ("Phase 1: MRN with prefix",     "+MRN: 12345678",                                 True),
    ("Phase 1: SSN dashed",          "+SSN to record: 123-45-6789",                    True),
    ("BARE 8-digit MRN near keyword","+patient 47218291 had reaction last visit",     True),
    ("Patient: <number>",            "+Patient: 12345678 - notes attached",            True),
    ("Pt#",                          "+Notes for Pt# 8675309 follow",                  True),
    ("SSN with spaces",              "+The id 123 45 6789 should match",               True),
    ("SSN with dots",                "+The id 123.45.6789 should match",               True),
    ("Email",                        "+contact patient at jdoe@example.com tomorrow",  True),
    ("US phone parens",              "+call (415) 555-1234 for results",               True),
    ("US phone dashed",              "+call 415-555-1234 for results",                 True),
    ("Bare DOB near keyword",        "+patient born 06/12/1985 - check records",       True),
    ("DOB with explicit prefix",     "+DOB: 06/12/1985",                               True),
    ("NPI",                          "+Provider ID: 1234567890 attended",              True),
    # Negative cases — should NOT block
    ("Empty diff",                   "",                                               False),
    ("Pattern docs (clean)",         "+This file describes MRN handling but contains no actual numbers", False),
    # Synthetic test data is correctly NOT blocked because \bMRN doesn't match after underscore
    # (underscores are word characters; word boundary fails). Per seed KB MRN-policy entry.
    ("SYNTHETIC_MRN allowed via word-boundary", "+SYNTHETIC_MRN: 12345678", False),
    ("Just a number",                "+x = 47218291  # iteration count",               False),  # no patient-context keyword nearby
    ("ClickUp link only",            "+see https://app.clickup.com/t/abc",             False),
]


def run() -> int:
    fail_count = 0
    pass_count = 0
    for label, line, should_block in CASES:
        diff = f"+++ b/test.py\n@@ +1,1 @@\n{line}\n" if line else ""
        resp = httpx.post(URL, json={"space": "teamvault-template", "diff": diff}, timeout=10)
        resp.raise_for_status()
        data = resp.json()
        hipaa = next((v for v in data["individual"] if v["pack"] == "hipaa-reference"), None)
        if hipaa is None:
            print(f"  [FAIL] {label}: no hipaa verdict")
            fail_count += 1
            continue
        blocked = data["overall"] == "block"
        ok = blocked == should_block
        mark = "✓" if ok else "✗"
        if ok:
            pass_count += 1
        else:
            fail_count += 1
        msg = hipaa["message"][:90]
        print(f"  {mark} [{label:46}] expect_block={should_block}, got_block={blocked}  | {msg}")
    print(f"\n{pass_count} passed, {fail_count} failed of {len(CASES)} cases")
    return 0 if fail_count == 0 else 1


if __name__ == "__main__":
    sys.exit(run())
