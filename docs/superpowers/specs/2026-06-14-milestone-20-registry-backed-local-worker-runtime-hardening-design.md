# Milestone 20 Registry-Backed Local Worker Runtime Hardening Design

## Goal

Make registry-backed local workers inspectable, recoverable, and operator-friendly without giving them control over source edits, verification, promotion, commits, pushes, remote providers, or autonomous routing.

Milestone 20 does not add OpenAI, Anthropic, Gemini, Grok, LM Studio remote execution, or best-model autonomous routing. It hardens the local evidence lane that already exists for registry-backed Ollama patch workers and read-only local model worker-pool profiles.

## Why This Milestone Comes Next

Milestone 19 made Git-native shell-worker lanes visible and recoverable. The next product gap is that local non-shell workers still appear as scattered artifacts: `agents/<worker_id>/`, `local-model-runs/<run_id>/`, patch review evidence, patch dry-run evidence, selected-agent evidence, and task-fit evidence all exist, but operators have to know the artifact layout to understand what happened.

The North Star self-check points at this slice:

- It builds the control room, not another coding agent.
- It makes parallel work more visible and recoverable.
- It keeps state local, file-backed, and inspectable.
- It works without paid frontier-model credits.
- It keeps workers replaceable and protects `main`.

## Product Boundary

In scope:

- Registry-backed local Ollama patch workers such as `qwopus-implementer` and `gemma4-12b-qat-implementer`.
- Registry-backed local model worker-pool profiles such as `local-qwopus-inspector` and `local-gemma4-summarizer`.
- Existing legacy `devflow task local` advisory artifacts only as read-only evidence inputs where useful.
- Read-only local worker lane summaries derived from existing evidence and task state.
- CLI, supervisor, operating-layer, and dogfood surfaces that show local worker evidence state and next safe actions.
- Deterministic refusal/recovery language for malformed, stale, missing, low-quality, or failed local worker evidence.
- Dogfood that proves the evidence lane without requiring a real model call.

Out of scope:

- Remote provider-backed adapters.
- Native OpenAI, Anthropic, Gemini, or Grok execution.
- Autonomous routing, scheduling, verification, promotion, commit, push, pull request creation, or cost policy automation.
- Letting local worker-pool profiles write `proposal.patch` or mutate source/workspaces.
- Letting local patch workers apply their own patch or verify themselves.
- Making Git-native worktrees the default runtime.

## Approaches Considered

### A. UI-Only Evidence Polish

Add a few more rows to `task show` and the operating layer from existing evidence paths.

This is cheap, but it leaves the state model scattered. Every surface would learn slightly different rules about local patch runs, read-only worker-pool runs, selected-agent evidence, and patch application state.

### B. Provider Adapter Expansion

Begin OpenAI-compatible or native provider execution now.

This is tempting but premature. The active contract still says provider-backed non-shell adapters are deferred until local registry/manual/shell alignment is stable. Adding providers before local evidence is clear would increase risk and process confusion.

### C. Recommended: Local Worker Lane Read Model

Add a read-only local worker lane projection, similar in spirit to Milestone 19's Git worker lane summary, but scoped to registry-backed local evidence.

This gives every surface one vocabulary for local worker status while preserving the current mutation ladder: local worker writes evidence, Dev-Flow reviews/dry-runs/applies/verifies/promotes separately, and humans remain in control.

## Operator Story

An operator creates a task and explicitly asks a local registry worker to inspect or draft evidence. After the run, the operator can answer these questions without opening raw artifact directories:

- Which local worker/profile ran?
- Was it a read-only worker-pool run or a local patch worker?
- Which packet, response, raw output, log, and metadata files were produced?
- Did the worker fail, produce low-quality evidence, or produce a patch candidate?
- If a patch exists, has it been normalized, reviewed, dry-run, applied, verified, and previewed for promotion?
- What is the exact next safe command?
- Which actions remain human-controlled?

## Architecture

### Local Worker Lane Projection

Add a read-only helper under `src/devflow/control_room/`:

```python
def local_worker_lane_summary(root: Path, task: TaskRecord, worker_id: str | None = None) -> dict[str, Any] | None:
    """Return a derived local-worker evidence summary for a task."""
```

The helper returns `None` when no local worker evidence exists. It must not run models, normalize patches, review patches, dry-run patches, apply patches, verify, promote, refresh Git evidence, mutate task state, or write derived evidence.

The projection should combine:

- `.devflow/tasks/<task_id>/agent-selection.json`
- `.devflow/tasks/<task_id>/agents/<agent_id>/run.json`
- `.devflow/tasks/<task_id>/agents/<agent_id>/proposal.patch`
- `.devflow/tasks/<task_id>/agents/<agent_id>/result.md`
- `.devflow/tasks/<task_id>/agents/<agent_id>/logs/worker.log`
- `.devflow/tasks/<task_id>/local-model-runs/<run_id>/run.json`
- `.devflow/tasks/<task_id>/local-model-runs/<run_id>/response.md`
- `.devflow/tasks/<task_id>/local-model-runs/<run_id>/raw_output.txt`
- `.devflow/tasks/<task_id>/local-model-runs/<run_id>/error.txt`
- normalized `patch-review.json`, `patch-dry-run.json`, and `patch-application.json` when present
- task verification and promotion readiness evidence

