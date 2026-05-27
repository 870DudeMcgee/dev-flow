# Agent Handoff

Date: 2026-05-26

## Current Canonical Target

Use docs/superpowers/specs/2026-05-27-devflow-agentic-control-plane-spec.md as the strategic north-star source of truth for the next major architecture wave.

Use docs/plans/2026-05-27-devflow-agentic-control-plane-implementation-plan.md as the executable implementation source of truth for artifact kernel, context packs, review-only worker adapter, diff-only implementer, repair loops, TDD state machine, task DAGs, traces, evals, and worktree-native parallelism.

Use docs/plans/2026-05-26-devflow-mvp-authoritative-spec.md as the single MVP source of truth.

Use docs/workflows/coordination-playbook.md as the active coordination topology.

Use docs/plans/2026-05-26-local-ai-dev-team-integration-plan.md as the active integration execution blueprint.

Use docs/plans/2026-05-26-vscode-only-mac-mini-onboarding-plan.md as the machine onboarding source of truth for VS Code-only setup.

Use docs/workflows/vscode-only-machine-setup-log.md as the required evidence log for Mac mini onboarding.

GLOBAL RULE: VS Code/Copilot, Codex Desktop, and Antigravity are separate peer orchestrators and should run in parallel across different claimed tasks whenever useful.

Each orchestrator has its own local qwen worker dev team for coding, testing, repair loops, and summarization. Human direction assigns or reassigns task ownership as needed.

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
- devflow artifact list <task-id>
- devflow artifact inspect <artifact-id-or-path>
- devflow context refresh
- devflow context build <task-file> --role <role> [--budget <tokens>]
- devflow context inspect <artifact-id-or-path>
- devflow context list <task-id>
- devflow agent review <task-file> [--profile <profile>]
- unified diff apply + dry-run
- artifact metadata/body storage under .devflow/artifacts/<task-id>/
- artifact body hash verification on read
- deterministic repo maps under .devflow/context/
- context packs emitted as context-pack.json artifacts
- review-only worker outputs emitted as review.json artifacts
- review result schema validation before artifact write
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
- local worker connectivity standardization and proving-run design

Out of scope for MVP:
- planning command
- DAG execution
- semantic indexing
- model routing engine
- AST editing protocol
- dashboard

Next architecture wave, still gated by deterministic control-plane rules:
- artifact kernel and artifact graph
- bounded context packs and repo maps
- schema-validated local worker outputs
- review-only worker harness before mutation-producing workers
- diff-only implementer artifacts routed through `devflow run`
- failure classification and bounded repair loops
- TDD state transitions and verification recipes
- traces and evals for harness improvement

## Critical Rules

- Use peer-orchestrated devflow workflows. Each orchestrator executes only its claimed tasks unless ownership is explicitly transferred.
- Prefer local worker delegation before spending cloud-model turns on iterative coding, test-writing, repair, failure explanation, and summarization loops.
- Unified diff only for patch protocol.
- `devflow run` previews by default.
- `--yes` is required to apply a patch.
- The git worktree must be clean before `devflow run` mutates task/report/code state.
- Protected path touches require human approval before apply.
- config.json is enforceable policy.
- constitution.md is advisory.
- Codex, VS Code/Copilot, and Antigravity are peer orchestrators.
- Local models are worker subagents for all orchestrators.
- Local models must not mutate repo state directly; their output flows back through the owning orchestrator, task files, verification, and reports.
- Do not assign permanent global roles like "Codex only plans" or "VS Code only codes".
- Before modifying code, claim a task or receive direct human instruction for the file scope.
- A claimed task may be completed end-to-end by any orchestrator and its local subagent team.

## Verified Current State

Verification command:

```bash
.venv/bin/python -m unittest discover -s tests -q
```

Current result:
- 73 tests pass with `unittest`
- editable install works with Homebrew Python 3.12
- `.venv/bin/devflow --help` starts correctly
- source path also works with `PYTHONPATH=src python3 -m unittest discover -s tests -q`
- `pytest` is not installed in the current Python or `.venv`

## Local Machine Runtime Repair

Systematic-debugging facts captured on 2026-05-26:

- Reproduction before repair: Homebrew portable Ruby 4.0.5_1 and Homebrew Python 3.12 hung before `--version`; `syspolicyd` was pinned near 100% CPU.
- Security logs showed Gatekeeper/syspolicy assessment errors, including notarization check failures and `qtn_proc` initialization failures.
- Repair step: `sudo killall syspolicyd`; launchd relaunched it cleanly.
- Verification after restart: Homebrew Python 3.12 and portable Ruby 4.0.5_1 both print versions inside the bounded startup probe.
- Homebrew portable Ruby version was restored from temporary 4.0.4 pin to official 4.0.5_1; `brew --env` works and Homebrew no longer reports dirty.
- Remaining Python import failure was a `pyexpat` linkage mismatch: both Python 3.12 and 3.14 `pyexpat` extensions loaded `/usr/lib/libexpat.1.dylib` while requiring Homebrew Expat 2.8.1 symbols.
- Repair step: relink both `pyexpat` extension modules to `/opt/homebrew/opt/expat/lib/libexpat.1.dylib` with `install_name_tool`, then ad-hoc re-sign them with `codesign --force --sign -`.
- Fresh `.venv` site-packages files initially had the macOS `hidden` flag, causing Python to skip `__editable__.devflow-0.1.0.pth`; `chflags -R nohidden .venv` repaired editable imports.
- Verification after relink and hidden-flag repair: Python 3.12 and 3.14 can import `pyexpat`, editable install succeeds, 35 tests pass from `.venv`, and `.venv/bin/devflow --help` starts.

## Immediate Gap Queue

No open MVP stabilization gaps remain in the current queue.

New strategic implementation queue:
- Phase 4 diff-only implementer from docs/plans/2026-05-27-devflow-agentic-control-plane-implementation-plan.md
- keep local/cloud workers artifact-only; do not grant direct write access
- route implementation diffs through artifact validation before any `devflow run` mutation path

Next active queue:
- run VS Code/Copilot-only audit handoff against completed smoke report/task artifacts using docs/workflows/vscode-smoke-audit-handoff.md
- execute local worker preflight from docs/workflows/local-worker-health-check-runbook.md before any VS Code proving rerun
- execute VS Code-only Mac mini onboarding phases and capture evidence in docs/workflows/vscode-only-machine-setup-log.md

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
- artifact kernel implemented with metadata/body separation, stable hashes, lineage fields, and artifact list/inspect CLI commands
- context pack compiler implemented with deterministic repo maps, bounded file snippets, task-contract sections, test mappings, and context pack artifacts
- review-only worker adapter implemented with role profile loading, stateless Ollama invocation, schema validation, graceful blocked artifacts, and `devflow agent review`
- future model routing is documented as post-MVP only in `docs/future-model-routing.md`
- local worker health-check runbook exists in `docs/workflows/local-worker-health-check-runbook.md`
- smoke integration proving artifacts exist in `docs/examples/002_smoke_multi_agent.*`
- smoke proving run has been executed successfully in temp repo with final COMPLETED status and passing verification
- proving run surfaced and documented two operational edge cases: trailing blank-context patch extraction risk and same-second checkpoint branch naming collisions
- VS Code-specific smoke audit runbook exists in `docs/workflows/vscode-smoke-audit-handoff.md`
