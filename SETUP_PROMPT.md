# 🚀 TeamVault Setup Prompt

> ✨ Paste the block below into Claude Code or Codex from inside the project repo you want to bind to your team's TeamVault space. The agent will ask you anything it needs from there — no editing required.

<p align="center">
  <img src="https://img.shields.io/badge/scope-install-7048e8?style=flat-square" alt="Scope: install">
  <img src="https://img.shields.io/badge/first%20run-~10%20min-orange?style=flat-square" alt="First run: ~10 minutes">
</p>

> ⚠️ **Heads up:** the install pulls `torch` (~2.5 GB) and downloads the Nomic embedding model (~547 MB) on first reindex. Plan 8-15 minutes for a fresh install on good Wi-Fi; longer on shared / conference Wi-Fi. Ideally have devs install ahead of any time-boxed demo.

---

## 📌 Paste this prompt

```
Install TeamVault on this machine and bind it to the project repo I'm currently in.

1. Clone the master template to a temp dir for the setup skill:
   git clone https://github.com/tin-io/teamvault /tmp/teamvault-master

2. Read /tmp/teamvault-master/.claude/skills/teamvault-setup/SKILL.md and execute it.

3. Ask me whatever you need to proceed — including the team space URL, whether to fork the master template if I don't have a space yet, which packs to enable, and whether to deploy the optional PR workflow skills.

4. When done, confirm by:
   - calling the MCP `vault_status` tool and showing me the output
   - showing me a `vault_search` query result
```

---

## 🤖 What the agent will ask you

The setup skill is **conversational**. Expect questions like:

1. **Do you already have a TeamVault space fork?** — If not, the skill walks you through forking `tin-io/teamvault` into your org and picking a name (e.g. `teamvault-<team>`).
2. **What's the space URL?** — e.g. `https://github.com/your-org/teamvault-<team>`.
3. **Confirm enabled packs in `space.yaml`?** — Master template defaults to `hipaa-reference` + `clickup-linkage`; you can keep, modify (comma-separated list), or set to `none`. Available in the master template: `hipaa-reference`, `clickup-linkage`, `jira-linkage`.
4. **Bind this project repo?** — Auto-detected from `git remote get-url origin`; confirms before committing.
5. **Deploy the optional PR workflow skills (`pr-push`, `pr-review`, `pr-fix`, `pr-pipeline`) into this project?** — Defaults to yes for teams using the GitHub PR flow; can be deferred.

Bring **one answer to each** and the skill handles everything else (cloning the fork, reconciling `space.yaml::name`, appending to `repos.yaml`, installing the sidecar, registering MCP with Claude Code, writing the project's `CLAUDE.md` block, and smoke-testing).

---

## 💡 Why the template-clone-first step

The setup skill lives in the master template, but a fresh Claude Code session in your project repo has no local copy of the master template yet. Cloning to `/tmp/teamvault-master` first gives the skill a stable place to read from. The actual install lands in `~/teamvault-<space-name>/` (cloned from your team's space fork) — `/tmp/teamvault-master` is just a read source for the skill.
