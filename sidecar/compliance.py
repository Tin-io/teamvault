"""TeamVault sidecar — machine-wide compliance posture (P0.7).

When ANY registered space has `compliance: true`, the sidecar enforces a
STRICT egress posture machine-wide, not just within that space:

- **Local-only embedding** — Nomic embeddings run locally (Python
  `sentence-transformers`; no remote API call). Structurally true in v0.0.
- **Remote inference blocked** — pack reviewers are regex (no LLM calls).
  Structurally true in v0.0.
- **Cross-space scrubbers** — search/publish content is run through the
  UNION of all compliance-true spaces' enabled packs, even when reading a
  non-compliance space. Prevents a permissive space from leaking content
  the compliance space's scrubbers would have redacted.
- **Strictest-regime search scrubbing** — search results (chunk, path, and
  metadata string values) are scrubbed by the same union before being
  returned to the caller.

The posture is surfaced in `/healthz.compliance` at boot.

Read-path defense
-----------------
The scrubbing pipeline is **FAIL-CLOSED**: if ANY compliance space's pack
runtime cannot fully scrub a piece of content (broken regex, oversize
input, pack-runtime load failure), the return value is the sentinel
`SCRUB_UNAVAILABLE` rather than the unscrubbed text. A broken pack
disables defense for that content; the sentinel surfaces the failure
visibly so the API consumer can react.

Per-query closure
-----------------
The pipeline uses a per-query scrubber CLOSURE
(`make_scrubber() -> Callable[[str], str]`) so PackRuntime is instantiated
ONCE per query rather than per chunk. This avoids the 100+ PackRuntime-
per-search self-DoS the naive per-call design caused. The closure also
captures the strict-posture flag once at build time, closing a TOCTOU
race where space.yaml could change mid-query.

v0.0 multi-space limit
----------------------
The sidecar registers ONE space (via `TEAMVAULT_SPACE_ROOT`). The cross-
space union semantics still kick in the moment that one space has
`compliance: true` — posture flips to strict and read-path scrubbing
engages. In v0.0 single-space deployment, a broken pack in the compliance
space DISABLES read-path defense (scrub returns SCRUB_UNAVAILABLE); the
commit / PR gate (`pack_runtime.fan_out_review` via P0.6) is the
remaining defense layer until v0.1's true multi-space.

`registered_space_roots()` returns a list; v0.1+ extends it to walk all
bound spaces.

Multi-process / cross-tenancy is **out of scope in v0.0** — sidecar is a
single-process service. Binding a new `compliance: true` space after
sidecar boot requires a sidecar restart (deferred to v0.1).
"""
from __future__ import annotations

import re
from pathlib import Path
from typing import Any, Callable

from sidecar import config


# Sentinel substituted into output when fail-closed semantics engage
# (broken regex, oversize input, pack runtime can't load, etc.). A consumer
# seeing this in a search result knows the underlying content COULD NOT be
# safely scrubbed and should treat the field as redacted.
SCRUB_UNAVAILABLE = "[SCRUB_UNAVAILABLE]"

# Sentinel substituted for opaque binary metadata under strict posture —
# can't be scrubbed (regex engines need text) so it's treated as a leak
# vector and replaced wholesale.
REDACTED_BINARY = b"[REDACTED-BINARY]"


# ---------- space.yaml readers ----------


def _read_compliance(space_root: Path) -> bool:
    """Read `space.yaml::compliance`.

    Missing file → False (no compliance gate).
    Malformed YAML or unreadable (OSError, e.g., PermissionError) → True
        (presume-strict / safe-mode). Matches `PackRuntime._read_compliance`
        semantics so commit-gate and read-path stay consistent under a
        broken or unreadable space.yaml.
    Well-formed → bool(doc['compliance']).
    """
    import yaml

    space_yaml = space_root / "space.yaml"
    if not space_yaml.exists():
        return False
    try:
        doc = yaml.safe_load(space_yaml.read_text()) or {}
    except (yaml.YAMLError, OSError):
        return True
    return bool(doc.get("compliance", False))


def _read_space_name(space_root: Path) -> str:
    """Read `space.yaml::name`. Fall back to directory basename.

    Output is sanitized: control characters and newlines are stripped so
    the value can't pollute the /healthz JSON output via a maliciously-
    named directory.
    """
    import yaml

    space_yaml = space_root / "space.yaml"
    raw = space_root.name
    if space_yaml.exists():
        try:
            doc = yaml.safe_load(space_yaml.read_text()) or {}
        except (yaml.YAMLError, OSError):
            doc = {}
        if isinstance(doc, dict):
            candidate = doc.get("name")
            if isinstance(candidate, str) and candidate.strip():
                raw = candidate
    return _sanitize_name(raw)


def _sanitize_name(name: str) -> str:
    """Strip control characters from a space name."""
    return re.sub(r"[\x00-\x1f\x7f]", "", name).strip()


# ---------- Registered spaces + posture ----------


