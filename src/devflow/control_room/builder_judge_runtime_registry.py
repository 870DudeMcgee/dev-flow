from __future__ import annotations

import threading
from pathlib import Path
from typing import Any

from devflow.control_room.builder_judge_loop import (
    list_builder_judge_loops,
    project_builder_judge_run,
)

# In-memory registry of live builder-judge loop payloads plus finished thread objects.
_bj_running_loops: dict[str, dict[str, Any]] = {}
_bj_threads: dict[str, threading.Thread] = {}
# ponytail: one global lock for this small shared registry; split later only if contention shows up.
_bj_state_lock = threading.Lock()
_bj_completed_thread_retention = 32


def _bj_prune_completed_threads_locked() -> None:
    completed_loop_ids = [loop_id for loop_id, thread in _bj_threads.items() if not thread.is_alive()]
    excess = len(completed_loop_ids) - _bj_completed_thread_retention
    for loop_id in completed_loop_ids[: max(excess, 0)]:
        _bj_threads.pop(loop_id, None)


def _bj_store_running_loop(
    loop_id: str,
    payload: dict[str, Any],
    thread: threading.Thread | None = None,
    *,
    prune: bool = True,
) -> None:
    with _bj_state_lock:
        if thread is not None:
            _bj_threads[loop_id] = thread
        _bj_running_loops[loop_id] = payload
        if prune:
            _bj_prune_completed_threads_locked()


def _bj_get_running_loop(loop_id: str) -> dict[str, Any] | None:
    with _bj_state_lock:
        _bj_prune_completed_threads_locked()
        payload = _bj_running_loops.get(loop_id)
        return dict(payload) if payload is not None else None


def _bj_list_visible_loops(root: Path) -> list[dict[str, Any]]:
    loops_by_id = {str(loop.get("loop_id") or ""): loop for loop in list_builder_judge_loops(root)}
    with _bj_state_lock:
        _bj_prune_completed_threads_locked()
        for loop_id, payload in _bj_running_loops.items():
            loops_by_id[loop_id] = project_builder_judge_run(payload, root=root)
    loops = list(loops_by_id.values())
    loops.sort(key=lambda loop: loop.get("started_at", ""), reverse=True)
    return loops
