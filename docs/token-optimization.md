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

## Command Support Matrix

The `/token-optimization` command behaves as a real reusable command surface across IDEs and agent platforms. The matrix below documents which tools support true slash commands, which support prompt files, and which only support repo-level instructions:

| Tool/Platform | Command/Prompt Interface | Integration Strategy |
| :--- | :--- | :--- |
| **Claude Code** | `/token-optimization` | Supported via [.claude/commands/token-optimization.md](.claude/commands/token-optimization.md) |
| **Gemini CLI** | `/token-optimization` | Supported via [.gemini/commands/token-optimization.toml](.gemini/commands/token-optimization.toml) |
| **VS Code Copilot** | Select `.github/prompts/token-optimization.prompt.md` | Supported via [.github/prompts/token-optimization.prompt.md](.github/prompts/token-optimization.prompt.md) |
| **Antigravity IDE** | Auto-triggered via rules | Supported via [.antigravity/rules.md](.antigravity/rules.md) |
| **ChatGPT Web** | No custom command support | Enforce manually by pointing the model to [skills/token-optimization/SKILL.md](skills/token-optimization/SKILL.md) |
