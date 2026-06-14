# Milestone 17 Task-Fit Context Routing Evidence Design

## Goal

Promote deterministic task-fit, context estimation, scout, routing, and routing-quality artifacts into an explicit evidence-only control-room slice.

The milestone should let Dev-Flow answer: "Given this task, which roles are needed, how much context does each role need, which registered agents are eligible, which candidates were rejected, and what is the next safe human-invoked command?"

## Trigger Evidence

Milestone 16 made local agent selection model-agnostic at the explicit role-selection boundary. It can rank installed registered local agents for a requested role and write selected-agent evidence, but it still does not infer task fit or choose agents across roles.

The repo already contains hidden experimental routing helpers:

- `devflow task fit`
- `devflow task scout`
- `devflow task route`
- `devflow task scorecard`
- legacy `devflow task pack`

Those helpers should not remain ambiguous poison context. Milestone 17 should harden the useful pieces into a stable evidence path, retire or keep hidden the legacy overlap, and align active docs so future workers understand the boundary.

## Product Decision

Milestone 17 is evidence-only routing, not autonomous execution.

Promote these pieces:

1. Deterministic `task-fit` evidence with bounded repo metadata, task metadata, risk classification, context layer, and recommended role tiers.
2. Deterministic scout reports for repo scope, risk, context, tests, and stale-context signals.
3. Role-scoped context-pack evidence using the existing agent context-pack contract.
4. Conservative routing decisions that resolve eligible registered agents per role and record selected, rejected, blocked, and unresolved candidates.
5. Routing-quality scorecards that compare the routing decision with actual worker, verification, review, and promotion evidence after a task runs.

Keep these deferred:

- automatic worker execution from a routing decision
- remote provider API calls
- provider-backed worktree orchestration
- silent model substitution
- worker-owned verification, promotion, commit, push, or pull request creation
- hidden memory, vector search, RAG, embeddings, or training
- automatic policy changes from routing scorecards

## Rejected Approaches

### Keep The Experimental Commands Hidden

This avoids risk but leaves existing task-fit/router code as misleading active source. Future agents can keep re-discovering it, assuming it is either obsolete or already endorsed. The better path is to make the safe parts explicit and fail closed around execution.

### Jump Directly To Autonomous Routing

This would violate the MVP boundary. Routing controls who gets work, so mistakes can amplify across many tasks. Dev-Flow needs visible evidence and outcome scorecards before any future autonomy policy can be considered.

### Hard-Code Josh's Current Local Models

That would undo Milestone 16's model-agnostic registry boundary. Routing must use registry definitions, adapter runtime eligibility, local discovery/selection evidence, useful context estimates, and role policy. Agent IDs are outputs of the decision, not the first input.

## Architecture

The implementation should stay inside `src/devflow/control_room/` for routing logic. `src/devflow/cli.py` may get only thin command wiring because it is the existing Typer entry point.

The routing path has five phases:

1. Build or refresh `task-fit.yaml` from canonical task state, bounded repo metadata, Code Map hints when present, relevant file statistics, and existing task evidence.
2. Build scout reports that refine deterministic evidence without invoking model providers.
3. Build or reference role-scoped context packs for the selected roles and candidate agents.
4. Resolve registry/provider/runtime eligibility, installed local selection evidence when present, useful context limits, risk policy, permission mode, and role match.
5. Write `routing-decision.yaml` and optional JSON output with selected roles, rejected candidates, unresolved roles, refusal reasons, next commands, and policy version.

`devflow task run` remains explicit. A routing decision can recommend a command such as `devflow task run <task_id> --worker <agent_id>`, but it must not execute it.

## Command Contract

Stable evidence commands:

```bash
devflow task fit <task_id>
devflow task fit <task_id> --json
devflow task scout <task_id> --role all
devflow task scout <task_id> --role risk --json
devflow task route <task_id>
devflow task route <task_id> --json
devflow task scorecard <task_id>
devflow task scorecard <task_id> --json
```

Existing `devflow agent context-pack <task_id> <agent_id> --role <role> --json` remains the stable role-scoped context-pack command. Legacy `devflow task pack` should stay hidden or be retired unless the implementation proves it adds unique value beyond `agent context-pack`.

Local availability remains explicit:

```bash
devflow agent discover-local --json
devflow agent select-local <task_id> --role implementation_worker --json
```

Routing may consume existing selected-agent evidence. It must not silently run local discovery, create registry entries, or choose an unregistered installed model unless a future command adds an explicit refresh flag and records that local-only read as evidence.

## Artifact Contract

Milestone 17 artifacts are derived evidence under `.devflow/tasks/<task_id>/`:

```text
task-fit.yaml
scout-repo_scope.yaml
scout-risk.yaml
scout-context.yaml
scout-test.yaml
scout-stale_context.yaml
routing-decision.yaml
routing-quality-scorecard.yaml
context-packs/<role>-<agent_id>.json
context-packs/<role>-<agent_id>.md
context-packs/<role>-<agent_id>.packet.json
```

Artifacts are not canonical task state. They must not mark a task complete, verified, review-ready, promoted, or blocked. Canonical state remains `task.yaml`, append-only events, verification evidence, review readiness, and promotion evidence.

## Task-Fit Contract

`task-fit.yaml` should include:

- task type
- repo scope
- context requirement
- reasoning requirement
- code edit risk
- architectural risk
- verification complexity
- required context layer
- recommended planner, worker, reviewer, verifier, summarizer, and scout tiers
- confidence
- deterministic repo scan metrics
- evidence inputs used
- stale or missing inputs

