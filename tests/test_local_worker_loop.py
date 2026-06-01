from __future__ import annotations

import json
import subprocess
from pathlib import Path
from typing import Any
from unittest.mock import patch

from typer.testing import CliRunner

from devflow.cli import app
from devflow.control_room.service import get_task
from devflow.control_room.scorecard import generate_scorecard


runner = CliRunner()


def _create_task(title: str) -> None:
    result = runner.invoke(app, ["task", "create", title])
    assert result.exit_code == 0, result.output


def test_qwen_implementer_prompt_composition(tmp_path: Path, monkeypatch: Any) -> None:
    monkeypatch.chdir(tmp_path)
    _create_task("Implement feature")

    with patch("devflow.control_room.local_ollama_worker.subprocess.run") as run_mock:
        run_mock.return_value = subprocess.CompletedProcess(
            ["ollama", "run", "qwen3.6:latest"],
            0,
            stdout="implementer response content",
            stderr="",
        )

        # Test agent parameter works as an alias for worker
        result = runner.invoke(app, ["task", "local", "task-0001", "--agent", "qwen-implementer"])

    assert result.exit_code == 1, "Should fail because planner output is missing"
    assert "Missing input worker output: .devflow/workspaces/task-0001/local-workers/qwen-planner/response.md" in result.output

    # Now create qwen-planner output
    planner_dir = tmp_path / ".devflow" / "workspaces" / "task-0001" / "local-workers" / "qwen-planner"
    planner_dir.mkdir(parents=True, exist_ok=True)
    (planner_dir / "response.md").write_text("planner plan", encoding="utf-8")

    with patch("devflow.control_room.local_ollama_worker.subprocess.run") as run_mock:
        run_mock.return_value = subprocess.CompletedProcess(
            ["ollama", "run", "qwen3.6:latest"],
            0,
            stdout="implementer response content",
            stderr="",
        )

        result = runner.invoke(app, ["task", "local", "task-0001", "--agent", "qwen-implementer"])

    assert result.exit_code == 0, result.output
    assert "Legacy Local Ollama Advisory Evidence Captured!" in result.output
    assert "local_worker_mode: legacy_advisory" in result.output
    assert "Suggested Next Action:" in result.output
    assert "devflow task local task-0001 --agent gemma-reviewer" in result.output

    from devflow.control_room.local_ollama_worker import find_latest_worker_evidence
    workspace = tmp_path / ".devflow" / "workspaces" / "task-0001"
    run_dir, _ = find_latest_worker_evidence(workspace, "qwen-implementer")
    assert run_dir is not None
    prompt_path = run_dir / "prompt.md"
    prompt = prompt_path.read_text(encoding="utf-8")
    assert "Worker: qwen-implementer" in prompt
    assert "Input worker: qwen-planner" in prompt
    assert "planner plan" in prompt
    assert "Unified diff or patch proposal of proposed changes" in prompt


def test_gemma_reviewer_dynamic_fallback(tmp_path: Path, monkeypatch: Any) -> None:
    monkeypatch.chdir(tmp_path)
    _create_task("Review feature")

    # If only planner output exists, gemma-reviewer falls back to planner
    planner_dir = tmp_path / ".devflow" / "workspaces" / "task-0001" / "local-workers" / "qwen-planner"
    planner_dir.mkdir(parents=True, exist_ok=True)
    (planner_dir / "response.md").write_text("planner plan", encoding="utf-8")

    with patch("devflow.control_room.local_ollama_worker.subprocess.run") as run_mock:
        run_mock.return_value = subprocess.CompletedProcess(
            ["ollama", "run", "gemma4:latest"],
            0,
            stdout="review approved",
            stderr="",
        )
        result = runner.invoke(app, ["task", "local", "task-0001", "--agent", "gemma-reviewer"])

    assert result.exit_code == 0, result.output
    from devflow.control_room.local_ollama_worker import find_latest_worker_evidence
    workspace = tmp_path / ".devflow" / "workspaces" / "task-0001"
    run_dir, _ = find_latest_worker_evidence(workspace, "gemma-reviewer")
    assert run_dir is not None
    prompt_path = run_dir / "prompt.md"
    prompt = prompt_path.read_text(encoding="utf-8")
    assert "Input worker: qwen-planner" in prompt
    assert "planner plan" in prompt

    # If implementer output also exists, gemma-reviewer reviews implementer
    impl_dir = tmp_path / ".devflow" / "workspaces" / "task-0001" / "local-workers" / "qwen-implementer"
    impl_dir.mkdir(parents=True, exist_ok=True)
    (impl_dir / "response.md").write_text("implementer code changes", encoding="utf-8")

    with patch("devflow.control_room.local_ollama_worker.subprocess.run") as run_mock:
        run_mock.return_value = subprocess.CompletedProcess(
            ["ollama", "run", "gemma4:latest"],
            0,
            stdout="review approved",
            stderr="",
        )
        result = runner.invoke(app, ["task", "local", "task-0001", "--agent", "gemma-reviewer"])

    assert result.exit_code == 0, result.output
    workspace = tmp_path / ".devflow" / "workspaces" / "task-0001"
    run_dir, _ = find_latest_worker_evidence(workspace, "gemma-reviewer")
    assert run_dir is not None
    prompt_path = run_dir / "prompt.md"
    prompt = prompt_path.read_text(encoding="utf-8")
    assert "Input worker: qwen-implementer" in prompt
    assert "implementer code changes" in prompt


