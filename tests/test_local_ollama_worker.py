from __future__ import annotations

import json
import subprocess
from pathlib import Path
from typing import Any
from unittest.mock import patch

from typer.testing import CliRunner

from devflow.cli import app
from devflow.control_room.service import get_task


runner = CliRunner()


def _find_run_dir(worker_name: str) -> Path:
    from devflow.control_room.local_ollama_worker import find_latest_worker_evidence
    workspace = Path(".devflow/workspaces/task-0001")
    run_dir, _ = find_latest_worker_evidence(workspace, worker_name)
    assert run_dir is not None
    return run_dir


def test_qwen_planner_prompt_is_composed_from_task_yaml_and_devflow_rules(
    tmp_path: Path,
    monkeypatch: Any,
) -> None:
    monkeypatch.chdir(tmp_path)
    Path("target.py").write_text("print('hello')\n", encoding="utf-8")
    _create_task("Plan local worker")
    task_yaml = Path(".devflow/tasks/task-0001/task.yaml")
    task_yaml.write_text(
        task_yaml.read_text(encoding="utf-8") + 'description: "Use local model planning"\n',
        encoding="utf-8",
    )

    with patch("devflow.control_room.local_ollama_worker.subprocess.run") as run_mock:
        run_mock.return_value = subprocess.CompletedProcess(
            ["ollama", "run", "qwen3.6:latest"],
            0,
            stdout="plan body",
            stderr="",
        )

        result = runner.invoke(app, ["task", "local", "task-0001", "--worker", "qwen-planner"])

    assert result.exit_code == 0, result.output
    worker_dir = _find_run_dir("qwen-planner")
    prompt = (worker_dir / "prompt.md").read_text(encoding="utf-8")
    assert "Dev-Flow rules" in prompt
    assert "Dev-Flow owns task state, isolated workspaces, logs, verification evidence, and human-controlled promotion." in prompt
    assert "Do not auto-edit repo files from model output." in prompt
    assert "title: Plan local worker" in prompt
    assert "description: Use local model planning" in prompt
    assert "status: created" in prompt
    assert 'description: "Use local model planning"' in prompt
    assert "target.py" in prompt
    assert "Smallest safe implementation slice" in prompt
    assert "Clean Codex/Antigravity prompt if useful" in prompt
    assert run_mock.call_args.kwargs["input"] == prompt
    assert run_mock.call_args.kwargs["timeout"] == 600


def test_qwen_planner_prompt_scrubs_existing_noisy_latest_log_line(
    tmp_path: Path,
    monkeypatch: Any,
) -> None:
    monkeypatch.chdir(tmp_path)
    _create_task("Prompt hygiene")
    task_yaml = Path(".devflow/tasks/task-0001/task.yaml")
    noisy_latest = "\x1b[?2026h" + ("\x1b[1G⠙ \x1b[K\x1b[1G⠹ \x1b[K" * 200) + "\x1b[?2026l"
    task_yaml.write_text(
        task_yaml.read_text(encoding="utf-8").replace(
            "latest_log_line: null",
            f"latest_log_line: {json.dumps(noisy_latest)}",
        ),
        encoding="utf-8",
    )

    with patch("devflow.control_room.local_ollama_worker.subprocess.run") as run_mock:
        run_mock.return_value = subprocess.CompletedProcess(
            ["ollama", "run", "qwen3.6:latest"],
            0,
            stdout="plan body",
            stderr="",
        )

        result = runner.invoke(app, ["task", "local", "task-0001", "--worker", "qwen-planner"])

    assert result.exit_code == 0, result.output
    worker_dir = _find_run_dir("qwen-planner")
    prompt = (worker_dir / "prompt.md").read_text(encoding="utf-8")
    assert "latest_log_line: null" in prompt
    assert "\\u001b" not in prompt
    assert "\\u2819" not in prompt


