# Module Connection Gap Closure and Qwen Supervision Plan

Date: 2026-06-20
Status: completed and pushed through Slice 6
Scope: implementation plan plus completion record; code changes landed in separate commits.
Primary checkout: `<repo-root>`

Local-worker note: this completed plan predates the current policy. Current
local-worker selection is `docs/local-worker-policy.md`: opt-in Qwen 3.6 27B Q5
MTP as the single normal lane, with other local routes as explicit exceptions.

> **For Hermes:** Use `devflow-analysis`, `subagent-driven-development`, and the Qwen single-flight references before supervising implementation. Qwen is a bounded worker, not the final verifier. The supervisor owns evidence, diff review, and verification.

## Completion Summary — 2026-06-21

All six implementation slices in this plan have been completed, verified, committed, and pushed to `origin/main`.

| Slice | Commit | Result |
|---|---|---|
| Slice 1 — Canonical TaskNextGate | `fca8fa7` | Task gate projection unified. |
| Slice 2 — Atomic BrainstormTaskBridge | `b3c76df` | Brainstorm task creation became an atomic backend bridge. |
| Slice 3 — WorkerOptionsProjection | `2d4f8b0` | Worker launch options are projected separately from shell fallback. |
| Slice 4 — BrowserActionPolicy Centralization | `247fb3f` | Browser mutation policy is centralized. |
| Slice 5 — StageArtifact / Builder-Judge Pipeline Integration | `cb031a8` | Quality-gated spec/plan status is visible as `draft` / `passed` / `escalated`. |
| Slice 6 — Local Model Runtime Lock Projection | `90096ab` | Provider/model-scoped local model runtime locks are covered and projected. |

Closure verification run after Slice 6:

```bash
env PYTHONPATH=src:. .venv/bin/python -m pytest \
  tests/test_task_next_gate.py \
  tests/test_brainstorm_task_bridge.py \
  tests/test_worker_options_projection.py \
  tests/test_operating_layer.py \
  tests/test_supervisor_operating_surface.py \
  tests/test_brainstorm_workbench.py \
  tests/test_builder_judge_loop.py \
  tests/test_local_model_runtime_lock.py \
  -q
```

Result:

```text
166 passed in 48.35s
```

The original `## Next Safe Action` at the bottom of this plan has been replaced because the old Slice 1 launch instruction is complete. The next work is the follow-on plan: `docs/superpowers/plans/2026-06-21-serial-local-agent-execution-queue-and-watchdogs.md`.

## Goal

Document the current DevFlow module-connection gaps in enough detail that a local Qwen Hermes worker can implement the fixes slice-by-slice under supervision without rediscovering the architecture.

The product contract being protected is:

```text
Idea / Brainstorm
  -> Spec / Plan artifacts
  -> Task creation + implementation context
  -> Worker selection / execution
  -> Patch or worker evidence gates
  -> Review readiness
  -> Verification
  -> Promotion / learning
```

Each arrow is a contract. A stage is not complete unless it leaves the operator with both a durable artifact and a visible next safe action.

## Terminology: Qwen vs Qwopus

| Name | What it is in this plan | Concrete evidence |
|---|---|---|
| **Qwen** | The local model family / Hermes worker profile intended for supervised implementation slices. Use this for the actual code-writing run unless the operator explicitly chooses another worker. | `qwen-worker` profile default model: `qwen3.6-32b-256k:latest`. |
| **Qwopus** | A DevFlow worker identity and evidence contract used by the existing task runtime. It is the specific patch-evidence path involved in the P0 gate bug. | `.devflow/agents/registry.yaml` defines `qwopus-implementer` with model `qwopus:latest`; `src/devflow/control_room/qwopus_evidence.py` reads its `proposal.patch` / `result.md` evidence. |

Why both appear: the implementation supervisor can be Qwen while the bug being fixed is proven through Qwopus-style evidence. The first slice should make the UI/projector respect the Qwopus patch gate (`review-patch -> patch-dry-run -> apply-patch`) regardless of whether the next code-writing worker is Qwen, Qwopus, or another local model.

## Source Evidence Summary

The investigation inspected these current modules:

