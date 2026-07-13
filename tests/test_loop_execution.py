"""Tests for the native V2 execution engine (devflow.loop.execution).

Two layers of evidence:

1. Offline full-chain test with a fake model client. Proves the orchestration,
   single-flight serialization, judge-decision parsing, persistence through the
   existing adapters, and stage transitions — deterministically, no fleet.

2. Real build test against the live builder lane (port 8084). Skipped unless the
   builder server is actually healthy, so CI stays green when the fleet is down.
   Run `pytest tests/test_loop_execution.py -v` with the builder up to exercise
   the real llama-server path (lane swap, lock, completion, loop-packet.md).
"""

from __future__ import annotations

import json
import urllib.error
import urllib.request
from pathlib import Path
from types import SimpleNamespace

import pytest

from devflow.loop import execution as ex
from devflow.loop import pipeline_run as pr
from devflow.loop.adapter import load_loop_state, save_loop_state
from devflow.loop.models import LoopStage
from devflow.loop.model_router import _global_local_model_runtime_status


class FakeClient:
    """Deterministic stand-in for LocalModelClient. No network."""

    def __init__(self, endpoint: str, *, timeout: int = 1):
        self.endpoint = endpoint
        self.calls = []

    def chat(self, *, messages, max_tokens=2048, temperature=0.0,
             reasoning=False, stop=None):
        sys = messages[0]["content"].lower()
        self.calls.append(sys)
        if "judge" in sys:
            if "planning judge" in sys:
                return json.dumps({"decision": "approve", "rationale": "ok"}), {}
            return json.dumps({"status": "passed", "rationale": "ok"}), {}
        if "planner" in sys:
            return json.dumps({
                "spec": "add a calculator module",
                "plan": "create calc.py with add()",
                "target_files": ["calc.py"],
                "verification_command": "python -c 'import ast,pathlib;ast.parse(pathlib.Path(\"calc.py\").read_text())'",
            }), {}
        return "def add(a, b):\n    return a + b\n", {}


def test_ensure_lane_fails_closed_when_router_start_fails(monkeypatch, tmp_path) -> None:
    slot = SimpleNamespace(
        transport="openai-http",
        endpoint="http://127.0.0.1:8088/v1",
        model_path="~/models/ornith.gguf",
        model_id="ornith-9b-mini",
        model_name="ornith-9b-mini",
    )
    monkeypatch.setattr(ex, "resolve_role_slot", lambda role: slot)

    def failed_start(command, *, check, env):
        assert check is True
        raise ex.subprocess.CalledProcessError(1, command)

    monkeypatch.setattr(ex.subprocess, "run", failed_start)

    with pytest.raises(ex.subprocess.CalledProcessError):
        ex.ensure_lane("final_judge", script=tmp_path / "model-router")


class RevisingPlannerClient:
    """Planner returns one revise-worthy plan, then a grounded plan."""

    planner_calls = 0

    def __init__(self, endpoint: str, *, timeout: int = 1):
        self.endpoint = endpoint

    def chat(self, *, messages, max_tokens=2048, temperature=0.0,
             reasoning=False, stop=None):
        sys = messages[0]["content"].lower()
        user = messages[1]["content"]
        if "judge" in sys:
            if "missing.py" in user:
                return json.dumps({
                    "decision": "revise",
                    "required_changes": ["Use grounded target files or clearly mark new files."],
                    "next_safe_action": "Revise the plan target files.",
                }), {}
            return json.dumps({"decision": "approve", "rationale": "ok"}), {}
        if "planner" in sys:
            type(self).planner_calls += 1
            target = "missing.py" if type(self).planner_calls == 1 else "calc.py"
            return json.dumps({
                "spec": "add a calculator module",
                "plan": f"create {target} with add()",
                "target_files": [target],
                "verification_command": "python -m pytest tests/test_loop_models.py -q",
            }), {}
        return "def add(a, b):\n    return a + b\n", {}


class RevisingBuilderClient:
    """Builder/judge fails once, then passes after feedback is supplied."""

    judge_calls = 0

    def __init__(self, endpoint: str, *, timeout: int = 1):
        self.endpoint = endpoint

    def chat(self, *, messages, max_tokens=2048, temperature=0.0,
             reasoning=False, stop=None):
        sys = messages[0]["content"].lower()
        if "judge" in sys:
            type(self).judge_calls += 1
            if type(self).judge_calls == 1:
                return json.dumps({"status": "failed", "rationale": "missing edge case"}), {}
            return json.dumps({"status": "passed", "rationale": "DoD satisfied"}), {}
        return "def add(a, b):\n    return a + b\n", {}


class CapturingPlannerContextClient:
    """Captures planner and judge prompts so tests can assert context routing."""

    planner_user_prompt = ""
    judge_user_prompt = ""

    def __init__(self, endpoint: str, *, timeout: int = 1):
        self.endpoint = endpoint

    def chat(self, *, messages, max_tokens=2048, temperature=0.0,
             reasoning=False, stop=None):
        sys = messages[0]["content"].lower()
        user = messages[1]["content"]
        if "planning judge" in sys:
            type(self).judge_user_prompt = user
            return json.dumps({"decision": "approve", "rationale": "ok"}), {}
        type(self).planner_user_prompt = user
        return json.dumps({
            "spec": "create a cron-backed semantic scorer",
            "plan": "write cron scorer and Obsidian queue integration",
            "target_files": ["brief_sorter.py"],
            "verification_command": "python -m pytest tests/test_sorter.py -q",
        }), {}


class StreamingBuilderClient:
    """Exercises the role-generic streaming contract without a live model."""

    streamed = False

    def __init__(self, endpoint: str, *, timeout: int = 1):
        self.endpoint = endpoint

    def chat_stream(self, *, messages, max_tokens=2048, temperature=0.0,
                    reasoning=False, stop=None, on_delta=None, on_reasoning_delta=None):
        type(self).streamed = True
        if on_delta:
            on_delta("def add(a, b):\n")
            on_delta("    return a + b\n")
        if on_reasoning_delta:
            on_reasoning_delta("I need to write a function that adds two numbers.\n")
        return (
            "def add(a, b):\n    return a + b\n",
            {"completion_tokens": max_tokens},
            "length",
            "I need to write a function that adds two numbers.\n",
        )


class FailingStreamingClient:
    def __init__(self, endpoint: str, *, timeout: int = 1):
        self.endpoint = endpoint

    def chat_stream(self, *, on_delta=None, on_reasoning_delta=None, **kwargs):
        if on_delta:
            on_delta("partial implementation")
        raise RuntimeError("model disconnected")


class ReasoningCaptureClient:
    reasoning_values = []
    user_prompts = []

    def __init__(self, endpoint: str, *, timeout: int = 1):
        self.endpoint = endpoint

    def chat(self, *, messages, max_tokens=2048, temperature=0.0,
             reasoning=False, stop=None):
        type(self).reasoning_values.append(reasoning)
        type(self).user_prompts.append(messages[-1]["content"])
        return json.dumps({"status": "passed", "rationale": "ok"}), {}


class VerifierLifecycleCaptureClient:
    root: Path
    run_id: str
    observed_control = {}

    def __init__(self, endpoint: str, *, timeout: int = 1):
        self.endpoint = endpoint

    def chat(self, *, messages, max_tokens=2048, temperature=0.0,
             reasoning=False, stop=None):
        type(self).observed_control = pr.read_execution_control(
            type(self).root,
            type(self).run_id,
        )
        return json.dumps({"status": "passed", "rationale": "ok"}), {}


def _fresh_root(tmp_path: Path) -> tuple[str, str]:
    root = tmp_path / "proj"
    root.mkdir()
    run_id = pr.create_pipeline_run(str(root), {"title": "t", "description": "d"})
    # Seed at assignment (prior stages done) — mirrors existing loop tests.
    from devflow.loop.adapter import save_loop_state
    from devflow.loop.models import LoopStage

    st = load_loop_state(root, run_id)
    st = st.model_copy(update={"stage": LoopStage.assignment})
    save_loop_state(root, st)
    return str(root), run_id


def test_run_role_derives_reasoning_from_canonical_role(tmp_path):
    ReasoningCaptureClient.reasoning_values = []
    root = tmp_path / "proj"
    root.mkdir()
    run_id = pr.create_pipeline_run(root, {"title": "t", "description": "d"})

    ex.run_role(
        root,
        role="planning_judge",
        system_prompt="judge",
        user_prompt="review",
        task_id=run_id,
        ensure_lane_on=False,
        client_factory=ReasoningCaptureClient,
    )
    ex.run_role(
        root,
        role="builder",
        system_prompt="build",
        user_prompt="implement",
        task_id=run_id,
        ensure_lane_on=False,
        client_factory=ReasoningCaptureClient,
    )

    assert ReasoningCaptureClient.reasoning_values == [True, False]


