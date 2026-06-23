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

| Failure              | When                                              |
|----------------------|---------------------------------------------------|
| missing_file         | PACK.yaml references a scrubber YAML that doesn't exist |
| malformed_yaml       | YAMLError loading the PACK.yaml or a scrubber YAML |
| regex_compile        | a pattern's regex doesn't compile (`[unclosed`)   |
| oversize_input       | diff exceeds `_MAX_DIFF_BYTES` (proxy for timeout / OOM) |

For `compliance: true` spaces, any of the above synthesizes a BLOCKING
reviewer verdict (`agent="__scrubber_health__"`) and `overall = "block"`.
For `compliance: false` spaces, the same failures synthesize ADVISORY
verdicts; `overall` stays `pass` unless a real scrubber match also fires.

The pack runtime never silently fails open under `compliance: true`.

Python's `re` module has no timeout; the oversize-input cap is the v0.0
proxy. A real timeout (e.g., the `regex` package, or `signal.alarm` under
Unix) is deferred to v0.1.

A malformed `space.yaml` falls back to `compliance: false` — assuming
`compliance: true` from a broken config would block all commits with no
clear remediation path.

See docs/CONTRACTS.md "Pack runtime failure modes" for the full table.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal


# Refuse to scrub diffs larger than this. Python's `re` module has no timeout
# and no memory cap; catastrophic backtracking on pathological input could
# hang or OOM the sidecar. The cap is a fail-closed proxy until v0.1 lands a
# real timeout (e.g., the `regex` package, or signal.alarm under Unix).
_MAX_DIFF_BYTES = 10_000_000  # 10 MB


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
    PR-review workflow) see the same shape they already handle."""

    pack: str
    type: str  # missing_file | malformed_yaml
    detail: str


@dataclass
class ScrubError:
    """Recorded at runtime during fan_out_review (regex compile failure,
    oversize input). Synthesized into the verdict like LoadError."""

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


# Synthetic agent name used for load- and runtime-failure verdicts.
_SCRUBBER_HEALTH_AGENT = "__scrubber_health__"


# ---------- Loader ----------


def _load_pack(pack_root: Path) -> tuple[Pack | None, list[LoadError]]:
    """Load a single pack. Returns (Pack | None, errors).

    P0.6: load errors (missing scrubber file, malformed YAML) are recorded
    instead of silently swallowed. Returned errors get synthesized into the
    verdict by PackRuntime.fan_out_review.
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

    contribs = doc.get("contributions", {}) or {}
    pack_name = doc.get("name", pack_root.name)

    agents = [pack_root / a["path"] for a in (contribs.get("agents") or [])]

    scrubbers: list[Scrubber] = []
    for sc in contribs.get("scrubbers") or []:
        sc_type = sc.get("type", "regex")
        sc_file = pack_root / sc["file"]
        if not sc_file.exists():
            errors.append(LoadError(pack=pack_name, type="missing_file", detail=str(sc["file"])))
            continue
        try:
            sc_doc = yaml.safe_load(sc_file.read_text()) or {}
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
        self.compliance = self._read_compliance()
        self.packs, self.load_errors = self._load_enabled()

    def _read_compliance(self) -> bool:
        """Read space.yaml::compliance. Defaults to False on missing-file or parse error.

        Rationale: assuming compliance: true from a broken config would block
        all commits with no clear remediation path. Better to fail OPEN on
        the compliance flag itself and surface the broken config via the
        load-error path (which IS reported in the verdict).
        """
        import yaml

        space_yaml = self.space_path / "space.yaml"
        if not space_yaml.exists():
            return False
        try:
            doc = yaml.safe_load(space_yaml.read_text()) or {}
        except yaml.YAMLError:
            return False
        return bool(doc.get("compliance", False))

    def _load_enabled(self) -> tuple[list[Pack], list[LoadError]]:
        import yaml

        space_yaml = self.space_path / "space.yaml"
        if not space_yaml.exists():
            return [], []
        try:
            space_doc = yaml.safe_load(space_yaml.read_text()) or {}
        except yaml.YAMLError as e:
            return [], [LoadError(pack="__space_yaml__", type="malformed_yaml", detail=str(e))]
        enabled = set(space_doc.get("enabled_packs") or [])

        packs_dir = self.space_path / "packs"
        if not packs_dir.exists():
            return [], []

        out_packs: list[Pack] = []
        out_errors: list[LoadError] = []
        for d in sorted(packs_dir.iterdir()):
            if not d.is_dir():
                continue
            # Directory name is the pack identifier for enable/disable. Convention:
            # directory name matches PACK.yaml::name. Disabled packs aren't loaded.
            if d.name not in enabled:
                continue
            p, errs = _load_pack(d)
            out_errors.extend(errs)
            if p:
                out_packs.append(p)
        return out_packs, out_errors

    def _failure_mode(self) -> Literal["blocking", "advisory"]:
        """Synthetic verdict severity for load + runtime failures."""
        return "blocking" if self.compliance else "advisory"

    # ---------- Scrub ----------

    def fan_out_scrub(self, text: str) -> str:
        """Run all enabled scrubbers. Returns text with matches replaced by [REDACTED].

        v0.0: silent-skip on regex compile error — used by /publish at write
        time and tolerant of a single broken pattern by design. The strict
        fail-closed semantics live on fan_out_review (commit / PR-time gate).
        Hardening fan_out_scrub is tracked as a follow-up to P0.6 once
        publish.py grows a way to surface the runtime errors back to the
        caller.
        """
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
                    except re.error:
                        continue
        return result

    # ---------- Review ----------

    def fan_out_review(self, diff: str) -> ReviewVerdictDC:
        """Run reviewers on the added lines of the diff.

        v0.0 logic per reviewer:
          - Default: run the pack's scrubbers against added text; match = fail.
          - Pack 'clickup' (advisory): check diff for ClickUp URL.
          - Pack 'jira-linkage' (advisory): check diff for Jira ticket reference.

        P0.6: scrubber failures synthesize `__scrubber_health__` verdicts.
        For compliance: true → blocking (overall: block). For compliance:
        false → advisory (overall stays: pass unless a real match fires).
        """
        # Oversize input check — proxy for timeout/OOM since Python re has no
        # timeout. Recorded once, applied as a top-level scrub error.
        runtime_errors: list[ScrubError] = []
        oversize = len(diff) > _MAX_DIFF_BYTES
        if oversize:
            runtime_errors.append(
                ScrubError(
                    pack="__runtime__",
                    type="oversize_input",
                    detail=(
                        f"diff size {len(diff)} bytes exceeds {_MAX_DIFF_BYTES} byte cap; "
                        "cannot scrub safely"
                    ),
                )
            )

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
                if oversize:
                    # Don't trust any reviewer's verdict on oversize input —
                    # the synthetic failure below covers it.
                    continue

                msg = "no patterns matched"
                pof = "pass"

                matches: list[str] = []
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
                            runtime_errors.append(
                                ScrubError(
                                    pack=pack.name,
                                    type="regex_compile",
                                    detail=str(exc),
                                    pattern_name=pat.get("name"),
                                )
                            )
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

                individual.append(
                    ReviewerVerdictDC(
                        pack=pack.name,
                        agent=rev.agent,
                        mode=rev.mode,
                        pass_or_fail=pof,
                        message=msg,
                    )
                )

        # Synthesize verdicts for load + runtime failures.
        mode = self._failure_mode()
        for err in self.load_errors:
            individual.append(
                ReviewerVerdictDC(
                    pack=err.pack,
                    agent=_SCRUBBER_HEALTH_AGENT,
                    mode=mode,
                    pass_or_fail="fail",
                    message=f"load failure: {err.type}: {err.detail}",
                )
            )
            if mode == "blocking":
                overall = "block"
        for err in runtime_errors:
            pat_info = f" (pattern: {err.pattern_name})" if err.pattern_name else ""
            individual.append(
                ReviewerVerdictDC(
                    pack=err.pack,
                    agent=_SCRUBBER_HEALTH_AGENT,
                    mode=mode,
                    pass_or_fail="fail",
                    message=f"runtime failure: {err.type}: {err.detail}{pat_info}",
                )
            )
            if mode == "blocking":
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
