# Agent Selection And Context Requirement Routing

Status: active architecture with Milestone 17 evidence-only routing implementation. This document does not enable autonomous routing, provider-backed worker execution, worker-owned verification, or promotion.

Dev-Flow should not choose agents by name first. It should classify the work, estimate the required context, ability, and risk, then route each role to the cheapest capable agent that can safely complete that role. This keeps Dev-Flow a control system: big-picture models decide direction, local and narrow models gather facts or execute bounded work, and Dev-Flow owns durable state, routing, isolation, evidence, verification, and promotion.

This design extends [agent-registry-and-adapter-runtime.md](agent-registry-and-adapter-runtime.md). Execution adapters remain bounded by the registry/manual/shell-alignment sequence and explicit human or dogfood invocation.

Milestone 17 promotes deterministic task-fit, scout, route, and routing-quality artifacts as derived evidence. The stable commands write evidence and recommend next commands only; humans or explicit dogfood lanes still invoke worker execution, verification, promotion, commit, push, and publication.

## 1. Core Loop

Routing has five steps:

1. Build a deterministic task-fit profile from the task description, declared scope, repo metadata, changed files, task history, and known project indexes.
2. Estimate context size before expensive planning.
3. Select the minimum context layer needed for each role.
4. Resolve eligible model capability profiles and pick the cheapest safe agent per role.
5. Record the routing decision, evidence, verification outcome, and post-run quality signal for future scoring.

Dev-Flow routes by role, not by personality:

- planner
- implementation worker
- reviewer
- verifier
- summarizer
- scout
- escalation judge

## 2. Task Fit Profile

Every routable task should receive a `task_fit` artifact before expensive planning. The profile is derived from deterministic metadata first, then optionally refined by cheap scout reports.

```yaml
task_fit:
  task_type: feature_implementation
  repo_scope: medium
  context_requirement: high
  reasoning_requirement: high
  code_edit_risk: medium
  architectural_risk: high
  verification_complexity: medium
  requires_big_picture: true
  requires_current_repo_state: true
  requires_historical_project_context: true
  context_layer: L4
  recommended_planner_tier: frontier
  recommended_worker_tier: strong_local_or_frontier
  recommended_reviewer_tier: frontier_or_specialized_local
  confidence: 0.76
```

Initial task-type vocabulary:

- `trivial_edit`
- `documentation_cleanup`
- `small_feature`
- `feature_implementation`
- `repo_refactor`
- `bug_fix`
- `test_repair`
- `architecture_change`
- `model_routing_change`
- `verification_only`
- `research_or_current_info`

Risk levels are `low`, `medium`, `high`, and `critical`. A `critical` architectural or routing risk always requires human-visible escalation evidence before worker assignment.

## 3. Deterministic Context Estimate

The context requirement estimator should run before model planning. It should inspect only bounded repo metadata, indexes, task artifacts, and selected file statistics.

```yaml
repo_scan:
  changed_files_count: 12
  relevant_files_count: 34
  relevant_lines_estimate: 4200
  relevant_tokens_estimate: 28000
  test_files_needed: 8
  docs_needed: 5
  task_history_tokens: 6000
  total_context_estimate: 39000
```

Recommended deterministic inputs:

- task title, description, acceptance criteria, and declared allowed files
- `git status --short`
- recent task events and verification summaries
- subsystem indexes and canonical docs
- file sizes and rough token estimates for relevant files
- test file count and expected verification command size

The estimator must distinguish advertised context from useful context. Model capability profiles store `useful_context_tokens` and `max_safe_context_tokens`; routing should prefer the useful value and treat the maximum as a hard ceiling, not a quality promise.

## 4. Context Layers

Every task receives a required context layer. Context layers control how much durable project memory may be loaded for a role.

| Layer | Includes | Example |
| --- | --- | --- |
| L0 | Task-only context | Fix typo |
| L1 | Task plus relevant files | Edit one helper |
| L2 | Task, relevant files, local subsystem docs | Add CLI flag |
| L3 | Task, subsystem docs, project architecture | Refactor task packet schema |
| L4 | Task, architecture, roadmap, past decisions | Design model routing system |
| L5 | Full strategic context and founder-level planning material | Decide future Dev-Flow architecture |