def test_run_role_persists_audition_route_provenance(tmp_path, monkeypatch):
    ReasoningCaptureClient.reasoning_values = []
    root = tmp_path / "proj"
    root.mkdir()
    run_id = pr.create_pipeline_run(root, {"title": "t", "description": "d"})
    monkeypatch.setenv(
        "DEVFLOW_AUDITION_OVERRIDES",
        '{"verifier": "qwen2.5-coder-7b-mini"}',
    )
    monkeypatch.setenv("DEVFLOW_AUDITION_DISABLE_THINKING", "1")

    ex.run_role(
        root,
        role="verifier",
        system_prompt="verify",
        user_prompt="inspect evidence",
        task_id=run_id,
        ensure_lane_on=False,
        client_factory=ReasoningCaptureClient,
    )

    feed = pr.load_pipeline_run(root, run_id)["worker-feed.jsonl"]
    assert [entry["event"] for entry in feed] == ["started", "completed"]
    assert {entry["configured_route"] for entry in feed} == {
        "qwen2.5-coder-7b-mini"
    }
    assert {entry["route_provenance"] for entry in feed} == {
        "audition_override"
    }
    assert {entry["reasoning_enabled"] for entry in feed} == {False}
    assert ReasoningCaptureClient.reasoning_values == [False]


def test_audition_thinking_flag_does_not_change_normal_routes(tmp_path, monkeypatch):
    ReasoningCaptureClient.reasoning_values = []
    root = tmp_path / "proj"
    root.mkdir()
    run_id = pr.create_pipeline_run(root, {"title": "t", "description": "d"})
    monkeypatch.setenv("DEVFLOW_AUDITION_DISABLE_THINKING", "true")

    ex.run_role(
        root,
        role="planning_judge",
        system_prompt="judge",
        user_prompt="inspect plan",
        task_id=run_id,
        ensure_lane_on=False,
        client_factory=ReasoningCaptureClient,
    )

    feed = pr.load_pipeline_run(root, run_id)["worker-feed.jsonl"]
    assert ReasoningCaptureClient.reasoning_values == [True]
    assert {entry["reasoning_enabled"] for entry in feed} == {True}


def test_audition_thinking_suppression_is_canonical_role_scoped(
    tmp_path, monkeypatch,
):
    ReasoningCaptureClient.reasoning_values = []
    root = tmp_path / "proj"
    root.mkdir()
    run_id = pr.create_pipeline_run(root, {"title": "t", "description": "d"})
    monkeypatch.setenv(
        "DEVFLOW_AUDITION_OVERRIDES",
        json.dumps({
            "planning_judge": "ornith-9b-mini",
            "build_judge": "ornith-9b-mini",
        }),
    )
    monkeypatch.setenv(
        "DEVFLOW_AUDITION_DISABLE_THINKING_ROLES", "build_judge"
    )

    ex.run_role(
        root,
        role="planning_judge",
        system_prompt="judge plan",
        user_prompt="inspect plan",
        task_id=run_id,
        ensure_lane_on=False,
        client_factory=ReasoningCaptureClient,
    )
    ex.run_role(
        root,
        role="judge",
        system_prompt="judge build",
        user_prompt="inspect diff",
        task_id=run_id,
        ensure_lane_on=False,
        client_factory=ReasoningCaptureClient,
    )

    feed = pr.load_pipeline_run(root, run_id)["worker-feed.jsonl"]
    started = [entry for entry in feed if entry["event"] == "started"]
    assert ReasoningCaptureClient.reasoning_values == [True, False]
    assert [(entry["role"], entry["reasoning_enabled"]) for entry in started] == [
        ("planning_judge", True),
        ("judge", False),
    ]
    assert {entry["route_provenance"] for entry in feed} == {
        "audition_override"
    }


def test_audition_role_token_budget_canonicalizes_generic_judge(
    tmp_path, monkeypatch,
):
    ReasoningCaptureClient.reasoning_values = []
    root = tmp_path / "proj"
    root.mkdir()
    run_id = pr.create_pipeline_run(root, {"title": "t", "description": "d"})
    monkeypatch.setenv(
        "DEVFLOW_AUDITION_OVERRIDES",
        '{"build_judge": "ornith-9b-mini"}',
    )
    monkeypatch.setenv(
        "DEVFLOW_AUDITION_ROLE_TOKEN_BUDGETS",
        '{"build_judge": 6000}',
    )

    ex.run_role(
        root,
        role="judge",
        system_prompt="judge build",
        user_prompt="inspect diff",
        task_id=run_id,
        ensure_lane_on=False,
        client_factory=ReasoningCaptureClient,
    )
    ex.run_role(
        root,
        role="judge",
        system_prompt="judge build",
        user_prompt="inspect diff",
        task_id=run_id,
        max_tokens=1024,
        ensure_lane_on=False,
        client_factory=ReasoningCaptureClient,
    )

    feed = pr.load_pipeline_run(root, run_id)["worker-feed.jsonl"]
    started = [entry for entry in feed if entry["event"] == "started"]
    assert [entry["requested_max_tokens"] for entry in started] == [6000, 1024]
    assert [entry["reasoning_enabled"] for entry in started] == [True, True]
    assert ReasoningCaptureClient.reasoning_values == [True, True]


def test_audition_role_token_budget_does_not_affect_normal_route(
    tmp_path, monkeypatch,
):
    root = tmp_path / "proj"
    root.mkdir()
    run_id = pr.create_pipeline_run(root, {"title": "t", "description": "d"})
    monkeypatch.setenv(
        "DEVFLOW_AUDITION_ROLE_TOKEN_BUDGETS",
        '{"builder": 4096}',
    )

    ex.run_role(
        root,
        role="builder",
        system_prompt="build",
        user_prompt="implement",
        task_id=run_id,
        ensure_lane_on=False,
        client_factory=ReasoningCaptureClient,
    )

    feed = pr.load_pipeline_run(root, run_id)["worker-feed.jsonl"]
    assert feed[0]["route_provenance"] != "audition_override"
    assert feed[0]["requested_max_tokens"] == 16384


@pytest.mark.parametrize(
    ("budgets", "message"),
    [
        ("not-json", "must be a JSON object"),
        ('{"judge": 4096}', "unknown canonical role"),
        ('{"build_judge": 0}', "positive integers"),
        ('{"build_judge": 6001}', "no greater than 6000"),
    ],
)
def test_audition_role_token_budget_rejects_invalid_env(
    tmp_path, monkeypatch, budgets, message,
):
    root = tmp_path / "proj"
    root.mkdir()
    run_id = pr.create_pipeline_run(root, {"title": "t", "description": "d"})
    monkeypatch.setenv(
        "DEVFLOW_AUDITION_OVERRIDES",
        '{"build_judge": "ornith-9b-mini"}',
    )
    monkeypatch.setenv("DEVFLOW_AUDITION_ROLE_TOKEN_BUDGETS", budgets)

    with pytest.raises(ValueError, match=message):
        ex.run_role(
            root,
            role="judge",
            system_prompt="judge build",
            user_prompt="inspect diff",
            task_id=run_id,
            ensure_lane_on=False,
            client_factory=ReasoningCaptureClient,
        )


def test_verifier_requests_reasoning_and_emits_model_agnostic_evidence(tmp_path, monkeypatch):
    ReasoningCaptureClient.reasoning_values = []
    ReasoningCaptureClient.user_prompts = []
    root = tmp_path / "proj"
    root.mkdir()
    run_id = pr.create_pipeline_run(root, {"title": "t", "description": "d"})
    state = load_loop_state(root, run_id).model_copy(update={"stage": LoopStage.verification})
    save_loop_state(root, state)
    pr.update_pipeline_run_record(root, run_id, "build-diff.patch", "diff")
    pr.update_pipeline_run_record(
        root,
        run_id,
        "build-manifest.json",
        json.dumps({
            "changed_files": [],
            "declared_target_files": [],
            "workspace": str(root),
        }),
    )
    pr.update_pipeline_run_record(
        root, run_id, "judge-decision.json", json.dumps({"status": "passed"})
    )
    monkeypatch.setattr(
        ex,
        "_run_workspace_tests",
        lambda *args, **kwargs: {
            "exit_code": 0,
            "passed": 1,
            "failed": 0,
            "errors": 0,
            "summary": "1 passed",
            "working_directory": str(root),
        },
    )

    receipt = ex.run_verifier(
        root,
        run_id,
        definition_of_done="Tests pass.",
        client_factory=ReasoningCaptureClient,
    )

    assert ReasoningCaptureClient.reasoning_values == [True]
    assert receipt.receipt_id.startswith("vr-verifier-")
    assert receipt.command.startswith("verifier (")
    assert "GLM" not in receipt.command
    assert receipt.summary.startswith("Verifier decision:")


