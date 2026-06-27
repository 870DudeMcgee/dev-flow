from __future__ import annotations

import json
import urllib.request
from pathlib import Path
from typing import Any

import pytest

from devflow.control_room.agent_registry import load_agent_registry
from devflow.control_room.brainstorm import (
    BrainstormError,
    escalate_brainstorm_session,
    run_brainstorm_message,
    start_brainstorm_from_idea,
)
from devflow.control_room.brainstorm_pipeline import (
    build_brainstorm_escalation_result,
    build_brainstorm_pipeline_detail,
)
from devflow.control_room.openrouter_agent import run_advice
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


def _write_local_qwen_profile(root: Path, *, base_url: str) -> None:
    providers_dir = root / ".devflow" / "providers"
    agents_dir = root / ".devflow" / "agents"
    providers_dir.mkdir(parents=True, exist_ok=True)
    agents_dir.mkdir(parents=True, exist_ok=True)
    (providers_dir / "qwen35-mtp.yaml").write_text(
        "\n".join(
            [
                "provider: qwen35-mtp",
                "adapter: openai_compatible",
                f"base_url: {base_url}",
                "default_timeout_seconds: 30",
                "enabled: true",
                "",
            ]
        ),
        encoding="utf-8",
    )
    (agents_dir / "registry.yaml").write_text(
        "\n".join(
            [
                "version: 1",
                "default_agent: local-qwen35-mtp",
                "agents:",
                "  local-qwen35-mtp:",
                "    provider: qwen35-mtp",
                "    model: qwen35-9b-mtp",
                "    adapter: openai_compatible",
                "    role: frontier_planner_architect_reviewer",
                "    tier: local",
                "    default_mode: read_only",
                "    execution_mode: automated",
                "    workspace: isolated_task_workspace",
                "    can_see:",
                "      - task_packet",
                "      - recent_events",
                "    can_touch:",
                "      - <task>/local-model-runs/**",
                "    cannot_touch:",
                "      - <main_checkout>/**",
                "      - <workspace>/**",
                "      - .git/**",
                "    allowed_reads:",
                "      - <task>/packet.json",
                "      - <task>/events.jsonl",
                "      - <workspace>/**",
                "    allowed_writes:",
                "      - <task>/local-model-runs/**",
                "    forbidden_writes:",
                "      - <main_checkout>/**",
                "      - <workspace>/**",
                "      - <task>/agents/**/proposal.patch",
                "      - .git/**",
                "    required_outputs:",
                "      - Write bounded local model evidence only.",
                "    completion_rules:",
                "      - Advisory evidence only.",
                "    can_run_shell: false",
                "    can_use_network: false",
                "    can_promote: false",
                "    hermes_delegable: true",
                "    enabled: true",
                "",
            ]
        ),
        encoding="utf-8",
    )


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
    import devflow.control_room.env_loader as env_loader_mod
    monkeypatch.setattr(env_loader_mod, "_HERMES_ENV_PATH", tmp_path / "nonexistent.env")

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
    monkeypatch.setenv("OPENROUTER_API_KEY", "sk-or-...cret")
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
    assert "sk-or-...cret" not in (tmp_path / payload["run_path"]).read_text(encoding="utf-8")


def test_brainstorm_hermes_codex_profile_does_not_fall_back_to_openrouter(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    setup_temp_git_repo(tmp_path)
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)

    def fail_urlopen(req: urllib.request.Request, timeout: float | None = None) -> MockResponse:
        raise AssertionError("Hermes subscription profile must not call OpenRouter-compatible HTTP APIs")

    monkeypatch.setattr(urllib.request, "urlopen", fail_urlopen)

    payload = run_brainstorm_message(
        root=tmp_path,
        message="Use the subscription-backed Codex profile.",
        session_id="session-hermes",
        profile_id="hermes-codex-gpt55",
    )

    assert payload["status"] == "failed"
    assert "Hermes/OpenAI subscription profile" in payload["error"]
    assert "OPENROUTER_API_KEY" not in payload["error"]
    assert payload["will_call_provider"] is False
    assert payload["provider"] == "openai-codex"
    assert payload["model"] == "gpt-5.5"
    records = [
        json.loads(line)
        for line in (tmp_path / payload["transcript_path"]).read_text(encoding="utf-8").splitlines()
    ]
    assert records[-1]["kind"] == "provider_error"
    assert "OPENROUTER_API_KEY" not in records[-1]["content"]


