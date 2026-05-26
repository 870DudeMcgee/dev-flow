# Hello Peer Orchestrator (Codex Desktop)

Date: 2026-05-26
Status: ACTIVE
Scope: Codex Desktop orchestrator with local Qwen worker subagents on Mac Studio

## 1. What Is devflow?

`devflow` is a file-based, safe coordination and execution plane for AI-generated code changes.

Instead of agents silently editing files in the workspace, all work is structured as canonical task files containing fenced unified diff blocks.

- **Coordination Surface**: Shared repo and `.devflow/`
- **Safety Surface**: Git checkpoint branches, clean-worktree gating, local verification commands
- **Orchestration Model**: Peer orchestration. Codex Desktop acts as a first-class peer orchestrator, running in parallel with VS Code and Antigravity.

---

## 2. Core Safety Rules

1. **Task Claiming is Mandatory**: Claim the task before modifying codebase files or task patch blocks.
2. **Clean Worktree Guard**: The git worktree must be clean before `devflow run` preview/apply mutation steps.
3. **Task-Based Patching**: Write changes as unified diff in Section 9 of the task file and let `devflow` safely apply and verify.

---

## 3. Codex Task Lifecycle

### Step A: Claim Task
Claim the task file using the `devflow` CLI:
```bash
PYTHONPATH=src python3 -m devflow task claim .devflow/tasks/<task_file>.md --agent codex --lock codex-desktop-session
```
*Note: Commit the task file change immediately to keep your git worktree clean.*

### Step B: Draft Code Patches
- Use local Qwen workers on `http://127.0.0.1:11434` (optimal `studio` profile maps to `qwen2.5-coder:32b-instruct`) for quick, high-turn drafting and syntax checking.
- Write final changes as a unified diff inside the Section 9 fenced `diff` block.
- Commit task markdown updates to keep the worktree clean.

### Step C: Dry-Run and Preview
Execute a dry-run to validate diff format, allowed path rules, and protected path constraints:
```bash
PYTHONPATH=src python3 -m devflow run .devflow/tasks/<task_file>.md
```
*Note: This generates a PREVIEWED report/status and does not apply any changes to source files.*

### Step D: Zero-Trust Apply and Verify
Apply the patch and run full verification suites:
```bash
PYTHONPATH=src python3 -m devflow run .devflow/tasks/<task_file>.md --yes
```
*Note: This creates a checkpoint branch, applies the patch, executes unit verification, rolls back to clean checkpoint on failure, and compiles a comprehensive audit report.*

---

## 4. Workspace Map

- `.devflow/config.json`: Enforceable machine policy (protected paths, checkpoint strategy, retry budgets)
- `.devflow/constitution.md`: Human-facing operating principles
- `.devflow/plans/`: Coordination plans
- `.devflow/tasks/`: Canonical executable tasks
- `.devflow/reports/`: Run audit logs
- `scripts/local_agent_runner.py`: Local Qwen worker helper

---

## 5. Orchestrator & Worker Configuration on Mac Studio

On the Mac Studio, Codex runs in the following peer configuration:
* **Orchestrator Lane**: Codex Desktop — handles planning, policy gating, dry-runs, and final reviews.
* **Worker Subagent Lane**: Local `qwen2.5-coder:32b-instruct` — handles high-fidelity coding drafts and test-repair loops.
