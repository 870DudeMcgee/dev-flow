# devflow Agentic Control Plane Implementation Plan

Date: 2026-05-27
Status: DRAFT EXECUTION PLAN
Spec: docs/superpowers/specs/2026-05-27-devflow-agentic-control-plane-spec.md
Workflow: Superpowers-style execution plan

## 1. Purpose

This plan turns the agentic control plane spec into a sequence of small, testable implementation phases. It is the working source of truth for building devflow from a deterministic task/diff runner into a universal agent harness.

The plan should be used to test future work against the source-of-truth spec before implementation, during review, and before completion.

## 2. Scope

In scope:

- artifact kernel
- artifact metadata and lineage
- context pack builder
- repo maps
- review-only local worker adapter
- schema validation for worker outputs
- diff-only implementer path
- failure classification and repair worker path
- TDD state transitions
- task DAG metadata
- traces and eval fixtures
- documentation and handoff updates

Out of scope for the first implementation wave:

- auto-merge
- auto-release
- dashboard UI
- cloud provider routing in the deterministic path
- embedding service dependency
- direct worker repo mutation
- unconstrained agent-to-agent communication

## 3. Global Acceptance Criteria

Every phase must preserve these rules:

1. Local and cloud workers produce artifacts only.
2. Only devflow preview/apply/verify/report may mutate repository state.
3. All code-changing worker output is represented as unified diff artifacts.
4. Artifacts are schema validated before use.
5. Artifacts record provenance and lineage.
6. Context packs bound worker input.
7. Risk tier and policy determine gates.
8. Verification evidence is required before completion.
9. Reports remain sufficient for another orchestrator to audit or continue the task.
10. Existing MVP behavior remains backward compatible unless explicitly changed by a task.

## 4. Verification Baseline

Primary test command:

```bash
.venv/bin/python -m unittest discover -s tests -q
```

Fallback source-path command:

```bash
PYTHONPATH=src python3 -m unittest discover -s tests -q
```

Doc-only changes should at minimum pass:

```bash
git diff --check
```

## 5. Phase 0 - Source-of-Truth Alignment

Goal: establish the spec and this plan as active references for future work.

Files:

- docs/superpowers/specs/2026-05-27-devflow-agentic-control-plane-spec.md
- docs/plans/2026-05-27-devflow-agentic-control-plane-implementation-plan.md
- docs/roadmap.md
- docs/agent-handoff.md
- README.md

Tasks:

1. Add 30,000-foot source-of-truth spec.
2. Add this implementation plan.
3. Cross-link spec and plan from roadmap, handoff, and README.
4. Verify no formatting or whitespace errors.

Acceptance:

- spec states north star, five planes, artifacts, context packs, governance, roles, risk, TDD states, and first slice
- plan states phases, exact paths, tests, rollback notes, and acceptance criteria
- project docs identify the new spec and plan as the next strategic source of truth

Verification:

```bash
git diff --check
```

Rollback:

- remove the two new docs and revert README/roadmap/handoff links

## 6. Phase 1 - Artifact Kernel

Goal: make every future worker output inspectable and replayable.

Files:

- src/devflow/artifacts.py
- src/devflow/cli.py
- src/devflow/schemas/artifact.schema.json
- tests/test_artifacts.py
- README.md
- docs/agent-handoff.md

Tasks:

1. Define an ArtifactMetadata structure with artifact_id, task_id, artifact_type, created_at, repo_head, input_hash, output_hash, parent_artifacts, metadata, verification_status, and apply_status.
2. Add deterministic artifact ID generation with timestamp plus short hash.
3. Add artifact writer that stores metadata and body under `.devflow/artifacts/<task_id>/`.
4. Add artifact list and inspect helpers.
5. Add CLI commands:
   - `devflow artifact list <task-id>`
   - `devflow artifact inspect <artifact-id-or-path>`
6. Add tests for artifact write/read/list/inspect and hash stability.

Acceptance:

- artifact metadata and body can be written without mutating source files
- artifact body hash matches metadata output_hash
- artifact list is stable and sorted
- inspect prints metadata and body location

Verification:

```bash
.venv/bin/python -m unittest tests.test_artifacts -q
.venv/bin/python -m unittest discover -s tests -q
```

Rollback:

- remove artifact module, schema, tests, CLI command wiring, and generated `.devflow/artifacts/` test fixtures if any

## 7. Phase 2 - Context Pack Compiler

Goal: stop workers from reading random repo context.

Files:

