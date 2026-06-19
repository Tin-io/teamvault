"""Write or update the TeamVault block in a project repo's CLAUDE.md.

Idempotent. Three behaviors:

- File missing: create CLAUDE.md with just the block.
- Markers present: replace the existing block in place (re-bind safe).
- Markers absent: append the block at the end of CLAUDE.md.

The block is intentionally STATIC — it never enumerates `knowledge_topics`
(those come from `vault_packs()` at runtime). Same block content for every
space.

Source: PLAN-2026-06-16-pack-knowledge-topics-and-query-log.md::Part 4.

Usage
-----
    python -m sidecar.scripts.write_claude_md_block [project_dir]

`project_dir` defaults to the current working directory.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path


BLOCK = """<!-- BEGIN teamvault-block -->
## TeamVault knowledge base

This project is bound to a TeamVault space. The space's enabled packs declare
the knowledge domains the team has accumulated prior art on.

- At the start of substantive work, call `vault_packs()` to see the covered
  domains.
- Before finalizing any design decision that touches a covered domain, call
  `vault_search(query, purpose=...)` — the `purpose` says what you're trying
  to decide.
- After applying or rejecting the results, call `vault_cite(query_id,
  paths_used, note)`. `paths_used=[]` is valid and records "we searched,
  nothing was useful." Always cite when you searched before a substantive
  decision.
- For domain questions outside any enabled pack, demand-side rule applies:
  ask the KB whenever you'd ask a senior teammate.
<!-- END teamvault-block -->"""

# DOTALL: span newlines. Non-greedy: stop at the FIRST close marker so
# duplicate (malformed) blocks downstream are left alone.
_MARKER_RE = re.compile(
    r"<!-- BEGIN teamvault-block -->.*?<!-- END teamvault-block -->",
    re.DOTALL,
)


def write_block(project_dir: Path) -> str:
    """Write or update the block in `{project_dir}/CLAUDE.md`.

    Returns "created" | "replaced" | "appended".
    """
    target = project_dir / "CLAUDE.md"

    if not target.exists():
        target.write_text(BLOCK + "\n")
        return "created"

    text = target.read_text()
    if _MARKER_RE.search(text):
        target.write_text(_MARKER_RE.sub(BLOCK, text))
        return "replaced"

    # Markers absent — append, preserving a single blank-line separator.
    if text.endswith("\n\n"):
        sep = ""
    elif text.endswith("\n"):
        sep = "\n"
    else:
        sep = "\n\n"
    target.write_text(text + sep + BLOCK + "\n")
    return "appended"


def main(argv: list[str] | None = None) -> int:
    args = argv if argv is not None else sys.argv[1:]
    project = Path(args[0]) if args else Path.cwd()
    if not project.exists():
        print(f"ERROR: directory does not exist: {project}", file=sys.stderr)
        return 2
    if not project.is_dir():
        print(f"ERROR: not a directory: {project}", file=sys.stderr)
        return 2
    status = write_block(project)
    print(f"teamvault-block {status} in {project / 'CLAUDE.md'}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