def test_verifier_uses_role_lifecycle_while_model_is_running(tmp_path, monkeypatch):
    root = tmp_path / "proj"
    root.mkdir()
    run_id = pr.create_pipeline_run(root, {"title": "t", "description": "d"})
    state = load_loop_state(root, run_id).model_copy(update={"stage": LoopStage.verification})
    save_loop_state(root, state)
    pr.update_pipeline_run_record(root, run_id, "build-diff.patch", "diff")
    pr.update_pipeline_run_record(
        root,
        run_id,
        "build-manifest.json",
        json.dumps({
            "changed_files": [],
            "declared_target_files": [],
            "workspace": str(root),
        }),
    )
    pr.update_pipeline_run_record(
        root, run_id, "judge-decision.json", json.dumps({"status": "passed"})
    )
    monkeypatch.setattr(
        ex,
        "_run_workspace_tests",
        lambda *args, **kwargs: {
            "exit_code": 0,
            "passed": 1,
            "failed": 0,
            "errors": 0,
            "summary": "1 passed",
            "working_directory": str(root),
        },
    )
    VerifierLifecycleCaptureClient.root = root
    VerifierLifecycleCaptureClient.run_id = run_id
    VerifierLifecycleCaptureClient.observed_control = {}

    ex.run_verifier(
        root,
        run_id,
        definition_of_done="Tests pass.",
        client_factory=VerifierLifecycleCaptureClient,
    )

    assert VerifierLifecycleCaptureClient.observed_control["status"] == "running"
    assert VerifierLifecycleCaptureClient.observed_control["active_role"] == "verifier"


def test_verifier_token_capped_pass_becomes_needs_review(tmp_path, monkeypatch):
    root = tmp_path / "proj"
    root.mkdir()
    run_id = pr.create_pipeline_run(root, {"title": "t", "description": "d"})
    state = load_loop_state(root, run_id).model_copy(
        update={"stage": LoopStage.verification, "builder_judge_passed": True}
    )
    save_loop_state(root, state)
    pr.update_pipeline_run_record(root, run_id, "build-diff.patch", "diff")
    pr.update_pipeline_run_record(
        root,
        run_id,
        "build-manifest.json",
        {
            "changed_files": [],
            "declared_target_files": [],
            "workspace": str(root),
        },
    )
    pr.update_pipeline_run_record(
        root, run_id, "judge-decision.json", {"status": "passed"}
    )
    monkeypatch.setattr(
        ex,
        "_run_workspace_tests",
        lambda *args, **kwargs: {
            "exit_code": 0,
            "passed": 1,
            "failed": 0,
            "errors": 0,
            "summary": "1 passed",
            "working_directory": str(root),
        },
    )
    monkeypatch.setattr(
        ex,
        "run_role",
        lambda *args, **kwargs: ex.RoleResult(
            role="verifier",
            model="free-review-fleet",
            endpoint="https://example.invalid/v1",
            content=json.dumps({"status": "passed", "rationale": "looks good"}),
            usage={},
            raw={"finish_reason": "length", "token_cap_reached": True},
        ),
    )

    receipt = ex.run_verifier(root, run_id, definition_of_done="Tests pass.")

    assert receipt.status == ex.ver.VerificationStatus.needs_review
    assert load_loop_state(root, run_id).stage == LoopStage.verification


def test_verifier_failed_test_gate_bypasses_model_pass(tmp_path, monkeypatch):
    root = tmp_path / "proj"
    root.mkdir()
    run_id = pr.create_pipeline_run(root, {"title": "t", "description": "d"})
    state = load_loop_state(root, run_id).model_copy(
        update={"stage": LoopStage.verification, "builder_judge_passed": True}
    )
    save_loop_state(root, state)
    pr.update_pipeline_run_record(root, run_id, "build-diff.patch", "diff")
    pr.update_pipeline_run_record(
        root,
        run_id,
        "build-manifest.json",
        {
            "changed_files": [],
            "declared_target_files": [],
            "workspace": str(root),
        },
    )
    pr.update_pipeline_run_record(
        root, run_id, "judge-decision.json", {"status": "passed"}
    )
    monkeypatch.setattr(
        ex,
        "_run_workspace_tests",
        lambda *args, **kwargs: {
            "exit_code": 1,
            "passed": 7,
            "failed": 1,
            "errors": 0,
            "summary": "1 failed, 7 passed",
            "working_directory": str(root),
        },
    )
    invoked = False

    def model_must_not_run(*args, **kwargs):
        nonlocal invoked
        invoked = True
        raise AssertionError("verifier model should not run after deterministic failure")

    monkeypatch.setattr(ex, "run_role", model_must_not_run)

    receipt = ex.run_verifier(root, run_id, definition_of_done="Tests pass.")

    assert invoked is False
    assert receipt.status == ex.ver.VerificationStatus.failed
    assert receipt.exit_code == 1
    assert "Deterministic verifier gates failed" in receipt.summary
    assert load_loop_state(root, run_id).stage == LoopStage.verification


_MISSING_VERIFIER_RECORD = object()
_DEFAULT_VERIFIER_MANIFEST = object()


def _run_host_bypass_case(
    tmp_path,
    monkeypatch,
    *,
    judge_record=_MISSING_VERIFIER_RECORD,
    manifest_record=_DEFAULT_VERIFIER_MANIFEST,
    changed_files=None,
    declared_target_files=None,
    test_result=None,
):
    root = tmp_path / "proj"
    root.mkdir()
    run_id = pr.create_pipeline_run(root, {"title": "t", "description": "d"})
    state = load_loop_state(root, run_id).model_copy(
        update={"stage": LoopStage.verification, "builder_judge_passed": True}
    )
    save_loop_state(root, state)
    pr.update_pipeline_run_record(root, run_id, "build-diff.patch", "diff")
    if manifest_record is _DEFAULT_VERIFIER_MANIFEST:
        manifest_record = {
            "changed_files": ["src/sample.py"] if changed_files is None else changed_files,
            "declared_target_files": (
                ["src/sample.py"]
                if declared_target_files is None
                else declared_target_files
            ),
            "workspace": str(root),
        }
    if manifest_record is not _MISSING_VERIFIER_RECORD:
        pr.update_pipeline_run_record(
            root, run_id, "build-manifest.json", manifest_record
        )
    if judge_record is not _MISSING_VERIFIER_RECORD:
        pr.update_pipeline_run_record(
            root, run_id, "judge-decision.json", judge_record
        )
    result = (
        test_result
        if test_result is not None
        else {
            "exit_code": 0,
            "passed": 1,
            "failed": 0,
            "errors": 0,
            "summary": "1 passed",
            "working_directory": str(root),
        }
    )
    monkeypatch.setattr(ex, "_run_workspace_tests", lambda *args, **kwargs: result)

    def model_path_must_not_run(*args, **kwargs):
        raise AssertionError("verifier model path must not run after host-gate bypass")

    monkeypatch.setattr(ex, "resolve_role_slot", model_path_must_not_run)
    monkeypatch.setattr(ex, "run_role", model_path_must_not_run)

    receipt = ex.run_verifier(root, run_id, definition_of_done="Tests pass.")
    data = pr.load_pipeline_run(root, run_id)
    receipt_name = f"verification-receipt-{receipt.receipt_id}.json"
    attestation_name = f"verification-attestation-{receipt.receipt_id}.json"
    assert data[receipt_name]["command"] == "verifier (deterministic host gates)"
    assert attestation_name in data
    assert not any(
        entry.get("role") == "verifier"
        for entry in data.get("worker-feed.jsonl", [])
    )
    assert load_loop_state(root, run_id).stage == LoopStage.verification
    return receipt


