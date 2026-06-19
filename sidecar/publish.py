"""TeamVault sidecar — publish flow.

Writes KB entry → runs pack scrubbers → commits → optionally pushes → reindexes.
"""
from __future__ import annotations

import hashlib
import re
from datetime import datetime, timezone
from pathlib import Path

from sidecar import config, ingest


def _slug_safe(slug: str) -> str:
    s = re.sub(r"[^a-z0-9-]+", "-", slug.lower()).strip("-")
    return s or "entry"


def _space_root(space: str) -> Path:
    if config.TEAMVAULT_SPACE_ROOT and config.TEAMVAULT_SPACE_ROOT.exists():
        return config.TEAMVAULT_SPACE_ROOT
    candidate = Path.home() / f"teamvault-{space}"
    if candidate.exists():
        return candidate
    raise FileNotFoundError(f"Space root not found for {space!r}")


def _is_compliance_space(root: Path) -> bool:
    """Read the space's compliance flag from space.yaml. Treats missing/unreadable as non-compliance."""
    try:
        import yaml

        doc = yaml.safe_load((root / "space.yaml").read_text()) or {}
        return bool(doc.get("compliance"))
    except Exception:
        return False


def _scrub_text_blob(blob: str, runtime) -> tuple[str, bool]:
    """Run scrubbers; return (scrubbed, any_match)."""
    scrubbed = runtime.fan_out_scrub(blob)
    return scrubbed, scrubbed != blob


def publish_entry(space: str, slug: str, content: str, frontmatter: dict) -> dict:
    """Write KB entry, run scrubbers (incl. on frontmatter values), commit, push, reindex.

    Compliance mode: if `space.yaml::compliance` is true and the pack runtime cannot load,
    publish is REFUSED (fail closed). Non-compliance mode allows publish with a logged warning.
    """
    try:
        root = _space_root(space)
    except FileNotFoundError as e:
        return {"path": "", "committed": False, "pushed": False, "error": str(e)}

    compliance = _is_compliance_space(root)

    # Build the combined text to scrub: content + every frontmatter string value.
    fm_input = dict(frontmatter or {})
    fm_value_strings: list[str] = []
    for v in fm_input.values():
        if isinstance(v, str):
            fm_value_strings.append(v)
        elif isinstance(v, (list, tuple)):
            fm_value_strings.extend(str(x) for x in v if isinstance(x, (str, int, float)))
    scrub_target = "\n".join([content, *fm_value_strings])

    try:
        from sidecar import pack_runtime

        runtime = pack_runtime.PackRuntime(root)
        _, matched = _scrub_text_blob(scrub_target, runtime)
        if matched:
            return {
                "path": "",
                "committed": False,
                "pushed": False,
                "error": "Content blocked by pack scrubber. Sensitive pattern matched in body or frontmatter; review entry.",
            }
    except Exception as e:
        if compliance:
            return {
                "path": "",
                "committed": False,
                "pushed": False,
                "error": f"compliance space: scrubber unavailable; refusing to publish (fail-closed). cause: {e}",
            }
        print(f"warning: pack scrubber not run: {e}")

    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    slug_clean = _slug_safe(slug)
    h = hashlib.sha256(content.encode("utf-8")).hexdigest()[:8]
    filename = f"{today}-{slug_clean}-{h}.md"

    entries_dir = root / "kb" / "entries"
    entries_dir.mkdir(parents=True, exist_ok=True)
    target = entries_dir / filename

    import frontmatter as fm_lib

    fm = dict(fm_input)
    fm.setdefault("created", datetime.now(timezone.utc).isoformat())
    fm.setdefault("source", "/teamvault-publish")
    fm.setdefault("confidence", 0.8)
    fm.setdefault("tags", [])

    # Use `metadata=` rather than **fm to avoid kwarg collisions with Post.__init__
    # reserved names (e.g. `handler`).
    post = fm_lib.Post(content, metadata=fm)
    target.write_text(fm_lib.dumps(post))

    committed = pushed = False
    error: str | None = None
    try:
        from git import Repo

        repo = Repo(root)
        rel = str(target.relative_to(root))
        repo.index.add([rel])
        repo.index.commit(f"kb: publish {slug_clean}")
        committed = True
        if not config.TEAMVAULT_DRY_RUN:
            try:
                repo.remote(name="origin").push()
                pushed = True
            except Exception as push_err:
                error = f"committed locally; push failed: {push_err}"
    except Exception as git_err:
        error = f"git operation failed: {git_err}"

    try:
        ingest.reindex_space(space)
    except Exception as reindex_err:
        msg = f"reindex error: {reindex_err}"
        error = f"{error}; {msg}" if error else msg

    return {
        "path": str(target.relative_to(root)),
        "committed": committed,
        "pushed": pushed,
        "error": error,
    }