def test_scorecard_frontier_escalation_avoided(tmp_path: Path, monkeypatch: Any) -> None:
    monkeypatch.chdir(tmp_path)
    _create_task("Scorecard test")

    # Set up events.jsonl with a successful local worker finish event
    task_dir = tmp_path / ".devflow" / "tasks" / "task-0001"
    events_file = task_dir / "events.jsonl"
    events_file.write_text(
        json.dumps({"event": "local_worker_finished", "worker_name": "qwen-planner", "status": "success"}) + "\n",
        encoding="utf-8"
    )

    # Trigger scorecard calculation
    monkeypatch.setenv("DEVFLOW_EXPERIMENTAL", "1")
    result = runner.invoke(app, ["task", "scorecard", "task-0001"])
    assert result.exit_code == 0, result.output
    assert "Frontier Escalation Avoided: yes" in result.output

    # Verify escalation avoided is false if escalation event is present
    events_file.write_text(
        json.dumps({"event": "local_worker_finished", "worker_name": "qwen-planner", "status": "success"}) + "\n" +
        json.dumps({"event": "escalate_to_frontier", "reason": "local failure"}) + "\n",
        encoding="utf-8"
    )
    result = runner.invoke(app, ["task", "scorecard", "task-0001"])
    assert result.exit_code == 0, result.output
    assert "Frontier Escalation Avoided: no" in result.output


def test_qwopus_registry_and_prompt_composition(tmp_path: Path, monkeypatch: Any) -> None:
    monkeypatch.chdir(tmp_path)
    _create_task("Qwopus test task")

    # 1. Registry test: Prove qwopus-implementer exists in the local worker registry.
    from devflow.control_room.local_ollama_worker import get_local_worker_definition
    definition = get_local_worker_definition("qwopus-implementer")
    assert definition.name == "qwopus-implementer"
    assert definition.model == "qwopus:latest"
    assert definition.role == "legacy advisory implementation scout; canonical patch worker is task run --worker qwopus-implementer"

    # Now create qwen-planner output
    planner_dir = tmp_path / ".devflow" / "workspaces" / "task-0001" / "local-workers" / "qwen-planner"
    planner_dir.mkdir(parents=True, exist_ok=True)
    (planner_dir / "response.md").write_text("planner plan", encoding="utf-8")

    # 3. CLI test & 4. Evidence path test
    with patch("devflow.control_room.local_ollama_worker.subprocess.run") as run_mock:
        run_mock.return_value = subprocess.CompletedProcess(
            ["ollama", "run", "qwopus:latest"],
            0,
            stdout="qwopus patch proposal",
            stderr="",
        )

        result = runner.invoke(app, ["task", "local", "task-0001", "--agent", "qwopus-implementer"])

    assert result.exit_code == 0, result.output
    assert "Legacy Local Ollama Advisory Evidence Captured!" in result.output
    assert "This was advisory-only qwopus output." in result.output
    assert "qwopus-implementer" in result.output

    from devflow.control_room.local_ollama_worker import find_latest_worker_evidence
    workspace = tmp_path / ".devflow" / "workspaces" / "task-0001"
    run_dir, _ = find_latest_worker_evidence(workspace, "qwopus-implementer")
    assert run_dir is not None
    # Prove Qwopus output is written under the run-ID evidence path:
    # .devflow/workspaces/<task-id>/local-workers/qwopus-implementer/<run-id>/
    assert "local-workers/qwopus-implementer/run_" in str(run_dir)

    # 2. Prompt test: Prove qwopus-implementer prompt is implementation/patch-proposal focused
    prompt_path = run_dir / "prompt.md"
    prompt = prompt_path.read_text(encoding="utf-8")
    assert "Worker: qwopus-implementer" in prompt
    assert "Input worker: qwen-planner" in prompt
    assert "1. Brief task understanding" in prompt
    assert "2. Relevant files likely to change" in prompt
    assert "3. Proposed implementation approach" in prompt
    assert "4. Unified diff of proposed changes if enough context is present" in prompt
    assert "5. Changed-file summary" in prompt
    assert "6. Focused pytest commands to run for verification" in prompt
    assert "7. Risks and assumptions" in prompt
    assert "8. Explicit reminder that this output is advisory evidence only and must not be applied automatically" in prompt

    # 8. Non-authority test: Prove a Qwopus local evidence run does not mark the task verified, promotion-ready, committed, merged, or applied.
    task = get_task(tmp_path, "task-0001")
    assert task.status == "complete"  # local runs set task status to complete/worker_failed/timeout, not verified or promoted
    assert task.verification_status == "not_run"