@pytest.mark.parametrize(
    ("judge_record", "expected_status", "review_finding"),
    [
        ({"status": "failed"}, ex.ver.VerificationStatus.failed, "failed"),
        ({"status": "blocked"}, ex.ver.VerificationStatus.failed, "failed"),
        (
            {"status": "needs_review"},
            ex.ver.VerificationStatus.needs_review,
            "needs_review",
        ),
        (
            _MISSING_VERIFIER_RECORD,
            ex.ver.VerificationStatus.needs_review,
            "needs_review",
        ),
        ("{", ex.ver.VerificationStatus.needs_review, "needs_review"),
        ({"status": "surprising"}, ex.ver.VerificationStatus.needs_review, "needs_review"),
        ([], ex.ver.VerificationStatus.needs_review, "needs_review"),
    ],
)
def test_verifier_prior_review_host_gate_bypasses_model(
    tmp_path,
    monkeypatch,
    judge_record,
    expected_status,
    review_finding,
):
    receipt = _run_host_bypass_case(
        tmp_path,
        monkeypatch,
        judge_record=judge_record,
    )

    assert receipt.status == expected_status
    assert receipt.exit_code == 1
    assert receipt.command == "verifier (deterministic host gates)"
    assert f"prior_review={review_finding}" in receipt.summary
    assert "scope=passed" in receipt.summary
    assert "tests=passed" in receipt.summary


@pytest.mark.parametrize(
    "manifest_record",
    [_MISSING_VERIFIER_RECORD, "{", []],
)
def test_verifier_missing_or_malformed_manifest_holds_before_model(
    tmp_path,
    monkeypatch,
    manifest_record,
):
    receipt = _run_host_bypass_case(
        tmp_path,
        monkeypatch,
        judge_record={"status": "passed"},
        manifest_record=manifest_record,
    )

    assert receipt.status == ex.ver.VerificationStatus.needs_review
    assert "prior_review=passed; scope=needs_review; tests=passed" in receipt.summary


@pytest.mark.parametrize(
    ("changed_files", "declared_target_files"),
    [
        (["src/sample.py", "tests/test_sample.py"], ["src/sample.py"]),
        (["src/sample.py"], ["src/sample.py", "tests/test_sample.py"]),
    ],
)
def test_verifier_exact_scope_mismatch_fails_before_model(
    tmp_path,
    monkeypatch,
    changed_files,
    declared_target_files,
):
    receipt = _run_host_bypass_case(
        tmp_path,
        monkeypatch,
        judge_record={"status": "passed"},
        changed_files=changed_files,
        declared_target_files=declared_target_files,
    )

    assert receipt.status == ex.ver.VerificationStatus.failed
    assert "prior_review=passed; scope=failed; tests=passed" in receipt.summary


@pytest.mark.parametrize(
    ("changed_files", "declared_target_files"),
    [
        (["src/sample.py", "src/sample.py"], ["src/sample.py"]),
        ([""], ["src/sample.py"]),
        (["/tmp/sample.py"], ["src/sample.py"]),
        (["src/../sample.py"], ["src/sample.py"]),
        ("src/sample.py", ["src/sample.py"]),
        ([1], ["src/sample.py"]),
        (["src/sample.py"], None),
    ],
)
def test_verifier_malformed_scope_holds_before_model(
    tmp_path,
    monkeypatch,
    changed_files,
    declared_target_files,
):
    root = tmp_path / "proj"
    root.mkdir()
    run_id = pr.create_pipeline_run(root, {"title": "t", "description": "d"})
    state = load_loop_state(root, run_id).model_copy(
        update={"stage": LoopStage.verification, "builder_judge_passed": True}
    )
    save_loop_state(root, state)
    pr.update_pipeline_run_record(root, run_id, "build-diff.patch", "diff")
    pr.update_pipeline_run_record(
        root,
        run_id,
        "build-manifest.json",
        {
            "changed_files": changed_files,
            "declared_target_files": declared_target_files,
            "workspace": str(root),
        },
    )
    pr.update_pipeline_run_record(
        root, run_id, "judge-decision.json", {"status": "passed"}
    )
    monkeypatch.setattr(
        ex,
        "_run_workspace_tests",
        lambda *args, **kwargs: {
            "exit_code": 0,
            "passed": 1,
            "failed": 0,
            "errors": 0,
            "summary": "1 passed",
        },
    )

    def model_path_must_not_run(*args, **kwargs):
        raise AssertionError("malformed scope must bypass verifier model")

    monkeypatch.setattr(ex, "resolve_role_slot", model_path_must_not_run)
    monkeypatch.setattr(ex, "run_role", model_path_must_not_run)

    receipt = ex.run_verifier(root, run_id, definition_of_done="Tests pass.")

    assert receipt.status == ex.ver.VerificationStatus.needs_review
    assert "prior_review=passed; scope=needs_review; tests=passed" in receipt.summary
    assert receipt.command == "verifier (deterministic host gates)"
    assert load_loop_state(root, run_id).stage == LoopStage.verification


def test_verifier_failure_precedence_keeps_simultaneous_host_findings(
    tmp_path,
    monkeypatch,
):
    receipt = _run_host_bypass_case(
        tmp_path,
        monkeypatch,
        judge_record={"status": "failed"},
        changed_files=["src/sample.py", "tests/test_sample.py"],
        declared_target_files=["src/sample.py"],
        test_result={
            "exit_code": 1,
            "passed": 0,
            "failed": 1,
            "errors": 0,
            "summary": "1 failed",
        },
    )

    assert receipt.status == ex.ver.VerificationStatus.failed
    assert "prior_review=failed; scope=failed; tests=failed" in receipt.summary


def test_verifier_failed_review_wins_over_malformed_scope(
    tmp_path,
    monkeypatch,
):
    receipt = _run_host_bypass_case(
        tmp_path,
        monkeypatch,
        judge_record={"status": "failed"},
        changed_files="src/sample.py",
        declared_target_files=["src/sample.py"],
    )

    assert receipt.status == ex.ver.VerificationStatus.failed
    assert "prior_review=failed; scope=needs_review; tests=passed" in receipt.summary


@pytest.mark.parametrize(
    "test_result",
    [
        {"exit_code": True, "passed": 1, "failed": 0, "errors": 0},
        {"exit_code": 0, "passed": 1, "failed": False, "errors": 0},
        {"exit_code": 0, "passed": 1, "failed": -1, "errors": 0},
        {"exit_code": 0, "passed": 1, "errors": 0},
    ],
)
def test_verifier_malformed_test_result_fails_before_model(
    tmp_path,
    monkeypatch,
    test_result,
):
    receipt = _run_host_bypass_case(
        tmp_path,
        monkeypatch,
        judge_record={"status": "passed"},
        test_result=test_result,
    )

    assert receipt.status == ex.ver.VerificationStatus.failed
    assert "prior_review=passed; scope=passed; tests=failed" in receipt.summary


def test_verifier_prompt_includes_scope_and_prior_judge_evidence(tmp_path, monkeypatch):
    ReasoningCaptureClient.user_prompts = []
    root = tmp_path / "proj"
    root.mkdir()
    run_id = pr.create_pipeline_run(root, {"title": "t", "description": "d"})
    state = load_loop_state(root, run_id).model_copy(update={"stage": LoopStage.verification})
    save_loop_state(root, state)
    pr.update_pipeline_run_record(root, run_id, "build-diff.patch", "diff")
    pr.update_pipeline_run_record(
        root,
        run_id,
        "build-manifest.json",
        json.dumps({
            "changed_files": ["src/feature.py", "tests/test_feature.py"],
            "declared_target_files": ["src/feature.py", "tests/test_feature.py"],
            "workspace": str(root),
        }),
    )
    pr.update_pipeline_run_record(
        root,
        run_id,
        "judge-decision.json",
        json.dumps({"decision": "passed"}),
    )
    monkeypatch.setattr(
        ex,
        "_run_workspace_tests",
        lambda *args, **kwargs: {
            "exit_code": 0,
            "passed": 1,
            "failed": 0,
            "errors": 0,
            "summary": "1 passed",
            "working_directory": str(root),
        },
    )

    ex.run_verifier(
        root,
        run_id,
        definition_of_done="Tests pass and only declared targets change.",
        client_factory=ReasoningCaptureClient,
    )

    prompt = ReasoningCaptureClient.user_prompts[-1]
    assert "# Prior Judge Decision\npassed" in prompt
    assert "changed_files: ['src/feature.py', 'tests/test_feature.py']" in prompt
    assert "declared_target_files: ['src/feature.py', 'tests/test_feature.py']" in prompt
    assert "scope_match: true" in prompt


