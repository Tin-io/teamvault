"""Unit tests for ``sidecar.ingest.make_context_prefix`` (v0.1 stretch — P1.5).

This test does NOT require a running sidecar — it imports the function
directly and exercises edge cases on the static (no-LLM) prefix builder.

Cases:
  - normal entry → contains title, type, date, tags, and summary
  - empty frontmatter → still produces a valid prefix using fallbacks
  - empty body → prefix returns a sane minimal fallback (no summary clause)
  - many tags → prefix capped at _PREFIX_MAX_TAGS
  - no H1 in body → uses fallback_title
  - frontmatter with non-list tags → does not crash
"""
from __future__ import annotations

import sys
from pathlib import Path

# Allow running this file directly (`python .build/test_make_context_prefix.py`)
# from the repo root without setting PYTHONPATH.
_REPO_ROOT = Path(__file__).resolve().parent.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from sidecar.ingest import _PREFIX_MAX_TAGS, make_context_prefix  # noqa: E402


def _expect(label: str, cond: bool, detail: str = "") -> int:
    mark = "PASS" if cond else "FAIL"
    print(f"  [{mark}] {label}" + (f" — {detail}" if detail and not cond else ""))
    return 0 if cond else 1


def run() -> int:
    failures = 0

    # ---------- Case 1: well-formed entry ----------
    fm = {
        "decision_type": "policy",
        "created": "2026-06-13",
        "tags": ["hipaa", "mrn", "team-policy"],
    }
    body = (
        "# Team policy: MRN handling in code and KB\n\n"
        "## Policy\n\n"
        "Medical Record Numbers must never appear in plaintext in any surface."
    )
    prefix = make_context_prefix(fm, body)
    failures += _expect(
        "well-formed: contains title",
        "Team policy: MRN handling in code and KB" in prefix,
        prefix,
    )
    failures += _expect("well-formed: contains entry_type", "policy" in prefix, prefix)
    failures += _expect("well-formed: contains created", "2026-06-13" in prefix, prefix)
    failures += _expect(
        "well-formed: contains tags",
        "hipaa" in prefix and "team-policy" in prefix,
        prefix,
    )
    failures += _expect(
        "well-formed: contains summary fragment",
        "Medical Record Numbers" in prefix,
        prefix,
    )
    failures += _expect(
        "well-formed: heading marker dropped from summary",
        "## Policy" not in prefix,
        prefix,
    )

    # ---------- Case 2: empty frontmatter ----------
    prefix2 = make_context_prefix({}, "# Some Title\n\nBody content here.")
    failures += _expect(
        "empty fm: produces non-empty prefix",
        bool(prefix2) and "Some Title" in prefix2,
        prefix2,
    )
    failures += _expect(
        "empty fm: entry_type falls back to 'entry'",
        "entry" in prefix2,
        prefix2,
    )
    failures += _expect(
        "empty fm: created falls back to 'unknown date'",
        "unknown date" in prefix2,
        prefix2,
    )
    failures += _expect(
        "empty fm: tags falls back to 'none'",
        "Tags: none" in prefix2,
        prefix2,
    )

    # ---------- Case 3: empty body ----------
    prefix3 = make_context_prefix({}, "")
    failures += _expect(
        "empty body: still produces a valid prefix",
        prefix3.startswith("From \"untitled\""),
        prefix3,
    )
    failures += _expect(
        "empty body: no summary clause appended",
        not prefix3.endswith(" "),
        prefix3,
    )

    # ---------- Case 4: many tags, capped ----------
    fm_many = {
        "decision_type": "pattern",
        "created": "2026-06-13",
        "tags": [f"tag{i}" for i in range(20)],
    }
    prefix4 = make_context_prefix(fm_many, "# T\n\nB.")
    # count tag0..tag19 occurrences in the tags segment
    rendered_tags = [f"tag{i}" for i in range(20) if f"tag{i}" in prefix4]
    failures += _expect(
        f"many tags: capped at {_PREFIX_MAX_TAGS}",
        len(rendered_tags) == _PREFIX_MAX_TAGS,
        f"rendered {len(rendered_tags)}: {rendered_tags}",
    )

    # ---------- Case 5: no H1, uses fallback_title ----------
    prefix5 = make_context_prefix(
        {"decision_type": "decision", "created": "2026-06-13", "tags": ["x"]},
        "No heading body here.\n\nMore text.",
        fallback_title="my-filename-stem",
    )
    failures += _expect(
        "no-H1: uses fallback_title",
        "my-filename-stem" in prefix5,
        prefix5,
    )

    # ---------- Case 6: tags as a single string (not list) ----------
    fm_str_tag = {"decision_type": "note", "created": "2026-06-13", "tags": "lonely"}
    prefix6 = make_context_prefix(fm_str_tag, "# Heading\n\nSome content.")
    failures += _expect(
        "string tag: normalized into csv",
        "lonely" in prefix6 and "Tags: lonely" in prefix6,
        prefix6,
    )

    # ---------- Case 7: None frontmatter (safety) ----------
    prefix7 = make_context_prefix(None, "# T\n\nBody.")  # type: ignore[arg-type]
    failures += _expect(
        "None fm: does not crash and produces prefix",
        bool(prefix7) and "T" in prefix7,
        prefix7,
    )

    print(f"\n{failures} failure(s).")
    return 0 if failures == 0 else 1


if __name__ == "__main__":
    sys.exit(run())
