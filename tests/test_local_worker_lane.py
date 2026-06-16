from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

from typer.testing import CliRunner

from devflow.cli import app
from devflow.control_room.local_worker_lane import local_worker_lane_summary
from devflow.control_room.models import TaskRecord
from devflow.control_room.worker_evidence import write_worker_evidence


runner = CliRunner()


def _task(task_id: str = "task-0001", *, verification_status: str = "not_run") -> TaskRecord:
    now = datetime(2026, 6, 14, tzinfo=timezone.utc)
    return TaskRecord(
        id=task_id,
        title="local worker lane",
        status="created",
        created_at=now,
        updated_at=now,
        worker="shell",
        workspace=f".devflow/workspaces/{task_id}",
        workspace_path=f".devflow/workspaces/{task_id}",
        verification_status=verification_status,
    )


def _write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def test_local_worker_lane_summary_reports_patch_worker_next_action(tmp_path: Path) -> None:
    task = _task()
    agent_dir = tmp_path / ".devflow/tasks/task-0001/agents/qwopus-implementer"
    _write_json(
        agent_dir / "run.json",
        {
            "schema_version": 1,
            "task_id": "task-0001",
            "agent_id": "qwopus-implementer",
            "status": "complete",
            "model": "qwopus:latest",
            "adapter": "ollama_chat",
            "proposal_patch_found": True,
            "proposal_patch_path": ".devflow/tasks/task-0001/agents/qwopus-implementer/proposal.patch",
            "proposal_patch_byte_length": 42,
            "proposed_file_count": 1,
            "proposed_file_paths": ["hello.txt"],
        },
    )
    (agent_dir / "proposal.patch").write_text("diff --git a/hello.txt b/hello.txt\n", encoding="utf-8")
    (agent_dir / "result.md").write_text("Patch proposed\n", encoding="utf-8")
    (agent_dir / "logs").mkdir(parents=True, exist_ok=True)
    (agent_dir / "logs/worker.log").write_text("ok\n", encoding="utf-8")

    summary = local_worker_lane_summary(tmp_path, task)

    assert summary is not None
    assert summary["lane_type"] == "local-patch-worker"
    assert summary["worker_id"] == "qwopus-implementer"
    assert summary["latest_status"] == "complete"
    assert summary["patch_candidate"] is True
    assert summary["readiness_status"] == "needs_review"
    assert summary["next_safe_action"] == "devflow task review-patch task-0001 --agent qwopus-implementer"
    assert ".devflow/tasks/task-0001/agents/qwopus-implementer/run.json" in summary["evidence_paths"]


def test_local_worker_lane_summary_reports_read_only_worker_pool_run(tmp_path: Path) -> None:
    task = _task()
    write_worker_evidence(
        root=tmp_path,
        worker_type="local_model_worker_pool",
        profile_id="local-qwopus-inspector",
        worker_id="local-qwopus-inspector",
        task_id="task-0001",
        run_id="run-1",
        packet_text="packet",
        raw_output="raw",
        response_text="response",
        model="qwopus:latest",
        adapter="ollama_chat",
        adapter_maturity="local_patch_runtime",
        permission_mode="read_only",
        hermes_delegable=True,
        runtime="local_model_client",
        status="success",
        started_at="2026-06-14T00:00:00+00:00",
        quality_notes="useful",
        quality_score=0.85,
    )

    summary = local_worker_lane_summary(tmp_path, task)

    assert summary is not None
    assert summary["lane_type"] == "local-model-worker-pool"
    assert summary["worker_id"] == "local-qwopus-inspector"
    assert summary["permission_mode"] == "read_only"
    assert summary["patch_candidate"] is False
    assert summary["readiness_status"] == "needs_review"
    assert summary["next_safe_action"] == "devflow agent evidence task-0001 --json"
    assert ".devflow/tasks/task-0001/local-model-runs/run-1/run.json" in summary["evidence_paths"]