def test_reviewer_fallback_order_for_qwopus(tmp_path: Path, monkeypatch: Any) -> None:
    monkeypatch.chdir(tmp_path)
    _create_task("Reviewer fallback order task")

    planner_dir = tmp_path / ".devflow" / "workspaces" / "task-0001" / "local-workers" / "qwen-planner"
    planner_dir.mkdir(parents=True, exist_ok=True)
    (planner_dir / "response.md").write_text("planner plan", encoding="utf-8")

    impl_dir = tmp_path / ".devflow" / "workspaces" / "task-0001" / "local-workers" / "qwen-implementer"
    impl_dir.mkdir(parents=True, exist_ok=True)
    (impl_dir / "response.md").write_text("qwen implementer plan", encoding="utf-8")

    qwopus_dir = tmp_path / ".devflow" / "workspaces" / "task-0001" / "local-workers" / "qwopus-implementer"
    qwopus_dir.mkdir(parents=True, exist_ok=True)
    (qwopus_dir / "response.md").write_text("qwopus implementer plan", encoding="utf-8")

    # 5. Reviewer fallback test: If both Qwopus and Qwen implementer evidence exist, gemma-reviewer should consume latest Qwopus evidence first.
    with patch("devflow.control_room.local_ollama_worker.subprocess.run") as run_mock:
        run_mock.return_value = subprocess.CompletedProcess(
            ["ollama", "run", "gemma4:latest"],
            0,
            stdout="review approved",
            stderr="",
        )
        result = runner.invoke(app, ["task", "local", "task-0001", "--agent", "gemma-reviewer"])

    assert result.exit_code == 0, result.output
    from devflow.control_room.local_ollama_worker import find_latest_worker_evidence
    workspace = tmp_path / ".devflow" / "workspaces" / "task-0001"
    run_dir, _ = find_latest_worker_evidence(workspace, "gemma-reviewer")
    assert run_dir is not None
    prompt = (run_dir / "prompt.md").read_text(encoding="utf-8")
    assert "Input worker: qwopus-implementer" in prompt
    assert "qwopus implementer plan" in prompt

    # 6. Fallback preservation test: If Qwopus evidence does not exist but Qwen implementer evidence does, gemma-reviewer should still consume Qwen implementer evidence.
    import shutil
    shutil.rmtree(qwopus_dir)

    with patch("devflow.control_room.local_ollama_worker.subprocess.run") as run_mock:
        run_mock.return_value = subprocess.CompletedProcess(
            ["ollama", "run", "gemma4:latest"],
            0,
            stdout="review approved",
            stderr="",
        )
        result = runner.invoke(app, ["task", "local", "task-0001", "--agent", "gemma-reviewer"])

    assert result.exit_code == 0, result.output
    workspace = tmp_path / ".devflow" / "workspaces" / "task-0001"
    run_dir, _ = find_latest_worker_evidence(workspace, "gemma-reviewer")
    assert run_dir is not None
    prompt = (run_dir / "prompt.md").read_text(encoding="utf-8")
    assert "Input worker: qwen-implementer" in prompt
    assert "qwen implementer plan" in prompt

    # 7. Legacy fallback test: If no implementer evidence exists, gemma-reviewer should still fall back to planner evidence.
    shutil.rmtree(impl_dir)

    with patch("devflow.control_room.local_ollama_worker.subprocess.run") as run_mock:
        run_mock.return_value = subprocess.CompletedProcess(
            ["ollama", "run", "gemma4:latest"],
            0,
            stdout="review approved",
            stderr="",
        )
        result = runner.invoke(app, ["task", "local", "task-0001", "--agent", "gemma-reviewer"])

    assert result.exit_code == 0, result.output
    workspace = tmp_path / ".devflow" / "workspaces" / "task-0001"
    run_dir, _ = find_latest_worker_evidence(workspace, "gemma-reviewer")
    assert run_dir is not None
    prompt = (run_dir / "prompt.md").read_text(encoding="utf-8")
    assert "Input worker: qwen-planner" in prompt
    assert "planner plan" in prompt
