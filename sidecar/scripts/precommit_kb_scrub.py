"""Pre-commit scrubber for kb/** changes — runs PackRuntime against staged content.

Refuses commit (exit 1) when any blocking pack reviewer matches the staged kb/**
diff. Advisory matches are surfaced but allow the commit, per the pack contract.

Source: P0.2 (docs/ROADMAP.md). Invoked by `sidecar/hooks/pre-commit` (installed
by /teamvault-setup §4.5). Pack runtime intentionally reused as-is per the
ticket body — keeps the local hook and PR-time workflow on one engine.

Usage
-----
    python -m sidecar.scripts.precommit_kb_scrub

Run from inside the space repo (cwd = git toplevel). Reads the staged kb/**
diff via `git diff --cached -- kb/` and feeds it to `PackRuntime.fan_out_review`.

Exit codes
----------
- 0: no kb/ changes, no enabled packs, all clean, or advisory-only matches
- 1: a blocking pack reviewer matched — commit refused
- 2: tooling error (git unavailable, PackRuntime not importable)
"""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path


def staged_kb_diff() -> str:
    """Return the unified diff of staged changes restricted to kb/**, or empty."""
    try:
        result = subprocess.run(
            ["git", "diff", "--cached", "--", "kb/"],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            check=True,
        )
    except FileNotFoundError:
        print("teamvault pre-commit: git not on PATH", file=sys.stderr)
        sys.exit(2)
    except subprocess.CalledProcessError as e:
        print(f"teamvault pre-commit: git diff failed: {e.stderr.strip()}", file=sys.stderr)
        sys.exit(2)
    return result.stdout


def main() -> int:
    diff = staged_kb_diff()
    if not diff.strip():
        return 0  # no kb/ changes staged → commit proceeds

    try:
        from sidecar.pack_runtime import PackRuntime
    except ImportError as e:
        print(f"teamvault pre-commit: pack_runtime not importable: {e}", file=sys.stderr)
        return 2

    runtime = PackRuntime(Path.cwd())
    if not runtime.packs:
        return 0  # space has no enabled packs; nothing to scrub

    verdict = runtime.fan_out_review(diff)
    fails = [v for v in verdict.individual if v.pass_or_fail == "fail"]

    if not fails:
        return 0

    # Surface every failure (blocking + advisory) so devs see full context.
    header = "BLOCKED" if verdict.overall == "block" else "advisory matches (commit allowed)"
    print(f"teamvault pre-commit: {header}", file=sys.stderr)
    for v in fails:
        tag = "BLOCK" if v.mode == "blocking" else "ADVISORY"
        print(f"  [{tag} {v.pack}/{v.agent}] {v.message}", file=sys.stderr)

    if verdict.overall == "block":
        print(
            "\nResolve the matches and re-stage, or publish via /teamvault-publish "
            "(which scrubs before commit).",
            file=sys.stderr,
        )
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
