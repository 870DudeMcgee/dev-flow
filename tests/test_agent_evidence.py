from __future__ import annotations

import json
from pathlib import Path

from typer.testing import CliRunner

from devflow.cli import app
from devflow.control_room.agent_evidence import summarize_agent_evidence
from devflow.control_room.service import create_task
from devflow.control_room.worker_evidence import write_worker_evidence


runner = CliRunner()


def test_summarize_agent_evidence_reports_local_model_runs(tmp_path: Path) -> None:
    task = create_task(tmp_path, "Evidence summary")
    write_worker_evidence(
        root=tmp_path,
        worker_type="local_model",
        profile_id="local-gemma4-qat",
        worker_id="local-gemma4-qat",
        task_id=task.id,
        run_id="run-1",
        packet_text="packet",
        raw_output="raw",
        response_text="response",
        model="gemma4:12b-it-qat",
        adapter="ollama_chat",
        adapter_maturity="local_patch_runtime",
        permission_mode="read_only",
        hermes_delegable=False,
        runtime="ollama",
        status="succeeded",
        started_at="2026-06-13T00:00:00Z",
    )

    summary = summarize_agent_evidence(tmp_path, task.id)

    assert summary.task_id == task.id
    assert summary.has_worker_evidence is True
    assert summary.local_model_runs[0].worker_id == "local-gemma4-qat"
    assert summary.next_safe_action == "review worker evidence before verification or promotion"


def test_agent_evidence_cli_is_read_only_json(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    assert runner.invoke(app, ["task", "create", "Evidence CLI"]).exit_code == 0
    task_yaml = Path(".devflow/tasks/task-0001/task.yaml").read_text(encoding="utf-8")

    result = runner.invoke(app, ["agent", "evidence", "task-0001", "--json"])

    assert result.exit_code == 0, result.output
    payload = json.loads(result.output)
    assert payload["task_id"] == "task-0001"
    assert Path(".devflow/tasks/task-0001/task.yaml").read_text(encoding="utf-8") == task_yaml
