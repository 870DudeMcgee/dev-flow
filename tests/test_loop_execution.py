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
import urllib.request
from pathlib import Path

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

    def __init__(self, endpoint: str, *, timeout: int = 1):
        self.endpoint = endpoint

    def chat(self, *, messages, max_tokens=2048, temperature=0.0,
             reasoning=False, stop=None):
        type(self).reasoning_values.append(reasoning)
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


def test_verifier_requests_reasoning_and_emits_model_agnostic_evidence(tmp_path, monkeypatch):
    ReasoningCaptureClient.reasoning_values = []
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
        json.dumps({"changed_files": [], "workspace": str(root)}),
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
    assert feed[-1]["finish_reason"] == "length"
    assert feed[-1]["token_cap_reached"] is True
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
