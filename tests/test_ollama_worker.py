from __future__ import annotations

import json
import os
import subprocess
from io import BytesIO
from pathlib import Path
from unittest.mock import patch, MagicMock
import urllib.error

import pytest
from typer.testing import CliRunner

from devflow.cli import app
from devflow.control_room.worker_adapter import UnsupportedWorkerAdapter, get_worker_adapter
from devflow.control_room.models import WorkerInput
from devflow.control_room.ollama_worker import OllamaChatWorkerAdapter
from devflow.control_room.agent_registry import AgentDefinition, ProviderDefinition
from devflow.control_room.service import apply_task_patch, create_task, run_shell_task


runner = CliRunner()


def test_get_ollama_chat_worker_adapter_rejects_direct_runtime() -> None:
    with pytest.raises(UnsupportedWorkerAdapter, match="local_patch_runtime"):
        get_worker_adapter("ollama_chat")


def test_get_ollama_chat_worker_adapter_allows_safe_local_patch_agent() -> None:
    agent = AgentDefinition(
        id="qwopus-implementer",
        provider="ollama",
        model="qwopus:latest",
        adapter="ollama_chat",
        role="implementation_worker",
        tier="strong_local",
        default_mode="workspace_write",
        execution_mode="automated",
        workspace="isolated_task_workspace",
        can_run_shell=False,
        can_use_network=False,
        can_promote=False,
        enabled=True,
    )
    provider = ProviderDefinition(
        id="ollama",
        provider="ollama",
        adapter="ollama_chat",
        base_url="http://127.0.0.1:11434",
        default_timeout_seconds=600,
        enabled=True,
    )

    adapter = get_worker_adapter("ollama_chat", agent=agent, provider=provider)

    assert isinstance(adapter, OllamaChatWorkerAdapter)


def test_ollama_worker_success(tmp_path: Path) -> None:
    # Initialize mock git repository in tmp_path
    subprocess.run(["git", "init"], cwd=tmp_path, capture_output=True)
    subprocess.run(["git", "config", "user.email", "test@example.com"], cwd=tmp_path, capture_output=True)
    subprocess.run(["git", "config", "user.name", "Test User"], cwd=tmp_path, capture_output=True)

    # Write a test file and commit it
    test_file = tmp_path / "hello.txt"
    test_file.write_text("Hello World\n", encoding="utf-8")
    subprocess.run(["git", "add", "hello.txt"], cwd=tmp_path, capture_output=True)
    subprocess.run(["git", "commit", "-m", "initial commit"], cwd=tmp_path, capture_output=True)

    # Set up task directories
    task_dir = tmp_path / ".devflow" / "tasks" / "task-ollama-1"
    task_dir.mkdir(parents=True)
    (task_dir / "logs").mkdir(parents=True)

    # Write task.yaml
    (task_dir / "task.yaml").write_text("id: task-ollama-1\ntitle: Test Task\nstatus: created\n", encoding="utf-8")

    # Set up workspace (copy hello.txt to workspace)
    workspace_path = tmp_path / ".devflow" / "workspaces" / "task-ollama-1"
    workspace_path.mkdir(parents=True)
    (workspace_path / "hello.txt").write_text("Hello World\n", encoding="utf-8")

    log_file = task_dir / "logs" / "worker.log"
    result_file = task_dir / "result.md"

    worker_input = WorkerInput(
        task_id="task-ollama-1",
        repo_root=tmp_path,
        workspace_path=workspace_path,
        task_file=task_dir / "task.yaml",
        context_file=task_dir / "events.jsonl",
        status_file=task_dir / "task.yaml",
        questions_file=task_dir / "questions.jsonl",
        result_file=result_file,
        log_file=log_file,
        command=["ollama", "task"],
        timeout_seconds=60,
    )

    # Set up context pack JSON so build_context_pack or loading finds it
    context_pack_data = {
        "context_pack": {
            "role": "worker",
            "context_layer": "L1",
            "includes": [],
            "excludes": [],
            "estimated_tokens": 100,
            "sources_metadata": [
                {
                    "path": "hello.txt",
                    "authority": "canonical",
                    "mode": "full",
                    "content": "Hello World\n"
                }
            ]
        }
    }
    (task_dir / "context-pack-worker.json").write_text(json.dumps(context_pack_data), encoding="utf-8")

    # Mock Ollama HTTP response returning a clean ready diff
    mock_response = MagicMock()
    response_dict = {
        "response": json.dumps({
            "status": "ready",
            "diff": "diff --git a/hello.txt b/hello.txt\n--- a/hello.txt\n+++ b/hello.txt\n@@ -1 +1 @@\n-Hello World\n+Hello beautiful World\n",
            "touched_paths": ["hello.txt"],
            "risk": "low",
            "confidence": 0.95
        })
    }
    mock_response.read.return_value = json.dumps(response_dict).encode("utf-8")

    adapter = OllamaChatWorkerAdapter()

    # Stub build_context_pack to return our dummy pack
    with patch("urllib.request.urlopen") as mock_urlopen, \
         patch("devflow.control_room.ollama_worker.build_context_pack", return_value=context_pack_data):
        mock_urlopen.return_value.__enter__.return_value = mock_response

        result = adapter.run(worker_input)

        assert result.status == "complete"
        assert "Worker completed successfully" in result.summary
        assert result.exit_code == 0
        assert log_file.exists()
        
        # Verify that workspace file hello.txt was NOT modified!
        assert (workspace_path / "hello.txt").read_text(encoding="utf-8") == "Hello World\n"
        
        # Verify proposed patch was written to evidence file
        patch_file = task_dir / "agents" / "default_agent" / "proposal.patch"
        assert patch_file.exists()
        assert "Hello beautiful World" in patch_file.read_text(encoding="utf-8")
        assert (task_dir / "agents" / "default_agent" / "raw_output.md").exists()
        assert (task_dir / "agents" / "default_agent" / "run.json").exists()


