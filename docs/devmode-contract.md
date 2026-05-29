# DevMode Contract

## Purpose

The DevMode Contract serves as the canonical source of truth for disciplined, token-efficient, and workspace-safe software engineering practices. By defining clear operational gates and a systematic violation recovery protocol, it establishes a reliable baseline for development across multiple environments.

---

## Instruction Priority

DevMode provides repo-level operational guidelines, but **higher-level system and user directives always outrank DevMode repo instructions**:
1. **Platform, System, Developer, and Safety Rules**: High-level constraints, safety limits, model policies, and system parameters occupy the highest priority. DevMode must not tell agents to ignore safety, platform, developer, or system constraints.
2. **Explicit User Instructions**: Direct requests, workspace settings, project instructions, or session overrides from the user outrank DevMode rules.
3. **Repository Instructions**: This contract, `AGENTS.md`, and specific skills provide the baseline operational guidelines only inside the host tool's allowed instruction hierarchy.

---

## The Four Gates

DevMode structures all software development into four structural gates:

```text
DevMode = Mode + Context + Change + Verification
```

### 1. Mode Gate

**Classify the task before acting.**
- Identify whether the current request is an **Investigation** (read-only audit, context gathering, planning) or a **Mutation** (editing code, writing tests, applying bug fixes).
- Maintain strict boundaries: do not make edits during investigative phases, and do not perform broad context scans during implementation phases.

### 2. Context Gate

**Search before broad reads.**
- Treat full-file reads as resource leaks.
- Always use targeted search (grep/ripgrep) to locate specific symbols, functions, or lines before opening a file.
- Inspect only the minimum necessary line ranges required for the task.

### 3. Change Gate

**Isolate edits and choose the right workflow.**
- Keep all modifications minimal, focused, and isolated to a single vertical slice.
- Choose the correct workflow or skill before editing (e.g., TDD for mutations, planning workflows for multi-step tasks).
- Never make changes directly in a shared environment without a clean, isolated worktree or branch boundary.

### 4. Verification Gate

**Provide fresh evidence before claiming completion.**
- Never assert success without running the actual verification commands (e.g., tests, linters, builds).
- Capture and report the actual outputs/logs as concrete evidence.

---

## Violation Recovery

If you realize a rule, gate, or discipline has been violated, execute the following **Operational Recovery Protocol** immediately:

1. **Stop**: Halt current execution immediately. Do not commit or push the non-compliant state.
2. **Preserve the worktree and evidence**: Do not destructively delete files or wipe state to recover from confusion. Keep all evidence and git history intact.
3. **Report what happened**: Verbally document and report the specific deviation in the chat.
4. **Identify the safest next action**: Determine the safest, non-destructive way to return to compliance (such as moving untested code to a backup file, writing the missing tests, and re-implementing).
5. **Continue only with verification or explicit user direction**: Do not proceed until you have verified the recovery action or received explicit direction from the user.

---

## Handoff Requirement

Every task completion report, shift handoff, or status update must be returned strictly in the following format:

```markdown
## Status

[complete | in-progress | blocked | needs-review | failed]

## Files Changed

- path/to/file (summary of changes)

## Verification

- `command run`: pass/fail + actual output logs

## Risks

- Specific technical risks, limitations, or potential side-effects

## Next Safe Action

- The single, concrete next action to take
```

---

## What DevMode Is Not

DevMode is designed strictly as a portable discipline layer for agentic coding. It is NOT:
- A coding agent
- A runtime framework
- A model router
- An autonomous task system
- Dev-Flow
- A replacement for human review