| Area | Producer / Consumer | Key files |
|---|---|---|
| Brainstorm pipeline | produces spec/plan/implementation artifacts and task action | `src/devflow/control_room/brainstorm.py`, `brainstorm_pipeline.py` |
| Browser action runner | consumes command strings and executes approved actions | `src/devflow/control_room/operating_layer_server.py` |
| Task execution | writes worker/task evidence | `src/devflow/control_room/service.py`, `ollama_worker.py`, `local_ollama_worker.py` |
| Routing | recommends model/worker commands without executing | `src/devflow/control_room/router.py`, `estimator.py` |
| Next-action projections | project task gates into dashboard/review/workbench/UI | `status_projection.py`, `qwopus_evidence.py`, `review_readiness.py`, `task_workbench.py`, `operating_layer.py` |
| Browser UI | renders launchpad, worker panel, review/evidence actions | `src/devflow/control_room/operating_layer_script.py` |
| Operator policy | reports browser allowed/blocked actions | `src/devflow/control_room/supervisor_surface.py`, `operating_layer.py`, `task_workbench.py` |
| Quality loop | produces builder/judge evidence and questions | `src/devflow/control_room/builder_judge_loop.py` |

Relevant product intent:

- `docs/operator-centered-mission.md:220-251` defines the canonical pipeline and says every arrow must produce artifact + visible next action.
- `docs/control-room-mvp.md:329` says the operating layer is the approved UI contract, but browser mutation scope is deliberately guarded.
- `AGENTS.md:39-50` says current tasks need useful controls and invisible orchestration is not welcome.

## Runtime Verification Already Performed

A temporary DevFlow repo/task was created and seeded with minimal Qwopus-style patch evidence:

```text
.devflow/tasks/task-0001/agents/qwopus-implementer/proposal.patch
.devflow/tasks/task-0001/agents/qwopus-implementer/result.md
.devflow/tasks/task-0001/agents/qwopus-implementer/raw_output.md
.devflow/tasks/task-0001/agents/qwopus-implementer/run.json
```

Projection builders were then called from source. The important result:

```json
{
  "projection_suggested_next_action": "devflow task review-patch task-0001 --agent qwopus-implementer",
  "projection_dashboard_next_action": {
    "label": "Run verification",
    "command": "devflow task verify task-0001 --shell \"<command>\""
  },
  "review_next_command": "devflow task verify task-0001 --shell \"<command>\"",
  "snapshot_task_next_action": {
    "label": "Run verification",
    "command": "devflow task verify task-0001 --shell \"<command>\""
  }
}
```

Interpretation: one backend helper knows the patch gate is next, but the visible operating-layer path skips to verification. This is a confirmed split-brain next-action bug, not speculation.

---

# Prioritized Gaps

## P0-1 — Patch Evidence Exists, But Visible Next Action Skips Patch Gates

### Current producer

`src/devflow/control_room/qwopus_evidence.py` has a correct patch-gate ladder.

Evidence:

- `qwopus_suggested_next_action(...)` at `qwopus_evidence.py:102-123`:
  - if `proposal.patch` exists and is not applied, return `_next_patch_gate_command(...)`.
- `_next_patch_gate_command(...)` at `qwopus_evidence.py:150-161`:
  - `review-patch` if review evidence is missing;
  - `patch-dry-run` if dry-run evidence is missing;
  - `apply-patch` when review and dry-run are present.

### Current consumers

The operating layer and review projections consume `dashboard_next_action` instead.

Evidence:

- `status_projection.py:165-215` maps completed worker output to `devflow task verify <task_id> --shell "<command>"`.
- `status_projection.py:291-318` sets `suggested_next_action` from `qwopus_suggested_next_action(...)`, but that field is separate from `dashboard_next_action`.
- `review_readiness.py:257-264` uses `projection.dashboard_next_action.command` when the task needs verification.
- `operating_layer.py:1362-1411` creates the task card from `projection.dashboard_next_action` and uses it for `actions`.
- `task_workbench.py:1064-1130` builds controls from the supplied `next_action_command`.

### Impact

When a local patch worker writes `proposal.patch`, the UI can tell the operator to verify before the patch was reviewed, dry-run, or applied. That breaks:

```text
Worker -> patch review -> patch dry-run -> patch application -> verification
```

### Required contract

Introduce one canonical task gate resolver:

```python
resolve_task_next_gate(root: Path, projection: TaskStatusProjection, *, project_id: str | None = None) -> TaskNextGate
```

Minimum fields:

