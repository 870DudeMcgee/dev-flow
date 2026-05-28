# Dev-Flow Token Optimization Guidelines

This document outlines the context-discipline policies and strategies for all Dev-Flow agents. Adhering to these rules keeps token usage minimal, avoids transcript bloat, and maximizes execution safety.

## 1. Search Before Reading

* **Principle**: Targeted search is vastly cheaper and faster than reading entire files.
* **Practice**: Always use search tools (e.g., `rg`, `grep_search`), symbol queries, or other nearest available search utilities first.
* **Constraint**: Never read a full file (e.g., loading hundreds of lines) when a targeted search or symbol lookup would answer your question.

## 2. Summarize Before Expanding

* **Principle**: Check lightweight projections before loading raw source files.
* **Practice**: First read high-level status summaries:
  1. `task.yaml` (canonical task identity and status)
  2. `summary.json` (latest cached state)
  3. `events.jsonl` (chronological action logs)
* **Constraint**: Only open implementation code if high-level files prove insufficient.

## 3. Role-Bounded Context

Context boundaries are strictly dictated by your current agent role:

| Role | Permitted Context | Primary Objective |
| :--- | :--- | :--- |
| **Planner** | North Star, MVP contract, constraints, current diff | Assess feasibility, design minimal slices, write plans |
| **Writer / Implementer** | Task packet, target files, directly related tests | Implement code, write isolated unit tests, verify changes |
| **Reviewer** | Plan, final diff, verification logs, adjacent tests | Inspect diff correctness, assess risks, verify code paths |
| **Debugger / Repair** | Latest failure trace, touched files, target test file | Analyze root cause, apply narrow patch, rerun tests |

## 4. Transcript Compression

* Do not restate complete files or full plans in the conversation log.
* Avoid pasting long test outputs or full passing logs.
* Never copy-paste unchanged code when editing a file; use precise line replacements or minimal diffs.
* Conclude every task slice or role swap with the canonical token-optimized handoff format.

## DevMode Relationship

DevMode is the master engineering workflow. Token optimization is one always-on budget discipline inside DevMode, not the whole workflow.

DevMode combines:

* `using-superpowers` as the baseline execution discipline.
* Matt Pocock engineering skills as routed escalation modes.
* `skills/token-optimization/` as the shared context-budget package.
* Dev-Flow project rules as the repo-specific operating contract.

Do not eagerly load every skill. Route to specialized skills only when the task clearly needs them.

## Silent Work Mode

DevMode must run silently across VS Code and Antigravity.

Agents use Superpowers, Matt Pocock skills, token optimization, and Dev-Flow rules internally. They must not narrate that workflow.

Do not produce progress narration unless the user explicitly asks for a live walkthrough.

Avoid phrases like:

* "I'll..."
* "I'm going to..."
* "I'm reading..."
* "I'm checking..."
* "Let me..."
* "Good..."
* "Actually..."
* "Now I..."
* "Starting..."
* "Completed..."
* "The plan is..."

Agent messages are allowed only for:

* a blocking question
* the final result
* a verification failure
* a risk that changes the next safe action

Default final response:

```text
Decision:
Files changed:
Verification:
Risks:
Next safe action:
```

When `/devmode` is invoked, print exactly one activation line before silent work:

```text
DevMode loaded: token optimization, repo discipline, read-only/implementation gating.
```

Do not print a skills-used line.

Include inspected files only when the user explicitly asks for them or when they are necessary evidence.

## Command Support Matrix

The active VS Code entry point is DevMode. DevMode keeps token optimization lightweight and always available without requiring agents to invoke the full token-optimization skill by default. The matrix below documents which tools support true slash commands, prompt files, skills, or repo-level instructions.

## VS Code Copilot

[.github/copilot-instructions.md](../.github/copilot-instructions.md) is the always-on lightweight DevMode rule. [.github/prompts/devmode.prompt.md](../.github/prompts/devmode.prompt.md) is the manual `/devmode` reusable prompt entrypoint. [.github/skills/devmode/SKILL.md](../.github/skills/devmode/SKILL.md) is the project-local DevMode skill/router.