def registered_space_roots() -> list[Path]:
    """List the space roots the sidecar is responsible for.

    v0.0: just `TEAMVAULT_SPACE_ROOT` (single-space). v0.1+ registers
    multiple spaces; this function returns all of them.

    Multi-process limit: binding a new space after sidecar boot is
    invisible until restart. v0.0 sidecar is single-process by design.
    """
    if config.TEAMVAULT_SPACE_ROOT and config.TEAMVAULT_SPACE_ROOT.exists():
        return [config.TEAMVAULT_SPACE_ROOT]
    return []


def machine_wide_compliance(space_paths: list[Path] | None = None) -> bool:
    """True if ANY registered space has `compliance: true`."""
    paths = space_paths if space_paths is not None else registered_space_roots()
    return any(_read_compliance(r) for r in paths)


def egress_invariants(space_paths: list[Path] | None = None) -> dict:
    """Machine-wide compliance posture for `/healthz.compliance`."""
    paths = space_paths if space_paths is not None else registered_space_roots()
    strict = machine_wide_compliance(paths)
    compliance_true_spaces = [_read_space_name(r) for r in paths if _read_compliance(r)]
    return {
        "posture": "strict" if strict else "permissive",
        "local_embedding_only": True,
        "remote_inference_blocked": True,
        "cross_space_scrubbers": strict,
        "strictest_regime_search_scrubbing": strict,
        "compliance_true_spaces": compliance_true_spaces,
    }


# ---------- Scrubber closure (per-query snapshot) ----------


def make_scrubber(space_paths: list[Path] | None = None) -> Callable[[str], str]:
    """Build a per-query scrubber closure with a SNAPSHOT of PackRuntimes.

    Under permissive posture, returns identity (no-op).

    Under strict posture, loads PackRuntime for each compliance-true space
    ONCE. The returned closure can be called many times per query (per
    chunk, per metadata string) without re-instantiating PackRuntime.

    Fail-closed semantics:
    - If a compliance-true space's PackRuntime cannot load (`OSError` on
      packs/ dir, `yaml.YAMLError` on space.yaml, etc.), the closure
      substitutes `SCRUB_UNAVAILABLE` for ALL inputs (union failure).
    - After each `fan_out_scrub` call, the closure inspects
      `rt.scrub_errors` (regex compile error, oversize input). Any error
      causes `SCRUB_UNAVAILABLE` substitution.

    The closure captures the strict-posture flag once at build time,
    closing the TOCTOU race where space.yaml could change between query
    start and per-chunk processing.
    """
    paths = space_paths if space_paths is not None else registered_space_roots()
    if not machine_wide_compliance(paths):
        return lambda t: t

    import yaml

    from sidecar import pack_runtime

    runtimes: list[pack_runtime.PackRuntime] = []
    for root in paths:
        if not _read_compliance(root):
            continue
        try:
            runtimes.append(pack_runtime.PackRuntime(root))
        except (OSError, yaml.YAMLError):
            # Compliance space's runtime can't load — the union is broken.
            # Fail-closed: any subsequent call returns SCRUB_UNAVAILABLE.
            return lambda t: SCRUB_UNAVAILABLE

    def scrub(text: str) -> str:
        result = text
        for rt in runtimes:
            result = rt.fan_out_scrub(result)
            # rt.scrub_errors is reset on each fan_out_scrub call. Non-empty
            # means a regex failed to compile OR input exceeded the oversize
            # cap. Either case fails the entire scrub: substitute the
            # sentinel rather than return unscrubbed text.
            if rt.scrub_errors:
                return SCRUB_UNAVAILABLE
        return result

    return scrub


def scrub_metadata(meta: Any, scrubber: Callable[[str], str]) -> Any:
    """Recursively scrub string values in a metadata structure.

    Handled types:
    - `dict`, `list`, `tuple`: recurse, preserving type for list/tuple
    - `str`: scrub
    - `bytes`: try UTF-8 decode + scrub + re-encode; on UnicodeDecodeError,
      return `REDACTED_BINARY` — under strict posture, opaque binary
      content can't be inspected so it's treated as a leak vector
    - Anything else (`int`, `float`, `datetime`, `date`, …): pass through
      unchanged. These types can't carry textual PHI in v0.0; if a custom
      yaml-loaded type wraps a string, the caller should pre-flatten it
      to a plain str before this function

    The str scrub may return `SCRUB_UNAVAILABLE`; the value propagates up
    through the structure unchanged (no special handling at recursion —
    the caller sees the sentinel and decides what to do).
    """
    if isinstance(meta, dict):
        return {k: scrub_metadata(v, scrubber) for k, v in meta.items()}
    if isinstance(meta, list):
        return [scrub_metadata(v, scrubber) for v in meta]
    if isinstance(meta, tuple):
        return tuple(scrub_metadata(v, scrubber) for v in meta)
    if isinstance(meta, str):
        return scrubber(meta)
    if isinstance(meta, bytes):
        try:
            decoded = meta.decode("utf-8")
        except UnicodeDecodeError:
            return REDACTED_BINARY
        scrubbed = scrubber(decoded)
        return scrubbed.encode("utf-8") if scrubbed != decoded else meta
    return meta