```python
class TaskNextGate(BaseModel):
    task_id: str
    label: str
    command: str | None
    gate: Literal[
        "inspect",
        "run_worker",
        "review_patch",
        "patch_dry_run",
        "apply_patch",
        "verify",
        "promotion_preview",
        "promote",
        "resolve_blocker",
        "inspect_failure",
        "cleanup_preview",
        "closed",
    ]
    safety_class: str
    requires_human_approval: bool
    supervisor_may_auto_run: bool
    reason: str
    evidence_paths: list[str]
```

Patch-worker order must be:

```text
proposal.patch present
  -> missing matching patch-review.json? review-patch
  -> missing matching patch-dry-run.json? patch-dry-run
  -> patch not applied? apply-patch
  -> verification missing/failed? verify
  -> promotion preview missing? promote-preview
  -> promote
```

### Implementation notes

Start with a read-only module:

```text
src/devflow/control_room/task_next_gate.py
```

Use existing helpers first:

- `read_qwopus_evidence(...)`
- `qwopus_patch_application_succeeded(...)`
- `build_review_readiness_projection(...)`
- `classify_supervisor_command(...)`
- `_scope_task_command` behavior should be preserved or moved into a shared helper.

Then replace consumers in this order:

1. `status_projection.py` — make `dashboard_next_action` use `TaskNextGate` or expose a compatibility projection from it.
2. `review_readiness.py` — use `TaskNextGate.command` instead of re-deriving verification too early.
3. `task_workbench.py` — controls should be generated from `TaskNextGate.gate`.
4. `operating_layer.py` — task `next_action`, `actions`, gate receipts should consume the same gate.
5. `operating_layer_script.py` — only adjust labels if the schema/intent names change.

### Tests to add

Create `tests/test_task_next_gate.py` with fixtures for:

- created task -> `run_worker`.
- shell-complete task without verification -> `verify`.
- Qwopus proposal patch without review -> `review_patch`.
- Qwopus proposal patch with review but no dry-run -> `patch_dry_run`.
- Qwopus proposal patch with review + dry-run but no application -> `apply_patch`.
- patch applied but not verified -> `verify`.
- verified but no promotion preview -> `promotion_preview`.

Focused verification:

```bash
env PYTHONPATH=src:. .venv/bin/python -m pytest \
  tests/test_task_next_gate.py \
  tests/test_operating_layer.py::test_operating_layer_snapshot_includes_browser_review_loop_summary \
  -q
```

---

## P0-2 — Brainstorm Implementation Context Is Not Atomically Bound To Created Task

### Current producer

Brainstorm escalation builds implementation context and a task creation action.

Evidence:

- `brainstorm_pipeline.py:34-40` defines `BrainstormImplementationContext` with:
  - `write_endpoint = "/api/task/write-context"`
  - `target_path_template = ".devflow/workspaces/{task_id}/implementation-context.md"`
- `brainstorm.py:312-352` handles implementation escalation:
  - writes `implementation.md`;
  - builds `BrainstormPipelineDetail`;
  - returns `action`, `pipeline_detail`, `implementation_context`, and `implementation_context_path`.
- `brainstorm_pipeline.py:206-234` builds a task creation command string, not an atomic task+context operation.
- `brainstorm_pipeline.py:237-288` constructs context from `spec.md`, `plan.md`, or transcript fallback.

### Current consumer

The context writer is a separate server endpoint.

Evidence:

- `operating_layer_server.py:759-777` handles `/api/task/write-context`:
  - requires a concrete `task_id`;
  - writes `.devflow/workspaces/<task_id>/implementation-context.md`.
- `operating_layer_script.py:421-437` can read implementation context from the pipeline payload.

### Impact

The handoff currently depends on browser choreography:

```text
escalate implementation
  -> receive task create command + context text
  -> run task create command
  -> parse or discover created task id
  -> call /api/task/write-context
```

If any browser step fails, the task exists but the worker loses the spec/plan context. This is a fragile Brainstorm -> Task bridge.

### Required contract

Add an atomic bridge:

```text
POST /api/brainstorm/create-task
```

or CLI equivalent:

```text
devflow brainstorm create-task <session_id> --stage implementation
```

It should:

1. load `pipeline.json` / build pipeline detail;
2. validate implementation stage is ready;
3. create the task through existing task service/CLI helpers;
4. write `implementation-context.md` into the new workspace;
5. append task event with brainstorm lineage;
6. write/update brainstorm pipeline lineage with `created_task_id`;
7. return task id, context path, action result, and first worker options.

### Implementation notes

