"""TeamVault sidecar — pack runtime.

Discovers packs under ${SPACE_ROOT}/packs/*/PACK.yaml. Loads enabled set
from space.yaml::enabled_packs. Exposes fan_out_review() and fan_out_scrub().

v0.0 contract:
  - agents: list of paths to .md reviewer agents
  - scrubbers: regex pattern banks (type: regex, file: <yaml>)
  - reviewers: agent + mode (advisory|blocking)
  - knowledge_topics (v0.1+): kebab-case domain names; the team's declaration
    of which domains they've accumulated KB on. Consumed by vault_packs().
  - skills (v0.2+): list of paths to skill DIRECTORIES (each containing a
    SKILL.md). Pack-shipped skills are not executed by the sidecar runtime —
    they're manifested for /teamvault-setup to copy into .claude/skills/ at
    install/upgrade time. Lets a pack be a self-contained domain capability
    bundle (scrubbers + reviewers + workflow skills together).

v0.1: ordering, depends_on, timeouts, mutually_exclusive_with, spawned agents.

Failure-mode contract (P0.6)
----------------------------
The pack runtime can fail in several ways; v0.0 enumerates and tests them
with required block behavior for `compliance: true` spaces:

| Failure              | When                                                       |
|----------------------|------------------------------------------------------------|
| missing_file         | PACK.yaml references a scrubber YAML that doesn't exist    |
|                      | (or it exists but isn't a regular file — directory, etc.)  |
| malformed_yaml       | YAMLError loading the PACK.yaml or a scrubber YAML; or any |
|                      | OSError reading a scrubber file                            |
| degenerate_pack      | PACK.yaml parsed but has no `name` field (empty/blank/     |
|                      | clobbered by a botched merge)                              |
| unresolved_pack      | space.yaml::enabled_packs entry does not match any pack    |
|                      | directory OR PACK.yaml `name:` field                       |
| regex_compile        | a pattern's regex doesn't compile (`[unclosed`)            |
| oversize_input       | input exceeds `_MAX_INPUT_BYTES` (proxy for timeout / OOM) |
| space_yaml malformed | space.yaml itself fails YAML parsing — load error is FORCE-|
|                      | BLOCKING regardless of the (unreadable) compliance flag    |

For `compliance: true` spaces, any of the above synthesizes a BLOCKING
reviewer verdict (`agent="scrubber-health"`) and `overall = "block"`.
For `compliance: false` spaces, the same failures synthesize ADVISORY
verdicts; `overall` stays `pass` unless a real scrubber match also fires.

The pack runtime never silently fails open under `compliance: true`.

Python's `re` module has no timeout; the oversize-input cap is the v0.0
proxy. A real timeout (e.g., the `regex` package, or `signal.alarm` under
Unix) is deferred to v0.1.

Special case — broken space.yaml. When space.yaml ITSELF fails to parse,
`_read_compliance` cannot determine the flag. Rather than silently fail-
open by defaulting to `compliance: false`, it presumes `compliance: true`
(safe-mode) AND the resulting `space-yaml` LoadError carries
`force_blocking=True` so the verdict blocks even if a downstream caller
re-overrides compliance.

See docs/CONTRACTS.md "Pack runtime failure modes" for the contract.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal


# Refuse to process inputs larger than this. Python's `re` module has no
# timeout and no memory cap; catastrophic backtracking on pathological input
# could hang or OOM the sidecar. The cap is a fail-closed proxy until v0.1
# lands a real timeout (e.g., the `regex` package, or signal.alarm under Unix).
# Measured in BYTES (UTF-8 encoded), not character count — multi-byte content
# can blow past the threshold long before character count would.
_MAX_INPUT_BYTES = 10_000_000  # 10 MB


# ---------- Models ----------


@dataclass
class Scrubber:
    type: str
    patterns: list[dict]


@dataclass
class Reviewer:
    agent: str
    mode: Literal["advisory", "blocking"]


@dataclass
class LoadError:
    """Recorded at pack-load time. Synthesized into a verdict by
    PackRuntime.fan_out_review so downstream consumers (precommit hook,
    PR-review workflow) see the same shape they already handle.

    `force_blocking=True` overrides the compliance-flag-derived mode for
    the verdict. Used for the broken-space.yaml case where the compliance
    flag itself can't be trusted.
    """

    pack: str
    type: str  # missing_file | malformed_yaml | degenerate_pack | unresolved_pack
    detail: str
    force_blocking: bool = False


@dataclass
class ScrubError:
    """Recorded at runtime during fan_out_review / fan_out_scrub
    (regex compile failure, oversize input). Synthesized into the verdict
    like LoadError.
    """

    pack: str
    type: str  # regex_compile | oversize_input
    detail: str
    pattern_name: str | None = None


@dataclass
class Pack:
    name: str
    version: str
    description: str
    root: Path
    agents: list[Path] = field(default_factory=list)
    scrubbers: list[Scrubber] = field(default_factory=list)
    reviewers: list[Reviewer] = field(default_factory=list)
    knowledge_topics: list[str] = field(default_factory=list)
    skills: list[Path] = field(default_factory=list)


_TOPIC_RE = re.compile(r"^[a-z0-9]+(-[a-z0-9]+)*$")


@dataclass
class ReviewerVerdictDC:
    pack: str
    agent: str
    mode: str
    pass_or_fail: str
    message: str


@dataclass
class ReviewVerdictDC:
    overall: str
    individual: list[ReviewerVerdictDC]


# Synthetic agent + pack identifiers used for load- and runtime-failure verdicts.
# Hyphenated (not underscored) so they don't render as bold in markdown tables
# (the GHA PR-comment workflow uses pipe-table cells).
_SCRUBBER_HEALTH_AGENT = "scrubber-health"
_SPACE_YAML_PACK = "space-yaml"
_RUNTIME_PACK = "runtime"


# ---------- Loader ----------


def _load_pack(pack_root: Path) -> tuple[Pack | None, list[LoadError]]:
    """Load a single pack. Returns (Pack | None, errors).

    P0.6: load errors (missing file / malformed YAML / non-file scrubber /
    degenerate PACK.yaml) are recorded instead of silently swallowed. Returned
    errors get synthesized into the verdict by PackRuntime.fan_out_review.
    """
    import yaml

    errors: list[LoadError] = []

    yaml_path = pack_root / "PACK.yaml"
    if not yaml_path.exists():
        return None, errors

    try:
        doc = yaml.safe_load(yaml_path.read_text()) or {}
    except yaml.YAMLError as e:
        errors.append(LoadError(pack=pack_root.name, type="malformed_yaml", detail=f"PACK.yaml: {e}"))
        return None, errors
    except OSError as e:
        errors.append(LoadError(pack=pack_root.name, type="malformed_yaml", detail=f"PACK.yaml: read failed: {e}"))
        return None, errors

    # Degenerate PACK.yaml — empty / whitespace-only / lacks the canonical
    # name field. An adversary or merge conflict that blanks the file would
    # otherwise produce a Pack with zero scrubbers + zero reviewers and pass
    # silently.
    if not isinstance(doc, dict) or not doc.get("name"):
        errors.append(LoadError(
            pack=pack_root.name,
            type="degenerate_pack",
            detail="PACK.yaml lacks a name field (likely empty, clobbered, or malformed)",
        ))
        return None, errors

    contribs = doc.get("contributions") or {}
    pack_name = doc["name"]

    agents = [pack_root / a["path"] for a in (contribs.get("agents") or [])]

    scrubbers: list[Scrubber] = []
    for sc in contribs.get("scrubbers") or []:
        sc_type = sc.get("type", "regex")
        sc_file = pack_root / sc["file"]
        # is_file() — narrower than exists(): returns False for directories,
        # symlinks-to-directories, missing files. Closes the IsADirectoryError
        # crash path (was: exists() True + read_text() raised uncaught).
        if not sc_file.is_file():
            detail = (
                f"{sc['file']}: not a regular file"
                if sc_file.exists()
                else str(sc["file"])
            )
            errors.append(LoadError(pack=pack_name, type="missing_file", detail=detail))
            continue
        try:
            sc_text = sc_file.read_text()
        except OSError as e:
            errors.append(LoadError(
                pack=pack_name,
                type="malformed_yaml",
                detail=f"{sc['file']}: read failed: {e}",
            ))
            continue
        try:
            sc_doc = yaml.safe_load(sc_text) or {}
        except yaml.YAMLError as e:
            errors.append(LoadError(pack=pack_name, type="malformed_yaml", detail=f"{sc['file']}: {e}"))
            continue
        patterns = sc_doc.get("patterns", []) if isinstance(sc_doc, dict) else sc_doc
        scrubbers.append(Scrubber(type=sc_type, patterns=patterns))

    reviewers = [
        Reviewer(agent=r["agent"], mode=r.get("mode", "advisory"))
        for r in (contribs.get("reviewers") or [])
    ]

    knowledge_topics: list[str] = []
    for topic in doc.get("knowledge_topics") or []:
        if isinstance(topic, str) and _TOPIC_RE.match(topic):
            knowledge_topics.append(topic)
        else:
            print(f"warning: pack {pack_name} declared invalid topic {topic!r} — dropped")

    skills: list[Path] = []
    for sk in contribs.get("skills") or []:
        sk_path = pack_root / sk["path"]
        if not sk_path.is_dir():
            print(f"warning: pack {pack_name} declared skill at {sk_path} but directory not found — dropped")
            continue
        if not (sk_path / "SKILL.md").exists():
            print(f"warning: pack {pack_name} skill {sk_path} missing SKILL.md — dropped")
            continue
        skills.append(sk_path)

    pack = Pack(
        name=pack_name,
        version=doc.get("version", "0.0.0"),
        description=doc.get("description", ""),
        root=pack_root,
        agents=agents,
        scrubbers=scrubbers,
        reviewers=reviewers,
        knowledge_topics=knowledge_topics,
        skills=skills,
    )
    return pack, errors


# ---------- Runtime ----------


class PackRuntime:
    """Loaded once per invocation; frozen for the session (snapshot consistency)."""

    def __init__(self, space_path: Path):
        self.space_path = space_path
        self.compliance, self._compliance_unreadable = self._read_compliance()
        self.packs, self.load_errors = self._load_enabled()
        # scrub_errors is mutated by fan_out_scrub on each call. Callers (e.g.,
        # publish.py) inspect both `load_errors` and `scrub_errors` to enforce
        # fail-closed semantics under compliance.
        self.scrub_errors: list[ScrubError] = []

    def _read_compliance(self) -> tuple[bool, bool]:
        """Return (compliance, unreadable).

        Missing space.yaml → (False, False) — no compliance gate.
        Malformed space.yaml → (True, True) — presume strict (safe-mode);
            the broken-space.yaml LoadError carries force_blocking=True so
            the verdict blocks no matter what.
        Well-formed space.yaml → (doc.get('compliance', False), False).
        """
        import yaml

        space_yaml = self.space_path / "space.yaml"
        if not space_yaml.exists():
            return False, False
        try:
            doc = yaml.safe_load(space_yaml.read_text()) or {}
        except yaml.YAMLError:
            return True, True
        return bool(doc.get("compliance", False)), False

    def _load_enabled(self) -> tuple[list[Pack], list[LoadError]]:
        import yaml

        space_yaml = self.space_path / "space.yaml"
        if not space_yaml.exists():
            return [], []
        try:
            space_doc = yaml.safe_load(space_yaml.read_text()) or {}
        except yaml.YAMLError as e:
            return [], [LoadError(
                pack=_SPACE_YAML_PACK,
                type="malformed_yaml",
                detail=str(e),
                force_blocking=True,
            )]
        enabled = set(space_doc.get("enabled_packs") or [])

        # Walk packs/ once. For each candidate dir, record (dir_name, pack | None,
        # errors). Then resolve enabled_packs entries against EITHER the dir name
        # or the PACK.yaml `name:` field, so a fork that ships a renamed dir still
        # resolves to its declared name, and the convention "dir name = pack name"
        # stays a convention rather than an enforced rule.
        pack_entries: list[tuple[str, Pack | None, list[LoadError]]] = []
        name_to_dir: dict[str, str] = {}
        packs_dir = self.space_path / "packs"
        if packs_dir.exists():
            for d in sorted(packs_dir.iterdir()):
                if not d.is_dir():
                    continue
                p, errs = _load_pack(d)
                pack_entries.append((d.name, p, errs))
                if p:
                    name_to_dir[p.name] = d.name

        dir_to_entry = {e[0]: e for e in pack_entries}

        out_packs: list[Pack] = []
        out_errors: list[LoadError] = []
        enabled_dirs: set[str] = set()
        for enabled_name in enabled:
            if enabled_name in dir_to_entry:
                enabled_dirs.add(enabled_name)
            elif enabled_name in name_to_dir:
                enabled_dirs.add(name_to_dir[enabled_name])
            else:
                out_errors.append(LoadError(
                    pack=enabled_name,
                    type="unresolved_pack",
                    detail=(
                        f"enabled_packs entry {enabled_name!r} matches no pack "
                        "directory or PACK.yaml name"
                    ),
                ))

        for dir_name, pack, errs in pack_entries:
            if dir_name not in enabled_dirs:
                continue
            if pack:
                out_packs.append(pack)
            out_errors.extend(errs)

        return out_packs, out_errors

    def _failure_mode(self) -> Literal["blocking", "advisory"]:
        """Default synthetic-verdict mode based on the space's compliance flag.

        Individual LoadErrors can override via `force_blocking=True` —
        used for broken-space.yaml where the flag itself is unreadable.
        """
        return "blocking" if self.compliance else "advisory"

    # ---------- Scrub ----------

    def fan_out_scrub(self, text: str) -> str:
        """Run all enabled scrubbers. Returns text with matches replaced by [REDACTED].

        P0.6: records regex compile errors and oversize-input failures as
        `ScrubError`s on `self.scrub_errors`. CALLER is expected to inspect
        `scrub_errors` after the call and enforce fail-closed semantics under
        compliance (see publish.py).

        On oversize input, scrubbers are skipped entirely and the input is
        returned unchanged — the caller MUST check scrub_errors to decide
        whether to use the (unscrubbed) result.
        """
        self.scrub_errors = []
        text_bytes = len(text.encode("utf-8"))
        if text_bytes > _MAX_INPUT_BYTES:
            self.scrub_errors.append(ScrubError(
                pack=_RUNTIME_PACK,
                type="oversize_input",
                detail=(
                    f"input size {text_bytes} bytes exceeds "
                    f"{_MAX_INPUT_BYTES} byte cap; scrub aborted"
                ),
            ))
            return text

        result = text
        for pack in self.packs:
            for sc in pack.scrubbers:
                if sc.type != "regex":
                    continue
                for pat in sc.patterns:
                    pattern_str = pat.get("pattern", "")
                    if not pattern_str:
                        continue
                    try:
                        result = re.sub(pattern_str, "[REDACTED]", result)
                    except re.error as exc:
                        self.scrub_errors.append(ScrubError(
                            pack=pack.name,
                            type="regex_compile",
                            detail=str(exc),
                            pattern_name=pat.get("name"),
                        ))
                        continue
        return result

    # ---------- Review ----------

    def fan_out_review(self, diff: str) -> ReviewVerdictDC:
        """Run reviewers on the added lines of the diff.

        v0.0 logic per reviewer:
          - Default: run the pack's scrubbers against added text; match = fail.
          - Pack 'clickup' (advisory): check diff for ClickUp URL.
          - Pack 'jira-linkage' (advisory): check diff for Jira ticket reference.

        P0.6: scrubber failures synthesize `scrubber-health` verdicts.
        For compliance: true → blocking (overall: block). For compliance:
        false → advisory (overall stays: pass unless a real match fires).

        Linkage checks (clickup, jira-linkage) run regardless of oversize
        input — they're cheap bounded regex against the diff, and SOC 2
        audit evidence depends on them appearing in the verdict even when
        scrubber matching is aborted.
        """
        runtime_errors: list[ScrubError] = []
        diff_bytes = len(diff.encode("utf-8"))
        oversize = diff_bytes > _MAX_INPUT_BYTES
        if oversize:
            runtime_errors.append(ScrubError(
                pack=_RUNTIME_PACK,
                type="oversize_input",
                detail=(
                    f"diff size {diff_bytes} bytes exceeds "
                    f"{_MAX_INPUT_BYTES} byte cap; pattern matching aborted"
                ),
            ))

        added: list[str] = []
        if not oversize:
            for line in diff.splitlines():
                if line.startswith("+") and not line.startswith("+++"):
                    added.append(line[1:])
        added_text = "\n".join(added)

        individual: list[ReviewerVerdictDC] = []
        overall = "pass"

        for pack in self.packs:
            for rev in pack.reviewers:
                msg = "no patterns matched"
                pof = "pass"

                matches: list[str] = []
                if not oversize:
                    for sc in pack.scrubbers:
                        if sc.type != "regex":
                            continue
                        for pat in sc.patterns:
                            pattern_str = pat.get("pattern", "")
                            if not pattern_str:
                                continue
                            try:
                                if re.search(pattern_str, added_text):
                                    matches.append(pat.get("name") or pattern_str[:40])
                            except re.error as exc:
                                runtime_errors.append(ScrubError(
                                    pack=pack.name,
                                    type="regex_compile",
                                    detail=str(exc),
                                    pattern_name=pat.get("name"),
                                ))
                                continue

                if matches:
                    msg = f"matched: {', '.join(matches)}"
                    pof = "fail"
                    if rev.mode == "blocking":
                        overall = "block"
                elif pack.name == "clickup":
                    has_link = bool(re.search(r"(app\.)?clickup\.com[/\w?=&-]*", diff))
                    if has_link:
                        msg = "ClickUp linkage detected"
                        pof = "pass"
                    else:
                        msg = "no ClickUp ticket linked (advisory: SOC 2 evidence)"
                        pof = "fail"
                        if rev.mode == "blocking":
                            overall = "block"
                elif pack.name == "jira-linkage":
                    # Match either:
                    #   - atlassian.net/browse/<KEY>-<N>  (explicit URL)
                    #   - <KEY>-<NUMBER>                  (bare ID; KEY 2+ uppercase/digits, NUMBER 1–6 digits)
                    has_link = bool(
                        re.search(
                            r"(atlassian\.net/browse/[A-Z][A-Z0-9_]+-\d+|\b[A-Z][A-Z0-9_]+-\d{1,6}\b)",
                            diff,
                        )
                    )
                    if has_link:
                        msg = "Jira ticket reference detected"
                        pof = "pass"
                    else:
                        msg = "no Jira ticket linked (advisory: SOC 2 evidence)"
                        pof = "fail"
                        if rev.mode == "blocking":
                            overall = "block"
                elif oversize:
                    # Scrubber-only reviewer on oversize input: skip the per-
                    # reviewer row entirely (we didn't actually scan; emitting
                    # "no patterns matched" would be misleading). The synthetic
                    # runtime verdict below carries the block signal.
                    continue

                individual.append(ReviewerVerdictDC(
                    pack=pack.name,
                    agent=rev.agent,
                    mode=rev.mode,
                    pass_or_fail=pof,
                    message=msg,
                ))

        # Synthesize verdicts for load + runtime failures.
        default_mode = self._failure_mode()
        for err in self.load_errors:
            verdict_mode: str = "blocking" if err.force_blocking else default_mode
            individual.append(ReviewerVerdictDC(
                pack=err.pack,
                agent=_SCRUBBER_HEALTH_AGENT,
                mode=verdict_mode,
                pass_or_fail="fail",
                message=f"load failure: {err.type}: {err.detail}",
            ))
            if verdict_mode == "blocking":
                overall = "block"
        for err in runtime_errors:
            pat_info = f" (pattern: {err.pattern_name})" if err.pattern_name else ""
            individual.append(ReviewerVerdictDC(
                pack=err.pack,
                agent=_SCRUBBER_HEALTH_AGENT,
                mode=default_mode,
                pass_or_fail="fail",
                message=f"runtime failure: {err.type}: {err.detail}{pat_info}",
            ))
            if default_mode == "blocking":
                overall = "block"

        return ReviewVerdictDC(overall=overall, individual=individual)


# ---------- Helper for FastAPI endpoint ----------


def run_review(space: str, diff: str) -> dict:
    from sidecar import config

    if config.TEAMVAULT_SPACE_ROOT and config.TEAMVAULT_SPACE_ROOT.exists():
        root = config.TEAMVAULT_SPACE_ROOT
    else:
        root = Path.home() / f"teamvault-{space}"
    rt = PackRuntime(root)
    v = rt.fan_out_review(diff)
    return {
        "overall": v.overall,
        "individual": [
            {"pack": i.pack, "agent": i.agent, "mode": i.mode, "pass_or_fail": i.pass_or_fail, "message": i.message}
            for i in v.individual
        ],
    }
