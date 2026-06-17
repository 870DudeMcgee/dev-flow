from __future__ import annotations

import json
import urllib.request
from pathlib import Path
from typing import Any

import pytest

from devflow.control_room.agent_registry import load_agent_registry
from devflow.control_room.brainstorm import escalate_brainstorm_session, run_brainstorm_message
from tests.helpers import setup_temp_git_repo


class MockResponse:
    def __init__(self, body: dict[str, Any]) -> None:
        self.body = json.dumps(body).encode("utf-8")

    def read(self, *args: Any, **kwargs: Any) -> bytes:
        return self.body

    def __enter__(self) -> "MockResponse":
        return self

    def __exit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        return None


def test_deepseek_flash_free_brainstorm_profile_is_registry_visible(tmp_path: Path) -> None:
    setup_temp_git_repo(tmp_path)

    profile = load_agent_registry(tmp_path).require_agent("deepseek-v4-flash-free-brainstormer")

    assert profile.provider == "openrouter"
    assert profile.model == "deepseek/deepseek-v4-flash:free"
    assert profile.default_mode == "frontier_read_only"
    assert "brainstorm" in profile.secondary_roles
    assert "<brainstorms>/**" in profile.allowed_writes


def test_brainstorm_message_missing_key_fails_without_fake_assistant_output(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    setup_temp_git_repo(tmp_path)
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)

    def fail_urlopen(req: urllib.request.Request, timeout: float | None = None) -> MockResponse:
        raise AssertionError("missing API key must fail before provider call")

    monkeypatch.setattr(urllib.request, "urlopen", fail_urlopen)

    payload = run_brainstorm_message(
        root=tmp_path,
        message="I want a better operating-layer brainstorm flow.",
        session_id="session-001",
    )

    assert payload["status"] == "failed"
    assert "OPENROUTER_API_KEY" in payload["error"]
    transcript = tmp_path / payload["transcript_path"]
    assert transcript.exists()
    records = [json.loads(line) for line in transcript.read_text(encoding="utf-8").splitlines()]
    assert records[-1]["role"] == "system"
    assert records[-1]["kind"] == "provider_error"
    assert not any(record.get("role") == "assistant" for record in records)


def test_brainstorm_message_calls_deepseek_free_and_appends_transcript(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    setup_temp_git_repo(tmp_path)
    monkeypatch.setenv("OPENROUTER_API_KEY", "sk-or-brainstorm-secret")
    captured_requests: list[dict[str, Any]] = []

    def mock_urlopen(req: urllib.request.Request, timeout: float | None = None) -> MockResponse:
        captured_requests.append(
            {
                "url": req.full_url,
                "timeout": timeout,
                "payload": json.loads(req.data.decode("utf-8")),
            }
        )
        return MockResponse(
            {
                "choices": [
                    {
                        "message": {
                            "content": json.dumps(
                                {
                                    "message": "Start by naming the desired user journey, then promote it to a spec.",
                                    "stage_hint": "spec",
                                }
                            )
                        }
                    }
                ],
                "usage": {"total_tokens": 42},
            }
        )

    monkeypatch.setattr(urllib.request, "urlopen", mock_urlopen)

    payload = run_brainstorm_message(
        root=tmp_path,
        message="Make the brainstorming area feel like Codex chat.",
        session_id="session-002",
    )

    assert payload["status"] == "success"
    assert payload["model"] == "deepseek/deepseek-v4-flash:free"
    assert payload["assistant_message"].startswith("Start by naming")
    assert captured_requests[0]["url"] == "https://openrouter.ai/api/v1/chat/completions"
    assert captured_requests[0]["payload"]["model"] == "deepseek/deepseek-v4-flash:free"

    transcript = tmp_path / payload["transcript_path"]
    records = [json.loads(line) for line in transcript.read_text(encoding="utf-8").splitlines()]
    assert [record["role"] for record in records] == ["user", "assistant"]
    assert "sk-or-brainstorm-secret" not in (tmp_path / payload["run_path"]).read_text(encoding="utf-8")


def test_brainstorm_escalation_writes_spec_plan_and_returns_task_action(tmp_path: Path) -> None:
    setup_temp_git_repo(tmp_path)
    run_brainstorm_message(
        root=tmp_path,
        message="Build a chat-first brainstorm to implementation flow.",
        session_id="session-003",
    )

    spec_payload = escalate_brainstorm_session(root=tmp_path, session_id="session-003", stage="spec")
    plan_payload = escalate_brainstorm_session(root=tmp_path, session_id="session-003", stage="plan")
    implementation_payload = escalate_brainstorm_session(
        root=tmp_path,
        session_id="session-003",
        stage="implementation",
        title="Build brainstorm workbench",
    )

    assert spec_payload["status"] == "ready"
    assert (tmp_path / spec_payload["artifact_path"]).read_text(encoding="utf-8").startswith("# Brainstorm Spec")
    assert plan_payload["status"] == "ready"
    assert (tmp_path / plan_payload["artifact_path"]).read_text(encoding="utf-8").startswith("# Brainstorm Plan")
    assert implementation_payload["action"]["label"] == "Open Implementation Task"
    assert implementation_payload["action"]["command"] == "devflow task create 'Build brainstorm workbench'"
    assert implementation_payload["action"]["safety_class"] == "approval_required_task_state"
