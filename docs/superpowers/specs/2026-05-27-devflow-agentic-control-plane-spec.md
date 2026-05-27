# devflow Agentic Control Plane Spec

Date: 2026-05-27
Status: DRAFT SOURCE OF TRUTH
Workflow: Superpowers-style goal -> spec -> implementation plan -> testable execution

## 1. 30,000 Foot Goal

devflow should become the deterministic control plane that lets any coding agent work inside the same repository safely, cheaply, and measurably.

Supported actors include Codex, Claude Code, Copilot, Cline, Antigravity, OpenCode, local Ollama models, humans, and future tools. devflow is not the AI coworker. devflow is the Git-and-artifact-native harness that defines the task, limits context, routes bounded workers, validates outputs, gates mutations, verifies results, rolls back failures, and records the audit trail.

The north star is agentic CI/CD for software engineering:

- AI workers produce artifacts, not trusted decisions.
- Orchestrators own intent, judgment, and task coordination.
- devflow owns deterministic policy, validation, mutation, verification, rollback, reports, and provenance.
- Every completed task must be replayable, reviewable, and testable against explicit evidence.

## 2. Core Thesis

The winning architecture is thin orchestration over fat artifacts.

A worker invocation must always have:

- a role
- a tiny input packet
- a strict output schema
- no direct write access
- a token and time budget
- a confidence field
- a failure or blocked field
- provenance metadata
- deterministic validation before any mutation path

Local and cloud models are untrusted proposal engines. devflow is the trusted control plane.

## 3. System Planes

### 3.1 Intent Plane

Captures goals, specs, human decisions, product direction, and architectural tradeoffs.

Primary artifacts:

- goal documents
- design specs
- decision records
- open questions
- acceptance criteria

### 3.2 Planning Plane

Turns approved intent into executable work.

Primary artifacts:

- plan JSON
- task markdown
- task DAGs
- ownership locks
- dependency metadata
- risk tiers
- verification recipes

### 3.3 Context Plane

Controls what each worker is allowed to know.

Primary artifacts:

- repo maps
- symbol maps
- dependency maps
- context packs
- retrieved snippets
- project, task, and failure memory

### 3.4 Execution Plane

Runs bounded worker jobs and deterministic verification loops.

Primary artifacts:

- prompts
- model responses
- test diffs
- implementation diffs
- repair diffs
- verification logs
- review results

### 3.5 Governance Plane

Decides whether work is trusted enough to apply or complete.

Primary artifacts:

- schemas
- risk policy
- capability permissions
- budgets
- hooks
- traces
- evals
- reports
- rollback records

## 4. Inviolable Control-Plane Rules

1. Task markdown remains canonical task state.
2. Plan JSON and DAG indexes are secondary mirrors.
3. Local workers must not mutate repository state directly.
4. Worker output that changes code must become a unified diff artifact.
5. Only devflow may preview, apply, verify, rollback, and report mutations.
6. Every worker invocation must produce a schema-validated artifact or a blocked result.
7. Every artifact must record provenance metadata.
8. Every task completion must cite deterministic evidence.
9. Reviewer models may block completion, but may not be the sole oracle of correctness.
10. Risk tier and autonomy level must determine required gates.

## 5. Artifact Supply Chain

Every agent output is treated like a build artifact.

Minimum artifact metadata:

```json
{
  "artifact_id": "art_20260527_153012_8f3c",
  "artifact_type": "implementation.diff",
  "task_id": "T-042",
  "role": "implementer",
  "agent_profile": "local-quality",
  "model": "qwen2.5-coder:14b",
  "prompt_version": "implementer@0.1.0",
  "schema_version": "diff_result@0.1.0",
  "created_at": "2026-05-27T15:30:12-05:00",
  "repo_head": "abc123",
  "input_hash": "sha256:...",
  "output_hash": "sha256:...",
  "parent_artifacts": ["task:T-042"],
  "allowed_paths": ["src/devflow/runner.py"],
  "touched_paths": ["src/devflow/runner.py"],
  "risk": "medium",
  "confidence": 0.72,
  "verification_status": "not_run",
  "apply_status": "not_applied"
}
```

Artifact storage shape:

```text
.devflow/artifacts/
  T-042/
    001-task.snapshot.md
    002-context-pack.json
    003-reviewer.prompt.txt
    004-review.json
    005-implementer.prompt.txt
    006-implementation.diff
    007-verification.log
    008-final-report.md
```

