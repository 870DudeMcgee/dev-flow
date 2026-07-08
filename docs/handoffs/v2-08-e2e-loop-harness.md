# V2-08 — Deterministic E2E Loop Harness

## Goal

Prove the V2 loop spine works as one product loop, not just isolated adapters.

The harness should run this deterministic chain against a fixture pipeline run:

```text
idea -> definition -> spec -> planning -> planning_judge -> assignment -> build_judge -> verification -> human_decision -> complete
```

## Non-goals

- No model calls.
- No worker subprocess execution.
- No broad operating-layer refactor.
- No UI work.
- No changes to legacy `control_room/` modules beyond adding a small CLI command wrapper.

## Files to create / modify

Create:

- `src/devflow/loop/e2e_harness.py`
- `tests/test_loop_e2e_harness.py`
- `docs/handoffs/v2-08-e2e-loop-harness.md`

Modify narrowly:

- `src/devflow/control_room/loop_command.py` — add a CLI command that calls the harness.

## Existing surfaces to import

Use only the already-built V2 adapters and stable pipeline storage:

- `devflow.loop.adapter.create_run_with_state`
- `devflow.loop.adapter.load_loop_state`
- `devflow.loop.adapter.save_loop_state`
- `devflow.loop.models.advance_stage`
- `devflow.loop.models.LoopStage`
- `devflow.loop.orient.run_orient`
- `devflow.loop.planning_judge.run_planning_judge`
- `devflow.loop.planning_judge.PlanningEvidence`
- `devflow.loop.builder_judge.prepare_builder_judge_assignment`
- `devflow.loop.builder_judge.record_builder_judge_result`
- `devflow.loop.verification.record_verification_receipt`
- `devflow.loop.verification.VerificationReceipt`
- `devflow.loop.verification.VerificationStatus`
- `devflow.loop.human_decision.record_human_decision`
- `devflow.loop.human_decision.HumanDecisionRecord`
- `devflow.loop.human_decision.HumanDecision`
- `devflow.control_room.pipeline_run.update_pipeline_run_record`
- `devflow.control_room.pipeline_run.load_pipeline_run`

## Deterministic rules

1. The harness creates one pipeline run with source metadata.
2. It runs `run_orient()` with a target file that must exist.
3. It writes fixture spec and plan artifacts.
4. It advances definition -> spec -> planning -> planning_judge through canonical state transitions.
5. It runs planning judge with approving evidence.
6. It prepares a builder/judge assignment.
7. It records a passed builder/judge result.
8. It records a passed verification receipt.
9. It records an accepted human decision.
10. It returns a compact report with final stage, expected stage chain, and evidence files.

## Tests required

- Harness reaches `complete`.
- Stage history includes every canonical forward stage in order.
- Required evidence files exist in `.devflow/pipeline-runs/<run_id>/`.
- CLI command emits JSON with `final_stage: complete`.
- Missing target file fails before mutating later stages.

## Verification

```bash
PYTHONPATH=src:. .venv/bin/python -m pytest tests/test_loop_e2e_harness.py -q
PYTHONPATH=src:. .venv/bin/python -m pytest tests/test_loop_models.py tests/test_loop_adapter.py tests/test_loop_orient.py tests/test_planning_judge.py tests/test_loop_builder_judge.py tests/test_loop_verification.py tests/test_loop_human_decision.py tests/test_loop_e2e_harness.py -q
.venv/bin/ruff check src/devflow/loop/e2e_harness.py src/devflow/control_room/loop_command.py tests/test_loop_e2e_harness.py
```