def test_role_prompts_are_model_agnostic_and_job_shaped():
    prompts = {
        "builder": ex.BUILDER_SYSTEM,
        "planner": ex.PLANNER_SYSTEM,
        "build_judge": ex.JUDGE_SYSTEM,
        "planning_judge": ex.PLANNING_JUDGE_SYSTEM,
        "verifier": ex.VERIFIER_SYSTEM,
    }

    for prompt in prompts.values():
        lowered = prompt.lower()
        for model_name in ("glm", "qwen", "gpt", "hy3", "laguna"):
            assert model_name not in lowered

    assert "start from the diff" in prompts["build_judge"].lower()
    assert "specific review questions" in prompts["build_judge"].lower()
    assert "narrowest" in prompts["build_judge"].lower()
    assert "supplied" in prompts["planner"].lower()
    assert "deterministic" in prompts["verifier"].lower()
    assert "contradict" in prompts["verifier"].lower()


def test_planning_judge_report_records_result_model_and_generic_fallbacks(
    tmp_path,
    monkeypatch,
):
    root = tmp_path / "proj"
    root.mkdir()
    run_id = pr.create_pipeline_run(root, {"title": "t", "description": "d"})
    state = load_loop_state(root, run_id).model_copy(
        update={"stage": LoopStage.planning_judge}
    )
    save_loop_state(root, state)
    pr.update_pipeline_run_record(root, run_id, "spec.md", "bounded spec")
    pr.update_pipeline_run_record(root, run_id, "plan.md", "bounded plan")
    result = ex.RoleResult(
        role="planning_judge",
        model="free-review-fleet",
        endpoint="https://example.invalid/v1",
        content=json.dumps({"decision": "approve"}),
        usage={},
        raw={},
    )
    monkeypatch.setattr(ex, "run_role", lambda *args, **kwargs: result)
    evidence = ex.pj.PlanningEvidence(
        run_id=run_id,
        plan_path="plan.md",
        spec_path="spec.md",
        target_files=["src/example.py"],
        verification_command="python -m pytest tests/test_example.py -q",
        files_exist=True,
        has_verification=True,
    )

    returned_result, report = ex.run_planning_judge_model(
        root,
        run_id,
        evidence=evidence,
        planner_content="{}",
        ensure_lane_on=False,
    )

    feed = pr.load_pipeline_run(root, run_id)["worker-feed.jsonl"]
    report_entry = next(
        entry for entry in feed if entry.get("role") == "planning_judge_report"
    )
    assert returned_result is result
    assert report_entry["model"] == result.model
    assert "Qwen" not in report.model_dump_json()


@pytest.mark.parametrize(
    "content",
    [
        '```json\n{"decision":"approve"}\n```',
        '  ```  \n  {"status":"passed"}  \n```  ',
        '``` JSON \r\n{"decision":"revise"}\r\n```',
    ],
)
def test_structured_judge_accepts_one_whole_response_json_fence(content):
    payload, valid = ex._structured_judge_payload(content)

    assert valid is True
    assert isinstance(payload, dict)


@pytest.mark.parametrize(
    "content",
    [
        'Here is the result:\n```json\n{"decision":"approve"}\n```',
        '```json\n{"decision":"approve"}\n```\nextra prose',
        '```json\n{"decision":"approve"}\n```\n```json\n{}\n```',
        '```json\n{"decision":"approve"\n```',
        '```json\n{"decision":"approve"}',
    ],
)
def test_structured_judge_rejects_nonexclusive_or_malformed_fences(content):
    payload, valid = ex._structured_judge_payload(content)

    assert valid is False
    assert payload["status"] == "needs_review"
    assert payload["partial_output"] == content.strip()


def test_token_capped_fenced_judge_output_still_fails_closed():
    result = ex.RoleResult(
        role="judge",
        model="ornith-9b-mini",
        endpoint="http://127.0.0.1:8088",
        content='```json\n{"status":"passed","rationale":"complete"}\n```',
        usage={},
        raw={"finish_reason": "length", "token_cap_reached": True},
    )

    payload = ex._build_judge_payload_from_result(result)

    assert payload["status"] == "needs_review"
    assert "token limit" in payload["rationale"]
    assert payload["partial_output"] == result.content


@pytest.mark.parametrize(
    ("content", "raw"),
    [
        ('{"decision":"approve","repo_grounding":"partial"', {}),
        (
            json.dumps({"decision": "approve", "repo_grounding": "looks good"}),
            {"finish_reason": "length", "token_cap_reached": True},
        ),
    ],
)
def test_planning_judge_incomplete_output_requires_revision(
    tmp_path,
    monkeypatch,
    content,
    raw,
):
    root = tmp_path / "proj"
    root.mkdir()
    run_id = pr.create_pipeline_run(root, {"title": "t", "description": "d"})
    state = load_loop_state(root, run_id).model_copy(
        update={"stage": LoopStage.planning_judge}
    )
    save_loop_state(root, state)
    result = ex.RoleResult(
        role="planning_judge",
        model="free-review-fleet",
        endpoint="https://example.invalid/v1",
        content=content,
        usage={},
        raw=raw,
    )
    monkeypatch.setattr(ex, "run_role", lambda *args, **kwargs: result)
    evidence = ex.pj.PlanningEvidence(
        run_id=run_id,
        plan_path="plan.md",
        spec_path="spec.md",
        target_files=["src/example.py"],
        verification_command="python -m pytest tests/test_example.py -q",
        files_exist=True,
        has_verification=True,
    )

    _, report = ex.run_planning_judge_model(
        root,
        run_id,
        evidence=evidence,
        planner_content="{}",
        ensure_lane_on=False,
    )

    assert report.decision == ex.pj.JudgeDecision.revise
    assert "complete structured response" in report.next_safe_action
    assert load_loop_state(root, run_id).stage == LoopStage.planning_judge


@pytest.mark.parametrize(
    ("content", "raw"),
    [
        ('{"status":"passed","rationale":"partial"', {}),
        (
            json.dumps({"status": "passed", "rationale": "looks good"}),
            {"finish_reason": "length", "token_cap_reached": True},
        ),
    ],
)
def test_build_judge_incomplete_output_never_passes(
    tmp_path,
    monkeypatch,
    content,
    raw,
):
    root, run_id = _fresh_root(tmp_path)
    state = load_loop_state(root, run_id).model_copy(
        update={"stage": LoopStage.build_judge}
    )
    save_loop_state(root, state)
    result = ex.RoleResult(
        role="judge",
        model="free-review-fleet",
        endpoint="https://example.invalid/v1",
        content=content,
        usage={},
        raw=raw,
    )
    monkeypatch.setattr(ex, "run_role", lambda *args, **kwargs: result)

    _, decision = ex.run_judge(
        root,
        run_id,
        definition_of_done="The bounded change passes review.",
        ensure_lane_on=False,
    )

    persisted = pr.load_pipeline_run(root, run_id)["judge-decision.json"]
    assert decision == "needs_review"
    assert persisted["status"] == "needs_review"
    assert persisted["partial_output"] == content
    assert load_loop_state(root, run_id).builder_judge_passed is False


def test_subscription_client_requires_explicit_model_endpoint():
    with pytest.raises(ValueError, match="hermes://chat/<provider>/<model>"):
        ex.HermesSubscriptionClient("hermes://chat")


def test_subscription_client_does_not_hide_failure_with_model_fallback(monkeypatch):
    client = ex.HermesSubscriptionClient("hermes://chat/zai/example-model")
    calls = []

    def fail(prompt, *, provider, model):
        calls.append((provider, model))
        raise RuntimeError("primary unavailable")

    monkeypatch.setattr(client, "_call", fail)

    with pytest.raises(RuntimeError, match="primary unavailable"):
        client.chat(messages=[{"role": "user", "content": "test"}])
    assert calls == [("zai", "example-model")]


