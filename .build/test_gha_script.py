"""Mirror of the inline `python -c` script in `.github/workflows/teamvault-review.yml`,
extracted so we can run it locally against the sandbox to verify it works before relying
on GHA to execute it.

Reads diff from /tmp/pr.diff (or argv[1]); writes verdict to /tmp/verdict.json.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path


def main() -> int:
    diff_path = Path(sys.argv[1] if len(sys.argv) > 1 else "/tmp/pr.diff")
    out_path = Path(sys.argv[2] if len(sys.argv) > 2 else "/tmp/verdict.json")

    # The GHA cd's into the checkout; pack_runtime is at sidecar/pack_runtime.py.
    # PackRuntime(Path.cwd()) loads packs/* relative to cwd.
    sys.path.insert(0, str(Path.cwd()))

    from sidecar import pack_runtime  # noqa: E402

    diff = diff_path.read_text()
    runtime = pack_runtime.PackRuntime(Path.cwd())
    verdict = runtime.fan_out_review(diff)

    out = {
        "overall": verdict.overall,
        "individual": [
            {"pack": v.pack, "agent": v.agent, "mode": v.mode, "pass_or_fail": v.pass_or_fail, "message": v.message}
            for v in verdict.individual
        ],
    }
    out_path.write_text(json.dumps(out, indent=2))
    print(json.dumps(out, indent=2))
    return 0 if verdict.overall == "pass" else 1


if __name__ == "__main__":
    sys.exit(main())
