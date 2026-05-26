# Agent Handoff

Date: 2026-05-26

## Current Canonical Target

Use docs/plans/2026-05-26-devflow-mvp-authoritative-spec.md as the single MVP source of truth.

Use docs/workflows/coordination-playbook.md as the active coordination topology.

Codex Desktop is currently taking lead on coordination reset, document normalization, gap analysis, and next-task sequencing.

## Implementation Scope

In scope:
- devflow init
- devflow status
- devflow task claim <task-file> --agent <owner> --lock <session>
- devflow task new <task-id> <title>
- devflow task release <task-file>
- devflow task status <task-file>
- devflow run <task-file> previews and writes PREVIEWED status/report
- devflow run <task-file> --yes applies, verifies, and writes final status/report
- unified diff apply + dry-run
- protected-file gating
- clean-worktree gating before run mutation
- checkpoint branch creation
- verification auto-detect/config override
- failure classification + retry budgets
- rollback on failure
- task report generation

Current coordination focus:
- synthesis and gap analysis
- task sequencing
- coordination documentation
- explicit ownership assignment per task
- peer-orchestrator handoffs where each IDE can execute a full task end-to-end

Out of scope for MVP:
- planning command
- DAG execution
- semantic indexing
- model routing engine
- AST editing protocol
- dashboard

## Critical Rules

- Unified diff only for patch protocol.
- `devflow run` previews by default.
- `--yes` is required to apply a patch.
- The git worktree must be clean before `devflow run` mutates task/report/code state.
- Protected path touches require human approval before apply.
- config.json is enforceable policy.
- constitution.md is advisory.
- Codex, VS Code/Cline, and Antigravity are peer orchestrators.
- Local models are worker subagents for all orchestrators.
- Do not assign permanent global roles like "Codex only plans" or "VS Code only codes".
- Before modifying code, claim a task or receive direct human instruction for the file scope.
- A claimed task may be completed end-to-end by any orchestrator and its local subagent team.

## Verified Current State

Verification command:

```bash
PYTHONPATH=src python3 -m unittest discover -s tests -q
```

Current result:
- 24 tests pass with `unittest`
- `pytest` is not installed in the current Python or `.venv`
- package metadata now exists, but local `pip` is blocked by a Python/pyexpat runtime issue before project install begins
- until editable install is verified on a healthy Python, tests still use `PYTHONPATH=src`

## Immediate Gap Queue

No open MVP stabilization gaps remain in the current queue, aside from verifying editable install on a healthy Python toolchain.

Completed stabilization items:
- package metadata and `devflow` console entrypoint declared in `pyproject.toml`
- `python -m devflow` entrypoint added
- task ownership metadata parsed and reported: `Assigned Agent`, `Owner Lock`, `Branch`, `Touched Files`
- `devflow status` counts CLAIMED tasks
- `devflow run` previews by default and requires `--yes` to apply
- dirty worktrees are blocked before run mutation
- `Allowed Files` supports exact paths, glob patterns, and `...` shorthand
- default config is conservative MVP policy: no active orchestrator/provider routing, `auto` verification, clean-worktree required, no auto-apply
- failed verification rolls source changes back to checkpoint state before writing FAILED task/report state
- plan JSON mirrors task status best-effort when the referenced plan exists
- task claim/release/status commands are available for peer-orchestrator ownership
- task new scaffolds canonical task Markdown
- `devflow init` creates peer orchestrator templates and local model worker policy in `.devflow/orchestrators/`
- reports include status transitions, safety decisions, and verification output snippets