The estimator must use bounded reads. It may count lines, file sizes, hashes, and task evidence. It must not load broad source files or archived material just to classify a task.

`model_routing_change`, critical architectural risk, protected-path edits, and cross-project task mutation must require human-visible escalation in the routing decision.

## Scout Contract

Initial scouts are deterministic reports:

- `repo_scope`: relevant files, subsystem roots, scope estimate, missing Code Map hints
- `risk`: edit risk, architecture risk, protected-path risk, provider/routing risk
- `context`: estimated context pack size, likely layer, missing indexes or docs
- `test`: likely affected tests and verification commands
- `stale_context`: archived, quarantined, obsolete, or contradictory docs to exclude or rewrite

Scout reports are advisory. They cannot override canonical task state, registry policy, or verification evidence.

## Routing Contract

`routing-decision.yaml` should include:

- `task_id`
- `policy_version`
- `decision_mode: evidence_only`
- `task_fit_profile_path`
- selected roles and agent IDs
- context-pack paths or required context-pack commands
- rejected candidates with concrete reasons
- unresolved roles with next safe actions
- explicit execution boundary text
- recommended next commands

Candidate rejection reasons should be concrete:

- role mismatch
- adapter not executable for the requested surface
- provider is planned or experimental-readonly
- model not installed
- no selected-agent evidence
- useful context below pack estimate
- permission mode cannot write the requested artifact
- high-risk task requires stronger planner or reviewer
- candidate is read-only and cannot serve as implementation worker

If no eligible implementation worker exists, routing should select no worker and report `needs_human_agent_selection` or `no_eligible_agent`. It should not fall back to shell unless policy explicitly identifies shell as the worker for that task and command.

## Scorecard Contract

The scorecard runs after worker and verification evidence exists. It compares the routing decision with outcomes:

- selected worker produced required evidence
- boundary violations or refusal paths occurred
- verification passed or failed
- review readiness status
- promotion readiness status
- context pack appeared sufficient or omitted required files
- local execution avoided remote provider usage
- escalation was required

Scorecards are measurement only. They do not tune model profiles, relax policy, complete goals, promote code, or authorize future autonomy.

## Error Handling

- Missing task: fail with a clear `Task not found` message and no artifact write.
- Invalid registry: fail closed and record no partial routing decision.
- Missing selected-agent evidence: route may still select non-model deterministic roles, but local model roles remain unresolved.
- Dirty workspace: record dirty-state evidence instead of failing by default; fail only when dirty state makes file relevance ambiguous beyond the confidence threshold.
- Missing context pack: report the exact `devflow agent context-pack ...` command needed.
- Critical risk: write a routing decision with escalation required and no automatic worker command.

## Testing

Focused tests should cover:

- deterministic task-fit classification for documentation, bug fix, refactor, model-routing, and verification-only tasks
- bounded context estimates and context layer thresholds
- scout report generation without provider calls
- route decisions using registry/runtime eligibility and selected-agent evidence
- refusal when a read-only profile would otherwise be chosen as an implementation worker
- refusal when useful context is below estimated pack size
- critical-risk escalation for `model_routing_change`
- JSON and text CLI output for stable commands without `DEVFLOW_EXPERIMENTAL`
- scorecard output from synthetic worker and verification evidence

Verification should include focused pytest for the touched routing modules, `git diff --check`, a stale-context scan for old autonomous-routing claims, and broader suite only if command visibility or artifact schema changes have broad blast radius.

## Documentation Updates

Implementation should update:

- `docs/architecture/agent-selection-and-context-routing.md` from planning-only to implemented evidence-only boundary where applicable
- `docs/architecture/agent-registry-and-adapter-runtime.md` to reference Milestone 17 as the first task-fit evidence slice
- `docs/control-room-mvp.md` and `docs/mvp-contract.md` to list stable evidence commands while keeping autonomous routing excluded
- `docs/roadmap.md` to mark Milestone 17 status accurately
- `CODE_MAP.md` if the routing boundary wording changes

## Acceptance Criteria

- Stable CLI commands produce task-fit, scout, route, and scorecard evidence without `DEVFLOW_EXPERIMENTAL`.
- Routing logic lives in `src/devflow/control_room/`; CLI changes are thin command wiring only.
- Routing selects agents from registry/runtime/local-selection evidence and never from hard-coded model names.
- Routing writes selected, rejected, blocked, and unresolved candidates with concrete reasons.
- Routing decisions do not run workers, call remote providers, apply patches, verify, promote, commit, push, or open pull requests.
- Local model availability is explicit evidence, not silent discovery.
- Critical routing/provider/architecture tasks require human-visible escalation.
- Focused tests cover estimator, scouts, router, scorecard, CLI visibility, and refusal paths.
- Active docs distinguish evidence-only routing from autonomous routing.

## Self-Check

- This builds the control room, not another coding agent.
- It makes parallel work more visible by showing role needs, context needs, candidate eligibility, and refusal reasons.
- It reduces ceremony by turning hidden experimental helpers into one explicit evidence path.
- State stays clear because artifacts are derived evidence, not canonical task authority.
- Users can see what is happening without reading provider modules or broad logs.
- It works without paid frontier-model credits because deterministic routing and local evidence are enough to make a decision visible.
- Workers remain replaceable because registry policy, runtime eligibility, and useful context profiles drive selection.
- The main repo is protected because routing cannot mutate, verify, promote, commit, push, or publish.
- Failures are understandable because unresolved roles and rejected candidates carry concrete next commands.
- This is useful now because Milestone 16 already created the registry/runtime/evidence boundary that routing can safely consume.