def test_local_qwen_openai_compatible_profile_runs_without_api_key(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    setup_temp_git_repo(tmp_path)
    _write_local_qwen_profile(tmp_path, base_url="http://127.0.0.1:9191/v1")
    monkeypatch.delenv("QWEN35_MTP_API_KEY", raising=False)
    captured_requests: list[dict[str, Any]] = []

    def mock_urlopen(req: urllib.request.Request, timeout: float | None = None) -> MockResponse:
        headers = {key.lower(): value for key, value in req.header_items()}
        captured_requests.append(
            {
                "url": req.full_url,
                "timeout": timeout,
                "headers": headers,
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
                                    "message": "Local Qwen is wired for Brainstorm.",
                                    "stage_hint": "brainstorm",
                                    "summary": "Local Qwen advisory works.",
                                    "recommendations": [
                                        {
                                            "title": "Use local Qwen",
                                            "rationale": "Hermes endpoint is local.",
                                            "next_safe_action": "continue",
                                        }
                                    ],
                                }
                            )
                        }
                    }
                ],
                "usage": {"total_tokens": 18},
            }
        )

    monkeypatch.setattr(urllib.request, "urlopen", mock_urlopen)

    brainstorm_payload = run_brainstorm_message(
        root=tmp_path,
        message="Use the local Qwen Hermes model for brainstorm.",
        session_id="session-local-qwen",
        profile_id="local-qwen35-mtp",
    )
    advice_payload = run_advice(
        root=tmp_path,
        profile_id="local-qwen35-mtp",
        job="status",
        max_prompt_chars=8_000,
    )

    assert brainstorm_payload["status"] == "success"
    assert brainstorm_payload["provider"] == "qwen35-mtp"
    assert brainstorm_payload["model"] == "qwen35-9b-mtp"
    assert advice_payload["status"] == "success"
    assert [request["url"] for request in captured_requests] == [
        "http://127.0.0.1:9191/v1/chat/completions",
        "http://127.0.0.1:9191/v1/chat/completions",
    ]
    assert all("authorization" not in request["headers"] for request in captured_requests)
    assert all(request["payload"]["model"] == "qwen35-9b-mtp" for request in captured_requests)


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
    implementation_with_done = escalate_brainstorm_session(
        root=tmp_path,
        session_id="session-003",
        stage="implementation",
        title="Build brainstorm workbench",
        definition_of_done="Start button is visible and task creation is logged.",
    )

    assert spec_payload["status"] == "ready"
    assert (tmp_path / spec_payload["artifact_path"]).read_text(encoding="utf-8").startswith("# Brainstorm Spec")
    assert plan_payload["status"] == "ready"
    assert (tmp_path / plan_payload["artifact_path"]).read_text(encoding="utf-8").startswith("# Brainstorm Plan")
    assert implementation_payload["action"]["label"] == "Open Implementation Task"
    assert implementation_payload["action"]["command"] == "devflow task create 'Build brainstorm workbench'"
    assert implementation_payload["action"]["safety_class"] == "approval_required_task_state"
    assert implementation_with_done["action"]["command"] == (
        "devflow task create --definition-of-done "
        "'Start button is visible and task creation is logged.' 'Build brainstorm workbench'"
    )
    pipeline = implementation_with_done["pipeline_detail"]
    assert pipeline["has_spec"] is True
    assert pipeline["has_plan"] is True
    assert pipeline["has_implementation"] is True
    assert pipeline["definition_of_done"] == "Start button is visible and task creation is logged."
    assert pipeline["artifacts"]["transcript"]["artifact_path"] == (
        ".devflow/brainstorms/session-003/transcript.jsonl"
    )
    assert pipeline["artifacts"]["implementation"]["artifact_path"] == (
        ".devflow/brainstorms/session-003/implementation.md"
    )
    assert pipeline["advisory_model"]["profile_id"] == "deepseek-v4-flash-free-brainstormer"
    assert pipeline["task_action"]["command"] == implementation_with_done["action"]["command"]
    assert pipeline["task_action"]["context_required"] is True
    assert pipeline["implementation_context"]["source_paths"] == [
        ".devflow/brainstorms/session-003/spec.md",
        ".devflow/brainstorms/session-003/plan.md",
    ]
    assert pipeline["implementation_context"]["target_path_template"] == (
        ".devflow/workspaces/{task_id}/implementation-context.md"
    )
    persisted = json.loads(
        (tmp_path / ".devflow" / "brainstorms" / "session-003" / "pipeline.json").read_text(encoding="utf-8")
    )
    assert persisted["task_action"]["command"] == implementation_with_done["action"]["command"]
    assert "## Definition of Done" in (tmp_path / implementation_with_done["artifact_path"]).read_text(encoding="utf-8")


