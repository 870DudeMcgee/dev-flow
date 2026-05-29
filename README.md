# 🌿 DevMode

[![MIT License](https://img.shields.io/badge/license-MIT-blue.svg)](LICENSE)
[![Based on Superpowers](https://img.shields.io/badge/based%20on-Superpowers-green.svg)](https://github.com/obra/superpowers)
[![Harnesses supported](https://img.shields.io/badge/harnesses-Gemini%20%7C%20Claude%20%7C%20Cursor%20%7C%20Codex%20%7C%20OpenCode-purple.svg)](#installation)

> **DevMode** is a high-discipline, token-efficient, and multi-IDE agentic engineering framework. It extends the core rules of Jesse Vincent's **Superpowers** to enforce mode classification, strict token-budget rationing, clean git worktree boundary protection, and rigorous verification gates.

```
                  +-----------------------------------+
                  |           Agent Invoked           |
                  +-----------------------------------+
                                    |
                                    v
                  +-----------------------------------+
                  |     skills/using-devmode/         |  <--- Mandatory Bootstrap
                  +-----------------------------------+
                                    |
            +-----------------------+-----------------------+
            |                                               |
            v                                               v
+-----------------------+                       +-----------------------+
|  MODE: INVESTIGATION  |                       |  MODE: IMPLEMENTATION |
|  - token-budget       |                       |  - test-driven-dev    |
|  - workspace-isolation|                       |  - systematic-debug   |
|  - explore-first      |                       |  - verify-before-done |
+-----------------------+                       +-----------------------+
            |                                               |
            +-----------------------+-----------------------+
                                    v
                  +-----------------------------------+
                  |       skills/worker-handoff/      |  <--- Structured Handoff
                  +-----------------------------------+
```

---

## 📖 Table of Contents

- [🌿 The Core Philosophy](#-the-core-philosophy)
- [🛡️ The Four Iron Laws](#️-the-four-iron-laws)
- [📦 Available Skills (20 total)](#-available-skills-20-total)
- [⚙️ Installation & Harness Setup](#️-installation--harness-setup)
- [🤝 Contributing & TDD-for-Skills](#-contributing--tdd-for-skills)
- [⚖️ Attribution & Licensing](#️-attribution--licensing)

---

## 🌿 The Core Philosophy

AI agents are extremely powerful, but left to their own devices, they suffer from **context expansion bloat**, **lazy verification loops**, and **symptom-oriented patching**. 

DevMode converts the agent's environment into a **high-leverage discipline harness**:

1. **Discipline First**: No code is written without a TDD failing test first. No bug is fixed without systematic root-cause investigation first.
2. **Context Rationing**: Broad file reads and generic directory searches are strictly gated by the `token-budget` skill. The agent must search first and read selectively.
3. **Workspace Isolation**: Agents operate in clean, isolated, git-protected worktrees or task branches, preventing state pollution.
4. **Independent Seams**: Code is decomposed into deep modules with small interfaces, maximizing testability and AI comprehension.

---

## DevMode Contract

DevMode is governed by the canonical contract in [docs/devmode-contract.md](docs/devmode-contract.md).

The short version:

1. Mode Gate — classify the task before acting.
2. Context Gate — search before broad reads.
3. Change Gate — isolate edits and choose the right workflow.
4. Verification Gate — provide fresh evidence before claiming completion.

Harness-specific files should route agents to the contract instead of duplicating the full rules.

---

## 📦 Skill Inventory by Gate

DevMode includes a curated library of **20 specialized skills** organized under the four operational gates:

### 1. Mode Gate Skills
*   [**`using-devmode`**](skills/using-devmode/SKILL.md): The master session bootstrap. Dictates mode gating and skill routing.
*   [**`brainstorming`**](skills/brainstorming/SKILL.md): Multi-approach visual exploration before design doc creation.
*   [**`writing-plans`**](skills/writing-plans/SKILL.md): Bite-sized, zero-placeholder implementation checklists.
*   [**`executing-plans`**](skills/executing-plans/SKILL.md): Plan execution inside the current session with review gating.

### 2. Context Gate Skills
*   [**`token-budget`**](skills/token-budget/SKILL.md): Strict token economics. Replaces lazy read loops with search-first patterns.
*   [**`token-optimization`**](skills/token-optimization/SKILL.md): Project-local lightweight context and search-policy management.
*   [**`grill-with-docs`**](skills/grill-with-docs/SKILL.md): Interactive spec refinement using `CONTEXT.md` and `ADRs`.

### 3. Change Gate Skills
*   [**`test-driven-development`**](skills/test-driven-development/SKILL.md): Strict RED-GREEN-REFACTOR loops. No code without tests.
*   [**`systematic-debugging`**](skills/systematic-debugging/SKILL.md): Investigate before fixing. Includes `root-cause-tracing` and `defense-in-depth` modules.
*   [**`workspace-isolation`**](skills/workspace-isolation/SKILL.md): Strict workspace boundaries. Prevents edits leaking to protected directories.
*   [**`using-git-worktrees`**](skills/using-git-worktrees/SKILL.md): Seamlessly provisioning isolated git worktrees.
*   [**`subagent-driven-development`**](skills/subagent-driven-development/SKILL.md): Isolated subagent execution with independent spec and quality reviewers.
*   [**`dispatching-parallel-agents`**](skills/dispatching-parallel-agents/SKILL.md): Orchestrating parallel non-dependent sub-tasks.
*   [**`improve-codebase-architecture`**](skills/improve-codebase-architecture/SKILL.md): Surfacing shallow modules and generating visual deepening reviews.
*   [**`writing-skills`**](skills/writing-skills/SKILL.md): Applying TDD to process documentation (RED-GREEN-REFACTOR for skills).

### 4. Verification Gate Skills
*   [**`verification-before-completion`**](skills/verification-before-completion/SKILL.md): Concrete evidence checking before claiming completion.
*   [**`worker-handoff`**](skills/worker-handoff/SKILL.md): Rigorous task handoff protocol using verified evidence.
*   [**`requesting-code-review`**](skills/requesting-code-review/SKILL.md): Preparing clean PR reviews.
*   [**`receiving-code-review`**](skills/receiving-code-review/SKILL.md): Implementing feedback with technical rigor.
*   [**`finishing-a-development-branch`**](skills/finishing-a-development-branch/SKILL.md): Automated branch verification and merge readiness.

---

## ⚙️ Installation & Harness Setup

DevMode can be integrated with major AI coding harnesses (such as Claude Code, Gemini, Cursor, Codex, and OpenCode) via symlinks, prompts, or custom loader configurations. Follow the setup instructions for your specific environment below:

### 1. Claude Code
Claude Code automatically scans `.claude-plugin/plugin.json` to load custom skills.
1. Clone this repository into your project root:
   ```bash
   git clone https://github.com/870DudeMcgee/devmode.git .devmode
   ```
2. Symlink the `.claude-plugin` config:
   ```bash
   ln -s .devmode/.claude-plugin .claude-plugin
   ```
3. Symlink the `skills` folder:
   ```bash
   ln -s .devmode/skills skills
   ```

### 2. Gemini CLI
Gemini CLI uses a bootstrap config mapping.
1. Reference `gemini-extension.json` in your global config.
2. Gemini CLI will automatically load `GEMINI.md` as its starting prompt context, bootstrap-loading `using-devmode`.

### 3. Cursor
Cursor respects directory instruction prompts.
1. Link Cursor's system prompt instructions to `.devmode/skills/using-devmode/SKILL.md` to trigger full framework awareness on every new chat session.

### 4. Codex
1. Copy or link `.codex-plugin/` directory to your project root.
2. Codex will discover the UI metadata and register DevMode skills.

### 5. OpenCode
Follow instructions in `.opencode/INSTALL.md` to set up the bootstrap loader.

### 6. VS Code / GitHub Copilot
DevMode includes experimental VS Code / GitHub Copilot guidance:

- `.github/copilot-instructions.md`
- `.github/instructions/devmode.instructions.md`
- `.github/prompts/devmode-plan.prompt.md`
- `.github/prompts/devmode-review.prompt.md`
- `docs/vscode-copilot.md`

See `docs/vscode-copilot.md` for setup and usage.

---

## 🤝 Contributing & TDD-for-Skills

We love contributions! However, to maintain the rigorous discipline of DevMode, **all skill additions and modifications MUST follow the TDD-for-Skills process**:

1. **RED Phase**: Write a pressure scenario (under the `/tests` folder) that triggers the failure you want to prevent. Run an agent without your changes and verify it fails.
2. **GREEN Phase**: Implement your skill in `skills/your-skill/SKILL.md` to address the specific excuse or loophole. Run the agent with the skill and verify it now complies.
3. **REFACTOR Phase**: Plug any remaining loopholes by updating the rationalization table in your skill.

For complete guidelines, read [**`writing-skills`**](skills/writing-skills/SKILL.md) and the [**Contributing Guide**](CONTRIBUTING.md).

---

## ⚖️ Attribution & Licensing

DevMode is released under the [MIT License](LICENSE).

It is based heavily on [**Superpowers**](https://github.com/obra/superpowers) by [Jesse Vincent](https://blog.fsck.com) and the team at [Prime Radiant](https://primeradiant.com). We are deeply grateful for their trailblazing work on AI agent discipline. Comprehensive attribution details can be found in [ATTRIBUTION.md](ATTRIBUTION.md).