Prefer backend-owned task creation over parsing stdout in JS. If a service-level task creation helper already exists, call that directly rather than shelling out from the server route. If the safe existing path is the CLI command runner, still return structured `task_id` from the server by reading the newly created task record, not by fragile text matching.

### Tests to add

- `test_brainstorm_create_task_bridge_writes_context_and_lineage`
- `test_brainstorm_create_task_bridge_refuses_missing_implementation_stage`
- `test_operating_layer_create_task_from_pipeline_returns_task_id`

Focused verification:

```bash
env PYTHONPATH=src:. .venv/bin/python -m pytest \
  tests/test_brainstorm_workbench.py \
  tests/test_operating_layer.py::test_operating_layer_brainstorm_implementation_escalation_exposes_task_action \
  -q
```

---

## P1-1 — Router/Agent Selection Exists, But Launchpad Mostly Presents Shell

### Current producer

`router.py` can recommend workers without running them.

Evidence:

- `router.py:110-120` estimates task fit and loads agent/provider registries.
- `router.py:194-204` selects best eligible worker and builds:
  - `recommended_next_commands["worker"] = "devflow task run <task_id> --worker <agent>"`.
- `router.py:254-274` marks the decision as `evidence_only`, with `will_run_worker: False`.
- `cli.py:2787-2858` wires `task auto-run` as estimate -> route -> selected worker -> execute.

### Current consumer

Launchpad and workbench controls do not expose a full worker-options projection.

Evidence:

- `operating_layer_script.py:1527-1534` renders `renderWorkerOptions(task)` from task capability `start_shell` / `retry`.
- `operating_layer_script.py:1581-1598` renders a worker panel, but the raw shell fallback remains the concrete guided path.
- `task_workbench.py:1064-1130` builds controls from next action/retry/verify/promote/close and does not consult routing decision or selected local-agent evidence.

### Impact

The operator sees a task but does not see the best available model/worker options. The system has routing intelligence, but the UI path still collapses to raw shell unless another surface happens to provide AI worker buttons.

### Required contract

Add a canonical worker options projection:

```python
build_worker_options(root: Path, task_id: str, *, project_id: str | None = None) -> list[WorkerOption]
```

Minimum fields:

```python
class WorkerOption(BaseModel):
    worker_id: str
    label: str
    command: str
    source: Literal["routing-decision", "agent-selection", "registry", "fallback-shell"]
    model: str | None
    provider: str | None
    is_local: bool
    enabled: bool
    safety_class: str
    requires_human_approval: bool
    blocked_reason: str | None
    evidence_paths: list[str]
```

### Implementation notes

Use sources in this priority order:

1. `routing-decision.yaml` if present and still matches the task.
2. `agent-selection.json` for local selected implementation worker.
3. registry executable local patch workers.
4. shell fallback.

Do not auto-run anything. This is a projection only.

### Tests to add

- `tests/test_worker_options_projection.py`
- Include no-registry/fallback shell, selected Qwopus, routing-decision worker, blocked runtime/profile cases.

---

## P1-2 — Browser Action Policy Is Duplicated And Drifting

### Current state

The server allows more than some browser summaries report.

Evidence:

- `operating_layer_server.py:164-190` initializes approval flags for:
  - idea capture;
  - task creation;
  - shell worker run;
  - verification;
  - promotion;
  - agent provider/model onboarding;
  - agent patch proposal.
- `operating_layer_server.py:1137-1152` validates exact `devflow agent propose-patch --task <id> --profile <profile> --json`.
- `operating_layer_server.py:1327-1334` approves patch proposal when classified as worker runtime.
- `supervisor_surface.py:293-300` says browser allowed mutations include `model/provider onboarding`.
- `operating_layer.py:1047-1053` and `task_workbench.py:607-613` list allowed mutations but omit model/provider onboarding.

### Impact

The server can execute some approval-gated actions that the review loop does not advertise, while other surfaces say they are allowed. This weakens operator trust and creates stale tests/docs.

### Required contract

Add one policy module:

```text
src/devflow/control_room/browser_action_policy.py
```

Responsibilities:

- return canonical `browser_allowed_mutations` and `browser_blocked_mutations`;
- validate exact approved command shapes;
- route approved commands to subprocess args;
- expose reason strings for UI summaries.

Consumers:

- `operating_layer_server.py`
- `task_workbench.py`
- `operating_layer.py`
- `supervisor_surface.py`
- tests