def test_brainstorm_escalation_result_mirrors_pipeline_detail_for_compatibility(tmp_path: Path) -> None:
    setup_temp_git_repo(tmp_path)
    session_id = "typed-response"
    session_dir = tmp_path / ".devflow" / "brainstorms" / session_id
    session_dir.mkdir(parents=True)
    records = [
        {
            "created_at": "2026-06-26T00:00:00Z",
            "role": "user",
            "kind": "message",
            "content": "Turn this brainstorm into a task.",
        }
    ]
    spec_path = session_dir / "spec.md"
    plan_path = session_dir / "plan.md"
    implementation_path = session_dir / "implementation.md"
    spec_path.write_text("# Brainstorm Spec\n\nBuild the thing.\n", encoding="utf-8")
    plan_path.write_text("# Brainstorm Plan\n\nShip it safely.\n", encoding="utf-8")
    implementation_path.write_text("# Implementation Task\n\nCreate the task.\n", encoding="utf-8")

    detail = build_brainstorm_pipeline_detail(
        tmp_path,
        session_id=session_id,
        stage="implementation",
        records=records,
        artifact_path=implementation_path,
        title="Build typed response",
        definition_of_done="Task action comes from pipeline detail.",
        model_info={"used_model": False, "profile_id": "test-profile"},
    )
    response = build_brainstorm_escalation_result(
        detail,
        artifact_path=".devflow/brainstorms/typed-response/implementation.md",
        model_info={"used_model": False, "profile_id": "test-profile"},
    ).model_dump(mode="json")

    pipeline = response["pipeline_detail"]
    assert pipeline["task_action"]["command"] == response["action"]["command"]
    assert pipeline["task_action"] == response["action"]
    assert response["implementation_context"] == pipeline["implementation_context"]["text"]
    assert response["implementation_context_path"] == pipeline["implementation_context"]["artifact_path"]

    spec_detail = build_brainstorm_pipeline_detail(
        tmp_path,
        session_id=session_id,
        stage="spec",
        records=records,
        artifact_path=spec_path,
        model_info={"used_model": False, "profile_id": "test-profile"},
    )
    spec_response = build_brainstorm_escalation_result(spec_detail).model_dump(mode="json")

    assert spec_response["pipeline_detail"]["stage"] == "spec"
    assert spec_response["pipeline_detail"]["task_action"] is None
    assert spec_response["action"] is None
    assert spec_response["implementation_context"] is None
    assert spec_response["implementation_context_path"] is None


def test_start_brainstorm_from_idea_creates_session_and_seeds_transcript(tmp_path: Path) -> None:
    from devflow.control_room.idea_foundry import capture_idea, show_idea

    setup_temp_git_repo(tmp_path)
    idea = capture_idea(tmp_path, "Seed text for the brainstorm", title="My Idea")
    idea_id = idea["id"]

    result = start_brainstorm_from_idea(tmp_path, idea_id)

    assert result["status"] == "ready"
    assert result["session_id"].startswith("brainstorm-")
    assert result["source_idea_id"] == idea_id
    metadata, _, _, _ = show_idea(tmp_path, idea_id)
    assert metadata["latest_brainstorm_session_id"] == result["session_id"]
    assert metadata["latest_brainstorm_session_path"] == f".devflow/brainstorms/{result['session_id']}"
    assert metadata["brainstorm_session_ids"] == [result["session_id"]]
    transcript_path = tmp_path / ".devflow" / "brainstorms" / result["session_id"] / "transcript.jsonl"
    records = [json.loads(line) for line in transcript_path.read_text(encoding="utf-8").splitlines()]
    assert len(records) == 1
    assert records[0]["role"] == "user"
    assert records[0]["kind"] == "brainstorm_start"
    assert records[0]["content"] == "Seed text for the brainstorm"
    assert records[0]["metadata"]["source_idea_id"] == idea_id


