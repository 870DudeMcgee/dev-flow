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
from devflow.control_room.persistence import save_task
from devflow.control_room.patch_dry_run import preview_patch_dry_run
from devflow.control_room.patch_review import normalize_agent_patch_candidate, review_patch_candidate
from devflow.control_room.service import apply_task_patch, create_task, run_shell_task


runner = CliRunner()


def _write_qwopus_task_0015_shape(root: Path):
    task = create_task(root, "Dogfood Qwopus task show UX")
    task_path = root / ".devflow" / "tasks" / task.id
    workspace_path = root / ".devflow" / "workspaces" / task.id
    workspace_path.mkdir(parents=True, exist_ok=True)
    (workspace_path / "hello.txt").write_text("Hello World\n", encoding="utf-8")

    agent_dir = task_path / "agents" / "qwopus-implementer"
    (agent_dir / "logs").mkdir(parents=True, exist_ok=True)
    (agent_dir / "packet.json").write_text("{}\n", encoding="utf-8")
    (agent_dir / "raw_output.md").write_text("raw Qwopus output\n", encoding="utf-8")
    (agent_dir / "proposal.patch").write_text(
        "--- a/hello.txt\n"
        "+++ b/hello.txt\n"
        "@@ -1 +1 @@\n"
        "-Hello World\n"
        "+Hello from task-0015 Qwopus\n",
        encoding="utf-8",
    )
    (agent_dir / "result.md").write_text(
        "# Result: task-0015\n\n"
        "## Summary\n\n"
        "Worker completed successfully and wrote proposal.patch\n\n"
        "## Status\n\n"
        "complete\n",
        encoding="utf-8",
    )
    (agent_dir / "run.json").write_text(
        json.dumps(
            {
                "task_id": task.id,
                "agent_id": "qwopus-implementer",
                "status": "complete",
                "summary": "Worker completed successfully and wrote proposal.patch",
                "exit_code": 0,
                "proposal_patch_path": str(agent_dir / "proposal.patch"),
            },
            indent=2,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )
    (agent_dir / "logs" / "worker.log").write_text("Worker completed successfully.\n", encoding="utf-8")

    task.status = "complete"
    task.worker = "qwopus-implementer"
    task.last_event = "worker_finished"
    task.last_exit_code = 0
    task.latest_log_line = "Worker completed successfully."
    task.log_path = f".devflow/tasks/{task.id}/agents/qwopus-implementer/logs/worker.log"
    task.result_path = f".devflow/tasks/{task.id}/agents/qwopus-implementer/result.md"
    save_task(task_path, task)
    return task


def _review_and_dry_run_qwopus(root: Path, task_id: str) -> None:
    run_id = normalize_agent_patch_candidate(root, task_id, "qwopus-implementer")
    review_patch_candidate(root, task_id, run_id=run_id)
    preview_patch_dry_run(root, task_id, run_id=run_id)


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


def test_task_show_qwopus_proposal_without_patch_application_suggests_apply_patch(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(tmp_path)
    task = _write_qwopus_task_0015_shape(tmp_path)

    result = runner.invoke(app, ["task", "show", task.id])

    assert result.exit_code == 0, result.output
    assert f"suggested_next_action: devflow task review-patch {task.id} --agent qwopus-implementer" in result.output


def test_task_show_qwopus_result_summary_uses_agent_result(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(tmp_path)
    task = _write_qwopus_task_0015_shape(tmp_path)

    result = runner.invoke(app, ["task", "show", task.id])

    assert result.exit_code == 0, result.output
    assert "result_summary:\n  Worker completed successfully and wrote proposal.patch" in result.output
    assert "result_summary:\n  Not run yet." not in result.output


def test_task_show_qwopus_patch_applied_without_verification_suggests_verify(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(tmp_path)
    task = _write_qwopus_task_0015_shape(tmp_path)
    _review_and_dry_run_qwopus(tmp_path, task.id)
    apply_task_patch(tmp_path, task.id, agent_id="qwopus-implementer")

    result = runner.invoke(app, ["task", "show", task.id])

    assert result.exit_code == 0, result.output
    assert f"suggested_next_action: Verify the task using 'devflow task verify {task.id} -- <command>'" in result.output
    assert "suggested_next_action: devflow task apply-patch" not in result.output


def test_task_show_qwopus_verified_patch_suggests_promote_preview(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(tmp_path)
    task = _write_qwopus_task_0015_shape(tmp_path)
    _review_and_dry_run_qwopus(tmp_path, task.id)
    apply_task_patch(tmp_path, task.id, agent_id="qwopus-implementer")
    verified = runner.invoke(app, ["task", "verify", task.id, "--shell", "test -f hello.txt"])
    assert verified.exit_code == 0, verified.output

    result = runner.invoke(app, ["task", "show", task.id])

    assert result.exit_code == 0, result.output
    assert f"suggested_next_action: devflow task promote-preview {task.id}" in result.output


def test_task_show_shell_worker_next_action_is_unchanged(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.chdir(tmp_path)
    created = runner.invoke(app, ["task", "create", "shell behavior remains unchanged"])
    assert created.exit_code == 0, created.output
    run = runner.invoke(app, ["task", "run", "task-0001", "--shell", "echo completed"])
    assert run.exit_code == 0, run.output

    result = runner.invoke(app, ["task", "show", "task-0001"])

    assert result.exit_code == 0, result.output
    assert "suggested_next_action: Verify the task using 'devflow task verify task-0001 -- <command>'" in result.output


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

    _review_and_dry_run_qwopus(tmp_path, task.id)
    apply_task_patch(tmp_path, task.id, agent_id="qwopus-implementer")

    assert (workspace_path / "hello.txt").read_text(encoding="utf-8") == "Hello from Qwopus\n"


def _write_local_patch_registry(root: Path, *, agent_id: str, model: str) -> None:
    agents_dir = root / ".devflow" / "agents"
    agents_dir.mkdir(parents=True, exist_ok=True)
    (agents_dir / "registry.yaml").write_text(
        "version: 1\n"
        "providers:\n"
        "  ollama:\n"
        "    provider: ollama\n"
        "    adapter: ollama_chat\n"
        "    base_url: http://127.0.0.1:11434\n"
        "    default_timeout_seconds: 600\n"
        "    enabled: true\n"
        "agents:\n"
        f"  {agent_id}:\n"
        "    provider: ollama\n"
        f"    model: {model}\n"
        "    adapter: ollama_chat\n"
        "    role: implementation_worker\n"
        "    tier: strong_local\n"
        "    default_mode: workspace_write\n"
        "    execution_mode: automated\n"
        "    workspace: isolated_task_workspace\n"
        "    can_run_shell: false\n"
        "    can_use_network: false\n"
        "    can_promote: false\n"
        "    enabled: true\n",
        encoding="utf-8",
    )


def _ready_patch_response() -> bytes:
    return json.dumps(
        {
            "message": {
                "content": json.dumps(
                    {
                        "status": "ready",
                        "diff": (
                            "diff --git a/hello.txt b/hello.txt\n"
                            "--- a/hello.txt\n"
                            "+++ b/hello.txt\n"
                            "@@ -1 +1 @@\n"
                            "-Hello World\n"
                            "+Hello from Gemma\n"
                        ),
                        "touched_paths": ["hello.txt"],
                        "risk": "low",
                        "confidence": 0.88,
                    }
                )
            },
            "done": True,
            "done_reason": "stop",
            "prompt_eval_count": 64,
            "eval_count": 128,
        }
    ).encode("utf-8")


def test_gemma_patch_worker_uses_native_chat_with_explicit_generation_options(tmp_path: Path) -> None:
    Path(tmp_path / "hello.txt").write_text("Hello World\n", encoding="utf-8")
    _write_local_patch_registry(
        tmp_path,
        agent_id="gemma4-12b-qat-implementer",
        model="gemma4:12b-it-qat",
    )
    task = create_task(tmp_path, "Gemma patch settings")

    mock_response = MagicMock()
    mock_response.status = 200
    mock_response.read.return_value = _ready_patch_response()

    with patch("urllib.request.urlopen") as mock_urlopen, \
         patch("devflow.control_room.ollama_worker.build_context_pack", return_value={}):
        mock_urlopen.return_value.__enter__.return_value = mock_response
        result = run_shell_task(tmp_path, task.id, [], worker_adapter="gemma4-12b-qat-implementer")

    assert result.status == "complete"
    request = mock_urlopen.call_args.args[0]
    assert request.full_url == "http://127.0.0.1:11434/api/chat"
    payload = json.loads(request.data.decode("utf-8"))
    assert payload["model"] == "gemma4:12b-it-qat"
    assert payload["stream"] is False
    assert payload["think"] is False
    assert payload["format"] == "json"
    assert payload["options"]["temperature"] == 0.2
    assert payload["options"]["num_ctx"] == 262144
    assert payload["options"]["num_predict"] == 4096
    assert [message["role"] for message in payload["messages"]] == ["system", "user"]

    agent_dir = tmp_path / ".devflow" / "tasks" / task.id / "agents" / "gemma4-12b-qat-implementer"
    run_json = json.loads((agent_dir / "run.json").read_text(encoding="utf-8"))
    assert run_json["request_endpoint"] == "/api/chat"
    assert run_json["request_payload_shape"] == "native_chat_messages"
    assert run_json["request_options"] == {"num_ctx": 262144, "num_predict": 4096, "temperature": 0.2}
    assert run_json["native_chat_think"] is False
    assert run_json["request_format"] == "json"
    assert run_json["ollama_response"]["done_reason"] == "stop"
    assert "message" not in run_json["ollama_response"]
    assert "Hello from Gemma" in (agent_dir / "proposal.patch").read_text(encoding="utf-8")


def test_non_gemma_patch_worker_keeps_generate_endpoint_with_explicit_generation_options(tmp_path: Path) -> None:
    Path(tmp_path / "hello.txt").write_text("Hello World\n", encoding="utf-8")
    task = create_task(tmp_path, "Qwopus patch settings")

    mock_response = MagicMock()
    mock_response.status = 200
    mock_response.read.return_value = json.dumps(
        {
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
            ),
            "done": True,
            "done_reason": "stop",
            "prompt_eval_count": 64,
            "eval_count": 128,
        }
    ).encode("utf-8")

    with patch("urllib.request.urlopen") as mock_urlopen, \
         patch("devflow.control_room.ollama_worker.build_context_pack", return_value={}):
        mock_urlopen.return_value.__enter__.return_value = mock_response
        result = run_shell_task(tmp_path, task.id, [], worker_adapter="qwopus-implementer")

    assert result.status == "complete"
    request = mock_urlopen.call_args.args[0]
    assert request.full_url == "http://127.0.0.1:11434/api/generate"
    payload = json.loads(request.data.decode("utf-8"))
    assert payload["model"] == "qwopus:latest"
    assert payload["format"] == "json"
    assert payload["stream"] is False
    assert payload["options"] == {"num_ctx": 262144, "num_predict": 4096, "temperature": 0.2}

    agent_dir = tmp_path / ".devflow" / "tasks" / task.id / "agents" / "qwopus-implementer"
    run_json = json.loads((agent_dir / "run.json").read_text(encoding="utf-8"))
    assert run_json["request_endpoint"] == "/api/generate"
    assert run_json["request_payload_shape"] == "generate_prompt_system"
    assert run_json["request_options"] == {"num_ctx": 262144, "num_predict": 4096, "temperature": 0.2}


def test_ollama_worker_malformed_json_reports_length_truncation(tmp_path: Path) -> None:
    Path(tmp_path / "hello.txt").write_text("Hello World\n", encoding="utf-8")
    _write_local_patch_registry(
        tmp_path,
        agent_id="gemma4-12b-qat-implementer",
        model="gemma4:12b-it-qat",
    )
    task = create_task(tmp_path, "Gemma truncated JSON")

    mock_response = MagicMock()
    mock_response.status = 200
    mock_response.read.return_value = json.dumps(
        {
            "message": {"content": "{\""},
            "done": True,
            "done_reason": "length",
            "prompt_eval_count": 4095,
            "eval_count": 1,
        }
    ).encode("utf-8")

    with patch("urllib.request.urlopen") as mock_urlopen, \
         patch("devflow.control_room.ollama_worker.build_context_pack", return_value={}):
        mock_urlopen.return_value.__enter__.return_value = mock_response
        result = run_shell_task(tmp_path, task.id, [], worker_adapter="gemma4-12b-qat-implementer")

    assert result.status == "worker_failed"

    agent_dir = tmp_path / ".devflow" / "tasks" / task.id / "agents" / "gemma4-12b-qat-implementer"
    assert (agent_dir / "raw_output.md").read_text(encoding="utf-8") == "{\""
    run_json = json.loads((agent_dir / "run.json").read_text(encoding="utf-8"))
    worker_failed = json.loads((agent_dir / "worker_failed.json").read_text(encoding="utf-8"))
    assert "Ollama stopped at length before returning complete JSON" in run_json["summary"]
    assert "eval_count=1" in run_json["summary"]
    assert run_json["ollama_response"]["done_reason"] == "length"
    assert "num_predict" in run_json["request_options"]
    assert worker_failed["summary"] == run_json["summary"]


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
    assert "suggested_next_action: devflow task review-patch task-0001 --agent qwopus-implementer" in result.output

    show = runner.invoke(app, ["task", "show", "task-0001"])
    assert show.exit_code == 0, show.output
    assert "agent_evidence:" in show.output
    assert "proposal_patch_path: .devflow/tasks/task-0001/agents/qwopus-implementer/proposal.patch" in show.output
    assert "latest_run_status: complete" in show.output
    assert "proposal_patch_bytes:" in show.output
    assert "proposed_file_count: 1" in show.output
    assert "next_suggested_command: devflow task review-patch task-0001 --agent qwopus-implementer" in show.output

    run_json = json.loads((Path(".devflow/tasks/task-0001/agents/qwopus-implementer/run.json")).read_text(encoding="utf-8"))
    assert run_json["proposal_patch_found"] is True
    assert run_json["proposal_patch_path"].endswith("proposal.patch")
    assert run_json["proposal_patch_byte_length"] > 0
    assert run_json["proposed_file_count"] == 1
    assert run_json["proposed_file_paths"] == ["hello.txt"]

    packet_json = json.loads((Path(".devflow/tasks/task-0001/agents/qwopus-implementer/packet.json")).read_text(encoding="utf-8"))
    serialized_packet = json.dumps(packet_json)
    assert "Update hello through canonical Qwopus" in serialized_packet
    assert "Produce a unified diff only" in serialized_packet
    assert "Dev-Flow applies patches, runs verification, and controls promotion separately." in serialized_packet
    assert "patch dry-run artifacts" in serialized_packet

    result_md = Path(".devflow/tasks/task-0001/agents/qwopus-implementer/result.md").read_text(encoding="utf-8")
    assert "Next action: `devflow task review-patch task-0001 --agent qwopus-implementer`" in result_md


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


def test_qwopus_no_patch_failure_is_visible_and_suggests_escalation(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.chdir(tmp_path)
    Path("hello.txt").write_text("Hello World\n", encoding="utf-8")
    created = runner.invoke(app, ["task", "create", "No patch Qwopus run"])
    assert created.exit_code == 0, created.output

    mock_response = MagicMock()
    mock_response.read.return_value = json.dumps(
        {
            "response": json.dumps(
                {
                    "status": "ready",
                    "diff": "",
                    "touched_paths": [],
                    "risk": "low",
                    "confidence": 0.4,
                }
            )
        }
    ).encode("utf-8")

    with patch("urllib.request.urlopen") as mock_urlopen, \
         patch("devflow.control_room.ollama_worker.build_context_pack", return_value={}):
        mock_urlopen.return_value.__enter__.return_value = mock_response
        run = runner.invoke(app, ["task", "run", "task-0001", "--worker", "qwopus-implementer"])

    assert run.exit_code == 1, run.output
    agent_dir = Path(".devflow/tasks/task-0001/agents/qwopus-implementer")
    run_json = json.loads((agent_dir / "run.json").read_text(encoding="utf-8"))
    assert run_json["proposal_patch_found"] is False
    assert run_json["proposal_patch_byte_length"] == 0
    assert "did not include a non-empty unified diff" in run_json["failure_reason"]

    show = runner.invoke(app, ["task", "show", "task-0001"])
    assert show.exit_code == 0, show.output
    assert "latest_run_status: worker_failed" in show.output
    assert "next_suggested_command: devflow task escalation-packet task-0001 --agent qwopus-implementer" in show.output


def test_qwopus_escalation_packet_is_compact_local_evidence(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.chdir(tmp_path)
    Path("hello.txt").write_text("Hello World\n", encoding="utf-8")
    created = runner.invoke(app, ["task", "create", "Escalate Qwopus failure"])
    assert created.exit_code == 0, created.output

    agent_dir = Path(".devflow/tasks/task-0001/agents/qwopus-implementer")
    agent_dir.mkdir(parents=True, exist_ok=True)
    (agent_dir / "result.md").write_text("# Result\n\nSummary: no usable patch\n", encoding="utf-8")
    (agent_dir / "raw_output.md").write_text("raw local output", encoding="utf-8")
    (agent_dir / "run.json").write_text(
        json.dumps(
            {
                "status": "worker_failed",
                "summary": "no diff",
                "failure_reason": "output without unified diff",
                "proposal_patch_byte_length": 0,
                "proposed_file_paths": [],
            }
        ),
        encoding="utf-8",
    )
    Path(".devflow/tasks/task-0001/patch-application.json").write_text(
        json.dumps({"error": "patch did not apply"}),
        encoding="utf-8",
    )
    Path(".devflow/tasks/task-0001/verification.json").write_text(
        json.dumps({"status": "failed", "command": "pytest tests/test_ollama_worker.py", "log_path": "logs/verify.log"}),
        encoding="utf-8",
    )
    unrelated_log = Path(".devflow/tasks/task-0001/logs/unrelated.log")
    unrelated_log.write_text("NOISY ARCHIVE MATERIAL", encoding="utf-8")

    result = runner.invoke(app, ["task", "escalation-packet", "task-0001", "--agent", "qwopus-implementer"])

    assert result.exit_code == 0, result.output
    assert "provider_calls: none" in result.output
    packet = Path(".devflow/tasks/task-0001/agents/qwopus-implementer/escalation-packet.md")
    packet_text = packet.read_text(encoding="utf-8")
    assert "Escalate Qwopus failure" in packet_text
    assert "output without unified diff" in packet_text
    assert "patch did not apply" in packet_text
    assert "Verification status: failed" in packet_text
    assert "Given this bounded Dev-Flow task" in packet_text
    assert "NOISY ARCHIVE MATERIAL" not in packet_text


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
