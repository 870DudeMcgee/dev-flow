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


def test_task_run_read_only_local_profile_reports_agent_run_next_action(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    setup_temp_git_repo(tmp_path)
    monkeypatch.chdir(tmp_path)
    assert runner.invoke(app, ["task", "create", "Read-only profile misuse"]).exit_code == 0

    result = runner.invoke(app, ["task", "run", "task-0001", "--worker", "local-qwopus-inspector"])

    assert result.exit_code != 0
    assert "read-only local model worker-pool profile" in result.output
    assert "devflow agent run --task <task-id> --profile local-qwopus-inspector" in result.output


def test_task_run_remote_provider_agent_still_fails_closed(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    setup_temp_git_repo(tmp_path)
    monkeypatch.chdir(tmp_path)
    assert runner.invoke(app, ["task", "create", "Remote refusal"]).exit_code == 0
    agents_dir = tmp_path / ".devflow" / "agents"
    agents_dir.mkdir(parents=True, exist_ok=True)
    (agents_dir / "registry.yaml").write_text(
        "version: 1\n"
        "agents:\n"
        "  remote-worker:\n"
        "    provider: openai\n"
        "    model: gpt-5\n"
        "    adapter: openai_chat\n"
        "    role: frontier_planner_architect_reviewer\n"
        "    tier: frontier\n"
        "    default_mode: frontier_read_only\n"
        "    execution_mode: automated\n"
        "    workspace: isolated_task_workspace\n"
        "    can_use_network: true\n"
        "    can_promote: false\n"
        "    enabled: true\n",
        encoding="utf-8",
    )

    result = runner.invoke(app, ["task", "run", "task-0001", "--worker", "remote-worker"])

    assert result.exit_code != 0
    assert "cannot execute" in result.output
    assert "experimental_readonly" in result.output


def test_agent_run_local_patch_profile_reports_task_run_next_action(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    setup_temp_git_repo(tmp_path)
    monkeypatch.chdir(tmp_path)
    assert runner.invoke(app, ["task", "create", "Patch profile misuse"]).exit_code == 0

    result = runner.invoke(app, ["agent", "run", "--task", "task-0001", "--profile", "qwopus-implementer", "--dry-run"])

    assert result.exit_code != 0
    assert "devflow task run <task-id> --worker qwopus-implementer" in result.output


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


def test_gemma_summarizer_prompt_requires_grounded_task_brief(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    setup_temp_git_repo(tmp_path)
    monkeypatch.chdir(tmp_path)
    create_result = runner.invoke(app, ["task", "create", "first approved evidence smoke"])
    assert create_result.exit_code == 0, create_result.output
    captured_payloads: list[dict[str, Any]] = []
    captured_urls: list[str] = []

    def mock_urlopen(req: urllib.request.Request, timeout: float | None = None) -> MockResponse:
        captured_urls.append(req.full_url)
        captured_payloads.append(json.loads(req.data.decode("utf-8")))
        body = {
            "message": {
                "role": "assistant",
                "content": (
                    "## Task Grounding\n"
                    "- Task ID: task-0001\n"
                    "- Task Title: first approved evidence smoke\n"
                    "- Task Status: created\n"
                    "- Worker/Profile: local-gemma4-summarizer\n"
                    "- Evidence Reviewed: bounded task packet\n\n"
                    "## Summary\nGrounded.\n\n"
                    "## Findings\n- Packet names task-0001.\n\n"
                    "## Risks Or Questions\n- None.\n\n"
                    "## Suggested Next Dev-Flow Action\nReview evidence."
                ),
            },
            "done": True,
        }
        return MockResponse(json.dumps(body).encode("utf-8"))

    monkeypatch.setattr(urllib.request, "urlopen", mock_urlopen)

    result = runner.invoke(
        app,
        ["agent", "run", "--task", "task-0001", "--profile", "local-gemma4-summarizer", "--json"],
    )

    assert result.exit_code == 0, result.output
    assert captured_urls == ["http://127.0.0.1:11434/api/chat"]
    native_payload = captured_payloads[0]
    assert native_payload["think"] is False
    assert native_payload["options"]["num_ctx"] >= 8192
    assert native_payload["options"]["temperature"] == 0
    messages = native_payload["messages"]
    system_prompt = messages[0]["content"]
    user_prompt = messages[1]["content"]
    assert "Never invent or substitute a task id" in system_prompt
    assert "If the packet says task-0001, the response must say task-0001" in user_prompt
    assert "Your response must begin with this exact task id: task-0001" in user_prompt
    assert len(user_prompt) < 6000
    assert "Source Pointers" not in user_prompt
    assert "## Task Grounding" in user_prompt
    assert "Task ID:" in user_prompt
    assert "Task Title:" in user_prompt
    assert "Evidence Reviewed:" in user_prompt
    payload = json.loads(result.output)
    run_metadata = json.loads((tmp_path / payload["run_metadata_path"]).read_text(encoding="utf-8"))
    assert run_metadata["runtime"] == "local_model_client.native_ollama_chat"
    assert run_metadata["base_url"] == "http://127.0.0.1:11434/api/chat"
    assert run_metadata["quality_score"] == 1.0


def test_gemma_summarizer_low_quality_response_is_flagged(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    setup_temp_git_repo(tmp_path)
    monkeypatch.chdir(tmp_path)
    create_result = runner.invoke(app, ["task", "create", "grounded evidence smoke"])
    assert create_result.exit_code == 0, create_result.output

    def mock_urlopen(req: urllib.request.Request, timeout: float | None = None) -> MockResponse:
        body = {
            "message": {
                "role": "assistant",
                "content": "Task ID: N/A\nThis is a generic local model readiness summary.",
            },
            "done": True,
        }
        return MockResponse(json.dumps(body).encode("utf-8"))

    monkeypatch.setattr(urllib.request, "urlopen", mock_urlopen)

    result = runner.invoke(
        app,
        ["agent", "run", "--task", "task-0001", "--profile", "local-gemma4-summarizer", "--json"],
    )

    assert result.exit_code == 1
    payload = json.loads(result.output)
    assert payload["status"] == "low_quality"
    assert payload["quality_score"] < 0.75
    assert "response did not include task id task-0001" in payload["quality_notes"]
    evidence_dir = tmp_path / payload["evidence_dir"]
    run_metadata = json.loads((evidence_dir / "run.json").read_text(encoding="utf-8"))
    assert run_metadata["status"] == "low_quality"
    assert run_metadata["quality_score"] == payload["quality_score"]


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