def test_qwen_planner_writes_prompt_response_and_run_metadata(
    tmp_path: Path,
    monkeypatch: Any,
) -> None:
    monkeypatch.chdir(tmp_path)
    _create_task("Write artifacts")

    with patch("devflow.control_room.local_ollama_worker.subprocess.run") as run_mock:
        run_mock.return_value = subprocess.CompletedProcess(
            ["ollama", "run", "qwen3.6:latest"],
            0,
            stdout="raw qwen response",
            stderr="diagnostic noise\n",
        )

        result = runner.invoke(app, ["task", "local", "task-0001", "--worker", "qwen-planner"])

    assert result.exit_code == 0, result.output
    worker_dir = _find_run_dir("qwen-planner")
    assert (worker_dir / "prompt.md").exists()
    assert (worker_dir / "response.raw.md").read_text(encoding="utf-8") == "raw qwen response"
    assert (worker_dir / "response.md").read_text(encoding="utf-8") == "raw qwen response"
    assert (worker_dir / "stderr.log").read_text(encoding="utf-8") == "diagnostic noise\n"
    run_json = json.loads((worker_dir / "run.json").read_text(encoding="utf-8"))
    assert run_json["task_id"] == "task-0001"
    assert run_json["worker_name"] == "qwen-planner"
    assert run_json["model"] == "qwen3.6:latest"
    assert run_json["command"] == ["ollama", "run", "qwen3.6:latest"]
    assert run_json["timeout_seconds"] == 600
    assert run_json["exit_code"] == 0
    assert run_json["status"] == "success"
    assert run_json["prompt_path"] == f".devflow/workspaces/task-0001/local-workers/qwen-planner/{worker_dir.name}/prompt.md"
    assert run_json["raw_response_path"] == f".devflow/workspaces/task-0001/local-workers/qwen-planner/{worker_dir.name}/response.raw.md"
    assert run_json["response_path"] == f".devflow/workspaces/task-0001/local-workers/qwen-planner/{worker_dir.name}/response.md"
    assert run_json["stderr_path"] == f".devflow/workspaces/task-0001/local-workers/qwen-planner/{worker_dir.name}/stderr.log"
    assert result.output.count(f"local_worker_run: .devflow/workspaces/task-0001/local-workers/qwen-planner/{worker_dir.name}/run.json") == 1
    assert get_task(Path.cwd(), "task-0001").status == "complete"


def test_success_sanitizes_spinner_stderr_before_task_latest_log_line(
    tmp_path: Path,
    monkeypatch: Any,
) -> None:
    monkeypatch.chdir(tmp_path)
    _create_task("Noisy local stderr")
    spinner_stderr = "\x1b[?2026h" + ("\x1b[1G⠙ \x1b[K\x1b[1G⠹ \x1b[K" * 200) + "\x1b[?2026l"

    with patch("devflow.control_room.local_ollama_worker.subprocess.run") as run_mock:
        run_mock.return_value = subprocess.CompletedProcess(
            ["ollama", "run", "qwen3.6:latest"],
            0,
            stdout="raw qwen response",
            stderr=spinner_stderr,
        )

        result = runner.invoke(app, ["task", "local", "task-0001", "--worker", "qwen-planner"])

    assert result.exit_code == 0, result.output
    worker_dir = _find_run_dir("qwen-planner")
    assert (worker_dir / "stderr.log").read_text(encoding="utf-8") == spinner_stderr
    task = get_task(Path.cwd(), "task-0001")
    assert task.latest_log_line is None
    task_yaml = Path(".devflow/tasks/task-0001/task.yaml").read_text(encoding="utf-8")
    assert "⠙" not in task_yaml
    assert "\x1b" not in task_yaml