- src/devflow/context.py
- src/devflow/repo_map.py
- src/devflow/cli.py
- tests/test_context.py
- tests/test_repo_map.py
- docs/agent-handoff.md

Tasks:

1. Define context pack metadata and section structures.
2. Build a simple repo map from file tree, Python symbols, imports, and tests.
3. Create `.devflow/context/repo-map.short.md`.
4. Create `.devflow/context/repo-map.symbols.json`.
5. Create `.devflow/context/repo-map.deps.json`.
6. Add context pack builder for a task and role using allowed files, touched files, task text, latest artifacts, and repo map entries.
7. Add CLI commands:
   - `devflow context refresh`
   - `devflow context build <task-file> --role <role>`
   - `devflow context inspect <context-pack-id-or-path>`

Acceptance:

- context pack includes task contract, allowed paths, role, token budget estimate, and selected sections
- context pack does not include files outside allowed/context paths unless explicitly requested by task metadata
- repo maps are deterministic enough for tests

Verification:

```bash
.venv/bin/python -m unittest tests.test_context tests.test_repo_map -q
.venv/bin/python -m unittest discover -s tests -q
```

Rollback:

- remove context/repo map modules, tests, CLI wiring, and generated `.devflow/context/` files

## 8. Phase 3 - Review-Only Worker Adapter

Goal: prove local agent harness value without mutation risk.

Files:

- src/devflow/agents/__init__.py
- src/devflow/agents/profiles.py
- src/devflow/agents/ollama.py
- src/devflow/agents/runner.py
- src/devflow/agents/schemas.py
- src/devflow/schemas/review_result.schema.json
- src/devflow/cli.py
- tests/test_agents.py
- tests/test_agent_review.py
- docs/workflows/local-worker-health-check-runbook.md
- docs/agent-handoff.md

Tasks:

1. Define role profile loader for `reviewer`.
2. Define model profile resolution with graceful fallback when preferred model is missing.
3. Add Ollama adapter using existing local runner behavior but returning structured invocation results.
4. Build reviewer prompt from task plus context pack.
5. Require review output schema:
   - status
   - summary
   - findings
   - required_actions
   - confidence
   - blocked_reason when blocked
6. Write review result as artifact.
7. Add CLI command:
   - `devflow agent review <task-file> --profile <profile>`
8. Tests should mock model invocation and validate schema behavior.

Acceptance:

- review-only command can run with mocked adapter
- invalid JSON or invalid schema creates blocked artifact, not a crash
- no source files are mutated by worker output
- unavailable preferred model reports fallback or blocked status clearly

Verification:

```bash
.venv/bin/python -m unittest tests.test_agents tests.test_agent_review -q
.venv/bin/python -m unittest discover -s tests -q
```

Rollback:

- remove agents package, schemas, tests, CLI command wiring, and generated review artifacts

## 9. Phase 4 - Diff-Only Implementer

Goal: allow local workers to propose code changes while preserving devflow as mutation authority.

Files:

- src/devflow/agents/runner.py
- src/devflow/agents/schemas.py
- src/devflow/schemas/diff_result.schema.json
- src/devflow/runner.py
- src/devflow/safety.py
- src/devflow/cli.py
- tests/test_agent_implement.py
- tests/test_runner.py
- tests/test_safety.py
- docs/agent-handoff.md

Tasks:

1. Define diff_result schema with status, artifact_type, diff, touched_paths, notes, risk, confidence, and blocked fields.
2. Add implementer role profile.
3. Validate returned diff parses as unified diff.
4. Validate touched_paths are inside task allowed files.
5. Validate protected paths are not touched.
5.1 Implement a static safety scanner in `src/devflow/safety.py`:
    - Scan the diff for hardcoded secret keywords (`secret`, `token`, `password`).
    - Scan for execution hazards (`subprocess` with `shell=True`, `eval(`, `exec(`).
    - Scan for destructive file/folder removals outside allowed paths.
    - Block and output a `BLOCKED` artifact if any safety audit fails.
6. Store implementation diff as artifact.
7. Add CLI command:
   - `devflow agent implement <task-file> --emit-diff`
   - `devflow guard scan-diff <artifact-id-or-path>` (CLI subcommand to manually audit a diff)
8. Do not automatically insert or apply the diff to task markdown in the first slice.

Acceptance:

- valid diff artifact is written and inspectable
- out-of-scope diff becomes blocked artifact
- protected path diff becomes blocked artifact
- static safety scanner correctly intercepts and blocks diff additions containing hardcoded tokens, Popen shell execution, or unconstrained file deletions
- source tree remains unchanged until a human/orchestrator routes the diff through `devflow run`