def test_subscription_client_uses_final_only_hermes_mode(monkeypatch):
    captured = {}

    def fake_run(cmd, **kwargs):
        captured["cmd"] = cmd
        captured["kwargs"] = kwargs
        return type("Proc", (), {
            "returncode": 0,
            "stdout": (
                "Warning: Unknown toolsets: none\n\n"
                "┌─ Reasoning ─────────────────────┐\n"
                "**Inspecting the bounded packet**\n\n"
                "<!-- -->**Producing the exact answer**\n\n"
                "final answer\n"
                "session_id: hidden-session\n"
            ),
            "stderr": "",
        })()

    monkeypatch.setattr(ex.subprocess, "run", fake_run)
    client = ex.HermesSubscriptionClient(
        "hermes://chat/openai-codex/gpt-5.6-luna"
    )

    content = client._call(
        "system\nuser prompt",
        provider="openai-codex",
        model="gpt-5.6-luna",
    )

    assert captured["cmd"] == [
        "hermes", "chat",
        "-q", "system user prompt",
        "-Q",
        "-m", "gpt-5.6-luna",
        "--provider", "openai-codex",
        "-t", "none",
        "--max-turns", "1",
        "--ignore-rules",
        "--source", "tool",
    ]
    assert captured["kwargs"]["capture_output"] is True
    assert captured["kwargs"]["timeout"] == 120
    assert content == "final answer"


def test_remote_non_reasoning_call_disables_provider_reasoning(monkeypatch):
    captured = {}

    def fake_post(endpoint, payload, timeout, api_key=None):
        captured.update(payload)
        return {"choices": [{"message": {"content": "ok"}}]}

    monkeypatch.setattr(ex.LocalModelClient, "_do_post", staticmethod(fake_post))
    client = ex.LocalModelClient(
        "https://openrouter.ai/api/v1",
        model_name="tencent/hy3:free",
        api_key="test-key",
    )

    content, _ = client.chat(messages=[{"role": "user", "content": "ping"}], reasoning=False)

    assert content == "ok"
    assert captured["reasoning_effort"] == "none"
    assert captured["include_reasoning"] is False


def test_remote_reasoning_call_uses_bounded_reasoning_effort(monkeypatch):
    captured = {}

    def fake_post(endpoint, payload, timeout, api_key=None):
        captured.update(payload)
        return {"choices": [{"message": {"content": "ok"}}]}

    monkeypatch.setattr(ex.LocalModelClient, "_do_post", staticmethod(fake_post))
    client = ex.LocalModelClient(
        "https://openrouter.ai/api/v1",
        model_name="tencent/hy3:free",
        api_key="test-key",
    )

    client.chat(messages=[{"role": "user", "content": "ping"}], reasoning=True)

    assert captured["reasoning_effort"] == "low"
    assert captured["include_reasoning"] is False


def test_remote_call_sends_ordered_model_fallbacks_and_records_actual_model(monkeypatch):
    captured = {}

    def fake_post(endpoint, payload, timeout, api_key=None):
        captured.update(payload)
        return {
            "model": "fallback/two:free",
            "choices": [{"message": {"content": "ok"}}],
            "usage": {"cost": 0},
        }

    monkeypatch.setattr(ex.LocalModelClient, "_do_post", staticmethod(fake_post))
    client = ex.LocalModelClient(
        "https://openrouter.ai/api/v1",
        model_name="primary/model:free",
        fallback_model_ids=("fallback/one:free", "fallback/two:free"),
        api_key="test-key",
    )

    content, usage = client.chat(messages=[{"role": "user", "content": "ping"}])

    assert content == "ok"
    assert "model" not in captured
    assert captured["models"] == [
        "primary/model:free", "fallback/one:free", "fallback/two:free",
    ]
    assert usage == {"cost": 0, "actual_model": "fallback/two:free"}


def test_remote_call_retries_blank_success_once(monkeypatch):
    calls = 0

    def fake_post(endpoint, payload, timeout, api_key=None):
        nonlocal calls
        calls += 1
        content = "" if calls == 1 else "usable"
        return {"model": "model:free", "choices": [{"message": {"content": content}}]}

    monkeypatch.setattr(ex.LocalModelClient, "_do_post", staticmethod(fake_post))
    client = ex.LocalModelClient(
        "https://openrouter.ai/api/v1", model_name="model:free", api_key="test-key"
    )

    content, _ = client.chat(messages=[{"role": "user", "content": "ping"}])

    assert calls == 2
    assert content == "usable"


def test_remote_non_reasoning_stream_disables_provider_reasoning(monkeypatch):
    captured = {}

    class FakeResponse:
        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def __iter__(self):
            return iter([b'data: {"choices":[{"delta":{"content":"ok"},"finish_reason":"stop"}]}\n'])

    def fake_urlopen(request, timeout):
        captured.update(json.loads(request.data))
        return FakeResponse()

    monkeypatch.setattr(urllib.request, "urlopen", fake_urlopen)
    client = ex.LocalModelClient(
        "https://openrouter.ai/api/v1",
        model_name="tencent/hy3:free",
        api_key="test-key",
    )

    content, _, _, _ = client.chat_stream(
        messages=[{"role": "user", "content": "ping"}],
        reasoning=False,
    )

    assert content == "ok"
    assert captured["reasoning_effort"] == "none"
    assert captured["include_reasoning"] is False


def test_local_client_sends_native_schema_decoder_controls_and_explicit_thinking(monkeypatch):
    captured = {}

    def fake_post(endpoint, payload, timeout, api_key=None):
        captured.update(payload)
        return {
            "model": "candidate-model",
            "choices": [{"message": {"content": '{"schema_version":1}'}}],
        }

    schema = {
        "type": "json_schema",
        "json_schema": {
            "name": "devflow_planner_v1",
            "strict": True,
            "schema": {"type": "object"},
        },
    }
    monkeypatch.setattr(ex.LocalModelClient, "_do_post", staticmethod(fake_post))
    client = ex.LocalModelClient(
        "http://127.0.0.1:8088", model_name="candidate-model"
    )

    client.chat(
        messages=[{"role": "user", "content": "plan"}],
        temperature=0.2,
        reasoning=True,
        request_options={
            "top_p": 0.9,
            "top_k": 20,
            "repeat_penalty": 1.1,
            "seed": 7,
            "response_format": schema,
        },
    )

    assert captured["temperature"] == 0.2
    assert captured["top_p"] == 0.9
    assert captured["top_k"] == 20
    assert captured["repeat_penalty"] == 1.1
    assert captured["seed"] == 7
    assert captured["response_format"] == schema
    assert captured["chat_template_kwargs"] == {"enable_thinking": True}
    assert client.last_request_payload == captured


def test_local_client_records_actual_retry_payload_when_template_kwargs_rejected(monkeypatch):
    calls = []

    def fake_post(endpoint, payload, timeout, api_key=None):
        calls.append(dict(payload))
        if len(calls) == 1:
            raise urllib.error.HTTPError(endpoint, 400, "bad template kwargs", {}, None)
        return {"choices": [{"message": {"content": "{}"}}]}

    monkeypatch.setattr(ex.LocalModelClient, "_do_post", staticmethod(fake_post))
    client = ex.LocalModelClient(
        "http://127.0.0.1:8088", model_name="candidate-model"
    )
    client.chat(
        messages=[{"role": "user", "content": "judge"}],
        reasoning=False,
        request_options={"response_format": {"type": "json_object"}},
    )

    assert calls[0]["chat_template_kwargs"] == {"enable_thinking": False}
    assert "chat_template_kwargs" not in calls[1]
    assert client.last_request_payload == calls[1]
    assert client.last_request_payload["response_format"] == {"type": "json_object"}


def test_local_stream_sends_same_bounded_request_options(monkeypatch):
    captured = {}

    class FakeResponse:
        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def __iter__(self):
            return iter([
                b'data: {"model":"candidate-model","choices":[{"delta":{"content":"{}"},"finish_reason":"stop"}]}\n'
            ])

    def fake_urlopen(request, timeout):
        captured.update(json.loads(request.data))
        return FakeResponse()

    monkeypatch.setattr(urllib.request, "urlopen", fake_urlopen)
    client = ex.LocalModelClient(
        "http://127.0.0.1:8088", model_name="candidate-model"
    )
    content, usage, finish, _ = client.chat_stream(
        messages=[{"role": "user", "content": "judge"}],
        reasoning=False,
        request_options={"top_p": 0.8, "top_k": 1, "seed": 11},
    )

    assert content == "{}"
    assert usage["actual_model"] == "candidate-model"
    assert finish == "stop"
    assert captured["top_p"] == 0.8
    assert captured["top_k"] == 1
    assert captured["seed"] == 11
    assert captured["chat_template_kwargs"] == {"enable_thinking": False}
    assert client.last_request_payload == captured


def test_local_client_rejects_unknown_request_option() -> None:
    client = ex.LocalModelClient(
        "http://127.0.0.1:8088", model_name="candidate-model"
    )
    with pytest.raises(ValueError, match="Unsupported local-model request options"):
        client.chat(
            messages=[{"role": "user", "content": "judge"}],
            request_options={"invented_sampler": 1},
        )


