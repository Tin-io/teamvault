# 🚀 TeamVault Setup Prompt

> ✨ Paste the block below into Claude Code or Codex from inside the project repo you want to bind to your team's TeamVault space. The agent will ask you anything it needs from there — no editing required.

<p align="center">
  <img src="https://img.shields.io/badge/scope-install-7048e8?style=flat-square" alt="Scope: install">
  <img src="https://img.shields.io/badge/first%20run-~10%20min-orange?style=flat-square" alt="First run: ~10 minutes">
</p>

> ⚠️ **Heads up:** the install pulls `torch` (~2.5 GB) and downloads the Nomic embedding model (~547 MB) on first reindex. Plan 8-15 minutes for a fresh install on good Wi-Fi; longer on shared / conference Wi-Fi. Ideally have devs install ahead of any time-boxed demo.

---

## 👥 The model (read once before pasting)

Your team forks `tin-io/teamvault` into your org **once** (e.g. `your-org/teamvault-<team-name>`). That fork is your team's **space** — all KB entries, all pack config, all binds live there. Every teammate clones the **fork** (not master) and runs the sidecar against it. Master stays as the upstream you periodically pull updates from.

The setup skill handles both flows from the same paste-in below:
- **First-time setup (the seeder):** the skill walks you through `gh repo fork tin-io/teamvault --org <your-org> --fork-name teamvault-<team>` first, then installs against the new fork.
- **Joining an existing team space:** you give the skill the URL of your team's fork; it clones that fork and installs against it.

The `/tmp/teamvault-master` clone in step 1 below is **NOT** your working tree — it exists only so the agent can read the setup skill (`SKILL.md`). The real install lands in `~/teamvault-<space-name>/`, cloned from your team's fork.

---

## 📌 Paste this prompt

```
Install TeamVault on this machine and bind it to the project repo I'm currently in.

1. Clone the master template to /tmp ONLY so the setup skill is readable —
   /tmp/teamvault-master is NOT my working tree, it's just where the agent
   reads SKILL.md from:
   git clone https://github.com/tin-io/teamvault /tmp/teamvault-master

2. Read /tmp/teamvault-master/.claude/skills/teamvault-setup/SKILL.md and execute it.

3. Ask me whatever you need to proceed — the skill will check whether my team
   already has a TeamVault space fork I should clone (I'll give you the URL),
   or whether I'm the first dev and need to fork tin-io/teamvault into our
   org first. Then it'll ask which packs to enable, whether to bind this
   project repo, and whether to deploy the optional PR workflow skills.

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