def test_task_show_includes_local_worker_lane_summary(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    result = runner.invoke(app, ["task", "create", "local lane"])
    assert result.exit_code == 0, result.output
    agent_dir = tmp_path / ".devflow/tasks/task-0001/agents/qwopus-implementer"
    _write_json(
        agent_dir / "run.json",
        {
            "schema_version": 1,
            "task_id": "task-0001",
            "agent_id": "qwopus-implementer",
            "status": "complete",
            "model": "qwopus:latest",
            "adapter": "ollama_chat",
            "proposal_patch_found": True,
            "proposal_patch_path": ".devflow/tasks/task-0001/agents/qwopus-implementer/proposal.patch",
        },
    )
    (agent_dir / "proposal.patch").write_text("diff --git a/hello.txt b/hello.txt\n", encoding="utf-8")

    show = runner.invoke(app, ["task", "show", "task-0001"])

    assert show.exit_code == 0, show.output
    assert "local_worker_lane: local-patch-worker" in show.output
    assert "local_worker: qwopus-implementer" in show.output
    assert "local_worker_readiness: needs_review" in show.output
    assert "local_worker_next_action: devflow task review-patch task-0001 --agent qwopus-implementer" in show.output


def test_openrouter_style_run_json_without_proposal_patch_found(tmp_path: Path) -> None:
    task = _task()
    agent_dir = tmp_path / ".devflow/tasks/task-0001/agents/openrouter-proposer"
    _write_json(
        agent_dir / "run.json",
        {
            "schema_version": 1,
            "task_id": "task-0001",
            "agent_id": "openrouter-proposer",
            "status": "success",
            "model": "deepseek-v4-pro",
            "adapter": "openai_compatible",
            "proposal_patch_path": ".devflow/tasks/task-0001/agents/openrouter-proposer/proposal.patch",
        },
    )
    (agent_dir / "proposal.patch").write_text("diff --git a/hello.txt b/hello.txt\n", encoding="utf-8")
    (agent_dir / "result.md").write_text("Patch proposed\n", encoding="utf-8")
    (agent_dir / "logs").mkdir(parents=True, exist_ok=True)
    (agent_dir / "logs/worker.log").write_text("ok\n", encoding="utf-8")

    summary = local_worker_lane_summary(tmp_path, task)

    assert summary is not None
    assert summary["lane_type"] == "local-patch-worker"
    assert summary["worker_id"] == "openrouter-proposer"
    assert summary["latest_status"] == "success"
    assert summary["patch_candidate"] is True
    assert summary["readiness_status"] == "needs_review"
    assert summary["next_safe_action"].startswith("devflow task review-patch task-0001 --agent openrouter-proposer")

def test_review_ready_includes_local_worker_lane_summary(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    result = runner.invoke(app, ["task", "create", "local lane"])
    assert result.exit_code == 0, result.output
    agent_dir = tmp_path / ".devflow/tasks/task-0001/agents/qwopus-implementer"
    _write_json(
        agent_dir / "run.json",
        {
            "schema_version": 1,
            "task_id": "task-0001",
            "agent_id": "qwopus-implementer",
            "status": "complete",
            "model": "qwopus:latest",
            "adapter": "ollama_chat",
            "proposal_patch_found": True,
        },
    )
    (agent_dir / "proposal.patch").write_text("diff --git a/hello.txt b/hello.txt\n", encoding="utf-8")

    review = runner.invoke(app, ["task", "review-ready", "task-0001", "--json"])

    assert review.exit_code == 0, review.output
    payload = json.loads(review.output)
    assert payload["local_worker_lane"] == "local-patch-worker"
    assert payload["local_worker"] == "qwopus-implementer"
    assert payload["local_worker_readiness"] == "needs_review"
    assert payload["local_worker_next_action"] == "devflow task review-patch task-0001 --agent qwopus-implementer"
    assert ".devflow/tasks/task-0001/agents/qwopus-implementer/run.json" in payload["evidence"]


def test_agent_evidence_json_includes_local_worker_lane_summary(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    result = runner.invoke(app, ["task", "create", "local lane"])
    assert result.exit_code == 0, result.output
    agent_dir = tmp_path / ".devflow/tasks/task-0001/agents/qwopus-implementer"
    _write_json(
        agent_dir / "run.json",
        {
            "schema_version": 1,
            "task_id": "task-0001",
            "agent_id": "qwopus-implementer",
            "status": "complete",
            "proposal_patch_found": True,
        },
    )
    (agent_dir / "proposal.patch").write_text("diff --git a/hello.txt b/hello.txt\n", encoding="utf-8")

    evidence = runner.invoke(app, ["agent", "evidence", "task-0001", "--json"])

    assert evidence.exit_code == 0, evidence.output
    payload = json.loads(evidence.output)
    assert payload["local_worker_lane"]["lane_type"] == "local-patch-worker"
    assert payload["local_worker_lane"]["worker_id"] == "qwopus-implementer"
    assert payload["local_worker_lane"]["readiness_status"] == "needs_review"
    assert (
        payload["local_worker_lane"]["next_safe_action"]
        == "devflow task review-patch task-0001 --agent qwopus-implementer"
    )


def test_local_worker_lane_summary_reports_failed_worker_recovery(tmp_path: Path) -> None:
    task = _task()
    agent_dir = tmp_path / ".devflow/tasks/task-0001/agents/qwopus-implementer"
    _write_json(
        agent_dir / "run.json",
        {
            "schema_version": 1,
            "task_id": "task-0001",
            "agent_id": "qwopus-implementer",
            "status": "failed",
            "summary": "model missing",
            "proposal_patch_found": False,
        },
    )

    summary = local_worker_lane_summary(tmp_path, task)

    assert summary is not None
    assert summary["readiness_status"] == "failed"
    assert "model missing" in summary["readiness_errors"]
    assert summary["next_safe_action"] == "devflow task escalation-packet task-0001 --agent qwopus-implementer"


def test_local_worker_lane_summary_reports_malformed_run_recovery(tmp_path: Path) -> None:
    task = _task()
    agent_dir = tmp_path / ".devflow/tasks/task-0001/agents/qwopus-implementer"
    agent_dir.mkdir(parents=True, exist_ok=True)
    (agent_dir / "run.json").write_text("{not json", encoding="utf-8")

    summary = local_worker_lane_summary(tmp_path, task)

    assert summary is not None
    assert summary["worker_id"] == "qwopus-implementer"
    assert summary["readiness_status"] == "failed"
    assert any("invalid run.json" in error for error in summary["readiness_errors"])
    assert summary["next_safe_action"] == "devflow task escalation-packet task-0001 --agent qwopus-implementer"


def test_local_worker_lane_summary_reports_patch_ladder_states(tmp_path: Path) -> None:
    agent_dir = tmp_path / ".devflow/tasks/task-0001/agents/qwopus-implementer"
    _write_json(
        agent_dir / "run.json",
        {"agent_id": "qwopus-implementer", "status": "complete", "proposal_patch_found": True},
    )
    (agent_dir / "proposal.patch").write_text("diff --git a/a.txt b/a.txt\n", encoding="utf-8")

    _write_json(
        tmp_path / ".devflow/tasks/task-0001/local-model-runs/run-1/patch-review.json",
        {"review_status": "low_risk_candidate"},
    )
    summary = local_worker_lane_summary(tmp_path, _task())
    assert summary is not None
    assert summary["readiness_status"] == "needs_dry_run"
    assert summary["next_safe_action"] == "devflow task patch-dry-run task-0001 --agent qwopus-implementer"

    _write_json(
        tmp_path / ".devflow/tasks/task-0001/local-model-runs/run-2/patch-dry-run.json",
        {"dry_run_status": "would_apply_cleanly"},
    )
    summary = local_worker_lane_summary(tmp_path, _task())
    assert summary is not None
    assert summary["readiness_status"] == "needs_apply"
    assert summary["next_safe_action"] == "devflow task apply-patch task-0001 --agent qwopus-implementer"

    _write_json(tmp_path / ".devflow/tasks/task-0001/patch-application.json", {"status": "applied"})
    summary = local_worker_lane_summary(tmp_path, _task())
    assert summary is not None
    assert summary["readiness_status"] == "needs_verification"
    assert summary["next_safe_action"] == 'devflow task verify task-0001 --shell "<command>"'

    summary = local_worker_lane_summary(tmp_path, _task(verification_status="passed"))
    assert summary is not None
    assert summary["readiness_status"] == "needs_promotion_preview"
    assert summary["next_safe_action"] == "devflow task promote-preview task-0001"

    _write_json(tmp_path / ".devflow/tasks/task-0001/promotion-preview.json", {"promotion_readiness": "ready"})
    summary = local_worker_lane_summary(tmp_path, _task(verification_status="passed"))
    assert summary is not None
    assert summary["readiness_status"] == "ready"
    assert summary["next_safe_action"] == "devflow task promote task-0001"