def test_gemma_reviewer_consumes_qwen_planner_output(
    tmp_path: Path,
    monkeypatch: Any,
) -> None:
    monkeypatch.chdir(tmp_path)
    _create_task("Review qwen")

    with patch("devflow.control_room.local_ollama_worker.subprocess.run") as run_mock:
        run_mock.return_value = subprocess.CompletedProcess(
            ["ollama", "run", "qwen3.6:latest"],
            0,
            stdout="Qwen says keep the slice tiny.",
            stderr="",
        )
        qwen = runner.invoke(app, ["task", "local", "task-0001", "--worker", "qwen-planner"])

    assert qwen.exit_code == 0, qwen.output

    with patch("devflow.control_room.local_ollama_worker.subprocess.run") as run_mock:
        run_mock.return_value = subprocess.CompletedProcess(
            ["ollama", "run", "gemma4:latest"],
            0,
            stdout="review body",
            stderr="",
        )
        gemma = runner.invoke(
            app,
            [
                "task",
                "local",
                "task-0001",
                "--worker",
                "gemma-reviewer",
                "--input-worker",
                "qwen-planner",
            ],
        )

    assert gemma.exit_code == 0, gemma.output
    worker_dir = _find_run_dir("gemma-reviewer")
    prompt = (worker_dir / "prompt.md").read_text(encoding="utf-8")
    assert "Input worker: qwen-planner" in prompt
    assert "Qwen says keep the slice tiny." in prompt
    assert "Verdict" in prompt
    assert "Clean implementation prompt" in prompt


def test_gemma_reviewer_fails_clearly_when_input_worker_output_is_missing(
    tmp_path: Path,
    monkeypatch: Any,
) -> None:
    monkeypatch.chdir(tmp_path)
    _create_task("Missing qwen output")

    with patch("devflow.control_room.local_ollama_worker.subprocess.run") as run_mock:
        result = runner.invoke(
            app,
            [
                "task",
                "local",
                "task-0001",
                "--worker",
                "gemma-reviewer",
                "--input-worker",
                "qwen-planner",
            ],
        )

    assert result.exit_code == 1, result.output
    run_mock.assert_not_called()
    worker_dir = _find_run_dir("gemma-reviewer")
    assert "Missing input worker output" in (worker_dir / "stderr.log").read_text(encoding="utf-8")
    run_json = json.loads((worker_dir / "run.json").read_text(encoding="utf-8"))
    assert run_json["status"] == "failed"
    assert run_json["exit_code"] == 1
    assert get_task(Path.cwd(), "task-0001").status == "worker_failed"


def test_subprocess_nonzero_exit_writes_stderr_and_failed_run_json(
    tmp_path: Path,
    monkeypatch: Any,
) -> None:
    monkeypatch.chdir(tmp_path)
    _create_task("Subprocess failure")

    with patch("devflow.control_room.local_ollama_worker.subprocess.run") as run_mock:
        run_mock.return_value = subprocess.CompletedProcess(
            ["ollama", "run", "qwen3.6:latest"],
            2,
            stdout="model still wrote text",
            stderr="ollama failed\n",
        )
        result = runner.invoke(app, ["task", "local", "task-0001", "--worker", "qwen-planner"])

    assert result.exit_code == 2, result.output
    worker_dir = _find_run_dir("qwen-planner")
    assert (worker_dir / "stderr.log").read_text(encoding="utf-8") == "ollama failed\n"
    run_json = json.loads((worker_dir / "run.json").read_text(encoding="utf-8"))
    assert run_json["status"] == "failed"
    assert run_json["exit_code"] == 2
    assert get_task(Path.cwd(), "task-0001").status == "worker_failed"


def test_subprocess_timeout_writes_timeout_status_in_run_json(
    tmp_path: Path,
    monkeypatch: Any,
) -> None:
    monkeypatch.chdir(tmp_path)
    _create_task("Subprocess timeout")

    with patch("devflow.control_room.local_ollama_worker.subprocess.run") as run_mock:
        run_mock.side_effect = subprocess.TimeoutExpired(
            ["ollama", "run", "qwen3.6:latest"],
            600,
            output="partial response",
            stderr="still running",
        )
        result = runner.invoke(app, ["task", "local", "task-0001", "--worker", "qwen-planner"])

    assert result.exit_code == 1, result.output
    worker_dir = _find_run_dir("qwen-planner")
    assert (worker_dir / "response.raw.md").read_text(encoding="utf-8") == "partial response"
    assert (worker_dir / "stderr.log").read_text(encoding="utf-8") == "still running"
    run_json = json.loads((worker_dir / "run.json").read_text(encoding="utf-8"))
    assert run_json["status"] == "timeout"
    assert run_json["exit_code"] is None
    assert get_task(Path.cwd(), "task-0001").status == "timeout"


