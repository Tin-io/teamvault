# 🗃️ TeamVault

> ✨ **Bidirectional knowledge sharing between developers and the agents they use** — same markdown substrate in git, two access patterns: agents query via MCP, humans browse via GitHub.

<p align="center">
  <img src="https://img.shields.io/badge/status-v0.0%20alpha-orange?style=flat-square" alt="Status: v0.0 alpha">
  <img src="https://img.shields.io/badge/license-MIT-green?style=flat-square" alt="License: MIT">
  <img src="https://img.shields.io/badge/python-3.10%2B-3776AB?style=flat-square&logo=python&logoColor=white" alt="Python 3.10+">
  <img src="https://img.shields.io/badge/sidecar-FastAPI-009688?style=flat-square&logo=fastapi&logoColor=white" alt="FastAPI sidecar">
  <img src="https://img.shields.io/badge/vector-LanceDB-7c3aed?style=flat-square" alt="LanceDB vector store">
  <img src="https://img.shields.io/badge/text-SQLite%20FTS5-003B57?style=flat-square&logo=sqlite&logoColor=white" alt="SQLite FTS5">
  <img src="https://img.shields.io/badge/embedding-Nomic%20v1.5-1e40af?style=flat-square" alt="Nomic Embed v1.5">
  <img src="https://img.shields.io/badge/protocol-MCP-7048e8?style=flat-square" alt="MCP protocol">
  <img src="https://img.shields.io/badge/fusion-RRF%20k%3D60-555?style=flat-square" alt="RRF k=60 fusion">
</p>

<p align="center">
  🍎 <b>macOS</b> v0.0 &nbsp;·&nbsp; 🐧 <b>Linux</b> v0.1 &nbsp;·&nbsp; 🪟 <b>Windows</b> v0.2 &nbsp;·&nbsp; 🐳 <b>Docker</b> v0.2 &nbsp;—&nbsp; <a href="docs/USER_GUIDE.md#os-support">full OS support table</a>
</p>

---

## 🧩 How it works (in 2 paragraphs)

Your team forks this repo as a "space" (or stays in this master template). Each dev clones the space; a local Python sidecar watches the clone, re-indexes `kb/entries/*.md` on `git pull` into a hybrid (BM25 + vector + RRF) search index, and exposes three MCP tools to Claude Code or Codex: `vault_search`, `vault_publish`, `vault_status`. One teammate publishes a decision; ~60 seconds later every teammate's agent can search it. Humans read the same markdown directly in GitHub.

**Packs** extend the runtime — drop a `packs/hipaa-reference/` directory with regex patterns + a reviewer agent prompt, and every PR gets reviewed for PHI leaks (blocking). Drop a `packs/clickup-linkage/` or `packs/jira-linkage/` directory and PRs without ticket links get flagged. The runtime is generic; what your team cares about is declared in packs you enable in `space.yaml`.

## 🚀 Install

Paste this into Claude Code or Codex from inside the project repo you want to bind:

```
Install TeamVault for this project.

1. Clone the master template to a temp dir:
   git clone https://github.com/tin-io/teamvault /tmp/teamvault-master

2. Read /tmp/teamvault-master/.claude/skills/teamvault-setup/SKILL.md and execute it.

3. When the skill asks for the team space URL, use your team's fork URL.

4. Confirm install completion by running the MCP `vault_status` tool.
```