The planner may need L4 or L5. The implementation worker usually receives L1 or L2, even when the planner used L4. The reviewer receives the diff, task contract, acceptance criteria, and targeted architecture notes. The verifier receives commands, expected outputs, logs, and verification history.

## 5. Context Pack Builder

The Context Pack Builder is deterministic infrastructure, not an AI agent. It builds the smallest role-specific context pack that preserves the required big picture.

Responsibilities:

1. Read `task.yaml` and related task artifacts.
2. Resolve relevant project memory and subsystem indexes.
3. Resolve relevant repo files and tests.
4. Estimate token size.
5. Build candidate context packs by role.
6. Select the smallest pack that satisfies the required context layer.
7. Record included and excluded sources with estimated tokens.

Planner context pack:

```yaml
context_pack:
  role: planner
  context_layer: L4
  includes:
    - project/vision.md
    - project/architecture/current.md
    - project/decisions/agent-routing.md
    - repo-map.md
    - relevant-file-index.md
    - task.yaml
    - previous-related-tasks.md
  excludes:
    - full source files unless needed
    - archived docs
    - stale brainstorms
  estimated_tokens: 22000
```

Worker context pack:

```yaml
context_pack:
  role: implementation_worker
  context_layer: L2
  includes:
    - task.yaml
    - acceptance_criteria.md
    - selected source files
    - selected tests
    - local conventions
  estimated_tokens: 12000
```

The builder must keep stale, archived, rejected, and historical material out of active packs unless a human or policy explicitly requests it as non-authoritative context.

## 6. Model Capability Profiles

Agent selection uses capability profiles, not hard-coded vendor names.

Current implemented slice: `devflow agent discover-local --json` inventories installed Ollama models, parses `ollama show` manifests, and derives conservative local capability profiles. `devflow agent select-local <task-id> --role <role> --json` ranks installed registry agents for an explicit role and writes `.devflow/tasks/<task-id>/agent-selection.json`. This is selection evidence only: it does not autonomously route, run workers, create registry entries for unregistered models, apply patches, verify, promote, merge, push, or call remote providers.

```yaml
model_capability_profile:
  model_id: qwen3.6-27b-local
  provider: local
  strengths:
    - code_review
    - local_refactor
    - summarization
    - bounded_planning
  weaknesses:
    - very_large_architecture_planning
    - ambiguous_product_strategy
  useful_context_tokens: 32000
  max_safe_context_tokens: 48000
  cost_class: local
  latency_class: medium
  trust_level: experimental
  allowed_roles:
    - scout
    - summarizer
    - test_writer
    - bounded_worker
    - reviewer
  disallowed_roles:
    - final_architect
    - promotion_authority
```

```yaml
model_capability_profile:
  model_id: frontier-architecture-high
  provider: openai
  strengths:
    - architecture
    - complex_planning
    - large_context_reasoning
    - debugging
    - final_review
  useful_context_tokens: 128000
  max_safe_context_tokens: 192000
  cost_class: expensive
  latency_class: medium
  trust_level: high
  allowed_roles:
    - architect
    - planner
    - final_reviewer
    - complex_worker
    - escalation_judge
```

Profile fields should be updated from real outcomes. If a model repeatedly fails tasks above 32k useful tokens, Dev-Flow should lower that model's useful context estimate even if the provider advertises a larger window.

## 7. Routing Rules

Routing chooses a role assignment from task fit, context estimate, policy, and model capability.

```yaml
routing_rules:
  trivial_edit:
    planner: none_or_local
    worker: local
    reviewer: local
    verifier: deterministic
  small_feature:
    planner: local_or_frontier_low
    worker: local
    reviewer: local_or_frontier
    verifier: deterministic
  repo_refactor:
    planner: frontier
    worker: strong_local_or_frontier
    reviewer: frontier
    verifier: deterministic
  architecture_change:
    planner: frontier
    worker: frontier_or_supervised_local
    reviewer: frontier
    verifier: deterministic_plus_human
  documentation_cleanup:
    planner: local
    worker: local
    reviewer: local
    verifier: deterministic
  model_routing_change:
    planner: frontier
    worker: frontier
    reviewer: frontier
    verifier: deterministic_plus_human
```