Verification:

```bash
.venv/bin/python -m unittest tests.test_agent_implement -q
.venv/bin/python -m unittest discover -s tests -q
```

Rollback:

- remove implementer role wiring, diff schema, tests, and generated artifacts

## 10. Phase 5 - Failure Classification and Repair Worker

Goal: make repair loops small, bounded, and evidence-driven.

Files:

- src/devflow/failures.py
- src/devflow/agents/runner.py
- src/devflow/schemas/failure_result.schema.json
- src/devflow/schemas/repair_result.schema.json
- src/devflow/cli.py
- tests/test_failures.py
- tests/test_agent_repair.py
- docs/agent-handoff.md

Tasks:

1. Extract current failure classification from runner into a richer failure module.
2. Add failure_result artifact schema.
3. Add repair role profiles for syntax, import, test, lint, and generic repair.
4. Add routing from failure type to repair role.
5. Add max repair loop budget.
6. Add CLI command:
   - `devflow agent repair <task-file> --max-loops <n>`
7. Ensure environment failures and protected path failures stop instead of invoking repair.

Acceptance:

- failure log can be classified into compact failure artifact
- repair worker receives failure artifact and relevant diff/snippets only
- repair output is a diff artifact and remains unapplied
- budget exhaustion creates blocked artifact

Verification:

```bash
.venv/bin/python -m unittest tests.test_failures tests.test_agent_repair -q
.venv/bin/python -m unittest discover -s tests -q
```

Rollback:

- remove failure module, repair role wiring, schemas, tests, CLI command, and generated artifacts

## 11. Phase 6 - TDD State Machine

Goal: enforce red/green/refactor/report as task state.

Files:

- src/devflow/states.py
- src/devflow/manager.py
- src/devflow/cli.py
- tests/test_states.py
- tests/test_manager.py
- docs/agent-handoff.md

Tasks:

1. Define TDD state enum and allowed transitions.
2. Add transition records with timestamp, reason, and artifact ID.
3. Support structured verification recipes parsed from config or task metadata:
    - Execute red, green, regression, and lint steps as separate subprocess runs.
    - Validate `expected: fail` rules by confirming non-zero exit codes.
    - Confirm expected failure message matches the `failure_must_contain` regex.
    - Validate `expected: pass` rules by asserting zero exit codes.
    - Support graceful linter degradation when linter is missing but `optional_if_missing` is true.
4. Add CLI command:
   - `devflow task transition <task-file> --to <state> --reason <reason> --artifact <id>`
5. Add TDD-oriented status output showing the active verification step results.

Acceptance:

- invalid transitions are rejected
- transitions preserve current MVP status compatibility
- verification recipes execute deterministically, correctly validating TDD red failures and green passes
- transition evidence is visible in task status or report

Verification:

```bash
.venv/bin/python -m unittest tests.test_states -q
.venv/bin/python -m unittest discover -s tests -q
```

Rollback:

- remove state module, transition command, tests, and task metadata changes

## 12. Phase 7 - Task DAG and Impact Analysis

Goal: make planning and parallel orchestration safer.

Files:

- src/devflow/dag.py
- src/devflow/impact.py
- src/devflow/cli.py
- tests/test_dag.py
- tests/test_impact.py
- docs/agent-handoff.md

Tasks:

1. Define DAG JSON schema for task dependencies.
2. Add ready/blocked/next task queries.
3. Add simple impact analysis using allowed paths, touched files, imports, test names, and recent git history.
4. Add CLI commands:
   - `devflow task ready --json`
   - `devflow task next --agent <agent>`
   - `devflow task graph`
   - `devflow impact <task-file>`

Acceptance:

- next task selection only returns unblocked dependency-ready tasks
- impact output lists likely files, verification targets, public interfaces, risk, and suggested split
- DAG remains optional and backward compatible with existing task files

Verification:

```bash
.venv/bin/python -m unittest tests.test_dag tests.test_impact -q
.venv/bin/python -m unittest discover -s tests -q
```

Rollback:

- remove DAG/impact modules, tests, CLI wiring, and generated DAG fixtures

## 13. Phase 8 - Traces and Evals

Goal: improve the harness based on evidence.

Files:

- src/devflow/traces.py
- src/devflow/evals.py
- src/devflow/cli.py
- tests/test_traces.py
- tests/test_evals.py
- .devflow/evals/README.md
- docs/agent-handoff.md

Tasks:

