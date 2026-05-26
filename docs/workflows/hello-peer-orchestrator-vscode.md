# Hello Peer Orchestrator (VS Code/Copilot)

Date: 2026-05-26
Status: ACTIVE
Scope: VS Code/Copilot orchestrator with local qwen worker subagents

Default rule for this workspace: peer-parallel orchestration. Use this VS Code/Copilot workflow whenever VS Code claims a task or is delegated a task by the human.

## 1. What Is devflow?

devflow is a file-based, safe coordination and execution plane for AI-generated code changes.

Instead of agents silently editing files in the workspace, all work is structured as canonical task files containing fenced unified diff blocks.

- Coordination Surface: shared repo and `.devflow/`
- Safety Surface: git checkpoint branches, clean-worktree gating, local verification commands
- Orchestration Model: no IDE is permanently planner/coder; each IDE runs a full-stack subagent team and claims tasks

## 2. Core Safety Rules

1. Task claiming is mandatory before modifying codebase files or task patch blocks.
2. Git worktree must be clean before `devflow run` preview/apply mutation steps.
3. For task execution, write changes as unified diff in section 9 and let devflow apply/verify.

## 3. VS Code/Copilot Task Lifecycle

### Step A: Claim Task

```bash
PYTHONPATH=src python3 -m devflow task claim .devflow/tasks/002_marketing_page.md --agent vscode --lock vscode-copilot-session
```

Commit the claim update immediately to keep worktree clean.

### Step B: Implement and Draft Diffs

- Use local qwen workers on `http://127.0.0.1:11434` for bounded coding/test suggestions.
- Write final changes as unified diff inside section 9 fenced `diff` block.
- Commit task markdown updates to keep worktree clean.

### Step C: Validate and Preview

```bash
PYTHONPATH=src python3 -m devflow run .devflow/tasks/002_marketing_page.md
```

This validates and previews only, writes PREVIEWED status/report, and does not apply source changes.

Commit preview status/report metadata before apply.

### Step D: Apply and Verify

```bash
PYTHONPATH=src python3 -m devflow run .devflow/tasks/002_marketing_page.md --yes
```

This creates checkpoint branch, applies patch, runs verification commands, rolls back on verification failure, and writes final report.

## 4. Workspace Map

- `.devflow/config.json`: enforceable policy (protected paths, checkpoint strategy, retry budgets)
- `.devflow/constitution.md`: advisory operating guidance
- `.devflow/plans/`: coordination plans
- `.devflow/tasks/`: canonical executable tasks
- `.devflow/reports/`: run audit logs
- `scripts/local_agent_runner.py`: local qwen model query helper

## 5. Orchestrator and Worker Roles

- VS Code/Copilot: orchestrator lane (target profile: GPT-5.5-high or nearest available high-reasoning profile)
- qwen local models: full worker subagent team lane
  - planner
  - coder
  - reviewer
  - tester
  - summarizer

Local workers propose artifacts; devflow remains the deterministic safety/apply/verify path.