The canonical shared token-optimization package remains at [skills/token-optimization/](../skills/token-optimization/). DevMode may consult it when a task has real context-bloat risk, but the default path is DevMode plus Superpowers-style discipline.

Superpowers and Matt Pocock skills are currently available from the local/user skill installs, not vendored into this repo's `.github/skills/` folder. The routed skill names are `using-superpowers`, `improve-codebase-architecture`, `grill-with-docs`, and `caveman`.

In VS Code Copilot Chat, run `/devmode` or use the prompt/reusable prompt UI. If the prompt does not appear, make sure the repo root is open. If working from a subfolder, enable `chat.useCustomizationsInParentRepositories`.

Recommended VS Code settings:

```json
{
  "chat.useAgentsMdFile": true,
  "chat.includeReferencedInstructions": true,
  "chat.includeApplyingInstructions": true,
  "chat.promptFiles": true,
  "chat.promptFilesRecommendations": true,
  "chat.useCustomizationsInParentRepositories": true
}
```

Use Chat diagnostics or `Chat: Open Customizations` to verify VS Code discovered the DevMode prompt file.

| Tool/Platform | Command/Prompt Interface | Integration Strategy |
| :--- | :--- | :--- |
| **Claude Code** | `/token-optimization` | Supported via [.claude/commands/token-optimization.md](.claude/commands/token-optimization.md) |
| **Gemini CLI** | `/token-optimization` | Supported via [.gemini/commands/token-optimization.toml](.gemini/commands/token-optimization.toml) |
| **VS Code Copilot** | `/devmode` or select `.github/prompts/devmode.prompt.md` | Supported via [.github/copilot-instructions.md](../.github/copilot-instructions.md), [.github/prompts/devmode.prompt.md](../.github/prompts/devmode.prompt.md), and [.github/skills/devmode/SKILL.md](../.github/skills/devmode/SKILL.md) |
| **Antigravity IDE** | `/devmode` | Closest-supported prompt/rule mechanism via [.agent/workflows/devmode.md](../.agent/workflows/devmode.md), [.agent/rules/devmode-token-first.md](../.agent/rules/devmode-token-first.md), [.antigravity/workflows/devmode.md](../.antigravity/workflows/devmode.md), and [.antigravity/rules.md](../.antigravity/rules.md) |
| **ChatGPT Web** | No custom command support | Enforce manually by pointing the model to [skills/token-optimization/SKILL.md](skills/token-optimization/SKILL.md) |

## Skills, Rules, and Workflows in Antigravity

It is crucial to understand how Antigravity integrates slash commands, rules, and behavior policies:
* **DevMode** is the master engineering workflow and operational baseline.
* **Token Optimization** is one always-on budget discipline inside the DevMode master workflow.
* **Antigravity manual command**: `/devmode` (triggered via the manual workflow file `.agent/workflows/devmode.md`, with `.antigravity/workflows/devmode.md` as the closest native workflow copy)
* **Antigravity always-on rule**: `.agent/rules/devmode-token-first.md`
* **Shared token-optimization package**: `skills/token-optimization/` acts strictly as low-level behavior reference material and is never loaded eagerly by default to avoid token bloat.
* **Limitation**: Antigravity does not visibly load reusable Superpowers-style skill files here; DevMode is enforced through prompt/rule workflow files.

## VS Code Skill Routing

The repo-local DevMode skill lives at `.github/skills/devmode/SKILL.md`. It routes to installed skills by name instead of copying their full instructions into every request.

Current routed skills:

* `using-superpowers`: baseline disciplined execution.
* `improve-codebase-architecture`: architecture, coupling, refactor, and codebase health work.
* `grill-with-docs`: plan/spec/docs/assumption alignment.
* `caveman`: simplification when a solution is overbuilt.
* `token-optimization`: context budget and transcript discipline.

Copy selected external skills into `.github/skills/` only when the repo needs portable team-shared skill definitions. Until then, keep the local/user installs as the source for Superpowers and Matt Pocock skills.

## Disabled VS Code Token Prompt

The old VS Code `/token-optimization` prompt is disabled at `.github/prompts-disabled/token-optimization.prompt.md`. Keep it as historical reference only. Do not restore it unless VS Code needs a separate token-optimization command again.
