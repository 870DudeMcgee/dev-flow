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