def test_unknown_local_worker_name_is_rejected(tmp_path: Path, monkeypatch: Any) -> None:
    monkeypatch.chdir(tmp_path)
    _create_task("Bad local worker")

    result = runner.invoke(app, ["task", "local", "task-0001", "--worker", "not-real"])

    assert result.exit_code == 1, result.output
    assert "Unknown local worker 'not-real'" in result.output
    assert not Path(".devflow/workspaces/task-0001/local-workers/not-real").exists()


def test_success_requires_zero_exit_code_not_nonempty_output(
    tmp_path: Path,
    monkeypatch: Any,
) -> None:
    monkeypatch.chdir(tmp_path)
    _create_task("Nonzero with output")

    with patch("devflow.control_room.local_ollama_worker.subprocess.run") as run_mock:
        run_mock.return_value = subprocess.CompletedProcess(
            ["ollama", "run", "qwen3.6:latest"],
            9,
            stdout="this looks like a useful answer",
            stderr="",
        )
        result = runner.invoke(app, ["task", "local", "task-0001", "--worker", "qwen-planner"])

    assert result.exit_code == 9, result.output
    worker_dir = _find_run_dir("qwen-planner")
    assert (worker_dir / "response.raw.md").read_text(encoding="utf-8") == "this looks like a useful answer"
    run_json = json.loads((worker_dir / "run.json").read_text(encoding="utf-8"))
    assert run_json["status"] == "failed"
    assert run_json["exit_code"] == 9
    assert get_task(Path.cwd(), "task-0001").status == "worker_failed"


def _create_task(title: str) -> None:
    result = runner.invoke(app, ["task", "create", title])
    assert result.exit_code == 0, result.output


