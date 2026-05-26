# devflow

devflow is a conservative, file-based runner for AI-generated unified diffs.

The MVP does not call LLM providers. Codex, VS Code/Cline, Antigravity, a local model, or a human can write a unified diff into a task file; devflow validates it, previews it, applies it only with explicit approval, verifies it, rolls back on failure, and writes a report.

## Core Commands

```bash
devflow init
devflow status
devflow task claim .devflow/tasks/001_example.md --agent codex --lock codex-desktop
devflow task status .devflow/tasks/001_example.md
devflow task release .devflow/tasks/001_example.md
devflow run .devflow/tasks/001_example.md
devflow run .devflow/tasks/001_example.md --yes
```

When running from source without an editable install:

```bash
PYTHONPATH=src python3 -m devflow --help
```

## Safety Contract

- Task Markdown is the canonical task status source.
- `plan.json` status mirroring is best-effort.
- `devflow run <task>` previews only and writes `PREVIEWED`.
- `devflow run <task> --yes` applies the patch after validation.
- The git worktree must be clean before devflow mutates task, report, or source state.
- Protected paths block before apply.
- `Allowed Files` accepts exact paths, glob patterns, and `...` shorthand.
- Failed verification rolls source changes back to checkpoint state.

## Task Format

Patch content lives in a fenced `diff` block:

````markdown
# Task: 001 - Update Sample
Status: PENDING
Plan: 001.plan.json
Assigned Agent: codex
Owner Lock: codex-desktop
Risk: LOW
Branch: devflow/task-001-codex
Touched Files:
- sample.txt

## 1. Objective
Update sample text.

## 2. Allowed Files
- sample.txt

## 3. Do Not Touch
- .env

## 4. Required Context
sample.txt contains hello.

## 5. Implementation Instructions
Apply the diff.

## 6. Patch Protocol
Unified diff.

## 7. Verification Commands
- true

## 8. Failure Handling
None.

## 9. Execution Results
```diff
diff --git a/sample.txt b/sample.txt
--- a/sample.txt
+++ b/sample.txt
@@ -1 +1 @@
-hello
+hello world
```

## 10. Final Report
Pending.
````

## Quickstart

Start from a clean git repo:

```bash
PYTHONPATH=src python3 -m devflow init
```

Create a task in `.devflow/tasks/`, then commit it before running:

```bash
git add .devflow
git commit -m "add devflow task"
```

Preview the patch:

```bash
PYTHONPATH=src python3 -m devflow run .devflow/tasks/001_example.md
```

Preview writes `.devflow` task/report/plan metadata. Inspect those files, then either commit them as a preview checkpoint or reset them before applying:

```bash
git status
git add .devflow
git commit -m "preview devflow task 001"
```

Apply from a clean worktree:

```bash
PYTHONPATH=src python3 -m devflow run .devflow/tasks/001_example.md --yes
```

For direct apply without a separate preview checkpoint, run `--yes` from the clean task state.

## Task Ownership

Peer orchestrators should claim tasks before editing their task files or touched-file scope:

```bash
PYTHONPATH=src python3 -m devflow task claim .devflow/tasks/001_example.md \
  --agent codex \
  --lock codex-desktop \
  --touch src/devflow/cli.py \
  --touch tests/test_cli.py
```

Inspect a single task:

```bash
PYTHONPATH=src python3 -m devflow task status .devflow/tasks/001_example.md
```

Release a task back to the shared queue:

```bash
PYTHONPATH=src python3 -m devflow task release .devflow/tasks/001_example.md
```

Claim refuses `CLAIMED` and `RUNNING` tasks unless `--force` is provided.

## Verify

```bash
PYTHONPATH=src python3 -m unittest discover -s tests -q
```

Current note: this local Python environment has a `pip`/`pyexpat` issue that blocks verifying `pip install -e .`; use `PYTHONPATH=src` until the Python toolchain is healthy.

## Multi-Orchestrator Model

Codex Desktop, VS Code/Cline, and Antigravity are peer orchestrators. Each can run a complete internal dev team with local model workers. Work is divided by claimed task and touched-file scope, not by permanent IDE role.

See:

- `docs/workflows/coordination-playbook.md`
- `docs/plans/2026-05-26-devflow-mvp-authoritative-spec.md`
- `docs/plans/2026-05-26-devflow-end-to-end-goal.md`
