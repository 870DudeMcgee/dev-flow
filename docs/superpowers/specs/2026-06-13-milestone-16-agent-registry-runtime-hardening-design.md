# Milestone 16 Agent Registry Runtime Hardening Design

## Goal

Make the existing agent registry and current executable worker paths behave like one permissioned runtime contract before any remote provider execution is promoted.

This milestone should make "workers are replaceable" feel real without letting agents own state, verification, promotion, routing, or publication.

## Trigger Evidence

Milestone 15B proved multi-project task state and promotion need durable baselines and explicit local Git state. The next product bottleneck is not another project registry slice; it is the worker boundary:

- `shell` and `manual` are stable runtime adapters.
- `qwopus-implementer` is an explicitly gated local Ollama patch runtime.
- read-only local worker-pool profiles write generalized WorkerEvidence under task-local `local-model-runs/`.
- provider-backed worker modules exist but are experimental-read-only or planned, and task execution must fail closed.
- task packets exist, but role-scoped context packs are not yet a first-class evidence artifact.
- evidence from shell, manual, local patch, and local model runs is readable, but not projected through one derived runtime/evidence summary.

This creates enough surface area that future agents can accidentally add provider-specific behavior in the wrong place. Milestone 16 should centralize the runtime decisions and make the safe paths boring.

## Product Decision

Milestone 16 is a runtime hardening milestone, not a provider launch.

Promote only these pieces:

1. A central resolved runtime projection for an agent/profile that says:
   - adapter maturity
   - provider class
   - execution surface
   - permission mode
   - whether task-run execution is allowed
   - whether `agent run` evidence is allowed
   - exact refusal text when blocked
   - expected evidence paths
2. Role-scoped context-pack evidence built from canonical task packets.
3. A derived task-local agent evidence summary that can compare shell/manual/local-patch/local-model evidence without changing canonical task state.
4. Dogfood of the current local patch ladder through explicit review, dry-run, apply, verify, review-ready, and promotion readiness gates.

Keep these deferred:

- remote OpenAI, Anthropic, Gemini, xAI, LM Studio, or OpenAI-compatible execution through stable task runs
- autonomous routing
- provider-backed worktree orchestration
- database state
- hidden memory, embeddings, RAG, or training loops
- automatic promotion, commit, push, pull request, or goal completion

## Architecture

Add a small derived runtime layer inside `src/devflow/control_room/` that reads existing registry/provider definitions and emits a normalized `ResolvedAgentRuntime` projection. Existing worker lookup and local worker-pool entry points should use this projection for eligibility and refusal messages instead of re-deriving policy in multiple places.

Add a `context_pack` module that builds role-scoped context evidence from `TaskPacket`. A context pack is derived and disposable. It records included sources, excluded sources, estimated size, role, agent id, task id, and truncation notes. It never becomes canonical task state.

Add an `agent_evidence` projection that reads existing task-local evidence paths and summarizes what each worker path produced. It must not rewrite worker outputs, infer verification success, or mark readiness. Review readiness remains owned by the existing review-readiness projection.

## Runtime Projection Contract

For a given `agent_id`, the projection should classify the execution surface:

- `task_run`: stable shell/manual or explicitly safe local patch runtime
- `agent_run`: read-only local worker-pool evidence profile
- `packet_only`: manual packet or future non-executable handoff
- `blocked`: experimental or planned provider-backed adapter

Required fields:

- `agent_id`
- `provider_id`
- `provider`
- `adapter`
- `adapter_maturity`
- `permission_mode`
- `execution_surface`
- `task_run_allowed`
- `agent_run_allowed`
- `packet_allowed`
- `remote_provider`
- `network_allowed`
- `can_promote`
- `refusal_reason`
- `next_command`
- `evidence_contract`

The projection is read-only. It does not create tasks, run agents, call providers, write packets, verify, promote, or mutate registry files.

## Context Pack Contract

Context packs live under:

```text
.devflow/tasks/<task_id>/context-packs/<role>-<agent_id>.json
.devflow/tasks/<task_id>/context-packs/<role>-<agent_id>.md
```

The JSON form should include:

- `schema_version`
- `task_id`
- `agent_id`
- `role`
- `permission_mode`
- `source_packet_path`
- `included_sources`
- `excluded_sources`
- `estimated_chars`
- `estimated_tokens`
- `truncation_notes`
- `created_at`

The markdown form should be concise enough for a worker packet and should not include hidden reasoning, secrets, or unbounded logs.

## Evidence Projection Contract

Derived evidence summaries should report:

- shell worker log/result/workspace evidence
- manual proof-agent handoff/result/question/failure evidence
- `qwopus-implementer` local patch evidence
- normalized patch review/dry-run/apply evidence where present
- read-only local worker-pool WorkerEvidence runs

The summary should say what exists and which command is the next safe action. It must not say verification passed unless `verification.json` says so, and it must not say promotion is ready unless the existing review-readiness projection says so.

## User-Facing Outcome

After Milestone 16, a user or supervisor should be able to answer:

```text
Which workers can run for this task, what are they allowed to do, what context will they see, what evidence will they leave, and why are unsafe providers blocked?
```

## Acceptance Criteria

- Runtime policy for stable, local patch, read-only local model, experimental-readonly, and planned adapters is projected through one module and covered by tests.
- `devflow task run` and `devflow agent run` use consistent refusal language for blocked profiles.
- Role-scoped context packs can be created for at least implementation and review roles from canonical task packet data.
- Agent evidence summary reads existing evidence without mutating canonical task state.
- Remote provider-backed adapters still fail closed through task execution.
- Focused tests cover runtime projection, context-pack creation, evidence summaries, and refusal paths.
- A dogfood task demonstrates the local patch ladder through review, dry-run, apply, verify, and review-ready evidence without remote provider calls.
- Active docs state that Milestone 16 hardens current runtime seams and does not launch remote provider execution or autonomous routing.

## Likely Files

- `src/devflow/control_room/agent_runtime.py`
- `src/devflow/control_room/context_pack.py`
- `src/devflow/control_room/agent_evidence.py`
- `src/devflow/control_room/worker_adapter.py`
- `src/devflow/control_room/local_model_worker_pool.py`
- `src/devflow/control_room/task_packet.py`
- `src/devflow/cli.py`
- `tests/test_agent_runtime.py`
- `tests/test_context_pack.py`
- `tests/test_agent_evidence.py`
- `tests/test_worker_adapter_safety.py`
- `tests/test_agent_local_worker_pool_cli.py`
- `tests/test_task_packet.py`
- `docs/roadmap.md`
- `docs/control-room-mvp.md`
- `docs/mvp-contract.md`

## Self-Check

- This builds the control room, not another coding agent.
- It makes replaceable workers more visible and recoverable.
- It reduces scattered adapter policy and refusal logic.
- State remains clearer because new artifacts are derived evidence, not canonical state.
- Users can see what a worker is allowed to do without reading provider-specific modules.
- It works without paid frontier-model credits.
- Workers remain replaceable because provider and role details stay declarative.
- Main repo protection remains intact because verification and promotion stay Dev-Flow-owned.
- Failures remain understandable through explicit refusal text and next commands.
- This is useful now because current local/manual/shell worker surfaces already exist.