1. Add trace span writer for context retrieval, model invocation, schema validation, diff validation, verification, and policy decisions.
2. Add eval fixture format for role harness behavior.
3. Add CLI commands:
   - `devflow trace list`
   - `devflow trace inspect <trace-id>`
   - `devflow eval run --role <role>`
   - `devflow eval compare --prompt <a> --prompt <b>`
4. Add seed evals for implementer allowed paths, reviewer scope creep, and repair minimality.

Acceptance:

- traces can be written and inspected for mocked worker runs
- evals can run deterministically without live model calls
- eval failures identify role, prompt version, fixture, and assertion

Verification:

```bash
.venv/bin/python -m unittest tests.test_traces tests.test_evals -q
.venv/bin/python -m unittest discover -s tests -q
```

Rollback:

- remove trace/eval modules, tests, CLI wiring, and generated eval fixtures

## 14. Phase 9 - Worktree-Native Parallelism

Goal: isolate substantial agent tasks by default.

Files:

- src/devflow/worktrees.py
- src/devflow/cli.py
- tests/test_worktrees.py
- docs/workflows/coordination-playbook.md
- docs/agent-handoff.md

Tasks:

1. Add worktree metadata structure for task, branch, path, base SHA, and owner.
2. Add CLI commands:
   - `devflow worktree create <task-file> --agent <agent>`
   - `devflow worktree status`
   - `devflow worktree remove <task-file> --keep-artifacts`
3. Add integration guard proposal for future `devflow integrate <task-file>`.

Acceptance:

- worktree creation is explicit and does not replace current branch-based checkpoint behavior
- substantial parallel tasks can be isolated without changing existing run behavior
- artifacts remain in the main coordination surface or are copied back safely

Verification:

```bash
.venv/bin/python -m unittest tests.test_worktrees -q
.venv/bin/python -m unittest discover -s tests -q
```

Rollback:

- remove worktree module, tests, CLI wiring, and created test worktrees

## 15. Phase 10 - Memory Invalidation Engine

Goal: manage and invalidate architectural memory deterministically.

Files:

- src/devflow/memory.py
- src/devflow/cli.py
- tests/test_memory.py
- docs/agent-handoff.md

Tasks:

1. Define `MemoryRecord` structure with evidence, confidence, last_validated, and `invalidated_by_paths`.
2. Implement memory JSON validation and local storage under `.devflow/memory/`.
3. Add a post-apply listener in `devflow run` that checks touched paths in the applied diff against active memory `invalidated_by_paths`:
    - Evict matching memories or stale them by setting confidence to `0.0` and status to `stale`.
4. Add CLI commands:
   - `devflow memory list`
   - `devflow memory add --type <type> --statement <statement> --evidence <evidence> --invalidate-on <paths>`
   - `devflow memory inspect <id>`

Acceptance:

- memory records are written and retrieved successfully
- applying a diff that touches a path listed in `invalidated_by_paths` immediately and deterministically flags the memory as `stale`
- stale memories are excluded from generated context packs

Verification:

```bash
.venv/bin/python -m unittest tests.test_memory -q
.venv/bin/python -m unittest discover -s tests -q
```

Rollback:

- remove memory module, tests, CLI wiring, and generated memory records

## 16. Documentation Tasks For Every Phase

Each implementation phase must update, where relevant:

- README.md
- docs/agent-handoff.md
- docs/roadmap.md
- docs/workflows/coordination-playbook.md

Acceptance:

- current command surface is documented
- current source-of-truth spec and plan are linked
- verified test command/result is updated
- known limitations and next step are recorded

## 17. Review Checklist For Every Phase

Before marking any phase complete, answer:

1. Which source-of-truth spec acceptance criteria does this phase satisfy?
2. Which files were intentionally touched?
3. Which risk tier applies?
4. Which worker, if any, generated artifacts?
5. Are all artifacts schema-valid?
6. Did any diff touch paths outside task scope?
7. Which deterministic checks passed?
8. Is rollback straightforward?
9. What remains blocked or intentionally deferred?

## 18. First Recommended Implementation Task

Task title:

- Phase 1 artifact kernel

Initial allowed files:

- src/devflow/artifacts.py
- src/devflow/cli.py
- src/devflow/schemas/artifact.schema.json
- tests/test_artifacts.py
- README.md
- docs/agent-handoff.md
- docs/roadmap.md

Initial verification:

```bash
.venv/bin/python -m unittest tests.test_artifacts -q
.venv/bin/python -m unittest discover -s tests -q
```

Reason:

The artifact kernel gives devflow durable memory, replayability, provenance, and auditability before it asks any local agent to produce code. It is the smallest valuable foundation for the whole architecture.