Required capabilities:

- inspect one artifact
- list artifacts for a task
- show artifact graph for a task
- replay a worker invocation with a different model or prompt version later

## 6. Task DAG

Task files are still canonical, but planning must support dependency graphs.

Minimum DAG node fields:

```json
{
  "id": "T-002",
  "type": "task",
  "title": "Implement Ollama adapter",
  "depends_on": ["T-001"],
  "produces": ["ollama_adapter"],
  "requires": ["agent_profile_schema"],
  "invalidates": ["worker_adapter_docs"],
  "risk": "medium"
}
```

Required commands over time:

- `devflow task next --agent <agent>`
- `devflow task ready --json`
- `devflow task graph`
- `devflow task blocked`
- `devflow task critical-path`

## 7. Context Engineering

Every worker invocation must go through:

```text
task -> retrieval -> context pack -> model -> schema validation -> artifact
```

It must not go through:

```text
task -> model randomly reads repo -> maybe useful output
```

Context pack metadata:

```json
{
  "context_pack_id": "ctx_T-042_repair_002",
  "task_id": "T-042",
  "role": "repair-test",
  "token_budget": 3500,
  "sections": [
    {"name": "task_contract", "tokens": 420, "source": ".devflow/tasks/T-042.md"},
    {"name": "latest_failure", "tokens": 900, "source": ".devflow/artifacts/T-042/verification.log"},
    {"name": "relevant_diff", "tokens": 600, "source": ".devflow/artifacts/T-042/implementation.diff"},
    {"name": "file_snippets", "tokens": 1200, "source": "src/devflow/runner.py"},
    {"name": "project_memory", "tokens": 300, "source": ".devflow/memory/retrieved.json"}
  ]
}
```

Context selection should score candidates by path relevance, symbol relevance, recent edit relevance, dependency relevance, failure relevance, memory relevance, token cost, and staleness.

## 8. Repo Maps

The Context Plane should maintain three map resolutions:

```text
.devflow/context/repo-map.short.md
.devflow/context/repo-map.symbols.json
.devflow/context/repo-map.deps.json
```

Short maps help humans and small models. Symbol maps help targeted retrieval. Dependency maps help impact analysis and test selection.

## 9. Roles

### 9.1 Core Roles

- cartographer: builds repo maps and context packs
- planner: converts approved design into DAG tasks
- test_writer: emits failing test diffs
- implementer: emits minimal implementation diffs
- repair: emits small repair diffs based on classified failures
- reviewer: emits structured review results
- summarizer: compresses logs and updates reports

### 9.2 Triggered Specialist Roles

- api_contract_reviewer
- security_reviewer
- migration_reviewer
- performance_reviewer
- docs_syncer
- ux_reviewer
- release_manager

Specialists must be routed deterministically by touched paths, diff contents, task risk, and artifact type. They should reduce context bloat, not create a standing committee.

## 10. Worker Capability Permissions

Profiles define what a worker may request. The harness enforces the limits.

Example:

```yaml
id: repair-test
model_profile: local_fast
permissions:
  read_files: true
  write_files: false
  emit_diff: true
  run_commands: false
  network: false
  read_secrets: false
  modify_protected_paths: false
  request_more_context: true
limits:
  max_input_tokens: 4000
  max_output_tokens: 1800
  max_runtime_seconds: 90
  max_diff_lines: 120
  max_files_touched: 2
```

## 11. Risk Tiers

Risk tiers determine gates.

- low: docs, tests, comments, isolated pure functions
- medium: CLI behavior, core modules, config parsing
- high: subprocess, filesystem mutation, network, auth, secrets, CI, git operations
- critical: releases, publishing, credentials, destructive operations

High and critical risk work requires specialist or human approval before completion.

## 12. TDD State Machine

TDD should be state, not vibes.

Required states over time:

```text
PENDING -> CLAIMED -> CONTEXT_READY -> TEST_PROPOSED -> TEST_PREVIEWED -> TEST_APPLIED -> RED_CONFIRMED -> IMPLEMENTATION_PROPOSED -> IMPLEMENTATION_PREVIEWED -> GREEN_ATTEMPTED -> GREEN_CONFIRMED -> REVIEWED -> COMPLETED
```

Allowed failure branch:

```text
GREEN_ATTEMPTED -> REPAIRING -> GREEN_CONFIRMED | BLOCKED
```

Every state transition must cite timestamp, reason, and artifact evidence.