def test_planner_and_qwen_judge_receive_persisted_readiness_context(tmp_path):
    CapturingPlannerContextClient.planner_user_prompt = ""
    CapturingPlannerContextClient.judge_user_prompt = ""
    root = tmp_path / "proj"
    root.mkdir()
    run_id = pr.create_pipeline_run(str(root), {"title": "t", "description": "d"})
    pr.update_pipeline_run_record(root, run_id, "readiness-packet.md", "frontier model semantic scoring into Obsidian")
    pr.update_pipeline_run_record(root, run_id, "brainstorm.md", "persistent Brainstorm Queue")
    st = load_loop_state(root, run_id)
    st = st.model_copy(update={"stage": LoopStage.planning_judge})
    save_loop_state(root, st)

    out = ex.run_planning_loop(
        root, run_id,
        topic="AI Brief Intelligence Sorter",
        max_rounds=1,
        ensure_lane_on=False,
        client_factory=CapturingPlannerContextClient,
    )

    assert out["planning_decision"] == "approve"
    assert "frontier model semantic scoring into Obsidian" in CapturingPlannerContextClient.planner_user_prompt
    assert "persistent Brainstorm Queue" in CapturingPlannerContextClient.planner_user_prompt
    assert "frontier model semantic scoring into Obsidian" in CapturingPlannerContextClient.judge_user_prompt
    state = load_loop_state(root, run_id)
    assert state.spec_path == "spec.md"
    assert state.plan_path == "plan.md"
    assert state.planning_judge_path == "planning-judge.json"


def test_role_budgets_and_streaming_metadata_are_persisted(tmp_path):
    root, run_id = _fresh_root(tmp_path)
    StreamingBuilderClient.streamed = False

    result = ex.run_role(
        root,
        role="builder",
        system_prompt="build",
        user_prompt="implement",
        task_id=run_id,
        ensure_lane_on=False,
        client_factory=StreamingBuilderClient,
    )

    assert ex.ROLE_TOKEN_BUDGETS == {
        "builder": 16384,
        "planner": 4096,
        "judge": 2048,
        "planning_judge": 2048,
        "verifier": 2048,
    }
    assert StreamingBuilderClient.streamed is True
    assert result.raw["finish_reason"] == "length"
    feed = pr.load_pipeline_run(root, run_id)["worker-feed.jsonl"]
    assert feed[0]["requested_max_tokens"] == 16384
    assert feed[0]["configured_route"] == feed[0]["model"]
    assert feed[0]["route_provenance"] in {"profile", "auto", "override"}
    assert feed[-1]["finish_reason"] == "length"
    assert feed[-1]["token_cap_reached"] is True
    assert feed[-1]["configured_route"] == feed[-1]["model"]
    assert feed[-1]["route_provenance"] == feed[0]["route_provenance"]
    assert "worker-live.json" not in pr.load_pipeline_run(root, run_id)


def test_stream_failure_preserves_partial_output_and_stalled_state(tmp_path):
    root, run_id = _fresh_root(tmp_path)

    with pytest.raises(RuntimeError, match="model disconnected"):
        ex.run_role(
            root, role="builder", system_prompt="build", user_prompt="implement",
            task_id=run_id, ensure_lane_on=False,
            client_factory=FailingStreamingClient,
        )

    data = pr.load_pipeline_run(root, run_id)
    assert data["worker-live.json"]["content"] == "partial implementation"
    assert data["worker-live.json"]["status"] == "stalled"
    assert data["execution-control.json"]["status"] == "stalled"
    assert [entry["event"] for entry in data["worker-feed.jsonl"]] == [
        "started", "failed"
    ]
    assert {entry["reasoning_enabled"] for entry in data["worker-feed.jsonl"]} == {
        False
    }


def test_builder_materializes_declared_patch_in_isolated_workspace(tmp_path):
    root, run_id = _fresh_root(tmp_path)
    patch = """diff --git a/calc.py b/calc.py
new file mode 100644
--- /dev/null
+++ b/calc.py
@@ -0,0 +1,2 @@
+def add(a, b):
+    return a + b
"""

    manifest = ex.materialize_builder_output(
        root, run_id, patch, target_files=["calc.py"]
    )

    workspace = Path(manifest["workspace"])
    assert (workspace / "calc.py").read_text() == "def add(a, b):\n    return a + b\n"
    assert manifest["changed_files"] == ["calc.py"]
    assert not (Path(root) / "calc.py").exists()
    assert (Path(root) / ".devflow" / "pipeline-runs" / run_id / "build-diff.patch").is_file()


def test_builder_rejects_undeclared_or_truncated_multi_file_output(tmp_path):
    root, run_id = _fresh_root(tmp_path)
    undeclared = """diff --git a/other.py b/other.py
new file mode 100644
--- /dev/null
+++ b/other.py
@@ -0,0 +1 @@
+bad = True
"""
    with pytest.raises(ex.BuilderOutputError, match="undeclared"):
        ex.materialize_builder_output(root, run_id, undeclared, target_files=["calc.py"])

    with pytest.raises(ex.BuilderOutputError, match="Could not parse multi-file greenfield"):
        ex.materialize_builder_output(
            root, run_id, "def a():\n    pass\n", target_files=["a.py", "b.py"]
        )


def test_builder_materializes_multi_file_greenfield_output(tmp_path):
    """Multi-file greenfield output using path-comment markers should be split
    into individual files in the isolated workspace."""
    root, run_id = _fresh_root(tmp_path)
    greenfield = (
        "# src/models.py\n"
        "from dataclasses import dataclass\n"
        "\n"
        "@dataclass\n"
        "class Item:\n"
        "    id: str\n"
        "\n"
        "# src/parser.py\n"
        "def parse(content):\n"
        "    return []\n"
    )
    manifest = ex.materialize_builder_output(
        root, run_id, greenfield, target_files=["src/models.py", "src/parser.py"]
    )
    workspace = Path(manifest["workspace"])
    assert sorted(manifest["changed_files"]) == ["src/models.py", "src/parser.py"]
    assert "class Item" in (workspace / "src/models.py").read_text()
    assert "def parse" in (workspace / "src/parser.py").read_text()


def test_builder_strips_two_file_greenfield_fences_ending_in_newline(tmp_path):
    root, run_id = _fresh_root(tmp_path)
    greenfield = (
        "# src/local_case.py\n"
        "```python\n"
        "def case_value():\n"
        "    return 1\n"
        "\n"
        "```\n"
        "# tests/test_local_case.py\n"
        "```python\n"
        "from src.local_case import case_value\n"
        "\n"
        "def test_case_value():\n"
        "    assert case_value() == 1\n"
        "```\n"
    )

    manifest = ex.materialize_builder_output(
        root,
        run_id,
        greenfield,
        target_files=["src/local_case.py", "tests/test_local_case.py"],
    )
    workspace = Path(manifest["workspace"])
    source = (workspace / "src/local_case.py").read_text(encoding="utf-8")
    test = (workspace / "tests/test_local_case.py").read_text(encoding="utf-8")

    assert "```" not in source
    assert "```" not in test
    compile(source, "src/local_case.py", "exec")
    compile(test, "tests/test_local_case.py", "exec")


def test_builder_workspace_preserves_parent_packages_for_new_modules(tmp_path):
    root, run_id = _fresh_root(tmp_path)
    root = Path(root)
    (root / "src/devflow/loop").mkdir(parents=True)
    (root / "src/devflow/__init__.py").write_text("\n")
    (root / "src/devflow/loop/__init__.py").write_text("\n")
    greenfield = (
        "# src/devflow/loop/run_labels.py\n"
        "def format_run_label(run_id, stage):\n"
        "    return f'{run_id} · {stage.upper()}'\n"
        "\n"
        "# tests/test_run_labels.py\n"
        "from devflow.loop.run_labels import format_run_label\n"
        "\n"
        "def test_format_run_label():\n"
        "    assert format_run_label('run-1', 'build') == 'run-1 · BUILD'\n"
    )

    manifest = ex.materialize_builder_output(
        root,
        run_id,
        greenfield,
        target_files=[
            "src/devflow/loop/run_labels.py",
            "tests/test_run_labels.py",
        ],
    )
    workspace = Path(manifest["workspace"])

    assert (workspace / "src/devflow/__init__.py").is_file()
    assert (workspace / "src/devflow/loop/__init__.py").is_file()
    result = ex._run_workspace_tests(
        workspace,
        test_files=["tests/test_run_labels.py"],
    )
    assert result["exit_code"] == 0, result["summary"]
    assert "in <duration>s" in result["summary"]


