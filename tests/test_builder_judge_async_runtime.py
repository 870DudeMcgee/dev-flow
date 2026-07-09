from __future__ import annotations

import threading
from pathlib import Path

from devflow.legacy.control_room import builder_judge_runtime_registry as bj_runtime
from devflow.legacy.control_room.builder_judge_async_runtime import start_workbench_implementation_async
from devflow.legacy.control_room.builder_judge_loop import BuilderJudgeConfig
from devflow.legacy.control_room.unified_workbench import WorkbenchImplementationPackage


class _FakePassedRun:
    status = "passed"
    final_draft = "Accepted implementation\n"
    final_score = 91
    evidence_path = ".devflow/builder-judge-loops/workbench-loop/run.json"

    def __init__(self, loop_id: str) -> None:
        self.loop_id = loop_id

    def model_dump(self, *, mode: str) -> dict[str, object]:
        assert mode == "json"
        return {
            "loop_id": self.loop_id,
            "run_id": f"{self.loop_id}-run",
            "status": self.status,
            "final_draft": self.final_draft,
            "final_score": self.final_score,
            "evidence_path": self.evidence_path,
            "rounds": [],
            "config": {"definition_of_done": "done"},
            "next_safe_action": "Create a task.",
        }


def _clear_builder_judge_state() -> None:
    with bj_runtime._bj_state_lock:
        bj_runtime._bj_running_loops.clear()
        bj_runtime._bj_threads.clear()


def test_workbench_async_runtime_stores_final_workbench_payload(tmp_path: Path) -> None:
    _clear_builder_judge_state()
    package = WorkbenchImplementationPackage(
        definition_of_done={"summary": "done"},
        starting_point={"summary": "start"},
        definition_of_done_markdown="done",
        starting_point_markdown="start",
    )
    config = BuilderJudgeConfig(
        definition_of_done="done",
        starting_point="start",
        builder_profile_id="builder-a",
        judge_profile_id="judge-a",
    )

    def fake_run_loop(root: Path, received_config: BuilderJudgeConfig, *, loop_id: str) -> _FakePassedRun:
        assert root == tmp_path
        assert received_config is config
        return _FakePassedRun(loop_id)

    running = start_workbench_implementation_async(
        tmp_path,
        session_id="session-1",
        loop_id="workbench-loop",
        package=package,
        config=config,
        run_loop=fake_run_loop,
    )

    assert running["status"] == "running"
    final = None
    for _ in range(100):
        final = bj_runtime._bj_get_running_loop("workbench-loop")
        if final and final.get("status") == "passed":
            break
        threading.Event().wait(0.02)

    try:
        assert final is not None
        assert final["status"] == "passed"
        assert final["workbench"]["session_id"] == "session-1"
        assert final["workbench"]["implementation_path"] == ".devflow/brainstorms/session-1/implementation.md"
        assert (tmp_path / ".devflow" / "brainstorms" / "session-1" / "implementation.md").read_text(
            encoding="utf-8"
        ) == "Accepted implementation\n"
    finally:
        _clear_builder_judge_state()