def _setup_ollama_worker_test(tmp_path: Path, task_id: str) -> Any:
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
    task_dir = tmp_path / ".devflow" / "tasks" / task_id
    task_dir.mkdir(parents=True)
    (task_dir / "logs").mkdir(parents=True)

    # Write task.yaml
    (task_dir / "task.yaml").write_text(f"id: {task_id}\ntitle: Test Task\nstatus: created\n", encoding="utf-8")

    # Set up workspace
    workspace_path = tmp_path / ".devflow" / "workspaces" / task_id
    workspace_path.mkdir(parents=True)
    (workspace_path / "hello.txt").write_text("Hello World\n", encoding="utf-8")

    log_file = task_dir / "logs" / "worker.log"
    result_file = task_dir / "result.md"

    from devflow.control_room.models import WorkerInput
    return WorkerInput(
        task_id=task_id,
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


def test_ollama_worker_message_content_success(tmp_path: Path) -> None:
    from devflow.control_room.ollama_worker import OllamaChatWorkerAdapter
    from unittest.mock import MagicMock

    worker_input = _setup_ollama_worker_test(tmp_path, "task-ollama-msg-content")
    
    mock_response = MagicMock()
    proposal_dict = {
        "status": "ready",
        "diff": "diff --git a/hello.txt b/hello.txt\n--- a/hello.txt\n+++ b/hello.txt\n@@ -1 +1 @@\n-Hello World\n+hello from message.content\n",
        "touched_paths": ["hello.txt"],
        "risk": "low",
        "confidence": 1.0
    }
    response_dict = {
        "message": {
            "role": "assistant",
            "content": json.dumps(proposal_dict)
        }
    }
    mock_response.read.return_value = json.dumps(response_dict).encode("utf-8")

    adapter = OllamaChatWorkerAdapter()

    with patch("urllib.request.urlopen") as mock_urlopen, \
         patch("devflow.control_room.ollama_worker.build_context_pack", return_value={}):
        mock_urlopen.return_value.__enter__.return_value = mock_response

        result = adapter.run(worker_input)

        assert result.status == "complete"
        assert result.exit_code == 0
        
        # proposal.patch is written exactly from the parsed diff
        patch_file = tmp_path / ".devflow" / "tasks" / "task-ollama-msg-content" / "agents" / "default_agent" / "proposal.patch"
        assert patch_file.exists()
        assert "hello from message.content" in patch_file.read_text(encoding="utf-8")


def test_ollama_worker_thinking_success(tmp_path: Path) -> None:
    from devflow.control_room.ollama_worker import OllamaChatWorkerAdapter
    from unittest.mock import MagicMock

    worker_input = _setup_ollama_worker_test(tmp_path, "task-ollama-thinking")
    
    mock_response = MagicMock()
    proposal_dict = {
        "status": "ready",
        "diff": "diff --git a/hello.txt b/hello.txt\n--- a/hello.txt\n+++ b/hello.txt\n@@ -1 +1 @@\n-Hello World\n+hello from top-level thinking\n",
        "touched_paths": ["hello.txt"],
        "risk": "low",
        "confidence": 1.0
    }
    response_dict = {
        "thinking": proposal_dict
    }
    mock_response.read.return_value = json.dumps(response_dict).encode("utf-8")

    adapter = OllamaChatWorkerAdapter()

    with patch("urllib.request.urlopen") as mock_urlopen, \
         patch("devflow.control_room.ollama_worker.build_context_pack", return_value={}):
        mock_urlopen.return_value.__enter__.return_value = mock_response

        result = adapter.run(worker_input)

        assert result.status == "complete"
        assert result.exit_code == 0
        
        # proposal.patch is written exactly from the parsed diff
        patch_file = tmp_path / ".devflow" / "tasks" / "task-ollama-thinking" / "agents" / "default_agent" / "proposal.patch"
        assert patch_file.exists()
        assert "hello from top-level thinking" in patch_file.read_text(encoding="utf-8")


def test_ollama_worker_malformed_fails_safely(tmp_path: Path) -> None:
    from devflow.control_room.ollama_worker import OllamaChatWorkerAdapter
    from unittest.mock import MagicMock

    worker_input = _setup_ollama_worker_test(tmp_path, "task-ollama-malformed")
    
    mock_response = MagicMock()
    # No valid JSON in any field
    response_dict = {
        "response": "totally malformed and not JSON at all",
        "thinking": "also not JSON",
    }
    mock_response.read.return_value = json.dumps(response_dict).encode("utf-8")

    adapter = OllamaChatWorkerAdapter()

    with patch("urllib.request.urlopen") as mock_urlopen, \
         patch("devflow.control_room.ollama_worker.build_context_pack", return_value={}):
        mock_urlopen.return_value.__enter__.return_value = mock_response

        result = adapter.run(worker_input)

        assert result.status == "worker_failed"
        assert result.exit_code == 1
        
        # Always preserve raw_output.md
        raw_output_file = tmp_path / ".devflow" / "tasks" / "task-ollama-malformed" / "agents" / "default_agent" / "raw_output.md"
        assert raw_output_file.exists()
        assert "totally malformed" in raw_output_file.read_text(encoding="utf-8")
        
        # proposal.patch is written only after a valid proposal (so it should not exist here)
        patch_file = tmp_path / ".devflow" / "tasks" / "task-ollama-malformed" / "agents" / "default_agent" / "proposal.patch"
        assert not patch_file.exists()
        
        # malformed output still writes worker_failed.json
        worker_failed_file = tmp_path / ".devflow" / "tasks" / "task-ollama-malformed" / "agents" / "default_agent" / "worker_failed.json"
        assert worker_failed_file.exists()
        worker_failed_data = json.loads(worker_failed_file.read_text(encoding="utf-8"))
        assert worker_failed_data["status"] == "worker_failed"
        assert "Malformed JSON from local Ollama worker" in result.summary


def test_ollama_worker_rejects_json_list_proposal_shape(tmp_path: Path) -> None:
    from devflow.control_room.ollama_worker import OllamaChatWorkerAdapter
    from unittest.mock import MagicMock

    worker_input = _setup_ollama_worker_test(tmp_path, "task-ollama-json-list")
    
    mock_response = MagicMock()
    response_dict = {
        "thinking": ["not", "a", "proposal"],
    }
    mock_response.read.return_value = json.dumps(response_dict).encode("utf-8")

    adapter = OllamaChatWorkerAdapter()

    with patch("urllib.request.urlopen") as mock_urlopen, \
         patch("devflow.control_room.ollama_worker.build_context_pack", return_value={}):
        mock_urlopen.return_value.__enter__.return_value = mock_response

        result = adapter.run(worker_input)

        assert result.status == "worker_failed"
        assert result.exit_code == 1
        
        raw_output_file = tmp_path / ".devflow" / "tasks" / "task-ollama-json-list" / "agents" / "default_agent" / "raw_output.md"
        assert raw_output_file.exists()
        assert "not" in raw_output_file.read_text(encoding="utf-8")
        
        patch_file = tmp_path / ".devflow" / "tasks" / "task-ollama-json-list" / "agents" / "default_agent" / "proposal.patch"
        assert not patch_file.exists()
        
        worker_failed_file = tmp_path / ".devflow" / "tasks" / "task-ollama-json-list" / "agents" / "default_agent" / "worker_failed.json"
        assert worker_failed_file.exists()
        worker_failed_data = json.loads(worker_failed_file.read_text(encoding="utf-8"))
        assert worker_failed_data["status"] == "worker_failed"
        
        assert any(term in result.summary.lower() for term in ["malformed", "invalid", "local ollama"])



def test_ollama_worker_list_fails_safely(tmp_path: Path) -> None:
    from devflow.control_room.ollama_worker import OllamaChatWorkerAdapter
    from unittest.mock import MagicMock

    worker_input = _setup_ollama_worker_test(tmp_path, "task-ollama-list")
    
    mock_response = MagicMock()
    response_dict = {
        "thinking": ["this", "is", "a", "list"]
    }
    mock_response.read.return_value = json.dumps(response_dict).encode("utf-8")

    adapter = OllamaChatWorkerAdapter()

    with patch("urllib.request.urlopen") as mock_urlopen, \
         patch("devflow.control_room.ollama_worker.build_context_pack", return_value={}):
        mock_urlopen.return_value.__enter__.return_value = mock_response

        result = adapter.run(worker_input)

        assert result.status == "worker_failed"
        assert result.exit_code == 1
        assert "Expected a JSON object (dict), but got a list." in result.summary


def test_ollama_worker_patch_written_exactly_from_parsed_diff(tmp_path: Path) -> None:
    from devflow.control_room.ollama_worker import OllamaChatWorkerAdapter
    from unittest.mock import MagicMock

    worker_input = _setup_ollama_worker_test(tmp_path, "task-ollama-exact-patch")
    
    mock_response = MagicMock()
    exact_diff = "--- hello.txt\n+++ hello.txt\n@@ -1 +1 @@\n-Hello World\n+hello from exact diff\n"
    proposal_dict = {
        "status": "ready",
        "diff": exact_diff,
        "touched_paths": ["hello.txt"],
        "risk": "low",
        "confidence": 1.0
    }
    response_dict = {
        "response": json.dumps(proposal_dict)
    }
    mock_response.read.return_value = json.dumps(response_dict).encode("utf-8")

    adapter = OllamaChatWorkerAdapter()

    with patch("urllib.request.urlopen") as mock_urlopen, \
         patch("devflow.control_room.ollama_worker.build_context_pack", return_value={}):
        mock_urlopen.return_value.__enter__.return_value = mock_response

        result = adapter.run(worker_input)

        assert result.status == "complete"
        assert result.exit_code == 0
        
        patch_file = tmp_path / ".devflow" / "tasks" / "task-ollama-exact-patch" / "agents" / "default_agent" / "proposal.patch"
        assert patch_file.exists()
        assert patch_file.read_text(encoding="utf-8") == exact_diff