### Summary Shape

Use stable vocabulary so all surfaces can render the same state:

```json
{
  "schema": 1,
  "task_id": "task-0001",
  "worker_id": "qwopus-implementer",
  "lane_type": "local-patch-worker",
  "profile_id": "qwopus-implementer",
  "model": "qwopus:latest",
  "adapter": "ollama_chat",
  "permission_mode": "workspace_write",
  "latest_run_id": "agent-qwopus-implementer",
  "latest_status": "complete",
  "patch_candidate": true,
  "patch_review_status": "low_risk_candidate",
  "patch_dry_run_status": "would_apply_cleanly",
  "patch_application_status": "applied",
  "verification_status": "passed",
  "promotion_readiness": "ready",
  "readiness_status": "ready",
  "readiness_errors": [],
  "readiness_warnings": [],
  "evidence_paths": [
    ".devflow/tasks/task-0001/agents/qwopus-implementer/run.json",
    ".devflow/tasks/task-0001/agents/qwopus-implementer/proposal.patch"
  ],
  "next_safe_action": "devflow task promote-preview task-0001"
}
```

Read-only worker-pool runs use `lane_type: "local-model-worker-pool"` and must report `patch_candidate: false` unless an existing patch artifact is explicitly present through the patch-worker path. Their next safe action is review-oriented, not mutation-oriented.

### Readiness Vocabulary

Use a small enum:

```text
ready
needs_review
needs_dry_run
needs_apply
needs_verification
needs_promotion_preview
failed
low_quality
missing
blocked
```

The next safe action ladder is deterministic:

- no local evidence: `devflow agent select-local <task_id> --role <role>`
- dry-run preview only: `devflow agent run --task <task_id> --profile <profile_id> --json`
- read-only worker success: `devflow agent evidence <task_id> --json`
- local patch worker produced patch: `devflow task review-patch <task_id> --agent <worker_id>`
- reviewed patch: `devflow task patch-dry-run <task_id> --agent <worker_id>`
- clean dry-run: `devflow task apply-patch <task_id> --agent <worker_id>`
- patch applied: `devflow task verify <task_id> --shell "<command>"`
- verified: `devflow task promote-preview <task_id>`
- promotion ready: `devflow task promote <task_id>`
- failure or malformed evidence: `devflow task escalation-packet <task_id> --agent <worker_id>` when available, otherwise `devflow task show <task_id>`

### Surface Integration

The projection should appear consistently in:

- `devflow task show <task_id>`
- `devflow task review-ready <task_id>`
- `devflow agent evidence <task_id> --json`
- `devflow supervisor status --json`
- `devflow supervisor packet --json`
- `devflow operating-layer snapshot --json`
- the selected task review panel in the operating-layer UI

The operating-layer UI should render this as compact evidence, not as a new execution button. Worker execution stays in trusted CLI.

### Dogfood

Add one production-readiness dogfood case that does not require real Ollama or remote provider availability. The case should run in a scratch Git repo and use deterministic fixture evidence plus existing CLI dry-run paths to prove:

- local worker dry-run outputs are visible;
- a synthetic read-only WorkerEvidence run is summarized without treating it as source truth;
- a synthetic local patch worker proposal goes through review, dry-run, apply, verify, and promote-preview gates;
- failed or low-quality evidence reports the correct next safe action;
- no source mutation occurs until `apply-patch`;
- no provider API calls, autonomous routing, auto-verification, auto-promotion, commit, push, database, or hidden memory are introduced.

## Safety Rules

- Local worker outputs are evidence, not truth.
- The projection is read-only and disposable.
- Patch workers may propose patches, but Dev-Flow owns review, dry-run, application, verification, and promotion.
- Read-only worker-pool profiles must never write patches or mutate source/workspaces.
- Provider-backed execution remains blocked unless a future milestone explicitly promotes it.
- The browser operating layer may show local worker evidence but must not add arbitrary worker execution.

## Acceptance Criteria

Milestone 20 is complete when:

1. A task with local patch worker evidence has one clear lane summary in CLI, supervisor, and operating-layer surfaces.
2. A task with read-only local model WorkerEvidence has one clear lane summary and review-only next safe action.
3. Patch proposal, review, dry-run, apply, verify, and promote-preview states produce deterministic next safe actions.
4. Malformed, missing, failed, and low-quality evidence produce deterministic refusal/recovery language.
5. Production-readiness dogfood includes the local worker lane hardening case and remains at or above the existing silver threshold.
6. Full release check passes on a clean promoted mainline.

## Explicit Non-Goals For The Next Agent

- Do not add remote provider adapters.
- Do not make `devflow agent run` choose a model automatically.
- Do not make local workers verify, promote, commit, push, or create PRs.
- Do not add a database.
- Do not expand browser mutation beyond already approved exact verification and promotion controls.