def test_greenfield_builder_prompt_omits_unrelated_sibling_context(tmp_path):
    root, run_id = _fresh_root(tmp_path)
    root = Path(root)
    (root / "tests").mkdir(exist_ok=True)
    (root / "tests" / "test_unrelated.py").write_text("SECRET_UNRELATED_CONTEXT = True\n")
    captured = {}

    class GreenfieldClient:
        def __init__(self, endpoint: str, *, timeout: int = 1):
            pass

        def chat(self, *, messages, **kwargs):
            captured["user_prompt"] = messages[1]["content"]
            return (
                "# src/new_helper.py\nVALUE = 1\n"
                "# tests/test_new_helper.py\n"
                "from src.new_helper import VALUE\n\n"
                "def test_value():\n    assert VALUE == 1\n",
                {},
            )

    ex.run_builder(
        root,
        run_id,
        assignment="Create a greenfield helper and test.",
        definition_of_done="Both declared files exist.",
        target_files=["src/new_helper.py", "tests/test_new_helper.py"],
        ensure_lane_on=False,
        client_factory=GreenfieldClient,
    )

    assert "SECRET_UNRELATED_CONTEXT" not in captured["user_prompt"]


def test_builder_refuses_oversized_packet_and_planner_chunks_files(tmp_path):
    files = [f"src/module_{index}.py" for index in range(13)]
    packets = ex.build_packets(files)
    cap = ex.MAX_TARGET_FILES_PER_BUILD

    expected_sizes = [cap] * (len(files) // cap)
    if len(files) % cap:
        expected_sizes.append(len(files) % cap)
    assert [len(packet["target_files"]) for packet in packets] == expected_sizes

    root, run_id = _fresh_root(tmp_path)
    with pytest.raises(ex.BuilderOutputError, match=f"at most {cap}"):
        ex.run_builder(
            root, run_id,
            assignment="too broad",
            definition_of_done="all modules exist",
            target_files=files,
            ensure_lane_on=False,
            client_factory=FakeClient,
        )


def test_execute_full_chain_offline(tmp_path):
    root, run_id = _fresh_root(tmp_path)

    out = ex.run_build_judge_verify(
        root, run_id,
        assignment="Implement add()",
        definition_of_done="add returns sum",
        target_files=["calc.py"],
        verification_command="python -c 'assert True'",
        client_factory=FakeClient,
        ensure_lane_on=False,  # offline: don't touch the real fleet
    )

    # Build produced content + loop-packet.md persisted
    assert out["build"].content.strip().startswith("def add")
    packet = pr.load_pipeline_run(root, run_id).get("loop-packet.md", "")
    assert "def add" in packet

    # Judge parsed -> passed -> stage advanced past build_judge
    assert out["decision"] == "passed"
    state = load_loop_state(root, run_id)
    assert state.stage in (LoopStage.verification, LoopStage.human_decision)

    # Verification (passed command) advanced to human_decision
    assert out["verification"] is not None
    assert out["verification"].status.value == "passed"
    state = load_loop_state(root, run_id)
    assert state.stage == LoopStage.human_decision


def test_execute_single_flight_lock_held(tmp_path):
    """While a role slot is held, no other acquire_role_slot can proceed."""
    from devflow.loop.model_router import acquire_role_slot

    root, _ = _fresh_root(tmp_path)
    with acquire_role_slot(Path(root), role="builder", task_id="x") as owner:
        # A second caller for a different role must see the lock occupied.
        status = _global_local_model_runtime_status(Path(root))
        assert status is not None
        assert status.state == "running"
        # Lock path is shared regardless of role/model:
        assert "global.lock" in status.lock_path
    # Released after exit
    assert _global_local_model_runtime_status(Path(root)) is None


def _port_healthy(port: int, timeout: float = 2.0) -> bool:
    try:
        urllib.request.urlopen(f"http://127.0.0.1:{port}/health", timeout=timeout)
        return True
    except Exception:
        return False


@pytest.mark.skipif(
    not _port_healthy(8084),
    reason="builder lane (8084) not resident; run model-router start 8084 first",
)
def test_execute_real_build_on_live_fleet(tmp_path):
    root, run_id = _fresh_root(tmp_path)
    result = ex.run_builder(
        root, run_id,
        assignment="Write a python function double(x) returning x*2.",
        definition_of_done="double returns x * 2",
        target_files=["mathy.py"],
    )
    assert result.role == "builder"
    assert len(result.content.strip()) > 0
    packet = pr.load_pipeline_run(root, run_id).get("loop-packet.md", "")
    assert len(packet.strip()) > 0
    state = load_loop_state(root, run_id)
    assert state.stage == LoopStage.build_judge


def test_plan_build_judge_offline(tmp_path):
    """Full plan->build->judge chain with a fake client (no fleet)."""
    root = tmp_path / "proj"
    root.mkdir()
    run_id = pr.create_pipeline_run(str(root), {"title": "t", "description": "d"})
    st = load_loop_state(root, run_id)
    st = st.model_copy(update={"stage": LoopStage.planning_judge})
    save_loop_state(root, st)
    # Pre-create the planned target file so files_exist -> True -> APPROVE.
    (root / "calc.py").write_text("")

    out = ex.run_plan_build_judge(
        root, run_id,
        topic="Add an add() function to calc.py",
        target_files=["calc.py"],
        definition_of_done="add() sums two numbers",
        ensure_lane_on=False,
        client_factory=FakeClient,
    )
    assert out["planning_decision"] == "approve"
    assert out["build"] is not None
    assert out["decision"] == "passed"
    state = load_loop_state(root, run_id)
    assert state.stage == LoopStage.verification
    # Planner artifacts persisted.
    assert "plan.md" in pr.load_pipeline_run(root, run_id)


def test_planning_loop_retries_until_approved(tmp_path):
    """A revise decision returns to the planner until the cap or approval."""
    RevisingPlannerClient.planner_calls = 0
    root = tmp_path / "proj"
    root.mkdir()
    run_id = pr.create_pipeline_run(str(root), {"title": "t", "description": "d"})
    st = load_loop_state(root, run_id)
    st = st.model_copy(update={"stage": LoopStage.planning_judge})
    save_loop_state(root, st)
    (root / "calc.py").write_text("")

    out = ex.run_planning_loop(
        root, run_id,
        topic="Add add()",
        max_rounds=3,
        ensure_lane_on=False,
        client_factory=RevisingPlannerClient,
    )

    assert out["planning_decision"] == "approve"
    assert len(out["planning_rounds"]) == 2
    assert out["planning_cap_exhausted"] is False
    assert load_loop_state(root, run_id).stage == LoopStage.assignment


def test_build_judge_loop_retries_until_passed(tmp_path):
    """A failed build judge result loops back to the builder before passing."""
    RevisingBuilderClient.judge_calls = 0
    root, run_id = _fresh_root(tmp_path)

    out = ex.run_build_judge_verify(
        root, run_id,
        assignment="Implement add()",
        definition_of_done="add returns sum",
        target_files=["calc.py"],
        max_rounds=3,
        client_factory=RevisingBuilderClient,
        ensure_lane_on=False,
    )

    assert out["decision"] == "passed"
    assert len(out["build_rounds"]) == 2
    assert out["build_cap_exhausted"] is False
    assert load_loop_state(root, run_id).stage == LoopStage.verification


@pytest.mark.skipif(
    not _port_healthy(8087),
    reason="planner lane (8087) not resident; run model-router start 8087 first",
)
def test_execute_real_planner_on_live_fleet(tmp_path):
    root = tmp_path / "proj"
    root.mkdir()
    run_id = pr.create_pipeline_run(str(root), {"title": "t", "description": "d"})
    st = load_loop_state(root, run_id)
    st = st.model_copy(update={"stage": LoopStage.planning_judge})
    save_loop_state(root, st)
    (root / "calc.py").write_text("")

    result, report = ex.run_planner(
        root, run_id,
        topic="Add an add(a,b) function to calc.py",
        target_files=["calc.py"],
    )
    assert result.role == "planner"
    assert len(result.content.strip()) > 0
    data = pr.load_pipeline_run(root, run_id)
    assert "spec.md" in data and "plan.md" in data
    assert report.decision.value in ("approve", "revise", "block")
