# 🧭 TeamVault — Strategy: The Governed Substrate for Agentic Development

> ✨ **The north-star strategy doc.** Where TeamVault is going, why, and how it converges the best of the agentic-coding ecosystem (ECC, oh-my-claudecode) with a mature, ticket-grounded workflow stack into **one composable, open-source, multi-context platform** — *without* drowning in the sprawl that sinks the alternatives.

<p align="center">
  <b>Created:</b> 2026-06-19 &nbsp;·&nbsp; <b>Status:</b> proposal / for review &nbsp;·&nbsp; <b>Audience:</b> maintainer + design partners &nbsp;·&nbsp; <b>Scope:</b> product strategy, positioning, architecture direction
</p>

**Related:** [ARCHITECTURE.md](ARCHITECTURE.md) · [ROADMAP.md](ROADMAP.md) · [CONTRACTS.md](CONTRACTS.md) · [KB-FOUNDATIONS.md](KB-FOUNDATIONS.md) · [CONTRIBUTING_PACKS.md](CONTRIBUTING_PACKS.md) · [AUTONOMOUS_BUILD_METHODOLOGY.md](AUTONOMOUS_BUILD_METHODOLOGY.md)

---

## 📑 Contents

1. [TL;DR](#1--tldr)
2. [The thesis](#2--the-thesis)
3. [Why this is viable (the evidence)](#3--why-this-is-viable-the-evidence)
4. [Landscape: what we're converging](#4--landscape-what-were-converging)
5. [The convergence principles](#5--the-convergence-principles)
6. [Architecture: how it all fits into TeamVault](#6--architecture-how-it-all-fits-into-teamvault)
7. [The v3 workflow — shipped as the flagship pack](#7--the-v3-workflow--shipped-as-the-flagship-pack)
8. [The knowledge tier & routing contract](#8--the-knowledge-tier--routing-contract)
9. [Direct answers to the viability questions](#9--direct-answers-to-the-viability-questions)
10. [Risks & honest caveats](#10--risks--honest-caveats)
11. [Phased roadmap](#11--phased-roadmap)
12. [Success metric](#12--success-metric)
13. [Open decisions](#13--open-decisions)
14. [Provenance](#14--provenance)

---

## 1. 🎯 TL;DR

- **Goal:** evolve TeamVault from a team KB (v0.0) into a general, composable, open-source **paradigm for agentic development** that serves an organization, a client, and personal projects from one engine — converging the best disciplines from ECC, oh-my-claudecode (OMC), and a mature ticket-grounded workflow.
- **Verdict: viable — with one reframe.** Lead as a **knowledge *substrate*** (the moat), not as a harness. Ship the workflow (the v3 loops, the convergence controller) as the **flagship *pack* on top of the substrate**. Be the layer OMC/ECC/Claude Code *plug into*; also offer a great workflow on it. Don't rebuild a harness to out-feature OMC head-on.
- **The proof it generalizes:** several independent knowledge-base systems already convergently evolved the *same* architecture (see [KB-FOUNDATIONS.md](KB-FOUNDATIONS.md)). One substrate serving personal + team + org + autonomous-agent use isn't a hypothesis — it already happened in practice. TeamVault is the productization of that convergence.
- **The one load-bearing technical move:** grow the pack contribution contract from `{agents, scrubbers, reviewers}` to also carry `{skills, commands, hooks, loops/orchestrators}`. Then *the harness is a pack*.
- **The hard constraint to respect:** per-space isolation is today *"a routing simplification, not a security control"* ([ARCHITECTURE.md §2](ARCHITECTURE.md)). Putting two different organizations' data (e.g., an employer's and a client's) on one machine requires hardening this first ([ROADMAP P0.7](ROADMAP.md)).
- **Success bar:** "makes the maintainer and their organizations compound across every project." OSS adoption and contending with OMC/ECC are *upside* on a foundation that's worth it regardless.

---

## 2. 🧩 The thesis

> **TeamVault is the governed, multi-tenant, auditable *memory substrate* for agentic development — a hybrid-search knowledge base as the spine, where whole capabilities (knowledge, governance, agents, and eventually entire workflows) install as opt-in *packs* scoped to isolated *spaces*. Bring your own harness, or use ours.**

The agentic-coding field is crowded with **harnesses** (OMC, ECC, Ralph, and a dozen others) and thin on **substrate**. Every harness bolts on a memory layer as an afterthought — OMC's wiki has no embeddings or governance; ECC's continuous-learning is flat files. None has spaces, packs, citation/audit, privacy gates, or compliance modes. That gap is TeamVault's wedge:

- **Harness features get commoditized.** Claude Code itself keeps absorbing them; ECC openly preaches *"strip scaffolding as models improve."* Betting the project on out-feature-ing OMC is the weak play.
- **Governed compounding memory is durable.** It gets *more* valuable as models improve and as more work flows through it. That's the moat.

So the strategy is **substrate-first, workflow-as-packs**. The substrate makes TeamVault irreplaceable; the workflow pack is the killer app that shows off the substrate. TeamVault's own roadmap already leans this way — [P2.12 `get_company_context`](ROADMAP.md) is explicitly *"substrate-under-harness positioning … lets OMC and similar harnesses pull team context without knowing about TeamVault internals."*

---

## 3. 🔬 Why this is viable (the evidence)

**1. The convergence already happened — five times.** Five independent systems — **a personal knowledge vault** (production, 500+ docs), **an autonomous-coding KB**, **a content-search API**, **a transcript-search pipeline**, and **a debugging KB** — without coordinating, rejected framework-heavy approaches (MemPalace, Bedrock KB, S3 Vectors) and built the *same* architecture: hybrid BM25 + vector + RRF, contextual retrieval, paragraph chunking, temporal decay, palace taxonomy (the full account is in [KB-FOUNDATIONS.md](KB-FOUNDATIONS.md)). We don't have to prove one architecture generalizes across personal / org / autonomous-agent use — there are already five data points that it does. TeamVault is the act of *naming and composing* that convergence into a tool.

**2. TeamVault is already the right shape.** It's not a KB we'd bend into a platform — it's *already* `core engine + packs + spaces`, KB-first, MIT, multi-OS-roadmapped. Its README states the thesis directly: *"The runtime is generic; what your team cares about is declared in packs you enable in `space.yaml`."* The hard architecture (multi-tenant spaces, pack runtime, git-distributed substrate, host adapters) is decided. [ARCHITECTURE.md §1](ARCHITECTURE.md) already commits to the multi-context goal: *"a company, a team, two people on a side project, or one person across many of their own repos … TeamVault makes no opinionated distinction between team and personal use."*

**3. We already have two best-in-class workflow pieces** to seed the flagship pack: a plan-review **Convergence Mode** (a genuine converge-and-exit loop controller) and a **KB-integrated ticket loop** (recall → implement → critic → review → publish) already running in production against TeamVault. The hardest parts of the harness layer are built; they just need to be generalized and re-homed as packs.

---

## 4. 🗺️ Landscape: what we're converging

Three sources feed TeamVault. Each is read for what to *steal*, not adopt wholesale.

### 4.1 ECC — "Everything Claude Code" (affaan-m/ecc)

**What it is:** a cross-harness "operator system" — 92 commands, 271 skills, 67 agents, ~1,495 docs, shimmed into 10+ tools. MIT core + a Pro/AgentShield commercial funnel.

**Identity:** sells *ideas / methodology*. Its real value is the writing and the **loop taxonomy**.

| Steal ✅ | Leave ❌ |
|---|---|
| The **loop taxonomy** (sequential `claude -p` chains → Ralphinho RFC-DAG → GAN harness → Santa Method → Council) as a *which-loop-for-which-task* decision matrix | 271-skill sprawl (violates its own "context is precious" rule) |
| **Anti-bias review** everywhere: reviewer ≠ author, model diversity (real Codex/Gemini reviewers), fresh reviewers per round | Marketing-coupled features; implausible 218k-star social proof; single squashed git history |
| Novel **hooks**: GateGuard *fact-forcing* (block first edit until the agent investigates), config-protection, context-monitor (tool-loop / scope-creep / cost-spike detection) | Tests validate *structure not behavior*; minified inline `node -e` hooks (poor auditability) |
| `instinct → evolve → promote` continuous-learning with confidence scoring; runtime hook profiles (`minimal/standard/strict`) | Many "loops" are *docs pointing at other repos*, not turnkey runtimes |

**Best philosophy line:** *"Every harness component encodes an assumption about what the model can't do alone. When models improve, re-test those assumptions. Strip away what's no longer needed."*

### 4.2 OMC — oh-my-claudecode (yeachan-heo)

**What it is:** a multi-agent orchestration framework. ~36k stars, ~293K LOC TS, 569 tests. *"Don't learn Claude Code. Just use OMC."*

**Identity:** sells *mechanical enforcement*. Its signature is a `Stop` hook that `decision:block`s Claude from quitting until state says done ("the boulder never stops").

| Steal ✅ | Leave ❌ |
|---|---|
| The **Stop-hook persistence pattern** *with* its hard-won anti-deadlock escapes (context-limit, auth, re-entrancy `stop_hook_active`, async-pending) | Massive surface area (40 skills, 19 agents, ~20 hooks, V1/V2 runtimes) |
| **UltraQA** "same failure 3× → bail" + architect-diagnose→executor-fix split | Token cost of persistence loops (ralph default 100 iters, auto-extends) |
| **self-improve**: tournament selection over git-worktree variants with *sealed* anti-cheat benchmarks + plateau/circuit-breaker termination | Skill↔hook divergence: rich logic in prompts, blunt hook just says "continue" — correctness depends on prompt adherence |
| **deep-interview** mathematical ambiguity gating (numeric clarity score + threshold) ; **ralplan** anchor gate (regex anchors → plan-first vs execute-now) | Deprecation churn; native-addon deps; reliance on experimental Claude Agent Teams |
| The **`critic` agent spec** (pre-commitment predictions, "what's MISSING", Realist Check); 4-tier memory; control/data-plane split; tool-error escalation ladder | |

**Best philosophy line:** *"A false approval costs 10-100× more than a false rejection."*

### 4.3 The ticket-grounded workflow (the maintainer's)

**What it is:** a Jira/issue-grounded, single-repo, dispatch-and-supervise autonomous build flow with a real safety floor.

- A **start-ticket ⇄ review-ticket** pairing — a **mandatory adversarial review gate** (a hard rule: 5 parallel fresh-context reviewers) before any commit; bounded fix retries; two human approval gates.
- A **plan-review** loop — the **jewel**: a converge-and-exit controller with iteration-aware reviewer suppression, trend sparklines (`🔴 4→1→0`), and a READY-TO-EXECUTE shortcut.
- A **KB-integrated ticket loop** *already in production* against TeamVault: ticket → `vault_search` → implement → `critic` before publish → code-review + `/teamvault-review` → `vault_publish` → PR.
- An **autonomous build methodology** — watchdog cron + a durable `JOURNAL.md` + phase-boundary critic fan-out (proven, but siloed).

**The gap (and the opportunity):** the **plan** side converges and exits; the **build** side only "retries twice and stops." There's no cross-pass trend signal for implementation and **no automatic re-plan when reviews surface spec-level findings.** That missing `review → re-plan` edge is exactly the nested loop the v3 design supplies (§7).

### 4.4 Head-to-head

| Dimension | ECC | OMC | The workflow | **TeamVault (target)** |
|---|---|---|---|---|
| Sells… | Ideas | Enforcement | Trust / org-grounding | **Governed substrate + workflow-as-packs** |
| Memory / KB | flat learning files | wiki (no embeddings) | a multi-tier KB stack | **first-class: hybrid search, spaces, packs, audit** |
| Multi-tenant | per-tool dotdirs | no | no | **spaces (one fork per context)** |
| Governance / audit | none | none | partial (TV packs) | **packs, cite/query-log, compliance modes** |
| Loop enforcement | docs + some turnkey | mechanical (Stop hook) | prompt-only (review gate) | **pack-provided (steal the Stop-hook pattern)** |
| Surface area | sprawl (271 skills) | large (293K LOC) | lean (~7 skills) | **tiny core + opt-in packs** |
| Lock-in | soft (funnel) | moderate (hook/MCP) | none | **none (markdown substrate, MIT)** |

---

## 5. 🧠 The convergence principles

Independently built, ECC + OMC + the ticket-grounded workflow + the converged KB systems agree on the same load-bearing truths. These are the design invariants TeamVault should encode:

1. **Anti-self-review** — verification by fresh-context, independent (ideally model-diverse) reviewers. A reviewer must never be the author.
2. **Loops converge and exit** — every loop needs explicit termination + convergence detection (trend, plateau, "3× same failure → bail"), never infinite iteration.
3. **Evidence over claims** — fresh command output, not "should work."
4. **Context is a scarce budget** — durable files + batch operations + compaction resistance.
5. **Clarity gate before code** — a numeric ambiguity / AC-clarity threshold gates execution.
6. **Compounding memory** — corrections and decisions become durable, searchable artifacts; the Nth session beats the 1st.
7. **Model routing by tier** — haiku for lookup, sonnet for implementation, opus for strategy/review.
8. **Control-plane / data-plane separation** — small loop state vs large knowledge artifacts, referenced by handle.
9. **Markdown + YAML frontmatter is the substrate; indexes are disposable** — hybrid BM25 + vector + RRF over a git-tracked source of truth ([KB-FOUNDATIONS.md](KB-FOUNDATIONS.md)).

---

## 6. 🏗️ Architecture: how it all fits into TeamVault

The whole convergence maps onto five layers TeamVault already has (or needs one extension for):

```
┌─ HOST ADAPTERS ── Claude Code today; Codex/others via *.tv.md (ROADMAP P2.3) ─┐
│                                                                                │
│   ┌─ WORKFLOW (the harness, shipped as PACKS) ──────────────────────────────┐ │
│   │  v3 convergence controller · loops · review panels · GateGuard hook ·    │ │
│   │  Stop-hook persistence · de-slop · model-diversity review                │ │
│   └──────────────────────────────┬──────────────────────────────────────────┘ │
│                                   │ recall / publish (the meta-loop)            │
│   ┌─ PACKS (the universal bundling unit) ───────────────────────────────────┐ │
│   │  knowledge_topics · reviewers · scrubbers · agents · [NEW] skills/hooks/ │ │
│   │  loops · governance · compliance.  jira-linkage · clickup-linkage · hipaa│ │
│   └──────────────────────────────┬──────────────────────────────────────────┘ │
│   ┌─ SPACES (multi-tenant isolation, one git fork each) ────────────────────┐ │
│   │  teamvault-org   ·   teamvault-client   ·   teamvault-personal           │ │
│   └──────────────────────────────┬──────────────────────────────────────────┘ │
│   ┌─ MEMORY PALACE (org-scale taxonomy — ROADMAP P3) ───────────────────────┐ │
│   │  Kingdom → Palace → Wing → Hall → Room  +  Tunnels (cross-refs)          │ │
│   └──────────────────────────────┬──────────────────────────────────────────┘ │
│   ┌─ CORE ENGINE (the substrate / moat) ────────────────────────────────────┐ │
│   │  FastAPI sidecar (single-writer) · MCP (vault_search/publish/status) ·   │ │
│   │  hybrid BM25(SQLite FTS5)+vector(LanceDB/Nomic)+RRF · cite/audit ·       │ │
│   │  markdown+frontmatter substrate (indexes disposable)                     │ │
│   └─────────────────────────────────────────────────────────────────────────┘ │
└────────────────────────────────────────────────────────────────────────────────┘
```

**Where each stolen idea lands:**

| Idea | Source | Lands as |
|---|---|---|
| Loop taxonomy / which-loop-for-which-task | ECC | A workflow-pack's loop selector |
| Anti-bias + model-diversity review | ECC (Santa) + workflow | Review pack (one reviewer via Codex/Gemini CLI) + `/teamvault-review` pack gate |
| GateGuard fact-forcing, config-protection, context-monitor | ECC | Hook contributions in a workflow pack |
| Stop-hook persistence + anti-deadlock escapes | OMC | The loop runtime inside the workflow pack |
| "3× same failure → bail"; critic spec; ambiguity gate; anchor gate | OMC | Build-loop guard + review agent + clarity gate |
| Convergence Mode (trend, plateau, READY-TO-EXECUTE) | the plan-review loop | The macro **convergence controller** |
| KB recall → critic → publish | the ticket loop | The **meta-loop**, native to the substrate |
| `instinct → evolve → promote` | ECC | The promotion ladder across spaces (§8) |
| Palace taxonomy + tunnels | the converged KB design | The Memory Palace layer |

**The one extension that makes it real:** today the [pack contract](CONTRACTS.md) contributes `{agents, scrubbers, reviewers}`. To let the harness ship as a pack, grow it to also carry `{skills, commands, hooks, loops/orchestrators}`. This is **not** yet roadmapped ([P2.4](ROADMAP.md) only adds *metadata* like `ordering`/`veto`/`depends_on`). It is the hinge between "TeamVault the KB" and "TeamVault the platform" — and it introduces a real new trust surface (see §10).

---

## 7. 🔁 The v3 workflow — shipped as the flagship pack

The workflow you're drawn to — *plan loop → dev loop → review loop, re-entering planning on new findings* — is the precise documented gap in the ticket-grounded flow. It composes as **three loop scales**, with the KB (the substrate) as the memory of the outermost one:

```
META LOOP (across tickets, lives in the KB) ── the compounding loop
  │  KB recall ─→ [ MACRO LOOP per ticket ] ─→ KB publish ─→ smarter next recall
  │
  └─ MACRO LOOP (per ticket): the Convergence Controller
        │
        ├─ PHASE 1 · PLAN     clarity/ambiguity gate + KB recall + plan-review convergence
        ├─ PHASE 2 · BUILD    phased impl + GateGuard + ultraqa "3× → bail" + de-slop
        ├─ PHASE 3 · REVIEW   5 fresh reviewers + 1 model-diverse + /teamvault-review pack gate
        └─ CONTROLLER decides the next edge:
             ✅ ship-grade, 0 findings        → EXIT → two human gates → commit/PR → KB publish
             ⚠️ code-local findings           → re-enter BUILD   (tight loop)
             ⚠️ spec/approach findings        → re-enter PLAN    ◀── the re-plan edge you wanted
             ❌ scope drift / trend stalled 2× → STOP → escalate to human
        terminate on: ship-grade · max_passes · token budget · plateau
```

The controller is a generalization of the plan-review loop's existing Convergence Mode, lifted from the *plan* scope to the *macro* scope. The exit path is unchanged — it still passes through the two human approval gates and the safety floor.

**Ranked grafts (the pack's contents):**

- **Tier 1 (prompt-only):** macro convergence controller · "3× same failure → bail" · model-diversity reviewer · fresh / anti-anchored reviewers on re-run.
- **Tier 2 (hooks):** GateGuard fact-forcing · bounded Stop-hook persistence *with* escapes · context-monitor (fixes the "agent froze for hours while the monitor stayed silent" blind spot) · config-protection.
- **Tier 3 (methodology):** numeric ambiguity gate · Council for decisions · `instinct→evolve→promote`.

---

## 8. 📚 The knowledge tier & routing contract

TeamVault is one tier of a coherent hierarchy. The biggest risk with several knowledge stores is fragmentation, so the **routing contract** must be explicit (and belongs in each repo's agent-rules file):

| Tier | Store | Scope | Holds |
|---|---|---|---|
| Personal | **a personal vault** | You | The *why*: meeting/decision context, stakeholder context, cross-project direction, personal repos |
| Team | **TeamVault** | a team / client | Team policy, conventions, postmortems + **packs** (governance) |
| Org | **an org KB** (planning) | your org (many repos) | Org code-knowledge: agent-rules files, memory, lessons — privacy-gated ("generalize-or-drop") |
| *(native)* | agent memory | you/project | Fast local recall of corrections/prefs |
| *(native)* | agent-rules file | repo | Always-on rules |

> **Routing rule:** personal/*why* → the personal vault · team-shared *how* → TeamVault · org code-knowledge → the org KB · fast per-project recall → agent memory · always-on rules → the repo's agent-rules file.
> **Promotion ladder:** a lesson starts personal (the personal vault) and is promoted up to team → org as it generalizes — the privacy gate is the promotion filter. (This is ECC's `instinct → evolve → promote`, with the three tiers as promotion targets.)

**Critical distinction to preserve:** the **KB holds *settled* knowledge**; the **live working state** (the loop ledger, current pass #, finding trend) stays in a control-plane file. Don't dissolve live state into the KB — that's the control-plane / data-plane split (principle #8). Session files are right to retire; the live-state file is not a session file.

**Convergence note:** a personal vault, TeamVault, and an org KB are three implementations of the *same engine* differentiated only by scope and a few feature-packs. The endgame is **one engine, many isolated spaces** — the personal vault and org KB fold in as space-types / feature-packs, not separate codebases.

---

## 9. ✅ Direct answers to the viability questions

- **Could it be done?** Yes. The R&D is done (five convergent systems); this is productization + convergence, not invention.
- **Could it be kept (maintained solo)?** Yes — *if* the core stays tiny and everything else is a pack. "All the best features" becomes a rich **pack ecosystem**, not a fat core. (Keep [ROADMAP P2.18](ROADMAP.md) GOVERNANCE.md + bus-factor mitigation.)
- **Adaptable to everyone, including you?** Yes — and you're the *ideal* first user. Most solo OSS authors over-fit to one context; you have **three genuinely different tenants** (an employer org, a client, and personal) forcing real generality. That's a structural advantage.
- **One repo / one setup / one KB for everything?** **One engine/setup: yes. One *KB*: no — and you shouldn't want it.** The design is one sidecar managing *many isolated spaces* (one fork each). The "one KB feel" comes from cross-space *tunnels* — which is exactly where leaks happen. Default to hard isolation; make cross-space references explicit, audited, opt-in.
- **Contend with OMC / ECC?** Yes — **in the niche they neglect** (governed compounding memory + a KB-native workflow), not by matching their breadth.

---

## 10. ⚠️ Risks & honest caveats

| Risk | Why it's real | Mitigation |
|---|---|---|
| **Substrate-vs-harness scope creep** | Trying to out-harness OMC is how you get ECC's 271-skill sprawl | Sequence: substrate first, harness as packs second. Tiny core. |
| **Solo maintainer / bus factor** | One person; OMC/ECC have momentum + funnel | Near-term bar = "useful to me + my orgs." OSS = upside. ([P2.18](ROADMAP.md)) |
| **Cross-tenant leakage (org ↔ client)** | Per-space isolation is *"a routing simplification, not a security control"* ([ARCH §2](ARCHITECTURE.md)) — two organizations on one machine | Harden isolation + finish data-egress invariants ([P0.7](ROADMAP.md)) before multi-org trust |
| **Executable-pack trust** | Workflow packs carry hooks/loops that *run code* — a malicious third-party pack = RCE on install. Today's packs (markdown + regex) are safe | Pack signing + registry trust tiers ([P2.1](ROADMAP.md), [P2.19](ROADMAP.md)) before workflow packs ship publicly |
| **Install friction (2.5GB torch + model)** | Blocks "anyone can use it" | Wheelhouse / Docker / lighter embeddings ([P1.3](ROADMAP.md), [P2.9](ROADMAP.md)) |
| **Harness commoditization** | Claude Code keeps absorbing harness features | The substrate outlives the harness — another reason to lead with it |
| **Naming** | "TeamVault" for personal / anyone use reads oddly | Already flagged ([P2.6](ROADMAP.md) workspace→variant; P3 naming). Minor. |

---

## 11. 🚦 Phased roadmap

Mapped onto the existing [ROADMAP.md](ROADMAP.md); respects "start simple."

**Phase 1 — Be the substrate; dogfood across all three contexts (→ v0.1).**
Finish P0 (audit log P0.1, scrubber hooks P0.2, egress invariants P0.7). Stand up three real spaces (`teamvault-org`, `teamvault-client`, `teamvault-personal`). Route the *existing* ticket + review skills (start-ticket / review-ticket / the ClickUp variant) to recall + publish against them. **You become tenant #1/#2/#3 on live work.**

**Phase 2 — Grow the pack contract to carry workflows (→ v0.2).**
Extend the [pack contract](CONTRACTS.md) with `{skills, hooks, loops}` contribution types (beyond [P2.4](ROADMAP.md)'s metadata). Ship the **v3 convergence controller as the first workflow pack**. Now the harness *is* a pack — and "contend with OMC" begins, as a KB-native workflow platform.

**Phase 3 — Absorb the siblings + Memory Palace (→ v0.2+).**
Fold the personal vault and org KB in as space-types / feature-packs (same engine — the convergence proves it). Land kingdom/palace/wing/hall/room/tunnels ([P3 "Mem Palace hierarchy"](ROADMAP.md)) as the org-scale organizer. Cross-space tunnels *with governance*.

**Phase 4 — Open it (→ v1).**
GOVERNANCE.md ([P2.18](ROADMAP.md)), light install (Docker/wheelhouse), signed pack registry with trust tiers ([P2.1](ROADMAP.md)), docs site. Position: *"the governed memory substrate for agentic development — bring your own harness, or use ours."*

---

## 12. 🏁 Success metric

The bar for "worth it" is **not** "dethrone OMC." It is: **one engine that makes the maintainer and their organizations compound across every project.** If it only ever does that, it has already succeeded. OSS stardom and out-competing OMC are *upside built on a foundation that's valuable regardless* — which is also the discipline that prevents the ECC trap (building abstractions for hypothetical users). Three real, divergent tenants are the forcing function for genuine generality.

---

## 13. ❓ Open decisions

For the maintainer / design partners to settle:

1. **Confirm substrate-first sequencing** — agree to lead with the substrate and ship the workflow as packs (vs. building a competing harness)?
2. **Which context first** for Phase-1 dogfooding — the org (most mature skills), the client (cleanest greenfield), or personal (lowest risk)?
3. **Cross-tenant model** — hard-isolated spaces only for now, with tunnels deferred until governance lands? (Recommended.)
4. **Naming** — keep "TeamVault" (with "space" covering personal/team/org) or rebrand before OSS launch?
5. **Hosting** — stay local-first / git-distributed, or plan a hosted option for non-technical adopters? (The org-KB plan defers this to a later "hosted-migration trigger.")
6. **Pack-security posture** — what trust tier / signing is required before *executable* (hook/loop) packs are accepted into the public registry?

---

## 14. 📋 Provenance

Synthesized from a research session (2026-06-19) that deep-dived two external harnesses ([ECC](https://github.com/affaan-m/ecc), [oh-my-claudecode](https://github.com/yeachan-heo/oh-my-claudecode)), a mature ticket-grounded workflow (a paired start-ticket / review-ticket / plan-review skill set with a KB-integrated ticket loop), the [AUTONOMOUS_BUILD_METHODOLOGY](AUTONOMOUS_BUILD_METHODOLOGY.md), a multi-system KB convergence study (distilled in [KB-FOUNDATIONS.md](KB-FOUNDATIONS.md)), and TeamVault's own [ARCHITECTURE](ARCHITECTURE.md) / [CONTRACTS](CONTRACTS.md) / [ROADMAP](ROADMAP.md). This is a proposal for review, not a committed plan.
