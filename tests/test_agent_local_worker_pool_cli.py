from __future__ import annotations

import json
import subprocess
import urllib.request
from pathlib import Path
from typing import Any

import pytest
from typer.testing import CliRunner

from devflow.cli import app
from devflow.control_room.local_model_client import LocalModelClient
from tests.helpers import setup_temp_git_repo


runner = CliRunner()


class MockResponse:
    def __init__(self, body: bytes, status: int = 200) -> None:
        self.body = body
        self.status = status

    def read(self, *args: Any, **kwargs: Any) -> bytes:
        return self.body

    def __enter__(self) -> "MockResponse":
        return self

    def __exit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        return None


def test_agent_list_show_policy_json_for_local_worker_pool(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    setup_temp_git_repo(tmp_path)
    monkeypatch.chdir(tmp_path)

    list_result = runner.invoke(app, ["agent", "list", "--json"])
    assert list_result.exit_code == 0, list_result.output
    list_payload = json.loads(list_result.output)
    profile = next(agent for agent in list_payload["agents"] if agent["id"] == "local-qwopus-inspector")
    assert profile["hermes_delegable"] is True
    assert profile["default_mode"] == "read_only"
    assert profile["machine_class"] == "mac_studio"
    assert profile["model_alias_group"] == "qwopus-qwen36-07d35212591f"

    show_result = runner.invoke(app, ["agent", "show", "local-qwopus-inspector", "--json"])
    assert show_result.exit_code == 0, show_result.output
    show_payload = json.loads(show_result.output)
    assert show_payload["model"] == "qwopus:latest"
    assert show_payload["local_model_worker_pool_runnable"] is True
    assert show_payload["required_verification_command"] == "ollama show qwopus:latest"

    policy_result = runner.invoke(app, ["agent", "policy", "--json"])
    assert policy_result.exit_code == 0, policy_result.output
    policy_payload = json.loads(policy_result.output)
    assert "proposal.patch writes by read-only profiles" in policy_payload["forbidden"]
    assert policy_payload["hermes"]["must_not_own_worker_state"] is True


def test_agent_run_dry_run_json_does_not_call_model_or_write_evidence(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    setup_temp_git_repo(tmp_path)
    monkeypatch.chdir(tmp_path)
    create_result = runner.invoke(app, ["task", "create", "local worker pool dry run"])
    assert create_result.exit_code == 0, create_result.output
    before_status = _git_status(tmp_path)

    def fail_chat(self: LocalModelClient, system_prompt: str, user_prompt: str) -> dict[str, Any]:
        raise AssertionError("dry-run must not call the local model")

    monkeypatch.setattr(LocalModelClient, "chat_completion", fail_chat)

    result = runner.invoke(
        app,
        ["agent", "run", "--task", "task-0001", "--profile", "local-qwopus-inspector", "--dry-run", "--json"],
    )

    assert result.exit_code == 0, result.output
    payload = json.loads(result.output)
    assert payload["dry_run"] is True
    assert payload["will_call_model"] is False
    assert payload["will_write_source"] is False
    assert payload["will_write_proposal_patch"] is False
    assert payload["machine_class"] == "mac_studio"
    assert payload["weight_class"] == "heavy"
    expected_dir = tmp_path / payload["expected_evidence_outputs"]["evidence_dir"]
    assert not expected_dir.exists()
    assert not (tmp_path / ".devflow/tasks/task-0001/agents/local-qwopus-inspector/proposal.patch").exists()
    assert _git_status(tmp_path) == before_status


def test_agent_run_fake_local_worker_writes_worker_evidence_without_proposal_patch(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    setup_temp_git_repo(tmp_path)
    monkeypatch.chdir(tmp_path)
    create_result = runner.invoke(app, ["task", "create", "local worker pool run"])
    assert create_result.exit_code == 0, create_result.output
    task_yaml_before = (tmp_path / ".devflow/tasks/task-0001/task.yaml").read_text(encoding="utf-8")
    git_status_before = _git_status(tmp_path)
    captured_requests: list[dict[str, Any]] = []

    def mock_urlopen(req: urllib.request.Request, timeout: float | None = None) -> MockResponse:
        captured_requests.append(
            {
                "url": req.full_url,
                "payload": json.loads(req.data.decode("utf-8")),
                "timeout": timeout,
            }
        )
        body = {
            "choices": [
                {
                    "message": {
                        "role": "assistant",
                        "content": "## Summary\nFake inspector evidence.\n\n## Suggested Next Dev-Flow Action\nReview only.",
                    }
                }
            ]
        }
        return MockResponse(json.dumps(body).encode("utf-8"))

    monkeypatch.setattr(urllib.request, "urlopen", mock_urlopen)

    result = runner.invoke(
        app,
        ["agent", "run", "--task", "task-0001", "--profile", "local-qwopus-inspector", "--json"],
    )

    assert result.exit_code == 0, result.output
    payload = json.loads(result.output)
    assert payload["status"] == "success"
    assert payload["model"] == "qwopus:latest"
    assert captured_requests[0]["url"] == "http://127.0.0.1:11434/v1/chat/completions"
    assert captured_requests[0]["payload"]["model"] == "qwopus:latest"

    evidence_dir = tmp_path / payload["evidence_dir"]
    assert (evidence_dir / "run.json").exists()
    assert (evidence_dir / "packet.md").exists()
    assert (evidence_dir / "response.md").read_text(encoding="utf-8").startswith("## Summary")
    assert (evidence_dir / "raw_output.txt").exists()
    assert not (evidence_dir / "proposal.patch").exists()
    assert not (tmp_path / ".devflow/tasks/task-0001/agents/local-qwopus-inspector/proposal.patch").exists()

    run_metadata = json.loads((evidence_dir / "run.json").read_text(encoding="utf-8"))
    assert run_metadata["profile_id"] == "local-qwopus-inspector"
    assert run_metadata["worker_type"] == "local_model_worker_pool"
    assert run_metadata["adapter_maturity"] == "local_patch_runtime"
    assert run_metadata["permission_mode"] == "read_only"
    assert run_metadata["hermes_delegable"] is True
    assert run_metadata["machine_class"] == "mac_studio"
    assert run_metadata["model_role_name"] == "qwopus-supervisor"

    assert (tmp_path / ".devflow/tasks/task-0001/task.yaml").read_text(encoding="utf-8") == task_yaml_before
    assert _git_status(tmp_path) == git_status_before


def test_agent_run_unknown_profile_fails_clearly(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    setup_temp_git_repo(tmp_path)
    monkeypatch.chdir(tmp_path)
    runner.invoke(app, ["task", "create", "local worker pool run"])

    result = runner.invoke(app, ["agent", "run", "--task", "task-0001", "--profile", "missing-profile", "--dry-run", "--json"])

    assert result.exit_code == 1
    assert "Unknown agent 'missing-profile'" in result.output


def _git_status(root: Path) -> str:
    return subprocess.run(
        ["git", "status", "--short"],
        cwd=root,
        text=True,
        capture_output=True,
        check=True,
    ).stdout
