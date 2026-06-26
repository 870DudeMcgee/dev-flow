from __future__ import annotations

import json
import socket
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch

import pytest

from devflow.control_room.local_model_runtime_lock import (
    LocalModelRuntimeLockError,
    list_local_model_runtime_status,
    local_model_lock_dir,
    local_model_runtime_lock,
    local_model_runtime_status,
    reclaim_stale_local_model_runtime_lock,
)
from devflow.control_room.local_ollama_worker import run_local_ollama_worker
from devflow.control_room.operating_layer import build_operating_layer_snapshot
from tests.helpers import setup_temp_git_repo


def test_local_model_runtime_lock_is_single_flight(tmp_path: Path) -> None:
    with local_model_runtime_lock(
        tmp_path,
        provider="ollama",
        model="qwen3.6-32b-256k:latest",
        task_id="task-0001",
        worker_id="qwen-worker",
    ) as owner:
        status = local_model_runtime_status(
            tmp_path,
            provider="ollama",
            model="qwen3.6-32b-256k:latest",
        )
        assert status is not None
        assert status.state == "running"
        assert status.task_id == "task-0001"
        assert status.worker_id == "qwen-worker"
        assert status.owner_id == owner.owner_id

        with pytest.raises(LocalModelRuntimeLockError, match="already running"):
            with local_model_runtime_lock(
                tmp_path,
                provider="ollama",
                model="qwen3.6-32b-256k:latest",
                task_id="task-0002",
                worker_id="another-worker",
            ):
                pass

    assert local_model_runtime_status(
        tmp_path,
        provider="ollama",
        model="qwen3.6-32b-256k:latest",
    ) is None


def test_local_model_runtime_lock_blocks_different_provider_or_model_on_same_machine(tmp_path: Path) -> None:
    with local_model_runtime_lock(
        tmp_path,
        provider="ollama",
        model="qwen3.6-32b-256k:latest",
        task_id="task-0001",
        worker_id="qwen-worker",
    ):
        with pytest.raises(LocalModelRuntimeLockError, match="another local model"):
            with local_model_runtime_lock(
                tmp_path,
                provider="ollama",
                model="qwopus:latest",
                task_id="task-0002",
                worker_id="qwopus-worker",
            ):
                pass
        with pytest.raises(LocalModelRuntimeLockError, match="another local model"):
            with local_model_runtime_lock(
                tmp_path,
                provider="llama-cpp",
                model="qwen3.6-32b-256k:latest",
                task_id="task-0003",
                worker_id="qwen-server-worker",
            ):
                pass
        statuses = list_local_model_runtime_status(tmp_path)

    assert set(statuses) == {"ollama/qwen3.6-32b-256k:latest"}
    assert statuses["ollama/qwen3.6-32b-256k:latest"]["task_id"] == "task-0001"


def test_operating_layer_snapshot_exposes_read_only_local_model_runtime_status(tmp_path: Path) -> None:
    setup_temp_git_repo(tmp_path)
    with local_model_runtime_lock(
        tmp_path,
        provider="ollama",
        model="qwen3.6-32b-256k:latest",
        task_id="task-0001",
        worker_id="qwen-worker",
    ):
        snapshot = build_operating_layer_snapshot(tmp_path)

    runtime = snapshot.local_model_runtime["ollama/qwen3.6-32b-256k:latest"]
    assert runtime["state"] == "running"
    assert runtime["task_id"] == "task-0001"
    assert runtime["worker_id"] == "qwen-worker"
    assert runtime["lock_path"] == ".devflow/runtime/locks/local-model/global.lock"


def test_stale_local_model_runtime_lock_is_reported_not_auto_deleted(tmp_path: Path) -> None:
    lock_dir = local_model_lock_dir(tmp_path, "ollama", "qwen3.6-32b-256k:latest")
    lock_dir.mkdir(parents=True)
    payload = {
        "owner_id": "dead-owner",
        "provider": "ollama",
        "model": "qwen3.6-32b-256k:latest",
        "task_id": "task-dead",
        "worker_id": "qwen-worker",
        "operation": "test",
        "pid": 999_999_999,
        "host": socket.gethostname(),
        "acquired_at": datetime.now(timezone.utc).isoformat(),
        "lock_path": ".devflow/runtime/locks/local-model/global.lock",
    }
    (lock_dir / "owner.json").write_text(json.dumps(payload) + "\n", encoding="utf-8")

    status = local_model_runtime_status(tmp_path, provider="ollama", model="qwen3.6-32b-256k:latest")
    assert status is not None
    assert status.state == "stale"

    with pytest.raises(LocalModelRuntimeLockError, match="stale runtime lock"):
        with local_model_runtime_lock(
            tmp_path,
            provider="ollama",
            model="qwen3.6-32b-256k:latest",
            task_id="task-new",
            worker_id="qwen-worker",
        ):
            pass

    assert lock_dir.exists(), "stale locks are reported, not blindly deleted"
    assert reclaim_stale_local_model_runtime_lock(tmp_path, provider="ollama", model="qwen3.6-32b-256k:latest") is True
    assert not lock_dir.exists()


def test_list_local_model_runtime_status_uses_provider_model_keys(tmp_path: Path) -> None:
    with local_model_runtime_lock(
        tmp_path,
        provider="ollama",
        model="qwopus:latest",
        task_id="task-0003",
        worker_id="qwopus-implementer",
    ):
        statuses = list_local_model_runtime_status(tmp_path)

    assert statuses["ollama/qwopus:latest"]["state"] == "running"
    assert statuses["ollama/qwopus:latest"]["task_id"] == "task-0003"


def test_legacy_local_ollama_worker_refuses_second_same_model_run(tmp_path: Path) -> None:
    workspace = tmp_path / ".devflow" / "workspaces" / "task-0004"
    workspace.mkdir(parents=True)
    task_yaml_text = "id: task-0004\ntitle: locked model\nstatus: created\n"

    with local_model_runtime_lock(
        tmp_path,
        provider="ollama",
        model="qwen3.6:latest",
        task_id="other-task",
        worker_id="qwen-planner",
    ):
        with patch("subprocess.run") as fake_run:
            result = run_local_ollama_worker(
                tmp_path,
                "task-0004",
                workspace,
                "qwen-planner",
                timeout_seconds=5,
                task_yaml_text=task_yaml_text,
            )

    fake_run.assert_not_called()
    assert result.status == "failed"
    assert result.exit_code == 1
    assert result.error_message is not None
    assert "already running" in result.error_message
    assert "single-flight" in result.stderr_path.read_text(encoding="utf-8")