`model_routing_change` is high leverage and high risk because it controls later work assignment. It must require frontier planning and review until Dev-Flow has enough scorecard evidence to relax the policy.

Routing output must be recorded:

```yaml
routing_decision:
  task_id: task-123
  policy_version: 1
  task_fit_profile_path: .devflow/tasks/task-123/task-fit.yaml
  selected:
    planner: openai-frontier-architect
    worker: qwen36-senior
    reviewer: frontier-code-reviewer
    verifier: deterministic-shell
  reason:
    - context estimate exceeds local-fast useful window
    - architectural risk is high
    - worker can receive bounded L2 implementation pack
  rejected:
    - agent: qwen-coder-fast
      reason: useful context below worker pack estimate
```

## 8. Scout Roles

Local models can gather routing signals without owning the plan. Scout outputs are evidence for the planner and router.

Initial scout roles:

- `repo_scope_scout`: identifies relevant files and subsystem roots.
- `risk_scout`: classifies code edit risk, architectural risk, and verification complexity.
- `context_scout`: estimates pack size and missing indexes.
- `test_scout`: identifies likely affected tests and verification commands.
- `stale_context_scout`: identifies archived, stale, or contradictory docs that must be excluded or rewritten.

Scout report:

```yaml
scout_report:
  role: repo_scope_scout
  relevant_files:
    - src/devflow/control_room/task.py
    - src/devflow/control_room/router.py
    - tests/test_agent_routing.py
  estimated_scope: medium
  likely_risks:
    - task schema migration
    - model profile compatibility
    - stale docs
  suggested_planner: frontier
  suggested_worker: local_possible_with_tight_context
  confidence: 0.72
```

Scout confidence is advisory. Dev-Flow should compare reports against deterministic estimates and post-run outcomes.

## 9. Filesystem Memory Indexes

Filesystem memory needs indexes so models do not rediscover project structure from scratch.

Recommended future structure:

```text
.devflow/
  memory/
    project_index.yaml
    architecture_index.yaml
    decision_index.yaml
    subsystem_index.yaml
    task_index.yaml
    model_capability_index.yaml
```

Subsystem index entry:

```yaml
subsystems:
  agent_routing:
    summary: Chooses models and agents based on task fit, context requirements, risk, and role.
    canonical_docs:
      - docs/architecture/agent-selection-and-context-routing.md
      - docs/architecture/agent-registry-and-adapter-runtime.md
    source_roots:
      - src/devflow/control_room/
    tests:
      - tests/test_agent_registry.py
      - tests/test_task_packet.py
    related_decisions:
      - .devflow/layers/architecture/decisions.jsonl
```

Indexes are routing aids, not authority. Canonical task state, project docs, and verification evidence remain the source of truth.

## 10. Feedback Loop

Routing quality must be measured after execution:

- Did the assigned agent finish without boundary violations?
- Did verification pass on the first run?
- Was frontier escalation needed after local failure?
- Did the context pack omit required files?
- Did the agent exceed useful context or latency expectations?
- Did review find architectural or safety mistakes?
- How much cost was avoided compared with frontier-only routing?

Metrics should update a model scorecard without granting autonomy automatically. Higher autonomy requires explicit policy changes, not just a good score.

## 11. Activation Sequence

Milestone 17 activates this capability as evidence-only routing after the registry and adapter-runtime foundations:

1. Keep the shell-worker control-room contract stable.
2. Load declarative agent and model capability registries.
3. Add read-only `agent list`, `agent show`, and `agent packet`.
4. Add manual packet adapter.
5. Align shell adapter with the registry contract.
6. Implement deterministic context estimates and task-fit profiles as derived `task fit` artifacts.
7. Implement role-based context pack evidence through `agent context-pack`.
8. Implement local scout reports as derived `task scout` artifacts.
9. Implement conservative routing decisions through `task route`, recording selected/rejected candidates, unresolved roles, and recommended next commands without invoking workers.
10. Implement routing-quality scorecards and escalation signals through `task scorecard`.

Deferred autonomy remains explicit: do not enable provider-backed execution, autonomous worker assignment, worker-owned verification, promotion, commit, push, publication, or self-promotion as part of the Milestone 17 evidence-only design.
