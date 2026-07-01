from __future__ import annotations

import json
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

import pytest

from devflow.control_room.builder_judge_loop import (
    BuilderJudgeConfig,
    BuilderJudgeConfigError,
    get_builder_judge_run,
    list_builder_judge_loops,
    run_builder_judge_loop,
)
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


def _make_builder_response(text: str = "This is a draft.") -> dict[str, Any]:
    return {
        "choices": [{"message": {"content": text}}],
        "usage": {"prompt_tokens": 10, "completion_tokens": 20},
    }


def _make_judge_response(score: int, issues: list[str], feedback: str = "OK") -> dict[str, Any]:
    content = json.dumps({"score": score, "issues": issues, "feedback": feedback})
    return {
        "choices": [{"message": {"content": content}}],
        "usage": {"prompt_tokens": 15, "completion_tokens": 25},
    }


def _setup_mock_provider(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    builder_responses: list[dict[str, Any]] | None = None,
    judge_responses: list[dict[str, Any]] | None = None,
) -> None:
    """Mock OpenRouter API calls for builder and judge."""
    monkeypatch.setenv("OPENROUTER_API_KEY", "sk-or-test-key")
    import devflow.control_room.env_loader as env_loader_mod
    monkeypatch.setattr(env_loader_mod, "_HERMES_ENV_PATH", tmp_path / "nonexistent.env")

    builder_queue = list(builder_responses or [_make_builder_response()])
    judge_queue = list(judge_responses or [_make_judge_response(90, [], "Good")])

    def mock_urlopen(req: urllib.request.Request, timeout: float | None = None) -> MockResponse:
        req_body = json.loads(req.data.decode("utf-8"))
        model = req_body.get("model", "")
        # Route based on model in the request
        if "qwen/qwen3.7-plus" in model.lower() or "sonnet" in model.lower() or "minimax" in model.lower():
            if builder_queue:
                return MockResponse(builder_queue.pop(0))
            return MockResponse(_make_builder_response())
        else:
            if judge_queue:
                return MockResponse(judge_queue.pop(0))
            return MockResponse(_make_judge_response(90, [], "Good"))

    monkeypatch.setattr(urllib.request, "urlopen", mock_urlopen)


def test_config_validation_empty_dod(tmp_path: Path) -> None:
    setup_temp_git_repo(tmp_path)
    config = BuilderJudgeConfig(definition_of_done="")
    with pytest.raises(BuilderJudgeConfigError, match="definition_of_done must not be empty"):
        run_builder_judge_loop(tmp_path, config)


def test_config_validation_same_builder_judge(tmp_path: Path) -> None:
    setup_temp_git_repo(tmp_path)
    config = BuilderJudgeConfig(
        definition_of_done="Write a cold email.",
        builder_profile_id="hermes-qwen37plus",
        judge_profile_id="hermes-qwen37plus",
    )
    with pytest.raises(BuilderJudgeConfigError, match="Builder and judge must be different"):
        run_builder_judge_loop(tmp_path, config)


def test_hermes_codex_profile_does_not_fall_back_to_openrouter(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    setup_temp_git_repo(tmp_path)
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)

    def fail_urlopen(req: urllib.request.Request, timeout: float | None = None) -> MockResponse:
        raise AssertionError("Hermes subscription profile must not call OpenRouter-compatible HTTP APIs")

    monkeypatch.setattr(urllib.request, "urlopen", fail_urlopen)

    config = BuilderJudgeConfig(
        definition_of_done="Draft a concise operating-layer next step.",
        builder_profile_id="hermes-codex-gpt55",
        judge_profile_id="hermes-opus48",
        pass_threshold=85,
        max_rounds=1,
    )

    run = run_builder_judge_loop(tmp_path, config)

    assert run.status == "failed"
    assert run.rounds == []
    assert run.stop_reason == "hermes_handoff_required"
    assert run.handoff_state is not None
    assert run.handoff_state["builder"]["profile"]["id"] == "hermes-codex-gpt55"
    assert "OPENROUTER_API_KEY" not in json.dumps(run.handoff_state)
    assert run.next_safe_action.startswith("hermes")