## 13. Failure Classification

Before repair, devflow should classify failure output into a compact artifact.

Initial taxonomy:

- syntax_error
- import_error
- type_error
- test_assertion
- snapshot_mismatch
- lint_format
- lint_static
- missing_dependency
- environment_failure
- timeout
- flaky_test
- protected_path_violation
- schema_validation_failure
- diff_apply_failure
- unknown

Environment failures and protected path violations must stop rather than trigger speculative repair.

## 14. Verification Recipes

Tasks should support structured verification recipes rather than only single command strings. A recipe organizes verification into named phases to drive the TDD state machine cleanly.

### 14.1 Recipe Structure
```yaml
verification:
  red:
    command: ".venv/bin/python -m unittest tests.test_agents -q"
    expected: fail
    failure_must_contain: "AgentProfile"
  green:
    command: ".venv/bin/python -m unittest tests.test_agents -q"
    expected: pass
  regression:
    command: ".venv/bin/python -m unittest discover -s tests -q"
    expected: pass
  lint:
    command: "ruff check src tests"
    expected: pass
    optional_if_missing: true
```

### 14.2 Execution Phase Behaviors
1. **RED Confirmation:** Evaluates the `red` command and confirms the test failed exactly as expected (non-zero exit code plus matching pattern). This triggers transition to `RED_CONFIRMED`.
2. **GREEN Verification:** Evaluates the `green` command. It must pass (zero exit code) before moving to `GREEN_CONFIRMED`.
3. **REGRESSION Safety:** Runs the broad test suite to verify no other features were broken.
4. **LINT Verification:** Enforces formatting and static analysis rules. If `optional_if_missing` is true, the stage degrades gracefully if tools are not found in the path.

## 15. Oracle Hierarchy

Correctness evidence is ranked:

1. deterministic tests
2. type checker or linter
3. schema validator
4. static analyzer
5. golden file or snapshot
6. human acceptance criteria
7. reviewer model
8. implementer self-assessment

Only the first six can mark work complete. Reviewer models may block completion.

## 16. Hooks

Hook events should make non-deterministic workers repeatable.

Initial events:

- TaskCreated
- TaskClaimed
- ContextPackCreated
- AgentStarted
- AgentCompleted
- ArtifactCreated
- DiffPreviewed
- DiffRejected
- BeforeApply
- AfterApply
- VerificationStarted
- VerificationFailed
- VerificationPassed
- RollbackStarted
- RollbackCompleted
- TaskCompleted
- MemoryExtracted

## 17. Memory

Memory is deliberate evidence, not magic.

### 17.1 Types of Memory
- **Project memory:** stable architecture facts, commands, and conventions.
- **Task memory:** discoveries during a specific task execution.
- **Failure memory:** recurring bugs, flaky tests, and repair lessons.

### 17.2 Deterministic Invalidation Rules
To prevent memory from becoming stale hallucination fuel, every memory entry must enforce active invalidation bounds:
1. **Source File Mapping:** Every memory entry must declare `invalidated_by_paths` (a list of exact file paths or glob patterns).
2. **Commit-Time Eviction:** When a git commit or `devflow run` apply mutates files matching a memory's `invalidated_by_paths`, the system must automatically flag that memory record as `stale` and set its `confidence` to `0.0`.
3. **Verification Contradiction:** If a verification command contradicts an active memory assertion, the memory must be evicted immediately.
4. **Human/Reviewer Flagging:** Human developers or reviewer models can explicitly mark a memory artifact as `invalidated`. Stale memories must be excluded from context packs.

## 18. Autonomy Levels

Default autonomy should be conservative.

- level 0 manual: no apply, no command execution
- level 1 preview: generate artifacts and preview diffs only
- level 2 safe_apply: apply low-risk work with gates; require approval for medium/high
- level 3 worktree_autonomous: apply and repair inside an isolated worktree
- level 4 pr_autonomous: open PRs but require human merge
- level 5 danger_zone: merge or release only by explicit configuration

## 19. Budgets

Budgets must include more than tokens.

Track:

- max model calls
- max repair loops
- max wall time
- max changed files
- max diff lines
- max test runtime
- max context tokens
- max output tokens

Budget exhaustion creates a blocked artifact with recommended escalation.

## 20. Model Routing

Model routing is capability based, not model-name based.

Profiles:

- local_fast: classification, summarization, syntax repair, log compression
- local_quality: implementation, test writing, local review
- cloud_frontier: architecture, ambiguous design, high-risk review

