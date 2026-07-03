from __future__ import annotations

import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

from devflow.control_room import builder_judge_runtime_registry as bj_runtime
from devflow.control_room.builder_judge_loop import (
    BuilderJudgeConfig,
    project_builder_judge_run,
    run_builder_judge_loop,
)
from devflow.control_room.unified_workbench import (
    WorkbenchImplementationPackage,
    finalize_workbench_run,
    workbench_running_payload,
)

RunLoop = Callable[..., Any]


def start_builder_judge_async_loop(
    root: Path,
    config: BuilderJudgeConfig,
    *,
    loop_id: str,
    run_loop: RunLoop = run_builder_judge_loop,
) -> dict[str, Any]:
    def _run_bj_loop() -> None:
        try:
            run = run_loop(root, config, loop_id=loop_id)
            payload = project_builder_judge_run(run, root=root)
        except Exception as exc:
            payload = project_builder_judge_run(
                {
                    "loop_id": loop_id,
                    "status": "failed",
                    "error": str(exc),
                    "rounds": [],
                    "config": config.model_dump(mode="json"),
                    "started_at": _now(),
                    "finished_at": _now(),
                    "stop_reason": "background_thread_error",
                    "next_safe_action": str(exc),
                },
                root=root,
            )
        bj_runtime._bj_store_running_loop(loop_id, payload, threading.current_thread())

    thread = threading.Thread(target=_run_bj_loop, daemon=True)
    start_payload = project_builder_judge_run(
        {
            "loop_id": loop_id,
            "run_id": "",
            "status": "running",
            "config": config.model_dump(mode="json"),
            "rounds": [],
            "started_at": _now(),
            "finished_at": None,
            "stop_reason": "",
            "next_safe_action": "",
        },
        root=root,
    )
    bj_runtime._bj_store_running_loop(loop_id, start_payload, thread, prune=False)
    thread.start()
    return start_payload


def start_workbench_implementation_async(
    root: Path,
    *,
    session_id: str,
    loop_id: str,
    package: WorkbenchImplementationPackage,
    config: BuilderJudgeConfig,
    run_loop: RunLoop = run_builder_judge_loop,
) -> dict[str, Any]:
    def _run_workbench_loop() -> None:
        try:
            run = run_loop(root, config, loop_id=loop_id)
            final = finalize_workbench_run(root, session_id=session_id, run=run, package=package)
            payload = project_builder_judge_run(run, root=root)
            payload["workbench"] = {
                "session_id": session_id,
                "implementation_path": final["implementation_path"],
                "refactor_offer_path": final["refactor_offer_path"],
                "next_action": final["next_action"],
                "package": package.model_dump(mode="json"),
            }
            bj_runtime._bj_store_running_loop(loop_id, payload)
        except Exception as exc:
            payload = project_builder_judge_run(
                {
                    "loop_id": loop_id,
                    "status": "failed",
                    "error": str(exc),
                    "rounds": [],
                    "config": config.model_dump(mode="json"),
                    "started_at": _now(),
                    "finished_at": _now(),
                    "stop_reason": "workbench_background_thread_error",
                    "next_safe_action": str(exc),
                    "workbench": {
                        "session_id": session_id,
                        "package": package.model_dump(mode="json"),
                    },
                },
                root=root,
            )
            bj_runtime._bj_store_running_loop(loop_id, payload, threading.current_thread())

    thread = threading.Thread(target=_run_workbench_loop, daemon=True)
    running_payload = project_builder_judge_run(
        workbench_running_payload(
            root,
            session_id=session_id,
            loop_id=loop_id,
            package=package,
            config=config,
        ),
        root=root,
    )
    bj_runtime._bj_store_running_loop(loop_id, running_payload, thread, prune=False)
    thread.start()
    return running_payload


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()