def test_dynamic_hermes_profile_returns_builder_judge_handoff_without_agent_not_found(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    setup_temp_git_repo(tmp_path)
    monkeypatch.setenv("HOME", tmp_path.as_posix())
    profile_dir = tmp_path / ".hermes" / "profiles" / "local-draft"
    profile_dir.mkdir(parents=True)
    (profile_dir / "config.yaml").write_text(
        """model:
  default: qwen36-27b-q5-mtp
  provider: qwen36-27b-q5-mtp
  base_url: http://127.0.0.1:8080/v1
""",
        encoding="utf-8",
    )

    def fail_urlopen(req: urllib.request.Request, timeout: float | None = None) -> MockResponse:
        raise AssertionError("Dynamic Hermes handoff profile must not call provider HTTP APIs")

    monkeypatch.setattr(urllib.request, "urlopen", fail_urlopen)

    run = run_builder_judge_loop(
        tmp_path,
        BuilderJudgeConfig(
            definition_of_done="Draft a concise operating-layer next step.",
            builder_profile_id="hermes-profile-local-draft",
            judge_profile_id="hermes-qwen37plus",
            pass_threshold=85,
            max_rounds=1,
        ),
    )

    assert run.status == "failed"
    assert run.stop_reason == "hermes_handoff_required"
    assert run.handoff_state is not None
    assert run.handoff_state["builder"]["profile"]["hermes_profile"] == "local-draft"
    assert "agent not found" not in json.dumps(run.model_dump(mode="json")).lower()


def test_config_validation_threshold_bounds(tmp_path: Path) -> None:
    setup_temp_git_repo(tmp_path)
    config = BuilderJudgeConfig(
        definition_of_done="Test",
        pass_threshold=40,
    )
    with pytest.raises(BuilderJudgeConfigError, match="pass_threshold must be between"):
        run_builder_judge_loop(tmp_path, config)


def test_loop_passes_on_first_round(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    setup_temp_git_repo(tmp_path)
    _setup_mock_provider(
        monkeypatch,
        tmp_path,
        builder_responses=[_make_builder_response("A perfect cold email.")],
        judge_responses=[_make_judge_response(95, [], "Excellent.")],
    )

    config = BuilderJudgeConfig(
        definition_of_done="A 5-line cold email for agency owners with one CTA.",
        builder_profile_id="hermes-qwen37plus",
        judge_profile_id="hermes-opus48",
        pass_threshold=85,
        max_rounds=3,
    )

    run = run_builder_judge_loop(tmp_path, config)

    assert run.status == "passed"
    assert len(run.rounds) == 1
    assert run.rounds[0].score == 95
    assert run.rounds[0].passed is True
    assert run.final_score == 95
    assert run.final_draft == "A perfect cold email."


def test_loop_iterates_then_passes(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    setup_temp_git_repo(tmp_path)
    _setup_mock_provider(
        monkeypatch,
        tmp_path,
        builder_responses=[
            _make_builder_response("Draft v1 - missing CTA."),
            _make_builder_response("Draft v2 - now with CTA."),
        ],
        judge_responses=[
            _make_judge_response(60, ["Missing CTA", "Too long"], "Needs work."),
            _make_judge_response(90, [], "Good now."),
        ],
    )

    config = BuilderJudgeConfig(
        definition_of_done="A 5-line cold email with one CTA.",
        builder_profile_id="hermes-qwen37plus",
        judge_profile_id="hermes-opus48",
        pass_threshold=85,
        max_rounds=5,
    )

    run = run_builder_judge_loop(tmp_path, config)

    assert run.status == "passed"
    assert len(run.rounds) == 2
    assert run.rounds[0].score == 60
    assert run.rounds[0].passed is False
    assert "Missing CTA" in run.rounds[0].issues
    assert run.rounds[1].score == 90
    assert run.rounds[1].passed is True
    assert run.final_score == 90


def test_loop_max_rounds_escalates(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    setup_temp_git_repo(tmp_path)
    _setup_mock_provider(
        monkeypatch,
        tmp_path,
        builder_responses=[
            _make_builder_response("Draft v1."),
            _make_builder_response("Draft v2."),
            _make_builder_response("Draft v3."),
        ],
        judge_responses=[
            _make_judge_response(50, ["Issue 1"], "Fail."),
            _make_judge_response(60, ["Issue 2"], "Better but not enough."),
            _make_judge_response(70, ["Issue 3"], "Still not passing."),
        ],
    )

    config = BuilderJudgeConfig(
        definition_of_done="A perfect cold email.",
        builder_profile_id="hermes-qwen37plus",
        judge_profile_id="hermes-opus48",
        pass_threshold=85,
        max_rounds=3,
        escalate_on_max_rounds=True,
    )

    run = run_builder_judge_loop(tmp_path, config)

    assert run.status == "escalated"
    assert len(run.rounds) == 3
    assert run.final_score == 70
    assert "max_rounds" in run.stop_reason


def test_loop_max_rounds_no_escalate(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    setup_temp_git_repo(tmp_path)
    _setup_mock_provider(
        monkeypatch,
        tmp_path,
        builder_responses=[_make_builder_response("Draft.")],
        judge_responses=[_make_judge_response(60, ["Bad"], "Fail.")],
    )

    config = BuilderJudgeConfig(
        definition_of_done="A cold email.",
        builder_profile_id="hermes-qwen37plus",
        judge_profile_id="hermes-opus48",
        pass_threshold=85,
        max_rounds=1,
        escalate_on_max_rounds=False,
    )

    run = run_builder_judge_loop(tmp_path, config)

    assert run.status == "max_rounds"
    assert len(run.rounds) == 1


def test_evidence_persisted(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    setup_temp_git_repo(tmp_path)
    _setup_mock_provider(
        monkeypatch,
        tmp_path,
        builder_responses=[_make_builder_response("Good draft.")],
        judge_responses=[_make_judge_response(92, [], "Great.")],
    )

    config = BuilderJudgeConfig(
        definition_of_done="A cold email.",
        builder_profile_id="hermes-qwen37plus",
        judge_profile_id="hermes-opus48",
        pass_threshold=85,
        max_rounds=3,
    )

    run = run_builder_judge_loop(tmp_path, config)

    # run.json should exist
    run_path = tmp_path / ".devflow" / "builder-judge-loops" / run.loop_id / "run.json"
    assert run_path.exists()
    saved = json.loads(run_path.read_text(encoding="utf-8"))
    assert saved["status"] == "passed"
    assert saved["loop_id"] == run.loop_id
    assert saved["rounds"]
    assert saved["config"]["definition_of_done"] == "A cold email."
    assert saved["final_score"] == 92
    assert saved["final_draft"] == "Good draft."
    assert saved["stop_reason"] == "passed_round_1"
    assert saved["next_safe_action"] == "Loop passed. Review the final draft."
    assert "loop_family" not in saved
    assert "status_label" not in saved
    assert "phases" not in saved
    assert "artifacts" not in saved

    # Round evidence should exist
    rounds_dir = tmp_path / ".devflow" / "builder-judge-loops" / run.loop_id / "rounds"
    assert rounds_dir.exists()
    round_file = rounds_dir / "round-01.json"
    assert round_file.exists()
    round_data = json.loads(round_file.read_text(encoding="utf-8"))
    assert round_data["score"] == 92

    # Builder and judge raw responses should exist
    assert (rounds_dir / "round-01-builder.raw.json").exists()
    assert (rounds_dir / "round-01-judge.raw.json").exists()


def test_list_and_get_run(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    setup_temp_git_repo(tmp_path)
    _setup_mock_provider(
        monkeypatch,
        tmp_path,
        builder_responses=[_make_builder_response("Draft.")],
        judge_responses=[_make_judge_response(88, [], "Pass.")],
    )

    config = BuilderJudgeConfig(
        definition_of_done="A cold email.",
        builder_profile_id="hermes-qwen37plus",
        judge_profile_id="hermes-opus48",
        pass_threshold=85,
        max_rounds=3,
    )

    run = run_builder_judge_loop(tmp_path, config)

    loops = list_builder_judge_loops(tmp_path)
    assert len(loops) == 1
    assert loops[0]["loop_family"] == "builder_judge"
    assert loops[0]["loop_id"] == run.loop_id
    assert loops[0]["run_id"] == run.run_id
    assert loops[0]["status"] == "passed"
    assert loops[0]["status_label"] == "Passed"
    assert loops[0]["final_score"] == 88
    assert loops[0]["rounds_completed"] == 1
    assert loops[0]["evidence_path"] == run.evidence_path

    full_run = get_builder_judge_run(tmp_path, run.loop_id)
    assert full_run is not None
    assert full_run["loop_family"] == "builder_judge"
    assert full_run["status"] == "passed"
    assert full_run["status_label"] == "Passed"
    assert full_run["evidence_path"] == run.evidence_path
    assert full_run["next_safe_action"] == run.next_safe_action
    assert full_run["config"]["definition_of_done"] == "A cold email."
    assert full_run["final_score"] == 88
    assert full_run["artifacts"][0]["path"] == run.evidence_path
    assert full_run["artifacts"][0]["exists"] is True
    assert len(full_run["rounds"]) == 1


def test_judge_response_parsing_fallback() -> None:
    """Judge response without JSON should still extract a score via regex."""
    from devflow.control_room.builder_judge_loop import _parse_judge_response

    score, issues, feedback = _parse_judge_response(
        "The draft is decent. Score: 72. Missing CTA and too verbose."
    )
    assert score == 72
    assert issues == []
    assert "decent" in feedback


def test_starting_point_used(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    setup_temp_git_repo(tmp_path)
    captured_requests: list[dict[str, Any]] = []

    _setup_mock_provider(
        monkeypatch,
        tmp_path,
        builder_responses=[_make_builder_response("Revised email.")],
        judge_responses=[_make_judge_response(90, [], "Good.")],
    )

    # Capture the builder request to verify starting point is included
    original_urlopen = urllib.request.urlopen

    def capturing_urlopen(req: urllib.request.Request, timeout: float | None = None) -> MockResponse:
        req_body = json.loads(req.data.decode("utf-8"))
        captured_requests.append(req_body)
        return original_urlopen(req, timeout=timeout)

    monkeypatch.setattr(urllib.request, "urlopen", capturing_urlopen)

    config = BuilderJudgeConfig(
        definition_of_done="A cold email.",
        starting_point="Dear Sir, I am writing to...",
        builder_profile_id="hermes-qwen37plus",
        judge_profile_id="hermes-opus48",
        pass_threshold=85,
        max_rounds=3,
    )

    run = run_builder_judge_loop(tmp_path, config)

    assert run.status == "passed"
    # The builder request should contain the starting point
    builder_request = captured_requests[0]
    user_prompt = builder_request["messages"][1]["content"]
    assert "Dear Sir" in user_prompt


def test_loop_failed_on_builder_error(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    setup_temp_git_repo(tmp_path)
    monkeypatch.setenv("OPENROUTER_API_KEY", "***")
    import devflow.control_room.env_loader as env_loader_mod
    monkeypatch.setattr(env_loader_mod, "_HERMES_ENV_PATH", tmp_path / "nonexistent.env")

    def fail_urlopen(req: urllib.request.Request, timeout: float | None = None) -> MockResponse:
        raise urllib.error.URLError("Connection refused")

    monkeypatch.setattr(urllib.request, "urlopen", fail_urlopen)

    config = BuilderJudgeConfig(
        definition_of_done="A cold email.",
        builder_profile_id="hermes-qwen37plus",
        judge_profile_id="hermes-opus48",
        pass_threshold=85,
        max_rounds=3,
    )

    run = run_builder_judge_loop(tmp_path, config)

    assert run.status == "failed"
    assert len(run.rounds) == 1
    assert run.rounds[0].error is not None
    assert "Builder failed" in run.rounds[0].error


def test_escalation_creates_question(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    setup_temp_git_repo(tmp_path)
    _setup_mock_provider(
        monkeypatch,
        tmp_path,
        builder_responses=[_make_builder_response("Draft.")],
        judge_responses=[_make_judge_response(60, ["Bad"], "Fail.")],
    )

    config = BuilderJudgeConfig(
        definition_of_done="A cold email.",
        builder_profile_id="hermes-qwen37plus",
        judge_profile_id="hermes-opus48",
        pass_threshold=85,
        max_rounds=1,
        escalate_on_max_rounds=True,
    )

    run = run_builder_judge_loop(tmp_path, config)

    assert run.status == "escalated"
    # A question record should have been created
    questions_dir = tmp_path / ".devflow" / "questions"
    assert questions_dir.exists()
    question_files = list(questions_dir.glob("Q-bj-*.json"))
    assert len(question_files) == 1
    import json as _json
    question = _json.loads(question_files[0].read_text(encoding="utf-8"))
    assert question["status"] == "open"
    assert question["task_id"] == run.loop_id
    assert "max rounds" in question["question"].lower()
    assert question["recommended_resume_command"] == f"devflow builder-judge show {run.loop_id}"


def test_no_escalation_does_not_create_question(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    setup_temp_git_repo(tmp_path)
    _setup_mock_provider(
        monkeypatch,
        tmp_path,
        builder_responses=[_make_builder_response("Draft.")],
        judge_responses=[_make_judge_response(60, ["Bad"], "Fail.")],
    )

    config = BuilderJudgeConfig(
        definition_of_done="A cold email.",
        builder_profile_id="hermes-qwen37plus",
        judge_profile_id="hermes-opus48",
        pass_threshold=85,
        max_rounds=1,
        escalate_on_max_rounds=False,
    )

    run = run_builder_judge_loop(tmp_path, config)

    assert run.status == "max_rounds"
    questions_dir = tmp_path / ".devflow" / "questions"
    if questions_dir.exists():
        question_files = list(questions_dir.glob("Q-bj-*.json"))
        assert len(question_files) == 0


def test_quality_gate_runs(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    setup_temp_git_repo(tmp_path)
    _setup_mock_provider(
        monkeypatch,
        tmp_path,
        builder_responses=[_make_builder_response("# My Spec\n\nA spec document.")],
        judge_responses=[_make_judge_response(92, [], "Excellent spec.")],
    )

    from devflow.control_room.builder_judge_loop import run_quality_gate

    run = run_quality_gate(
        tmp_path,
        stage="spec",
        transcript_text="### User\n\nI want a cold email tool.\n### Assistant\n\nGreat idea!",
    )

    assert run.status == "passed"
    assert run.final_score == 92
    assert "spec" in run.loop_id


def test_quality_gate_invalid_stage(tmp_path: Path) -> None:
    setup_temp_git_repo(tmp_path)
    from devflow.control_room.builder_judge_loop import run_quality_gate

    with pytest.raises(BuilderJudgeConfigError, match="Unknown quality-gate stage"):
        run_quality_gate(tmp_path, stage="invalid", transcript_text="test")


def test_quality_gate_passed_writes_stage_artifact_with_passed_status(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A passed quality gate produces a StageArtifact with status='passed',
    quality_gate_path, and score."""
    setup_temp_git_repo(tmp_path)
    _setup_mock_provider(
        monkeypatch,
        tmp_path,
        builder_responses=[_make_builder_response("# My Spec\n\nPassed spec.")],
        judge_responses=[_make_judge_response(92, [], "Excellent.")],
    )

    from devflow.control_room.builder_judge_loop import run_quality_gate

    run = run_quality_gate(
        tmp_path,
        session_id="session-qg-001",
        stage="spec",
        transcript_text="### User\n\nI want a cold email tool.",
    )

    assert run.status == "passed"
    assert run.final_score == 92

    # StageArtifact should exist with 'passed' status.
    from devflow.control_room.stage_artifact import load_stage_artifact

    sa = load_stage_artifact(tmp_path, "session-qg-001", "spec")
    assert sa is not None
    assert sa.status == "passed"
    assert sa.source == "builder_judge"
    assert sa.score == 92
    assert sa.quality_gate_path is not None
    assert (tmp_path / sa.artifact_path).exists()

    from devflow.control_room.brainstorm_pipeline import build_brainstorm_pipeline_state

    pipeline = build_brainstorm_pipeline_state(tmp_path, session_id="session-qg-001")
    spec_stage = {stage.id: stage for stage in pipeline.stages}["spec"]
    assert spec_stage.status == "passed"
    assert spec_stage.artifact_path == sa.artifact_path
    assert sa.quality_gate_path in spec_stage.evidence_paths


def test_quality_gate_escalated_writes_stage_artifact_with_escalated_status(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """An escalated quality gate produces a StageArtifact with status='escalated'.
    Escalation should also preserve the existing question-creation assertion."""
    setup_temp_git_repo(tmp_path)
    captured_q = []

    def capture_urlopen(req: urllib.request.Request, timeout: float | None = None) -> MockResponse:
        req_body = json.loads(req.data.decode("utf-8"))
        model = req_body.get("model", "")
        if "qwen/qwen3.7-plus" in model.lower():
            return MockResponse(_make_builder_response("Draft v1."))
        else:
            captured_q.append(True)
            return MockResponse(_make_judge_response(60, ["Bad"], "Fail."))

    monkeypatch.setattr(urllib.request, "urlopen", capture_urlopen)
    monkeypatch.setenv("OPENROUTER_API_KEY", "***")
    import devflow.control_room.env_loader as env_loader_mod
    monkeypatch.setattr(env_loader_mod, "_HERMES_ENV_PATH", tmp_path / "nonexistent.env")

    from devflow.control_room.builder_judge_loop import run_quality_gate

    # Max rounds = 1 so it hits escalation immediately.
    run = run_quality_gate(
        tmp_path,
        session_id="session-qg-002",
        stage="plan",
        max_rounds=1,
        transcript_text="### User\n\nI want a plan.",
    )

    assert run.status == "escalated"
    # A question record should have been created (existing assertion preserved).
    questions_dir = tmp_path / ".devflow" / "questions"
    assert questions_dir.exists()
    question_files = list(questions_dir.glob("Q-bj-*.json"))
    assert len(question_files) == 1

    # StageArtifact should exist with 'escalated' status.
    from devflow.control_room.stage_artifact import load_stage_artifact

    sa = load_stage_artifact(tmp_path, "session-qg-002", "plan")
    assert sa is not None
    assert sa.status == "escalated"
    assert sa.source == "builder_judge"

    from devflow.control_room.brainstorm_pipeline import build_brainstorm_pipeline_state

    pipeline = build_brainstorm_pipeline_state(tmp_path, session_id="session-qg-002")
    plan_stage = {stage.id: stage for stage in pipeline.stages}["plan"]
    assert plan_stage.status == "escalated"
    assert plan_stage.artifact_path == sa.artifact_path