### Tests to add

- Approval-policy unit tests for each allowed browser mutation.
- Snapshot tests proving `operator_layer`, `review_loop`, and task workbench report the same allowed/blocked mutation lists.

---

## P2-1 — Review Loop / Task Actions Are Still Partly Duplicated

### Current state

`operating_layer.py` already composes `build_task_workbench(...)`, but recomputes some task/review concepts.

Evidence:

- `operating_layer.py:513-523` builds the dashboard and task workbench, then maps workbench tasks into operating-layer tasks.
- `operating_layer.py:584-590` calls its own `_review_loop_summary(...)`.
- `operating_layer.py:1025-1073` contains an independent `OperatingLayerReviewLoop` summary.
- `task_workbench.py:561-633` contains its own review-loop summary with similar allowed/blocked lists.
- `operating_layer.py:2328-2358` and `task_workbench.py:1037-1061` both build task actions.
- `task_workbench.py:1064-1130` separately builds task controls.

### Impact

The system now has a promising `TaskWorkbench` module, but still carries parallel projection logic. This makes future fixes like `TaskNextGate` and `BrowserActionPolicy` harder because every action/policy change must be patched in several places.

### Required contract

Make `TaskWorkbench` the canonical source for task-centered projection:

- lanes;
- tasks;
- review queue;
- promotion candidates;
- evidence stream;
- gate receipts;
- worker activity;
- review loop;
- task actions and controls.

`operating_layer.py` should mostly adapt the workbench schema to the public snapshot shape and compose non-task-wide surfaces: project, freshness, goals, multi-project, operator readiness, agent catalog, action rail.

---

## P2-2 — Builder/Judge Loop Is Useful But Not A First-Class Pipeline Stage Artifact

### Current producer

Builder/Judge loop is implemented and writes evidence.

Evidence:

- `builder_judge_loop.py:145-185` implements `run_builder_judge_loop(...)`.
- `builder_judge_loop.py:571-604` writes run and round evidence.
- `builder_judge_loop.py:626-670` creates a question when max rounds are reached.
- `builder_judge_loop.py:700-744` provides `run_quality_gate(...)` for spec/plan.

Server exposes it:

- `operating_layer_server.py:137-141` routes builder/judge endpoints.
- `operating_layer_server.py:569-665` starts builder/judge, including async mode.

### Current gap

Brainstorm stage artifacts are still basically `spec.md`, `plan.md`, and `implementation.md`:

- `brainstorm.py:630-694` writes stage artifacts directly.
- `brainstorm_pipeline.py:405-424` computes next step based on whether those files exist.

Quality-gate output does not appear to become the accepted stage artifact with a clear status such as draft/passed/escalated.

### Impact

The quality loop is an evidence island. It can run and write proof, but the Brainstorm -> Spec -> Plan progression does not appear to depend on or display a canonical quality-gated artifact state.

### Required contract

Add a stage artifact model:

```python
class StageArtifact(BaseModel):
    stage: Literal["spec", "plan", "implementation"]
    source: Literal["brainstorm", "builder_judge", "manual"]
    status: Literal["draft", "passed", "escalated", "accepted"]
    artifact_path: str
    quality_gate_path: str | None
    score: int | None
    next_action: str | None
```

Brainstorm pipeline should render state from `StageArtifact`, not just file existence.

---

## P2-3 — Local Qwen/Ollama Has No Obvious Model-Level Single-Flight Gate In DevFlow Runtime Paths

### Current state

Local worker paths can call Ollama through separate mechanisms:

- `ollama_worker.py:224-233` directly calls the Ollama HTTP API.
- `local_ollama_worker.py:239-248` shells out to `ollama run`.
- `service.py:307-388` protects task mutation with `task_mutation_lock(root, task_id, "run")`, but that is task-scoped, not model-scoped.
- `parallel_worker.py:124-132` can run shell worker batches with `ThreadPoolExecutor`.

### Impact

This Mac should treat Qwen as single-flight. Without a model/provider lock, a supervisor could launch overlapping local model work from different DevFlow or Hermes paths, causing hangs, thermal overload, context failures, or blended diffs.

### Required contract

Add a shared local model runtime lock for any DevFlow path that calls the same local model:

```text
.devflow/runtime/locks/local-model/<provider>/<model>.lock
```

Expose read-only status in the operating layer snapshot:

