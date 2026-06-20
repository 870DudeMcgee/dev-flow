from __future__ import annotations

import json
import os
import urllib.request
import urllib.error
import yaml
from pathlib import Path
import pytest
from typer.testing import CliRunner

from devflow.cli import app
from devflow.control_room.goals import goal_dir
from devflow.control_room.local_model_client import LocalModelClient
from tests.helpers import setup_temp_git_repo

class MockResponse:
    def __init__(self, body: bytes, status: int = 200, reason: str = "OK"):
        self.body = body
        self.status = status
        self.reason = reason

    def read(self, *args, **kwargs):
        return self.body

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        pass


def test_1_missing_local_model_id_fails_clearly(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    # Test 1: missing LOCAL_MODEL_ID fails clearly
    setup_temp_git_repo(tmp_path)
    monkeypatch.chdir(tmp_path)

    # Ensure LOCAL_MODEL_ID is NOT in env
    monkeypatch.delenv("LOCAL_MODEL_ID", raising=False)

    runner = CliRunner()
    # Create normal task
    create_res = runner.invoke(app, ["task", "create", "normal task"])
    assert create_res.exit_code == 0

    # Snapshot workspace and task to check for changes
    task_yaml_path = tmp_path / ".devflow" / "tasks" / "task-0001" / "task.yaml"
    task_yaml_orig = task_yaml_path.read_text(encoding="utf-8")
    verification_json_orig = (tmp_path / ".devflow" / "tasks" / "task-0001" / "verification.json").read_text(encoding="utf-8")

    # Run review, should fail clearly
    review_res = runner.invoke(app, ["task", "local-review", "task-0001"])
    assert review_res.exit_code != 0
    assert "LOCAL_MODEL_ID" in review_res.output

    # Assert no task/source state mutation
    assert task_yaml_path.read_text(encoding="utf-8") == task_yaml_orig
    assert (tmp_path / ".devflow" / "tasks" / "task-0001" / "verification.json").read_text(encoding="utf-8") == verification_json_orig


def test_2_local_client_sends_openai_compatible_payload(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    # Test 2: local client sends OpenAI-compatible payload
    setup_temp_git_repo(tmp_path)
    monkeypatch.chdir(tmp_path)

    monkeypatch.setenv("LOCAL_MODEL_ID", "test-model")
    monkeypatch.setenv("LOCAL_MODEL_BASE_URL", "http://my-host/v1")
    monkeypatch.setenv("LOCAL_MODEL_TEMPERATURE", "0.5")

    captured_reqs = []

    def mock_urlopen(req, timeout=None):
        captured_reqs.append({
            "url": req.full_url,
            "headers": dict(req.headers),
            "data": json.loads(req.data.decode("utf-8")),
            "method": req.get_method(),
        })
        mock_body = {
            "choices": [{
                "message": {
                    "role": "assistant",
                    "content": "# Local Model Review\n\n## Understanding\nLooks great!"
                }
            }]
        }
        return MockResponse(json.dumps(mock_body).encode("utf-8"))

    monkeypatch.setattr(urllib.request, "urlopen", mock_urlopen)

    runner = CliRunner()
    runner.invoke(app, ["task", "create", "normal task"])

    review_res = runner.invoke(app, ["task", "local-review", "task-0001"])
    assert review_res.exit_code == 0

    assert len(captured_reqs) == 1
    req = captured_reqs[0]
    assert req["url"] == "http://my-host/v1/chat/completions"
    assert req["method"] == "POST"
    assert req["data"]["model"] == "test-model"
    assert req["data"]["temperature"] == 0.5
    assert len(req["data"]["messages"]) == 2
    assert req["data"]["messages"][0]["role"] == "system"
    assert req["data"]["messages"][1]["role"] == "user"
    assert "Task Packet: task-0001" in req["data"]["messages"][1]["content"]


def test_3_successful_local_review_writes_evidence_artifacts(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    # Test 3: successful local review writes evidence artifacts
    setup_temp_git_repo(tmp_path)
    monkeypatch.chdir(tmp_path)

    monkeypatch.setenv("LOCAL_MODEL_ID", "test-model")

    assistant_content = "# Local Model Review\n\n## Understanding\nTest evidence output."
    mock_body = {
        "choices": [{
            "message": {
                "role": "assistant",
                "content": assistant_content
            }
        }]
    }

    def mock_urlopen(req, timeout=None):
        return MockResponse(json.dumps(mock_body).encode("utf-8"))

    monkeypatch.setattr(urllib.request, "urlopen", mock_urlopen)

    runner = CliRunner()
    runner.invoke(app, ["task", "create", "normal task"])

    review_res = runner.invoke(app, ["task", "local-review", "task-0001"])
    assert review_res.exit_code == 0

    # Assert run directory and files exist
    runs_dir = tmp_path / ".devflow" / "tasks" / "task-0001" / "local-model-runs"
    assert runs_dir.exists()
    
    run_folders = [p for p in runs_dir.iterdir() if p.is_dir()]
    assert len(run_folders) == 1
    run_dir = run_folders[0]

    assert (run_dir / "request.json").exists()
    assert (run_dir / "prompt.md").exists()
    assert (run_dir / "response.json").exists()
    assert (run_dir / "response.md").exists()
    assert (run_dir / "proposal.md").exists()
    assert (run_dir / "run.json").exists()

    assert (run_dir / "response.md").read_text(encoding="utf-8") == assistant_content
    assert (run_dir / "proposal.md").read_text(encoding="utf-8") == assistant_content

    run_meta = json.loads((run_dir / "run.json").read_text(encoding="utf-8"))
    assert run_meta["status"] == "success"
    assert run_meta["model"] == "test-model"


def test_4_successful_local_review_does_not_mutate_task_execution_state(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    # Test 4: successful local review does not mutate task execution state
    setup_temp_git_repo(tmp_path)
    monkeypatch.chdir(tmp_path)

    monkeypatch.setenv("LOCAL_MODEL_ID", "test-model")

    mock_body = {
        "choices": [{
            "message": {
                "role": "assistant",
                "content": "# Local Model Review\n\n## Understanding\nUnmutated."
            }
        }]
    }
    monkeypatch.setattr(urllib.request, "urlopen", lambda r, timeout=None: MockResponse(json.dumps(mock_body).encode("utf-8")))

    runner = CliRunner()
    runner.invoke(app, ["task", "create", "normal task"])

    task_yaml_orig = yaml.safe_load((tmp_path / ".devflow" / "tasks" / "task-0001" / "task.yaml").read_text(encoding="utf-8"))
    verification_orig = json.loads((tmp_path / ".devflow" / "tasks" / "task-0001" / "verification.json").read_text(encoding="utf-8"))
    worker_log_orig = (tmp_path / ".devflow" / "tasks" / "task-0001" / "logs" / "worker.log").read_text(encoding="utf-8")
    verify_log_orig = (tmp_path / ".devflow" / "tasks" / "task-0001" / "logs" / "verify.log").read_text(encoding="utf-8")

    review_res = runner.invoke(app, ["task", "local-review", "task-0001"])
    assert review_res.exit_code == 0

    # Reload and assert completely unmutated
    task_yaml_after = yaml.safe_load((tmp_path / ".devflow" / "tasks" / "task-0001" / "task.yaml").read_text(encoding="utf-8"))
    verification_after = json.loads((tmp_path / ".devflow" / "tasks" / "task-0001" / "verification.json").read_text(encoding="utf-8"))
    worker_log_after = (tmp_path / ".devflow" / "tasks" / "task-0001" / "logs" / "worker.log").read_text(encoding="utf-8")
    verify_log_after = (tmp_path / ".devflow" / "tasks" / "task-0001" / "logs" / "verify.log").read_text(encoding="utf-8")

    assert task_yaml_after["status"] == "created"
    assert task_yaml_after == task_yaml_orig
    assert verification_after["status"] == "not_run"
    assert verification_after == verification_orig
    assert worker_log_after == worker_log_orig
    assert verify_log_after == verify_log_orig


def test_5_goal_linked_task_packet_is_used(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    # Test 5: goal-linked task packet is used
    setup_temp_git_repo(tmp_path)
    monkeypatch.chdir(tmp_path)

    monkeypatch.setenv("LOCAL_MODEL_ID", "test-model")

    brief_path = tmp_path / "my_goal.md"
    brief_path.write_text("## Goal Brief\nImplement durables.", encoding="utf-8")

    runner = CliRunner()
    runner.invoke(app, ["goal", "init", "--from", "my_goal.md"])
    runner.invoke(app, ["goal", "create-task", "G-0001", "TS-0001"])

    mock_body = {
        "choices": [{
            "message": {
                "role": "assistant",
                "content": "# Local Model Review"
            }
        }]
    }
    monkeypatch.setattr(urllib.request, "urlopen", lambda r, timeout=None: MockResponse(json.dumps(mock_body).encode("utf-8")))

    review_res = runner.invoke(app, ["task", "local-review", "task-0001"])
    assert review_res.exit_code == 0

    runs_dir = tmp_path / ".devflow" / "tasks" / "task-0001" / "local-model-runs"
    run_dir = next(runs_dir.iterdir())
    
    prompt_text = (run_dir / "prompt.md").read_text(encoding="utf-8")
    assert "G-0001" in prompt_text
    assert "TS-0001" in prompt_text
    assert "forbidden context" in prompt_text.lower()
    assert "Acceptance Criteria" in prompt_text


def test_6_unreachable_server_fails_with_evidence(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    # Test 6: unreachable server fails with evidence
    setup_temp_git_repo(tmp_path)
    monkeypatch.chdir(tmp_path)

    monkeypatch.setenv("LOCAL_MODEL_ID", "test-model")

    def mock_urlopen_fail(req, timeout=None):
        raise urllib.error.URLError("Connection refused")

    monkeypatch.setattr(urllib.request, "urlopen", mock_urlopen_fail)

    runner = CliRunner()
    runner.invoke(app, ["task", "create", "normal task"])

    review_res = runner.invoke(app, ["task", "local-review", "task-0001"])
    assert review_res.exit_code != 0
    assert "unreachable" in review_res.output.lower() or "connection refused" in review_res.output.lower()

    # Assert error evidence exists
    runs_dir = tmp_path / ".devflow" / "tasks" / "task-0001" / "local-model-runs"
    assert runs_dir.exists()
    run_dir = next(runs_dir.iterdir())
    assert (run_dir / "error.txt").exists()
    assert (run_dir / "run.json").exists()
    
    run_meta = json.loads((run_dir / "run.json").read_text(encoding="utf-8"))
    assert run_meta["status"] == "failed"
    assert "connection" in run_meta["error_message"].lower() or "unreachable" in run_meta["error_message"].lower()


def test_7_empty_assistant_response_fails_clearly(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    # Test 7: empty assistant response fails clearly
    setup_temp_git_repo(tmp_path)
    monkeypatch.chdir(tmp_path)

    monkeypatch.setenv("LOCAL_MODEL_ID", "test-model")

    mock_body = {
        "choices": [{
            "message": {
                "role": "assistant",
                "content": ""
            }
        }]
    }
    monkeypatch.setattr(urllib.request, "urlopen", lambda r, timeout=None: MockResponse(json.dumps(mock_body).encode("utf-8")))

    runner = CliRunner()
    runner.invoke(app, ["task", "create", "normal task"])

    review_res = runner.invoke(app, ["task", "local-review", "task-0001"])
    assert review_res.exit_code != 0
    assert "empty assistant content" in review_res.output.lower()

    # Assert response.json was saved but proposal.md was not
    runs_dir = tmp_path / ".devflow" / "tasks" / "task-0001" / "local-model-runs"
    run_dir = next(runs_dir.iterdir())
    assert (run_dir / "response.json").exists()
    assert not (run_dir / "proposal.md").exists()


def test_8_task_show_displays_local_model_run_evidence(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    # Test 8: task show displays local model run evidence
    setup_temp_git_repo(tmp_path)
    monkeypatch.chdir(tmp_path)

    monkeypatch.setenv("LOCAL_MODEL_ID", "test-model")

    mock_body = {
        "choices": [{
            "message": {
                "role": "assistant",
                "content": "# Local Model Review\n\nShow evidence review."
            }
        }]
    }
    monkeypatch.setattr(urllib.request, "urlopen", lambda r, timeout=None: MockResponse(json.dumps(mock_body).encode("utf-8")))

    runner = CliRunner()
    runner.invoke(app, ["task", "create", "normal task"])
    runner.invoke(app, ["task", "local-review", "task-0001"])

    show_res = runner.invoke(app, ["task", "show", "task-0001"])
    assert show_res.exit_code == 0
    assert "Local Model Runs" in show_res.output
    assert "latest: .devflow/tasks/task-0001/local-model-runs" in show_res.output
    assert "response.md" in show_res.output
    assert "review this evidence" in show_res.output


def test_9_no_transformers_torch_heavy_imports() -> None:
    # Test 9: no transformers/torch/heavy ML imports
    source_files = [
        Path("src/devflow/control_room/local_model_client.py"),
        Path("src/devflow/control_room/local_packet_worker.py"),
    ]
    for p in source_files:
        if p.exists():
            content = p.read_text(encoding="utf-8")
            assert "transformers" not in content
            assert "torch" not in content
            assert "llama_cpp" not in content
            assert "import openai" not in content


def test_10_no_registry_router_scheduler_side_effects(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    # Test 10: no registry/router/scheduler side effects
    setup_temp_git_repo(tmp_path)
    monkeypatch.chdir(tmp_path)

    monkeypatch.setenv("LOCAL_MODEL_ID", "test-model")
    mock_body = {
        "choices": [{
            "message": {
                "role": "assistant",
                "content": "# Local Model Review"
            }
        }]
    }
    monkeypatch.setattr(urllib.request, "urlopen", lambda r, timeout=None: MockResponse(json.dumps(mock_body).encode("utf-8")))

    runner = CliRunner()
    runner.invoke(app, ["task", "create", "normal task"])
    runner.invoke(app, ["task", "local-review", "task-0001"])

    # Ensure no worker registry changes, no local_model_adapter registry, no scheduler, no database
    assert not (tmp_path / ".devflow" / "scheduler.yaml").exists()
    assert not (tmp_path / ".devflow" / "local_model_adapter.yaml").exists()
    assert not (tmp_path / ".devflow" / "control_room" / "local_model_adapter").exists()


def test_11_packet_size_cap_is_respected(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    # Test 11: packet size cap is respected
    setup_temp_git_repo(tmp_path)
    monkeypatch.chdir(tmp_path)

    monkeypatch.setenv("LOCAL_MODEL_ID", "test-model")

    mock_body = {
        "choices": [{
            "message": {
                "role": "assistant",
                "content": "# Local Model Review"
            }
        }]
    }
    monkeypatch.setattr(urllib.request, "urlopen", lambda r, timeout=None: MockResponse(json.dumps(mock_body).encode("utf-8")))

    runner = CliRunner()
    runner.invoke(app, ["task", "create", "normal task"])

    # Run review with very small max-packet-chars
    review_res = runner.invoke(app, ["task", "local-review", "task-0001", "--max-packet-chars", "100"])
    assert review_res.exit_code == 0
    assert "TRUNCATION WARNING" in review_res.output

    runs_dir = tmp_path / ".devflow" / "tasks" / "task-0001" / "local-model-runs"
    run_dir = next(runs_dir.iterdir())
    
    prompt_text = (run_dir / "prompt.md").read_text(encoding="utf-8")
    assert "TRUNCATION WARNING" in prompt_text
    # Check that bounded task packet inside prompt has been capped/truncated
    assert len(prompt_text) < 16000


def test_12_base_url_joining_is_safe() -> None:
    # Test 12: base url joining is safe
    client1 = LocalModelClient(base_url="http://host", model_id="test-model")
    assert client1.get_completions_url() == "http://host/v1/chat/completions"

    client2 = LocalModelClient(base_url="http://host/", model_id="test-model")
    assert client2.get_completions_url() == "http://host/v1/chat/completions"

    client3 = LocalModelClient(base_url="http://host/v1", model_id="test-model")
    assert client3.get_completions_url() == "http://host/v1/chat/completions"

    client4 = LocalModelClient(base_url="http://host/v1/", model_id="test-model")
    assert client4.get_completions_url() == "http://host/v1/chat/completions"


def test_native_chat_default_uses_large_context_and_preserves_large_prompt(monkeypatch: pytest.MonkeyPatch) -> None:
    captured_payload: dict = {}

    def mock_urlopen(req: urllib.request.Request, timeout: float | None = None) -> MockResponse:
        request_data = req.data
        assert isinstance(request_data, bytes)
        captured_payload.update(json.loads(request_data.decode("utf-8")))
        return MockResponse(json.dumps({"message": {"content": "ok"}, "done": True}).encode("utf-8"))

    monkeypatch.setattr(urllib.request, "urlopen", mock_urlopen)
    client = LocalModelClient(base_url="http://127.0.0.1:11434/v1", model_id="qwen3.6-32b-256k:latest")
    large_prompt = "A" * 60000

    client.native_chat_completion("system", large_prompt)

    assert captured_payload["options"]["num_ctx"] == 262144
    assert captured_payload["messages"][1]["content"] == large_prompt


def test_openai_compatible_client_preserves_large_prompt(monkeypatch: pytest.MonkeyPatch) -> None:
    captured_payload: dict = {}

    def mock_urlopen(req: urllib.request.Request, timeout: float | None = None) -> MockResponse:
        request_data = req.data
        assert isinstance(request_data, bytes)
        captured_payload.update(json.loads(request_data.decode("utf-8")))
        return MockResponse(
            json.dumps({"choices": [{"message": {"role": "assistant", "content": "ok"}}]}).encode("utf-8")
        )

    monkeypatch.setattr(urllib.request, "urlopen", mock_urlopen)
    client = LocalModelClient(base_url="http://127.0.0.1:11434/v1", model_id="qwen3.6-32b-256k:latest")
    large_prompt = "B" * 60000

    client.chat_completion("system", large_prompt)

    assert captured_payload["messages"][1]["content"] == large_prompt


def test_regression_1_packet_excludes_workspace(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    # 1. packet generation excludes .devflow/workspaces/**
    setup_temp_git_repo(tmp_path)
    monkeypatch.chdir(tmp_path)

    runner = CliRunner()
    runner.invoke(app, ["task", "create", "normal task"])

    # Create dummy files in workspace that should be excluded
    w_dir = tmp_path / ".devflow" / "workspaces" / "task-0001"
    
    venv_file = w_dir / ".venv-1" / "file.txt"
    venv_file.parent.mkdir(parents=True, exist_ok=True)
    venv_file.write_text("SENSITIVE VENV CONTENT", encoding="utf-8")

    git_file = w_dir / ".git" / "file.txt"
    git_file.parent.mkdir(parents=True, exist_ok=True)
    git_file.write_text("SENSITIVE GIT CONTENT", encoding="utf-8")

    monkeypatch.setenv("LOCAL_MODEL_ID", "test-model")
    mock_body = {"choices": [{"message": {"role": "assistant", "content": "# Local Model Review\n\nok"}}]}
    monkeypatch.setattr(urllib.request, "urlopen", lambda r, t=None: MockResponse(json.dumps(mock_body).encode("utf-8")))

    runner.invoke(app, ["task", "local-review", "task-0001"])

    runs_dir = tmp_path / ".devflow" / "tasks" / "task-0001" / "local-model-runs"
    run_dir = next(runs_dir.iterdir())
    prompt_text = (run_dir / "prompt.md").read_text(encoding="utf-8")

    assert "SENSITIVE VENV CONTENT" not in prompt_text
    assert "SENSITIVE GIT CONTENT" not in prompt_text
    assert "workspaces/task-0001" not in prompt_text


def test_regression_2_packet_excludes_saved_packet(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    # 2. packet generation excludes saved packet.json/packet.md
    setup_temp_git_repo(tmp_path)
    monkeypatch.chdir(tmp_path)

    runner = CliRunner()
    runner.invoke(app, ["task", "create", "normal task"])

    t_dir = tmp_path / ".devflow" / "tasks" / "task-0001"
    
    packet_json = t_dir / "packet.json"
    packet_json.write_text("SENSITIVE JSON PACKET", encoding="utf-8")

    packet_md = t_dir / "packet.md"
    packet_md.write_text("SENSITIVE MD PACKET", encoding="utf-8")

    monkeypatch.setenv("LOCAL_MODEL_ID", "test-model")
    mock_body = {"choices": [{"message": {"role": "assistant", "content": "# Local Model Review\n\nok"}}]}
    monkeypatch.setattr(urllib.request, "urlopen", lambda r, t=None: MockResponse(json.dumps(mock_body).encode("utf-8")))

    runner.invoke(app, ["task", "local-review", "task-0001"])

    runs_dir = t_dir / "local-model-runs"
    run_dir = next(runs_dir.iterdir())
    prompt_text = (run_dir / "prompt.md").read_text(encoding="utf-8")

    assert "SENSITIVE JSON PACKET" not in prompt_text
    assert "SENSITIVE MD PACKET" not in prompt_text
    assert "packet.json" not in prompt_text
    assert "packet.md" not in prompt_text


def test_regression_3_packet_excludes_runs_artifacts(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    # 3. packet generation excludes local-model-runs/** prompt/response artifacts
    setup_temp_git_repo(tmp_path)
    monkeypatch.chdir(tmp_path)

    runner = CliRunner()
    runner.invoke(app, ["task", "create", "normal task"])

    t_dir = tmp_path / ".devflow" / "tasks" / "task-0001"
    
    run_dir = t_dir / "local-model-runs" / "run-9999"
    run_dir.mkdir(parents=True, exist_ok=True)
    (run_dir / "response.md").write_text("SENSITIVE RESPONSE CONTENT", encoding="utf-8")
    (run_dir / "prompt.md").write_text("SENSITIVE PROMPT CONTENT", encoding="utf-8")
    (run_dir / "run.json").write_text("SENSITIVE RUN CONTENT", encoding="utf-8")

    monkeypatch.setenv("LOCAL_MODEL_ID", "test-model")
    mock_body = {"choices": [{"message": {"role": "assistant", "content": "# Local Model Review\n\nok"}}]}
    monkeypatch.setattr(urllib.request, "urlopen", lambda r, t=None: MockResponse(json.dumps(mock_body).encode("utf-8")))

    runner.invoke(app, ["task", "local-review", "task-0001"])

    runs_dir = t_dir / "local-model-runs"
    latest_run_dir = sorted([p for p in runs_dir.iterdir() if p.is_dir() and p.name != "run-9999"])[-1]
    prompt_text = (latest_run_dir / "prompt.md").read_text(encoding="utf-8")

    assert "SENSITIVE RESPONSE CONTENT" not in prompt_text
    assert "SENSITIVE PROMPT CONTENT" not in prompt_text
    assert "local-model-runs" not in prompt_text


def test_regression_4_second_run_excludes_first_run(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    # 4. local-review second run does not include first run prompt/response
    setup_temp_git_repo(tmp_path)
    monkeypatch.chdir(tmp_path)

    runner = CliRunner()
    runner.invoke(app, ["task", "create", "normal task"])

    monkeypatch.setenv("LOCAL_MODEL_ID", "test-model")
    
    mock_body_1 = {"choices": [{"message": {"role": "assistant", "content": "# Local Model Review\n\nFIRST RUN RESPONSE CONTENT"}}]}
    monkeypatch.setattr(urllib.request, "urlopen", lambda r, t=None: MockResponse(json.dumps(mock_body_1).encode("utf-8")))
    runner.invoke(app, ["task", "local-review", "task-0001"])

    mock_body_2 = {"choices": [{"message": {"role": "assistant", "content": "# Local Model Review\n\nSECOND RUN RESPONSE CONTENT"}}]}
    monkeypatch.setattr(urllib.request, "urlopen", lambda r, t=None: MockResponse(json.dumps(mock_body_2).encode("utf-8")))
    runner.invoke(app, ["task", "local-review", "task-0001"])

    t_dir = tmp_path / ".devflow" / "tasks" / "task-0001"
    runs_dir = t_dir / "local-model-runs"
    
    run_folders = sorted([p for p in runs_dir.iterdir() if p.is_dir()])
    assert len(run_folders) == 2
    
    prompt_2_text = (run_folders[1] / "prompt.md").read_text(encoding="utf-8")
    assert "FIRST RUN RESPONSE CONTENT" not in prompt_2_text
    assert "local-model-runs" not in prompt_2_text


def test_regression_5_mocked_urlopen_completes_quickly(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    # 5. local worker test uses mocked urlopen and completes quickly
    import time
    setup_temp_git_repo(tmp_path)
    monkeypatch.chdir(tmp_path)

    monkeypatch.setenv("LOCAL_MODEL_ID", "test-model")
    mock_body = {"choices": [{"message": {"role": "assistant", "content": "# Local Model Review\n\nok"}}]}
    monkeypatch.setattr(urllib.request, "urlopen", lambda r, timeout=None: MockResponse(json.dumps(mock_body).encode("utf-8")))

    start = time.time()
    runner = CliRunner()
    runner.invoke(app, ["task", "create", "normal task"])
    res = runner.invoke(app, ["task", "local-review", "task-0001"])
    duration = time.time() - start
    print(res.output)
    assert res.exit_code == 0
    assert duration < 2.0  # Must be extremely fast


def test_regression_6_prompt_size_cap(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    # 6. prompt size cap is enforced (MAX_TOTAL_INCLUDED_SOURCE_CHARS)
    setup_temp_git_repo(tmp_path)
    monkeypatch.chdir(tmp_path)

    runner = CliRunner()
    runner.invoke(app, ["goal", "init", "--from", "docs/architecture.md"]) # Just init goal

    # Create very large PRD and out-of-scope files
    g_dir = goal_dir(tmp_path, "G-0001")
    (g_dir / "prd.md").write_text("A" * 10000, encoding="utf-8")
    (g_dir / "out-of-scope.md").write_text("B" * 5000, encoding="utf-8")

    runner.invoke(app, ["goal", "create-task", "G-0001", "TS-0001"])

    monkeypatch.setenv("LOCAL_MODEL_ID", "test-model")
    mock_body = {"choices": [{"message": {"role": "assistant", "content": "# Local Model Review\n\nok"}}]}
    monkeypatch.setattr(urllib.request, "urlopen", lambda r, t=None: MockResponse(json.dumps(mock_body).encode("utf-8")))

    runner.invoke(app, ["task", "local-review", "task-0001"])

    runs_dir = tmp_path / ".devflow" / "tasks" / "task-0001" / "local-model-runs"
    run_dir = next(runs_dir.iterdir())
    prompt_text = (run_dir / "prompt.md").read_text(encoding="utf-8")

    # Assert local packet generation does not silently neuter normal project context.
    assert "A" * 10000 in prompt_text
    assert "B" * 5000 in prompt_text