def test_idea_started_brainstorm_lineage_flows_to_spec_plan_and_implementation(tmp_path: Path) -> None:
    from devflow.control_room.idea_foundry import capture_idea

    setup_temp_git_repo(tmp_path)
    idea = capture_idea(tmp_path, "Turn rough ideas into linked execution artifacts.", title="Linked execution")
    idea_id = idea["id"]
    session = start_brainstorm_from_idea(tmp_path, idea_id)["session_id"]

    spec_payload = escalate_brainstorm_session(root=tmp_path, session_id=session, stage="spec")
    plan_payload = escalate_brainstorm_session(root=tmp_path, session_id=session, stage="plan")
    implementation_payload = escalate_brainstorm_session(
        root=tmp_path,
        session_id=session,
        stage="implementation",
        title="Build linked execution artifacts",
        definition_of_done="Spec, plan, and task context retain source idea lineage.",
    )

    spec_lineage = json.loads((tmp_path / ".devflow" / "brainstorms" / session / "spec.lineage.json").read_text())
    plan_lineage = json.loads((tmp_path / ".devflow" / "brainstorms" / session / "plan.lineage.json").read_text())
    implementation_lineage = json.loads(
        (tmp_path / ".devflow" / "brainstorms" / session / "implementation.lineage.json").read_text()
    )

    assert spec_payload["lineage"]["source_idea_id"] == idea_id
    assert spec_payload["lineage"]["brainstorm_session_id"] == session
    assert spec_payload["lineage"]["artifact_stage"] == "spec"
    assert spec_payload["lineage"]["spec_path"] == f".devflow/brainstorms/{session}/spec.md"
    assert spec_lineage == {
        "schema_version": 1,
        "artifact_stage": "spec",
        "artifact_path": f".devflow/brainstorms/{session}/spec.md",
        "brainstorm_path": f".devflow/brainstorms/{session}",
        "brainstorm_session_id": session,
        "source_idea_id": idea_id,
    }

    assert plan_payload["lineage"]["source_idea_id"] == idea_id
    assert plan_payload["lineage"]["spec_path"] == f".devflow/brainstorms/{session}/spec.md"
    assert plan_payload["lineage"]["plan_path"] == f".devflow/brainstorms/{session}/plan.md"
    assert plan_lineage["artifact_stage"] == "plan"
    assert plan_lineage["source_idea_id"] == idea_id

    lineage = implementation_payload["lineage"]
    assert lineage["source_idea_id"] == idea_id
    assert lineage["brainstorm_session_id"] == session
    assert lineage["spec_path"] == f".devflow/brainstorms/{session}/spec.md"
    assert lineage["plan_path"] == f".devflow/brainstorms/{session}/plan.md"
    assert lineage["implementation_path"] == f".devflow/brainstorms/{session}/implementation.md"
    assert implementation_lineage["artifact_stage"] == "implementation"
    assert implementation_lineage["source_idea_id"] == idea_id
    assert implementation_payload["action"]["lineage"] == lineage
    assert implementation_payload["pipeline_detail"]["lineage"] == lineage
    assert implementation_payload["pipeline_detail"]["implementation_context"]["lineage"] == lineage
    assert implementation_payload["pipeline_detail"]["implementation_context"]["source_paths"] == [
        f".devflow/brainstorms/{session}/spec.md",
        f".devflow/brainstorms/{session}/plan.md",
    ]
    assert f"Idea: `{idea_id}`" in (tmp_path / spec_payload["artifact_path"]).read_text(encoding="utf-8")
    assert f"Idea: `{idea_id}`" in (tmp_path / plan_payload["artifact_path"]).read_text(encoding="utf-8")


def test_start_brainstorm_from_idea_reuses_existing_session_for_same_idea(tmp_path: Path) -> None:
    from devflow.control_room.idea_foundry import capture_idea

    setup_temp_git_repo(tmp_path)
    idea = capture_idea(tmp_path, "Some text", title="Reuse Test")
    idea_id = idea["id"]

    first = start_brainstorm_from_idea(tmp_path, idea_id)
    second = start_brainstorm_from_idea(tmp_path, idea_id)

    assert second["status"] == "reuse"
    assert second["session_id"] == first["session_id"]
    assert second["source_idea_id"] == idea_id
    assert isinstance(second["appended_seed_record"], bool)


def test_start_brainstorm_from_idea_nonexistent_idea_fails(tmp_path: Path) -> None:
    setup_temp_git_repo(tmp_path)

    with pytest.raises(BrainstormError, match="Idea not found: I-9999"):
        start_brainstorm_from_idea(tmp_path, "I-9999")


