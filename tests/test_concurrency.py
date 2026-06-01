from __future__ import annotations

import tempfile
from pathlib import Path
import concurrent.futures

from devflow.control_room.service import create_task, get_task, init_control_room

def test_concurrent_task_creation() -> None:
    with tempfile.TemporaryDirectory() as tmp_dir:
        tmp_path = Path(tmp_dir)
        init_control_room(tmp_path)

        num_tasks = 5
        def run_create(idx: int) -> str:
            record = create_task(tmp_path, f"Concurrent task {idx}")
            return record.id

        with concurrent.futures.ThreadPoolExecutor(max_workers=num_tasks) as executor:
            futures = [executor.submit(run_create, i) for i in range(num_tasks)]
            task_ids = [f.result() for f in concurrent.futures.as_completed(futures)]

        assert len(task_ids) == num_tasks
        assert len(set(task_ids)) == num_tasks

        for task_id in task_ids:
            task = get_task(tmp_path, task_id)
            assert task.id == task_id
            assert task.status == "created"
            assert (tmp_path / ".devflow" / "tasks" / task_id / "task.yaml").exists()
            assert (tmp_path / ".devflow" / "workspaces" / task_id).is_dir()