The current repo may use Ollama and qwen profiles, but the architecture must allow model swaps through config.

## 21. Workflow Profiles

Superpowers should be supported as a workflow profile, not hardcoded as the only process.

Candidate profiles:

- superpowers: brainstorming, design review, planning, worktree, TDD, review, finish
- hotfix: reproduce, minimal fix, targeted verify, review, complete
- refactor: characterization tests, mechanical change, behavior verify, cleanup, review
- spike: isolate worktree, prototype, report, discard or promote

## 22. Worktree-Native Parallelism

Parallel agents should use isolated worktrees when tasks are substantial.

Task metadata should track:

```yaml
worktree:
  path: .devflow/worktrees/T-042
  branch: devflow/T-042/agent-codex
  base_sha: abc123
  owner: codex
```

Integration should run conflict checks, full verification, artifact graph checks, review gates, and report generation.

## 23. Review Contract

Reviews must be structured and severity-based.

Minimum review result:

```json
{
  "status": "changes_requested",
  "summary": "Implementation changes CLI output outside task scope.",
  "findings": [
    {
      "severity": "blocking",
      "category": "scope",
      "file": "src/devflow/__main__.py",
      "line": 88,
      "message": "CLI output changed outside acceptance criteria.",
      "suggested_fix": "Move output formatting change to a separate task."
    }
  ],
  "required_actions": ["Revert unrelated CLI output change."]
}
```

Blocking findings prevent task completion until resolved or explicitly waived by a human.

## 24. Evals and Traces

devflow should improve its harness through evidence.

Evals should test role behavior:

- implementer respects allowed paths
- implementer avoids unrelated cleanup
- reviewer catches scope creep
- reviewer catches missing tests
- repair fixes import errors without rewriting everything

Traces should capture context retrieval, model invocation, schema validation, diff validation, verification, repair loops, and policy decisions.

## 25. Source-of-Truth Acceptance Criteria

Future implementation should be tested against this spec by asking:

1. Does this feature keep models as proposal engines and devflow as the mutation authority?
2. Does every worker output become a schema-validated artifact?
3. Does every artifact record provenance, lineage, hashes, role, model, prompt version, and schema version?
4. Does every model invocation use a bounded context pack?
5. Does every mutation flow through unified diff preview/apply/verify/report?
6. Does every completion cite deterministic evidence from the oracle hierarchy?
7. Does the system degrade safely when a model, schema, context pack, or verification step fails?
8. Does the feature improve replayability, auditability, or measurable harness quality?

## 26. Non-Goals For The First Implementation Wave

- fully autonomous multi-agent coding
- auto-merge or auto-release
- live dashboard UI
- embedding-heavy semantic retrieval as a required dependency
- cloud provider routing in the deterministic MVP path
- direct worker file mutation
- unconstrained agent-to-agent chat

## 27. Recommended First Slice

Build `devflow agent review <task>` first.

Why:

- exercises task parsing
- exercises context pack creation
- exercises model invocation
- exercises schema validation
- exercises artifact writing
- exercises policy decision output
- avoids code mutation risk

Then add diff-only implementer, repair worker, TDD state machine, DAG routing, traces, and evals.

## 28. Adversarial Safety Checks

To protect local environments and ensure developer security, the Governance Plane must enforce deterministic static diff scanning prior to human preview or apply execution.

### 28.1 Safety Violation Audits
Every worker-generated unified diff must be parsed and audited against safety heuristics:
1. **Secrets Scanner:** Block additions matching entropy patterns or containing keywords like `key`, `secret`, `token`, `password`, or `credential`.
2. **Execution Hazards:** Scan for subprocess invocation variants (`subprocess.Popen`, `subprocess.call`) with `shell=True`, `eval(`, `exec(`, or direct socket bindings.
3. **Destructive Hazards:** Scan for unconstrained file deletion patterns (`shutil.rmtree`, `os.remove`, `os.unlink`) sweeping folders outside the task's allowed files.
4. **Credential Paths:** Scan for reads on sensitive directories (`/etc/`, `~/.ssh/`, `~/.aws/`).

### 28.2 Enforcement Policy
If any safety check triggers a violation:
- The system must immediately **block** execution.
- The mutation is **discarded**.
- A `BLOCKED` artifact is written detailing the violation severity, and a report is compiled for human governance escalation. No code is ever applied.