def test_manual_spec_escalation_exposes_draft_status_in_pipeline_stages(tmp_path: Path) -> None:
    """Manual spec/plan escalation still works and exposes pipeline_detail["stages"]
    with draft status from StageArtifact, not just file-existence 'complete'."""
    setup_temp_git_repo(tmp_path)
    run_brainstorm_message(
        root=tmp_path,
        message="Draft test idea.",
        session_id="session-draft",
    )

    spec_payload = escalate_brainstorm_session(root=tmp_path, session_id="session-draft", stage="spec")

    # Existing payload contract preserved.
    assert spec_payload["status"] == "ready"
    assert (tmp_path / spec_payload["artifact_path"]).read_text(encoding="utf-8").startswith("# Brainstorm Spec")

    pipeline = spec_payload["pipeline_detail"]

    # stages now carries quality-gate-aware status, not just 'complete'/'pending'.
    stages_map = {s["id"]: s for s in pipeline["stages"]}
    spec_stage = stages_map["spec"]

    # Manual escalation should show 'draft' (not 'complete', because no quality gate ran).
    assert spec_stage["status"] == "draft", f"Expected 'draft' for manual spec stage, got {spec_stage['status']!r}"

    # The plan stage should still be 'pending' before it's escalated.
    plan_stage = stages_map["plan"]
    assert plan_stage["status"] == "pending"

    # Persisted pipeline.json carries the draft status.
    persisted = json.loads(
        (tmp_path / ".devflow" / "brainstorms" / "session-draft" / "pipeline.json").read_text(encoding="utf-8")
    )
    persisted_stages_map = {s["id"]: s for s in persisted.get("stages", [])}
    assert persisted_stages_map["spec"]["status"] == "draft"


def test_model_error_spec_escalation_writes_fallback_artifact(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    setup_temp_git_repo(tmp_path)
    session_id = "session-model-error"
    session_dir = tmp_path / ".devflow" / "brainstorms" / session_id
    session_dir.mkdir(parents=True)
    session_dir.joinpath("transcript.jsonl").write_text(
        json.dumps(
            {
                "created_at": "2026-06-26T12:00:00Z",
                "role": "user",
                "kind": "message",
                "content": "Make the browser pipeline recover from provider errors.",
            },
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )
    monkeypatch.setenv("OPENROUTER_API_KEY", "sk-test")
    import devflow.control_room.brainstorm as brainstorm_mod

    def fail_chat_completion(**_kwargs: Any) -> dict[str, Any]:
        raise RuntimeError("Provider 'openrouter' request failed: HTTP Error 404: Not Found")

    monkeypatch.setattr(brainstorm_mod, "_chat_completion_for_profile", fail_chat_completion)

    payload = escalate_brainstorm_session(
        root=tmp_path,
        session_id=session_id,
        stage="spec",
        use_model=True,
    )

    assert payload["status"] == "ready"
    assert payload["model_info"]["used_model"] is False
    assert "HTTP Error 404" in payload["model_info"]["error"]
    spec_path = tmp_path / payload["artifact_path"]
    assert spec_path.exists()
    assert "Model error:" in spec_path.read_text(encoding="utf-8")
    assert payload["pipeline_detail"]["has_spec"] is True
    stages_map = {stage["id"]: stage for stage in payload["pipeline_detail"]["stages"]}
    assert stages_map["spec"]["status"] == "draft"


def test_manual_plan_escalation_exposes_draft_status_in_pipeline_stages(tmp_path: Path) -> None:
    """Same draft-status check but for plan stage."""
    setup_temp_git_repo(tmp_path)
    run_brainstorm_message(
        root=tmp_path,
        message="Plan draft idea.",
        session_id="session-plan-draft",
    )

    spec_payload = escalate_brainstorm_session(root=tmp_path, session_id="session-plan-draft", stage="spec")
    plan_payload = escalate_brainstorm_session(root=tmp_path, session_id="session-plan-draft", stage="plan")

    pipeline = plan_payload["pipeline_detail"]
    stages_map = {s["id"]: s for s in pipeline["stages"]}

    # Manual plan escalation should show 'draft'.
    assert stages_map["spec"]["status"] == "draft"
    assert stages_map["plan"]["status"] == "draft", f"Expected 'draft' for manual plan stage, got {stages_map['plan']['status']!r}"
