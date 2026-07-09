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
import os
import urllib.request
from pathlib import Path

import pytest

from devflow.loop import execution as ex
from devflow.loop import pipeline_run as pr
from devflow.loop.adapter import load_loop_state
from devflow.loop.models import LoopStage
from devflow.loop.model_router import _global_local_model_runtime_status


class FakeClient:
    """Deterministic stand-in for LocalModelClient. No network."""

    def __init__(self, endpoint: str, *, timeout: int = 1):
        self.endpoint = endpoint
        self.calls = []

    def chat(self, *, messages, max_tokens=2048, temperature=0.0,
             reasoning=False, stop=None):
        sys = messages[0]["content"]
        self.calls.append(sys)
        if "judge" in sys.lower():
            return json.dumps({"status": "passed", "rationale": "ok"}), {}
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