```json
{
  "local_model_runtime": {
    "qwen3.6-32b-256k:latest": {
      "state": "running",
      "task_id": "task-0004",
      "pid": 12345,
      "started_at": "...",
      "elapsed_seconds": 180,
      "queue_depth": 1
    }
  }
}
```

Implementation should preserve existing task locks and add model locks around the actual Ollama call, not around all task state mutation.

---

# Recommended Implementation Order

## Slice 1 — Canonical TaskNextGate

Why first: it fixes the confirmed split-brain bug and creates the shared primitive later slices can consume.

Allowed files for Qwen worker:

```text
src/devflow/control_room/task_next_gate.py
tests/test_task_next_gate.py
src/devflow/control_room/status_projection.py
src/devflow/control_room/review_readiness.py
src/devflow/control_room/task_workbench.py
src/devflow/control_room/operating_layer.py
tests/test_operating_layer.py
```

Non-goals:

- no browser JS redesign unless a failing test proves the label/intent must change;
- no remote provider calls;
- no promotion/push;
- no broad refactor of TaskWorkbench.

Verification:

```bash
env PYTHONPATH=src:. .venv/bin/python -m pytest \
  tests/test_task_next_gate.py \
  tests/test_operating_layer.py::test_operating_layer_snapshot_includes_browser_review_loop_summary \
  tests/test_operating_layer.py::test_operating_layer_server_blocks_approval_required_actions \
  -q
```

Acceptance:

- synthetic Qwopus patch evidence projects `review-patch`, not verification;
- existing shell-complete tasks still project verification;
- ready-to-promote tasks still project promotion preview/promote as before;
- task workbench and operating-layer task action agree on the same command.

## Slice 2 — Atomic BrainstormTaskBridge

Allowed files:

```text
src/devflow/control_room/brainstorm_task_bridge.py
src/devflow/control_room/brainstorm.py
src/devflow/control_room/brainstorm_pipeline.py
src/devflow/control_room/operating_layer_server.py
src/devflow/control_room/operating_layer_script.py
tests/test_brainstorm_workbench.py
tests/test_operating_layer.py
```

Verification:

```bash
env PYTHONPATH=src:. .venv/bin/python -m pytest \
  tests/test_brainstorm_workbench.py \
  tests/test_operating_layer.py::test_operating_layer_brainstorm_implementation_escalation_exposes_task_action \
  -q
```

Acceptance:

- one backend call creates task and writes `implementation-context.md`;
- task event or metadata records brainstorm lineage;
- browser no longer needs fragile stdout parsing to bind context to task;
- existing manual task creation remains unchanged.

## Slice 3 — WorkerOptionsProjection

Allowed files:

```text
src/devflow/control_room/worker_options.py
tests/test_worker_options_projection.py
src/devflow/control_room/task_workbench.py
src/devflow/control_room/operating_layer.py
src/devflow/control_room/operating_layer_script.py
```

Acceptance:

- created tasks expose shell fallback and eligible AI workers separately;
- selected local worker / routing-decision evidence is visible when present;
- blocked workers show reason, not silent disappearance;
- no worker runs automatically.

## Slice 4 — BrowserActionPolicy Centralization

Allowed files:

```text
src/devflow/control_room/browser_action_policy.py
src/devflow/control_room/operating_layer_server.py
src/devflow/control_room/task_workbench.py
src/devflow/control_room/operating_layer.py
src/devflow/control_room/supervisor_surface.py
tests/test_operating_layer.py
tests/test_supervisor_operating_surface.py
```

Acceptance:

- one allowed/blocked mutation list across supervisor, workbench, operating layer;
- exact approved command validation remains as strict as current behavior;
- existing approval tests still pass.

## Slice 5 — StageArtifact / Builder-Judge Pipeline Integration

Allowed files:

```text
src/devflow/control_room/stage_artifact.py
src/devflow/control_room/brainstorm_pipeline.py
src/devflow/control_room/brainstorm.py
src/devflow/control_room/builder_judge_loop.py
tests/test_brainstorm_workbench.py
tests/test_builder_judge_loop.py
```

Acceptance:

- quality-gated spec/plan status is visible as draft/passed/escalated;
- non-quality-gated manual path still works;
- escalated quality loops still create questions.

## Slice 6 — Local Model Runtime Lock Projection

Allowed files:

```text
src/devflow/control_room/local_model_runtime_lock.py
src/devflow/control_room/ollama_worker.py
src/devflow/control_room/local_ollama_worker.py
src/devflow/control_room/operating_layer.py
tests/test_local_model_runtime_lock.py
```

Acceptance:

- lock is model/provider-scoped, not task-scoped;
- stale locks are detectable and reported, not blindly deleted;
- no second Qwen run starts while a live same-model lock exists;
- snapshot exposes read-only runtime status.

---

# Qwen Hermes Supervision Plan

## Supervisor stance

Hermes supervisor controls the loop:

```text
supervisor baseline
  -> launch one bounded qwen-worker slice
  -> monitor single-flight/progress
  -> inspect diff and logs
  -> run verification independently
  -> send repair packet or accept slice
  -> only then launch next slice
```

Do not accept any of these as final proof:

- Qwen saying it passed;
- cron job `last_status=ok`;
- generated files merely existing;
- one syntax check without allowlist/diff review.

## Preflight before launching Qwen

Run/read-only capture:

```bash
git status --short --branch
git diff --stat
```

Then check:

- no existing `hermes -p qwen-worker chat` process is already active;
- Qwen single-flight lock is free or points to a live intentionally running process;
- exact slice packet is saved in a run directory;
- allowed files are explicit;
- verification commands are explicit;
- non-goals include no push, no promotion, no broad refactor.

## Preferred launch shape

Use the dedicated profile path when we actually start implementation:

```bash
hermes -p qwen-worker chat -q "$(cat /path/to/worker-packet.md)"
```

For long slices, use the existing single-flight helper pattern from `~/.hermes/scripts/qwen_single_flight_lib.sh` when available. The lock must track the child Hermes PID, not just the wrapper PID.

If launched through cron/no-agent wrapper, use separate watchdogs:

- progress watchdog: read-only, two-minute cadence, reports log/stdout movement or stall;
- completion watchdog: after worker exits, runs diff allowlist and verification.

## Worker packet template

```markdown
# Worker Packet: <slice name>

## Mission
Implement exactly one slice from `docs/superpowers/plans/2026-06-20-module-connection-gap-closure-and-qwen-supervision.md`.

## Context
DevFlow is a local-first operating layer. The current problem is module handoff split-brain: producers know the right artifact/gate, but consumers show a different next action.

## Allowed Files
- <exact paths only>

## Non-Goals
- no push
- no commit unless explicitly instructed
- no provider calls
- no broad refactor outside allowed files
- no unrelated formatting churn

## Required Behavior
- [ ] Add/adjust tests first where practical.
- [ ] Implement smallest production change to satisfy tests.
- [ ] Keep existing public snapshot shape unless the packet explicitly changes it.
- [ ] Preserve browser approval gates.

## Verification Commands
```bash
<exact commands>
```

## Output Required
- files changed
- tests added/changed
- commands run and real output
- risks/blockers
- anything outside allowlist
```

## Repair loop

If verification fails, supervisor sends a smaller repair packet with:

- failing command output;
- exact files still allowed;
- one correction objective;
- no new broad scope.

Stop after repeated failure and split the slice. Do not thrash.

---

# Documentation / Verification Policy For This File

Because this is a documentation-only change, required local verification is:

```bash
git diff --check -- docs/superpowers/plans/2026-06-20-module-connection-gap-closure-and-qwen-supervision.md
```

Targeted stale-context search. Build the quarantined-path string from fragments so the check does not match this instruction block itself:

```bash
env PYTHONPATH=src:. .venv/bin/python - <<'PY'
from pathlib import Path
path = Path('docs/superpowers/plans/2026-06-20-module-connection-gap-closure-and-qwen-supervision.md')
patterns = [
    '/Users/jewelbait/Desktop/Dev' + 'Flow',
    'old static ' + 'files',
    'public/' + ' active product',
]
for lineno, line in enumerate(path.read_text(encoding='utf-8').splitlines(), 1):
    if any(pattern in line for pattern in patterns):
        print(f'{lineno}: {line}')
PY
```

Expected:

- `git diff --check` exits 0;
- stale-context search prints no matches, unless a prohibited path appears inside a warning that is clearly marked as prohibited.

## Next Safe Action

This plan is complete. Do not relaunch Slice 1 from this document.

Next safe action: use `docs/superpowers/plans/2026-06-21-serial-local-agent-execution-queue-and-watchdogs.md` to implement the durable serial local-agent packet/run-directory/watchdog workflow that emerged during these slices.
