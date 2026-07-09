"""Deterministic end-to-end harness for the V2 loop spine.

This module proves the clean V2 loop adapters compose into one product loop:
idea -> definition -> spec -> planning -> planning_judge -> assignment ->
build_judge -> verification -> human_decision -> complete.

No model calls. No worker subprocesses. No shell execution.
"""
from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

from pydantic import BaseModel, Field

from devflow.loop.pipeline_run import load_pipeline_run, update_pipeline_run_record
from devflow.loop.adapter import create_run_with_state, load_loop_state, save_loop_state
from devflow.loop.builder_judge import (
    BuilderJudgeAssignment,
    prepare_builder_judge_assignment,
    record_builder_judge_result,
)
from devflow.loop.human_decision import HumanDecision, HumanDecisionRecord, record_human_decision
from devflow.loop.models import LoopStage, advance_stage
from devflow.loop.orient import run_orient
from devflow.loop.planning_judge import PlanningEvidence, run_planning_judge
from devflow.loop.verification import VerificationReceipt, VerificationStatus, record_verification_receipt


DEFAULT_FIXTURE_TARGET = "src/devflow/loop/models.py"
EXPECTED_STAGE_CHAIN = [
    LoopStage.idea,
    LoopStage.definition,
    LoopStage.spec,
    LoopStage.planning,
    LoopStage.planning_judge,
    LoopStage.assignment,
    LoopStage.build_judge,
    LoopStage.verification,
    LoopStage.human_decision,
    LoopStage.complete,
]


class E2ELoopHarnessReport(BaseModel):
    """Compact report from a deterministic V2 loop harness run."""

    run_id: str
    final_stage: LoopStage
    expected_stage_chain: list[LoopStage] = Field(default_factory=list)
    observed_stage_chain: list[LoopStage] = Field(default_factory=list)
    evidence_files: list[str] = Field(default_factory=list)
    target_file: str
    verification_command: str


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _assert_target_exists(root: Path, target_file: str) -> None:
    target = (root / target_file).resolve()
    root_resolved = root.resolve()
    try:
        target.relative_to(root_resolved)
    except ValueError as exc:
        raise ValueError(f"Target file escapes root: {target_file}") from exc
    if not target.is_file():
        raise FileNotFoundError(f"Fixture target file does not exist: {target_file}")


def _advance_and_save(root: Path, run_id: str, stage: LoopStage) -> LoopStage:
    state = load_loop_state(root, run_id)
    state = advance_stage(state, stage)
    save_loop_state(root, state)
    return state.stage


def _write_fixture_definition_artifacts(root: Path, run_id: str, target_file: str) -> None:
    spec_md = "\n".join(
        [
            "# Fixture Spec",
            "",
            "Deterministic V2 loop harness spec.",
            "",
            f"Target file: `{target_file}`",
            "",
        ]
    )
    plan_md = "\n".join(
        [
            "# Fixture Plan",
            "",
            "1. Run orient/scout adapter.",
            "2. Approve planning judge evidence.",
            "3. Link builder/judge and record pass.",
            "4. Record verification pass and human acceptance.",
            "",
        ]
    )
    update_pipeline_run_record(root, run_id, "fixture-spec.md", spec_md)
    update_pipeline_run_record(root, run_id, "fixture-plan.md", plan_md)

    state = load_loop_state(root, run_id)
    state = state.model_copy(
        update={
            "spec_path": "fixture-spec.md",
            "plan_path": "fixture-plan.md",
        }
    )
    save_loop_state(root, state)


def _evidence_files(root: Path, run_id: str) -> list[str]:
    data = load_pipeline_run(root, run_id)
    return sorted(data.keys())


def run_e2e_loop_harness(
    root: Path | str,
    *,
    target_file: str = DEFAULT_FIXTURE_TARGET,
    verification_command: str = "PYTHONPATH=src:. python -m pytest tests/test_loop_models.py -q",
) -> E2ELoopHarnessReport:
    """Run the V2 loop spine end-to-end against deterministic fixture evidence."""
    root_path = Path(root)
    _assert_target_exists(root_path, target_file)

    run_id, initial_state = create_run_with_state(
        root_path,
        {
            "fixture": "v2-e2e-loop-harness",
            "target_file": target_file,
        },
    )
    observed = [initial_state.stage]

    state, orient = run_orient(root_path, run_id, files_to_touch=[target_file])
    if not orient.ready:
        raise RuntimeError("Orient fixture did not become ready; cannot continue E2E harness.")
    observed.append(state.stage)

    _write_fixture_definition_artifacts(root_path, run_id, target_file)
    observed.append(_advance_and_save(root_path, run_id, LoopStage.spec))
    observed.append(_advance_and_save(root_path, run_id, LoopStage.planning))
    observed.append(_advance_and_save(root_path, run_id, LoopStage.planning_judge))

    planning_evidence = PlanningEvidence(
        run_id=run_id,
        plan_path="fixture-plan.md",
        spec_path="fixture-spec.md",
        target_files=[target_file],
        verification_command=verification_command,
        constraints=["deterministic_fixture_only", "no_model_calls"],
        files_exist=True,
        has_verification=True,
    )
    state, _planning_report = run_planning_judge(root_path, run_id, planning_evidence)
    observed.append(state.stage)

    assignment = BuilderJudgeAssignment(
        run_id=run_id,
        assignment_id="fixture-assignment",
        definition_of_done="Deterministic fixture passes through builder/judge link.",
        target_files=[target_file],
        verification_command=verification_command,
        builder_judge_run_id="fixture-builder-judge",
    )
    state, _link = prepare_builder_judge_assignment(root_path, assignment)
    observed.append(state.stage)

    state, _result_link = record_builder_judge_result(
        root_path,
        run_id,
        builder_judge_run_id="fixture-builder-judge",
        status="passed",
        evidence_path="builder-judge-link.json",
    )
    observed.append(state.stage)

    receipt = VerificationReceipt(
        run_id=run_id,
        receipt_id="fixture-verification",
        status=VerificationStatus.passed,
        command=verification_command,
        summary="Deterministic fixture verification passed.",
        evidence_path="verification-receipt-fixture-verification.json",
        exit_code=0,
        created_at=_utc_now(),
    )
    state, _receipt = record_verification_receipt(root_path, receipt)
    observed.append(state.stage)

    decision = HumanDecisionRecord(
        run_id=run_id,
        decision_id="fixture-human-acceptance",
        decision=HumanDecision.accept,
        summary="Accepted deterministic V2 loop fixture.",
        notes="No model calls or worker subprocesses were used.",
        created_at=_utc_now(),
    )
    state, _decision = record_human_decision(root_path, decision)
    observed.append(state.stage)

    return E2ELoopHarnessReport(
        run_id=run_id,
        final_stage=state.stage,
        expected_stage_chain=list(EXPECTED_STAGE_CHAIN),
        observed_stage_chain=observed,
        evidence_files=_evidence_files(root_path, run_id),
        target_file=target_file,
        verification_command=verification_command,
    )
