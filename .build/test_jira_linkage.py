"""Verify the jira-linkage pack's runtime behavior against the sandbox.

Cases:
1. Diff with bare PROJ-1234 → jira-linkage passes; advisory does not block.
2. Diff with atlassian.net/browse/PROJ-1234 URL → jira-linkage passes.
3. Diff with ENG-567 (different project key) → jira-linkage passes.
4. Diff with no Jira reference → jira-linkage advisory fails (but overall=pass since advisory).
5. Diff with PHI → hipaa-reference still blocks (regression test).
6. Diff with both Jira link and ClickUp link → both advisory packs pass.
"""
from __future__ import annotations

import json
import os
import sys

import httpx


PORT = int(os.environ.get("TEAMVAULT_PORT", "18100"))
URL = f"http://localhost:{PORT}/review"


def review(diff: str) -> dict:
    r = httpx.post(URL, json={"space": "teamvault-template", "diff": diff}, timeout=30)
    r.raise_for_status()
    return r.json()


def find(result: dict, pack: str) -> dict | None:
    return next((v for v in result["individual"] if v["pack"] == pack), None)


CASES = [
    {
        "label": "bare PROJ-1234 in diff",
        "diff": "+++ b/src/foo.ts\n@@ +1 @@\n+// implements PROJ-1234\n+export const foo = 1;\n",
        "expect_jira_pass": True,
        "expect_overall": "pass",
    },
    {
        "label": "atlassian.net URL in diff",
        "diff": "+++ b/README.md\n@@ +1,2 @@\n+## Notes\n+see https://your-org.atlassian.net/browse/PROJ-9876 for context\n",
        "expect_jira_pass": True,
        "expect_overall": "pass",
    },
    {
        "label": "ENG-567 (different project key)",
        "diff": "+++ b/src/eng.ts\n@@ +1 @@\n+// ENG-567 — refactor request\n+export const x = 2;\n",
        "expect_jira_pass": True,
        "expect_overall": "pass",
    },
    {
        "label": "no Jira reference (advisory fails)",
        "diff": "+++ b/src/orphan.ts\n@@ +1 @@\n+// just a random refactor\n+export const y = 3;\n",
        "expect_jira_pass": False,
        "expect_overall": "pass",  # advisory does not block overall
    },
    {
        "label": "PHI diff (regression: hipaa-reference still blocks)",
        "diff": "+++ b/test.py\n@@ +1 @@\n+MRN: 12345678 belongs to patient\n",
        "expect_jira_pass": False,
        "expect_overall": "block",  # hipaa-reference is blocking
    },
    {
        "label": "both Jira + ClickUp linked",
        "diff": "+++ b/README.md\n@@ +1,2 @@\n+see PROJ-1234\n+also https://app.clickup.com/t/abc\n",
        "expect_jira_pass": True,
        "expect_overall": "pass",
    },
]


def main() -> int:
    failures: list[str] = []
    for case in CASES:
        result = review(case["diff"])
        jira = find(result, "jira-linkage")
        if jira is None:
            failures.append(f"{case['label']}: jira-linkage verdict missing entirely")
            print(f"  ✗ [{case['label']}] FAIL: jira-linkage verdict missing")
            continue
        jira_passed = jira["pass_or_fail"] == "pass"
        overall = result["overall"]

        ok = (jira_passed == case["expect_jira_pass"]) and (overall == case["expect_overall"])
        mark = "✓" if ok else "✗"
        if not ok:
            failures.append(case["label"])
        print(
            f"  {mark} [{case['label']:50}] "
            f"jira={'PASS' if jira_passed else 'FAIL'} (expected {'PASS' if case['expect_jira_pass'] else 'FAIL'}) | "
            f"overall={overall} (expected {case['expect_overall']}) | "
            f"msg={jira['message']}"
        )

    print(f"\n{len(CASES) - len(failures)} passed, {len(failures)} failed of {len(CASES)} cases")
    return 0 if not failures else 1


if __name__ == "__main__":
    sys.exit(main())
