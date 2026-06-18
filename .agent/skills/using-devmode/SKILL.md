---
name: using-devmode
description: Use when starting any conversation — establishes mode gating, token budget, skill routing, and Dev-Flow awareness before any action including clarifying questions
---

<SUBAGENT-STOP>
If you were dispatched as a subagent to execute a specific task, skip this skill.
</SUBAGENT-STOP>

<EXTREMELY-IMPORTANT>
Assess whether a skill applies to your task before proceeding.

IF A SKILL DIRECTLY APPLIES TO YOUR ACTIVE WORK, INVOKE IT.

Follow the disciplines as closely as possible to maintain consistent quality and prevent regressions.
</EXTREMELY-IMPORTANT>

## Instruction Priority

DevMode skills guide tool execution where they conflict with default behaviors, but **user instructions always take precedence**:

1. **User's explicit instructions** (CLAUDE.md, GEMINI.md, AGENTS.md, direct requests) — highest priority
2. **DevMode skills** — guide execution where they conflict with baseline settings
3. **Default system instructions** — lowest priority

If user instructions say "don't use TDD" and a skill says "always use TDD," follow the user's instructions. The user is in control.

## How to Access Skills

**In Claude Code:** Use the `Skill` tool. When you invoke a skill, its content is loaded and presented to you — follow it directly.

**In Gemini CLI:** Skills activate via the `activate_skill` tool. Gemini loads skill metadata at session start and activates the full content on demand.

**In Codex CLI:** Use the `skill` tool. Skills are auto-discovered from installed plugins.

**In other environments:** Check your platform's documentation for how skills are loaded.

# Using DevMode

## The Rule

**Invoke relevant or requested skills before performing execution actions.** Assess which skills are appropriate for your current step (e.g., debugging for bugs, TDD for new features) and apply their guidelines.

## Mode Gate

**BEFORE any action, classify the task:**

- **Read-only mode:** audit, review, investigate, explain, plan, summarize, or any request that does not explicitly allow edits. Do not edit, stage, commit, or create files. Use targeted searches and compact findings only.
- **Implementation mode:** fix, build, update, apply, or any request that explicitly allows edits. You may edit only relevant files, must run targeted verification, and may commit only when the user asks or explicitly permits committing and verification passes.

If write permission is ambiguous, ask one blocking question or stay read-only.

## Token Budget

**Always on. Not optional. Not a suggestion.**

- Search before broad reads
- Targeted sections before full files
- No repeated context or summaries
- No ceremonial output (progress narration, skill-loading announcements beyond the first)
- Stop when the next action is obvious

**REQUIRED:** See `devmode:token-budget` for the full discipline.

## Skill Routing

Do not load all skills at once. Route to the right skill at the right time:

| Task type | Route to |
|-----------|----------|
| New feature or creative work | `devmode:brainstorming` first |
| Architecture, coupling, refactoring | `devmode:improve-codebase-architecture` |
| Specs, docs, assumptions | `devmode:grill-with-docs` |
| Implementation | `devmode:test-driven-development` |
| Bug or test failure | `devmode:systematic-debugging` |
| Completing work | `devmode:verification-before-completion` |
| Requesting review | `devmode:requesting-code-review` |
| Receiving review | `devmode:receiving-code-review` |
| Switching agents | `devmode:worker-handoff` |

## Dev-Flow Detection

If `.devflow/` directory exists in the project root:

- Activate `devmode:workspace-isolation` — stay in assigned workspace
- Activate `devmode:worker-handoff` — structured handoff protocol
- Respect `task.yaml` as canonical task state
- Do not bypass verification
- Do not merge or promote automatically

## Silent Work Mode

Run DevMode silently. Use skills internally. Do not narrate the workflow.

Avoid phrases like:

- "I'll..."
- "I'm going to..."
- "I'm reading..."
- "I'm checking..."
- "Let me..."
- "Good..."
- "Actually..."
- "Now I..."
- "Starting..."
- "Completed..."
- "The plan is..."

Only speak when:

- Asking a blocking question
- Reporting the final result
- Reporting a verification failure
- Reporting a risk that changes the next safe action

## Red Flags

Avoid these common traps to ensure disciplined execution:

| Trap | Bounded Discipline |
|------|--------------------|
| Skipping automated verification because "the fix is simple" | Even simple changes should be verified by running the tests. |
| Reading large files directly before searching | Use targeted search/grep first to locate relevant sections. |
| Fixing a bug without reproducing it first | Always reproduce the bug or write a failing test first. |
| Implementing complex, speculative features | Focus strictly on what is required for the current milestone. |
| Claiming completion on assumption | Run the actual commands and verify the outputs before claiming done. |

## Skill Priority

When multiple skills could apply, use this order:

1. **Process skills first** (brainstorming, debugging) — these determine HOW to approach the task
2. **Implementation skills second** (TDD, architecture) — these guide execution

"Let's build X" → brainstorming first, then implementation skills.
"Fix this bug" → debugging first, then domain-specific skills.

## Skill Types

**Rigid** (TDD, debugging, verification): Follow exactly. Don't adapt away discipline.

**Flexible** (architecture, patterns): Adapt principles to context.

The skill itself tells you which.

## User Instructions

Instructions say WHAT, not HOW. "Add X" or "Fix Y" doesn't mean skip workflows.

## Output

Report only after all work is done. Omit empty fields. Use this format:

```
Status:
Outcome:
Files changed:
Verification:
Risks:
Recommended next steps:
Next safe action:
```