def test_registry_backed_qwopus_run_writes_patch_artifacts_and_can_apply(tmp_path: Path) -> None:
    (tmp_path / "hello.txt").write_text("Hello World\n", encoding="utf-8")
    task = create_task(tmp_path, "docs/polish: update hello with Qwopus")
    workspace_path = tmp_path / task.workspace
    assert (workspace_path / "hello.txt").read_text(encoding="utf-8") == "Hello World\n"

    context_pack_data = {
        "context_pack": {
            "role": "worker",
            "context_layer": "L1",
            "includes": [],
            "excludes": [],
            "estimated_tokens": 100,
            "sources_metadata": [
                {
                    "path": "hello.txt",
                    "authority": "canonical",
                    "mode": "full",
                    "content": "Hello World\n",
                }
            ],
        }
    }
    mock_response = MagicMock()
    response_dict = {
        "response": json.dumps(
            {
                "status": "ready",
                "diff": (
                    "diff --git a/hello.txt b/hello.txt\n"
                    "--- a/hello.txt\n"
                    "+++ b/hello.txt\n"
                    "@@ -1 +1 @@\n"
                    "-Hello World\n"
                    "+Hello from Qwopus\n"
                ),
                "touched_paths": ["hello.txt"],
                "risk": "low",
                "confidence": 0.91,
            }
        )
    }
    mock_response.read.return_value = json.dumps(response_dict).encode("utf-8")

    with patch("urllib.request.urlopen") as mock_urlopen, \
         patch("devflow.control_room.ollama_worker.build_context_pack", return_value=context_pack_data):
        mock_urlopen.return_value.__enter__.return_value = mock_response

        task_res = run_shell_task(tmp_path, task.id, [], worker_adapter="qwopus-implementer")

    assert task_res.status == "complete"
    request = mock_urlopen.call_args.args[0]
    assert json.loads(request.data.decode("utf-8"))["model"] == "qwopus:latest"

    agent_dir = tmp_path / ".devflow" / "tasks" / task.id / "agents" / "qwopus-implementer"
    assert (agent_dir / "packet.json").exists()
    assert (agent_dir / "raw_output.md").exists()
    assert (agent_dir / "proposal.patch").exists()
    assert (agent_dir / "result.md").exists()
    assert (agent_dir / "run.json").exists()
    assert (agent_dir / "logs" / "worker.log").exists()
    packet_json = json.loads((agent_dir / "packet.json").read_text(encoding="utf-8"))
    completion_rules = "\n".join(packet_json["completion_rules"])
    assert "For docs/polish tasks, do not invent new docs files" in completion_rules
    assert "If a task explicitly requires a new file, creating it is allowed." in completion_rules
    assert "Do not create files" not in completion_rules
    assert "Hello from Qwopus" in (agent_dir / "proposal.patch").read_text(encoding="utf-8")
    assert (workspace_path / "hello.txt").read_text(encoding="utf-8") == "Hello World\n"

    apply_task_patch(tmp_path, task.id, agent_id="qwopus-implementer")

    assert (workspace_path / "hello.txt").read_text(encoding="utf-8") == "Hello from Qwopus\n"


