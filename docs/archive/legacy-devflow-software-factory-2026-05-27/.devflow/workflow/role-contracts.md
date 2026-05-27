# Devflow Role Contracts

## Philosophy

Roles are capabilities, not identities. Any orchestrator (Codex, VS Code/Copilot, Antigravity) can assume any role. The role contract defines what context is received, what actions are allowed, and what outputs are required.

---

## Planner

**Purpose:** Convert goals into task packets and dependency-ready plans.

**Receives:**
- User goal or feature request
- Repo summary / repo map
- Constraints and protected paths

**Rules:**
- No code edits.
- Keep context small — prefer repo maps over file contents.
- Output a task packet with acceptance criteria.
- Identify risk tier and verification commands.
- Split large tasks into bounded subtasks.

**Produces:**
- Task packet in `.devflow/tasks/<id>.md`
- Optional plan in `.devflow/plans/<id>.plan.json`

---

## Implementer

**Purpose:** Implement one task from a packet with minimal mutation.

**Receives:**
- Task packet
- Relevant implementation files
- Relevant existing tests
- Context pack (`devflow context build <task> --role implementer`)

**Rules:**
- Only touch files in the allowed paths.
- Emit minimal unified diff.
- No unrelated cleanup.
- No dependency changes unless approved.
- No protected file changes unless approved.
- Stop if required files are outside allowed paths.
- Preserve public API unless task explicitly says otherwise.

**Produces:**
- Unified diff in the task packet's `## 9. Execution Results` block
- Diff result artifact conforming to `diff-result.schema.json`

---

## Tester

**Purpose:** Write or identify tests that validate the task's behavior changes.

**Receives:**
- Task packet
- Implementation diff or target files
- Existing test files near the target code
- Test fixtures

**Rules:**
- Prefer red/green: write a failing test first, then confirm it passes after implementation.
- Keep test changes scoped to the task.
- Avoid broad test rewrites.
- If no test is practical, explain why.

**Produces:**
- Test file additions or modifications
- Verification commands to run

---

## Reviewer

**Purpose:** Review diffs against the task contract. Be strict.

**Receives:**
- Task packet
- Final diff
- Verification result
- Context pack (`devflow context build <task> --role reviewer`)

**Rules:**
- Check for task compliance, scope creep, protected files, missing tests, unsafe changes.
- Blocking findings for: scope creep, missing verification, protected file changes, unsafe mutations.
- Non-blocking findings for: style, naming, documentation.
- Do not mutate the task's files — produce a review result only.

**Produces:**
- Review result conforming to `review-result.schema.json`

---

## Repair Agent

**Purpose:** Fix failed verification with the smallest possible change.

**Receives:**
- Latest failure summary (not full log)
- Current diff
- Touched files only

**Rules:**
- Read only failure summary, current diff, and touched files.
- Make the smallest possible repair.
- Do not redesign or refactor.
- Stop after repair budget is exhausted (respect `failure_taxonomy` retry limits in `config.json`).
- Classify the failure type before attempting repair.

**Produces:**
- Repair diff
- Updated verification result
- Failure classification

---

## Local Model Worker

**Purpose:** Execute bounded subtasks delegated by an orchestrator.

**Receives:**
- Specific subtask prompt from the orchestrator
- Bounded file context

**Rules:**
- Workers are subagents, not orchestrators.
- Workers must not mutate repo state directly.
- All outputs flow back through the owning orchestrator and `devflow run` safety gates.
- Workers may help with: patch drafting, test generation, failure explanation, small repair loops, summarization.

**Produces:**
- Proposed text (diff, test, summary) returned to the orchestrator for validation.
