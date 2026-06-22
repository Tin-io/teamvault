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
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal


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
class Pack:
    name: str
    version: str
    description: str
    root: Path
    agents: list[Path] = field(default_factory=list)
    scrubbers: list[Scrubber] = field(default_factory=list)
    reviewers: list[Reviewer] = field(default_factory=list)
    # knowledge_topics: optional kebab-case domain names. v0.1+ contract surface.
    # The team's declaration of "we've accumulated prior art on these domains."
    # Consumed by vault_packs() to prompt the agent to vault_search before
    # finalizing decisions in covered domains. NOT enforcement (no scrubber
    # runs against it).
    knowledge_topics: list[str] = field(default_factory=list)
    # skills: list of pack-shipped skill DIRECTORIES (each containing SKILL.md).
    # v0.2+ contract. Not executed by the sidecar — manifested for
    # /teamvault-setup to copy into .claude/skills/ at install/upgrade time.
    # Each Path points to a directory (e.g., `<pack_root>/skills/start-clickup`).
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


# ---------- Loader ----------


def _load_pack(pack_root: Path) -> Pack | None:
    import yaml

    yaml_path = pack_root / "PACK.yaml"
    if not yaml_path.exists():
        return None
    doc = yaml.safe_load(yaml_path.read_text()) or {}
    contribs = doc.get("contributions", {}) or {}

    agents = [pack_root / a["path"] for a in (contribs.get("agents") or [])]

    scrubbers: list[Scrubber] = []
    for sc in contribs.get("scrubbers") or []:
        sc_type = sc.get("type", "regex")
        sc_file = pack_root / sc["file"]
        if not sc_file.exists():
            continue
        sc_doc = yaml.safe_load(sc_file.read_text()) or {}
        patterns = sc_doc.get("patterns", []) if isinstance(sc_doc, dict) else sc_doc
        scrubbers.append(Scrubber(type=sc_type, patterns=patterns))

    reviewers = [
        Reviewer(agent=r["agent"], mode=r.get("mode", "advisory"))
        for r in (contribs.get("reviewers") or [])
    ]

    pack_name = doc.get("name", pack_root.name)

    # knowledge_topics: optional list of kebab-case domain names.
    # Invalid entries (non-string or not matching _TOPIC_RE) are dropped with a
    # warning; the pack still loads. Missing field → empty list.
    knowledge_topics: list[str] = []
    for topic in doc.get("knowledge_topics") or []:
        if isinstance(topic, str) and _TOPIC_RE.match(topic):
            knowledge_topics.append(topic)
        else:
            print(f"warning: pack {pack_name} declared invalid topic {topic!r} — dropped")

    # skills: each entry is a directory path under the pack root. The directory
    # must contain a SKILL.md for downstream deployment. Missing dirs / missing
    # SKILL.md are dropped with a warning (pack still loads — skills are
    # advisory manifest, not runtime-load-blocking).
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

    return Pack(
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


# ---------- Runtime ----------


class PackRuntime:
    """Loaded once per invocation; frozen for the session (snapshot consistency)."""

    def __init__(self, space_path: Path):
        self.space_path = space_path
        self.packs = self._load_enabled()

    def _load_enabled(self) -> list[Pack]:
        import yaml

        space_yaml = self.space_path / "space.yaml"
        if not space_yaml.exists():
            return []
        space_doc = yaml.safe_load(space_yaml.read_text()) or {}
        enabled = set(space_doc.get("enabled_packs") or [])

        packs_dir = self.space_path / "packs"
        if not packs_dir.exists():
            return []

        out: list[Pack] = []
        for d in sorted(packs_dir.iterdir()):
            if not d.is_dir():
                continue
            p = _load_pack(d)
            if p and p.name in enabled:
                out.append(p)
        return out

    # ---------- Scrub ----------

    def fan_out_scrub(self, text: str) -> str:
        """Run all enabled scrubbers. Returns text with matches replaced by [REDACTED]."""
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
          - Pack 'clickup-linkage' (advisory): check diff for ClickUp URL.
        """
        added = []
        for line in diff.splitlines():
            if line.startswith("+") and not line.startswith("+++"):
                added.append(line[1:])
        added_text = "\n".join(added)

        individual: list[ReviewerVerdictDC] = []
        overall = "pass"

        for pack in self.packs:
            for rev in pack.reviewers:
                # Initialize per-reviewer outputs so they're never unbound across iterations
                # even when a pack has reviewers but no scrubbers and isn't a special-case pack.
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
                        except re.error:
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
                    #   - <KEY>-<NUMBER>                   (bare ID; KEY is 2+ uppercase/digits, NUMBER 1-6 digits)
                    # Generous regex — see packs/jira-linkage/agents/jira-linkage-reviewer.md for limits.
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