def test_registry_backed_qwopus_cli_output_names_canonical_evidence_paths(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.chdir(tmp_path)
    Path("hello.txt").write_text("Hello World\n", encoding="utf-8")
    created = runner.invoke(app, ["task", "create", "Update hello through canonical Qwopus"])
    assert created.exit_code == 0, created.output

    context_pack_data = {
        "context_pack": {
            "role": "worker",
            "context_layer": "L1",
            "includes": [],
            "excludes": [],
            "estimated_tokens": 100,
            "sources_metadata": [
                {
                    "path": "hello.txt",
                    "authority": "canonical",
                    "mode": "full",
                    "content": "Hello World\n",
                }
            ],
        }
    }
    mock_response = MagicMock()
    response_dict = {
        "response": json.dumps(
            {
                "status": "ready",
                "diff": (
                    "diff --git a/hello.txt b/hello.txt\n"
                    "--- a/hello.txt\n"
                    "+++ b/hello.txt\n"
                    "@@ -1 +1 @@\n"
                    "-Hello World\n"
                    "+Hello from canonical Qwopus\n"
                ),
                "touched_paths": ["hello.txt"],
                "risk": "low",
                "confidence": 0.92,
            }
        )
    }
    mock_response.read.return_value = json.dumps(response_dict).encode("utf-8")

    with patch("urllib.request.urlopen") as mock_urlopen, \
         patch("devflow.control_room.ollama_worker.build_context_pack", return_value=context_pack_data):
        mock_urlopen.return_value.__enter__.return_value = mock_response
        result = runner.invoke(app, ["task", "run", "task-0001", "--worker", "qwopus-implementer"])

    assert result.exit_code == 0, result.output
    assert "worker_mode: registry_backed_local_ollama_patch_worker" in result.output
    assert "worker_note: writes proposal.patch evidence only; Dev-Flow applies patches separately and verifies separately." in result.output
    assert "raw_output_path: .devflow/tasks/task-0001/agents/qwopus-implementer/raw_output.md" in result.output
    assert "proposal_patch_path: .devflow/tasks/task-0001/agents/qwopus-implementer/proposal.patch" in result.output
    assert "run_metadata_path: .devflow/tasks/task-0001/agents/qwopus-implementer/run.json" in result.output
    assert "agent_result_path: .devflow/tasks/task-0001/agents/qwopus-implementer/result.md" in result.output
    assert "agent_log_path: .devflow/tasks/task-0001/agents/qwopus-implementer/logs/worker.log" in result.output
    assert "suggested_next_action: devflow task apply-patch task-0001 --agent qwopus-implementer" in result.output

    show = runner.invoke(app, ["task", "show", "task-0001"])
    assert show.exit_code == 0, show.output
    assert "agent_evidence:" in show.output
    assert "proposal_patch_path: .devflow/tasks/task-0001/agents/qwopus-implementer/proposal.patch" in show.output


def test_ollama_worker_connection_failure(tmp_path: Path) -> None:
    # Set up task directories
    task_dir = tmp_path / ".devflow" / "tasks" / "task-ollama-2"
    task_dir.mkdir(parents=True)
    (task_dir / "logs").mkdir(parents=True)

    workspace_path = tmp_path / ".devflow" / "workspaces" / "task-ollama-2"
    workspace_path.mkdir(parents=True)

    log_file = task_dir / "logs" / "worker.log"
    result_file = task_dir / "result.md"

    worker_input = WorkerInput(
        task_id="task-ollama-2",
        repo_root=tmp_path,
        workspace_path=workspace_path,
        task_file=task_dir / "task.yaml",
        context_file=task_dir / "events.jsonl",
        status_file=task_dir / "task.yaml",
        questions_file=task_dir / "questions.jsonl",
        result_file=result_file,
        log_file=log_file,
        command=["ollama", "task"],
        timeout_seconds=60,
    )

    adapter = OllamaChatWorkerAdapter()

    with patch("urllib.request.urlopen", side_effect=urllib.error.URLError("Connection refused")), \
         patch("devflow.control_room.ollama_worker.build_context_pack", return_value={}):
        result = adapter.run(worker_input)

        assert result.status == "worker_failed"
        assert "Ollama could not be reached at configured local URL http://127.0.0.1:11434" in result.summary
        assert "ollama serve" in result.summary
        assert result.exit_code == 1
        assert log_file.exists()


def test_registry_backed_qwopus_missing_model_failure_preserves_raw_ollama_error(tmp_path: Path) -> None:
    Path(tmp_path / "hello.txt").write_text("Hello World\n", encoding="utf-8")
    task = create_task(tmp_path, "Missing Qwopus model")
    raw_error = b'{"error":"model \\"qwopus:latest\\" not found, try pulling it first"}'
    http_error = urllib.error.HTTPError(
        "http://127.0.0.1:11434/api/generate",
        404,
        "Not Found",
        {},
        BytesIO(raw_error),
    )

    with patch("urllib.request.urlopen", side_effect=http_error), \
         patch("devflow.control_room.ollama_worker.build_context_pack", return_value={}):
        task_res = run_shell_task(tmp_path, task.id, [], worker_adapter="qwopus-implementer")

    assert task_res.status == "worker_failed"
    agent_dir = tmp_path / ".devflow" / "tasks" / task.id / "agents" / "qwopus-implementer"
    run_json = json.loads((agent_dir / "run.json").read_text(encoding="utf-8"))
    worker_failed = json.loads((agent_dir / "worker_failed.json").read_text(encoding="utf-8"))
    assert "Ollama model 'qwopus:latest' is missing" in run_json["summary"]
    assert "ollama pull qwopus:latest" in run_json["summary"]
    assert "model \\\"qwopus:latest\\\" not found" in run_json["summary"]
    assert worker_failed["summary"] == run_json["summary"]


def test_ollama_worker_malformed_json_preserves_raw_output_and_points_to_it(tmp_path: Path) -> None:
    task_dir = tmp_path / ".devflow" / "tasks" / "task-ollama-json"
    task_dir.mkdir(parents=True)
    (task_dir / "logs").mkdir(parents=True)

    workspace_path = tmp_path / ".devflow" / "workspaces" / "task-ollama-json"
    workspace_path.mkdir(parents=True)
    log_file = task_dir / "logs" / "worker.log"

    worker_input = WorkerInput(
        task_id="task-ollama-json",
        repo_root=tmp_path,
        workspace_path=workspace_path,
        task_file=task_dir / "task.yaml",
        context_file=task_dir / "events.jsonl",
        status_file=task_dir / "task.yaml",
        questions_file=task_dir / "questions.jsonl",
        result_file=task_dir / "result.md",
        log_file=log_file,
        command=["ollama", "task"],
        timeout_seconds=60,
    )

    mock_response = MagicMock()
    mock_response.read.return_value = json.dumps({"response": "not json at all"}).encode("utf-8")

    with patch("urllib.request.urlopen") as mock_urlopen, \
         patch("devflow.control_room.ollama_worker.build_context_pack", return_value={}):
        mock_urlopen.return_value.__enter__.return_value = mock_response
        result = OllamaChatWorkerAdapter().run(worker_input)

    raw_output = task_dir / "agents" / "default_agent" / "raw_output.md"
    assert result.status == "worker_failed"
    assert raw_output.read_text(encoding="utf-8") == "not json at all"
    assert "Malformed JSON from local Ollama worker; inspect raw output" in result.summary


def test_ollama_worker_blocked_status(tmp_path: Path) -> None:
    # Set up task directories
    task_dir = tmp_path / ".devflow" / "tasks" / "task-ollama-3"
    task_dir.mkdir(parents=True)
    (task_dir / "logs").mkdir(parents=True)

    workspace_path = tmp_path / ".devflow" / "workspaces" / "task-ollama-3"
    workspace_path.mkdir(parents=True)

    log_file = task_dir / "logs" / "worker.log"
    result_file = task_dir / "result.md"

    worker_input = WorkerInput(
        task_id="task-ollama-3",
        repo_root=tmp_path,
        workspace_path=workspace_path,
        task_file=task_dir / "task.yaml",
        context_file=task_dir / "events.jsonl",
        status_file=task_dir / "task.yaml",
        questions_file=task_dir / "questions.jsonl",
        result_file=result_file,
        log_file=log_file,
        command=["ollama", "task"],
        timeout_seconds=60,
    )

    mock_response = MagicMock()
    response_dict = {
        "response": json.dumps({
            "status": "blocked",
            "blocked_reason": "prohibited pattern found",
            "diff": "",
            "touched_paths": [],
            "risk": "critical",
            "confidence": 0.0
        })
    }
    mock_response.read.return_value = json.dumps(response_dict).encode("utf-8")

    adapter = OllamaChatWorkerAdapter()

    with patch("urllib.request.urlopen") as mock_urlopen, \
         patch("devflow.control_room.ollama_worker.build_context_pack", return_value={}):
        mock_urlopen.return_value.__enter__.return_value = mock_response

        result = adapter.run(worker_input)

        assert result.status == "blocked"
        assert "prohibited pattern found" in result.summary
        assert result.exit_code == 1
