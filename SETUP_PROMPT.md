# 🚀 TeamVault Setup Prompt

> ✨ Copy the block below and paste it into your Claude Code or Codex session, from inside the project repo you want to bind to your team's TeamVault space.

<p align="center">
  <img src="https://img.shields.io/badge/scope-install-7048e8?style=flat-square" alt="Scope: install">
  <img src="https://img.shields.io/badge/first%20run-~10%20min-orange?style=flat-square" alt="First run: ~10 minutes">
</p>

> ⚠️ **Heads up:** the install pulls `torch` (~2.5 GB) and downloads the Nomic embedding model (~547 MB) on first reindex. Plan 8-15 minutes for a fresh install on good Wi-Fi; longer on shared / conference Wi-Fi. Ideally have devs install ahead of any time-boxed demo.

---

## 📌 Paste this prompt

```
Install TeamVault for this project.

1. Clone the master template to a temp dir:
   git clone https://github.com/tin-io/teamvault /tmp/teamvault-master

2. Read /tmp/teamvault-master/.claude/skills/teamvault-setup/SKILL.md and execute it.

3. When the skill asks for the team space URL, use:
   https://github.com/your-org/teamvault-<space>
   (whichever fork your team uses)

4. Confirm install completion by:
   - running the MCP `vault_status` tool and showing me the output
   - showing me a `vault_search` query result
```

---

## 🤖 What the agent does

That's it. The agent will:
1. 📦 Clone the master template (~1 MB)
2. 📚 Read the setup skill
3. 🛠️ Walk through forking/cloning the team space, reconciling `space.yaml::name`, appending the current project to `repos.yaml`, installing the sidecar, registering the MCP endpoint via the `claude mcp add` CLI, and smoke testing

> 💡 If you don't yet have a team space fork (you're the first dev on your team to install), the setup skill walks you through `gh repo fork tin-io/teamvault --org your-org` first.

## 💡 Why the template-clone-first step

The setup skill lives inside the master template repo, but a fresh Claude Code session in your project repo has no local copy of the master template yet. Cloning it to `/tmp/teamvault-master` first gives the skill a stable place to read from. The actual install lands in `~/teamvault-<space-name>/` (cloned from the team space fork) — `/tmp/teamvault-master` is just a read source for the skill.