The agent walks the install in ~10 min on first run (the slow part is downloading `torch` + the Nomic embedding model). See [SETUP_PROMPT.md](SETUP_PROMPT.md) for the canonical paste-in prompt and [USER_GUIDE — Quick start](docs/USER_GUIDE.md#quick-start) for prerequisites + step-by-step expectations.

## 📚 Documentation

**👉 Start here: [`docs/USER_GUIDE.md`](docs/USER_GUIDE.md)** — 11-section comprehensive guide. Install → the four daily moves (search · publish · review · status) → how packs work → workflow integration (`/start-ticket`+`/review-ticket`, OMC, vanilla Claude Code, Codex) → your responsibility → frictionless adoption recommendations → troubleshooting pointer → glossary. Links onward to every other doc.

If you want to skip directly to a specific topic:

| When you need... | Read... |
|---|---|
| 🎯 **Install + daily use (start here)** | [USER_GUIDE.md](docs/USER_GUIDE.md) |
| 🧭 **The vision & strategy — where TeamVault is going** | [STRATEGY.md](docs/STRATEGY.md) |
| 🏗️ **The canonical architecture** | [ARCHITECTURE.md](docs/ARCHITECTURE.md) |
| 📐 Reference: HTTP API + MCP + pack contract + env vars | [CONTRACTS.md](docs/CONTRACTS.md) |
| 📚 The underlying KB pattern catalog this builds on | [KB-FOUNDATIONS.md](docs/KB-FOUNDATIONS.md) |
| 🛠️ Day-of failure modes (symptom → check → fix) | [TROUBLESHOOTING.md](docs/TROUBLESHOOTING.md) |
| 🧱 Build your own pack | [CONTRIBUTING_PACKS.md](docs/CONTRIBUTING_PACKS.md) |
| 🗺️ What's coming in v0.1 / v0.2 / v0.3 | [ROADMAP.md](docs/ROADMAP.md) |
| 🤖 How this repo was built autonomously over a 24h Sabbath window | [AUTONOMOUS_BUILD_METHODOLOGY.md](docs/AUTONOMOUS_BUILD_METHODOLOGY.md) |


## 🗂️ Repository structure

```
sidecar/                 🐍 Python FastAPI sidecar (localhost:8100) + MCP shim
packs/                   🧩 Reference packs (hipaa-reference, clickup-linkage, jira-linkage)
.claude/skills/          ⚡ Slash commands the install registers with Claude Code
.github/workflows/       🤖 GHA workflow for PR-stage pack-runtime review
kb/entries/              📝 Team KB markdown — the source of truth (master ships one meta-template entry; teams add their own)
docs/                    📚 All documentation (see Documentation section above)
.build/                  🛠️ Build/test scaffolding (local; build journal + plans are gitignored)
SETUP_PROMPT.md          🚀 Canonical paste-this-prompt for install
LICENSE                  📜 MIT + HIPAA-pack disclaimer
```

## 🧰 Stack at a glance

| Layer | Technology |
|---|---|
| 🌐 HTTP API | [FastAPI](https://fastapi.tiangolo.com/) + [Uvicorn](https://www.uvicorn.org/) on `localhost:8100` |
| 🔢 Vector store | [LanceDB](https://lancedb.com/) (file-based, embedded) |
| 🔤 Text search | [SQLite FTS5](https://www.sqlite.org/fts5.html) (BM25, porter stemmer) |
| 🧠 Embeddings | [Nomic Embed v1.5](https://huggingface.co/nomic-ai/nomic-embed-text-v1.5) (768-dim, local) |
| 🧮 Hybrid fusion | Reciprocal Rank Fusion, k=60 |
| ✂️ Chunking | Paragraph-bounded, 512 tokens, 64 overlap |
| 🔌 Agent integration | [Model Context Protocol (MCP)](https://modelcontextprotocol.io/) stdio shim |
| 📂 Substrate | Markdown + YAML frontmatter in git (the source of truth) |
| 🔐 Compliance reviewer | Pack-extensible runtime (HIPAA reference pack ships in v0.0) |
| 🦾 Supervisor (v0.0) | macOS launchd plist · v0.1 systemd · v0.2 Windows Service / Docker |

## 🤝 Contributing

Open an issue or PR against [tin-io/teamvault](https://github.com/tin-io/teamvault). For pack contributions specifically, see [docs/CONTRIBUTING_PACKS.md](docs/CONTRIBUTING_PACKS.md) — three-tier governance model (core / official / community), `PACK.yaml` schema with v0.1 extension preview, contributor checklist.

🛡️ `main` is protected: only repo admins can merge. Non-admin contributors open PRs against `main`; admins review + merge.

## 📜 License

MIT. See [LICENSE](LICENSE) — includes a HIPAA-pack disclaimer worth reading if your team handles PHI or is considering forking the `hipaa-reference` pack for production use.
