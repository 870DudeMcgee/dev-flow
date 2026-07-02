from __future__ import annotations

import json
from pathlib import Path

from typer.testing import CliRunner

from devflow.cli import app
from devflow.control_room.operating_layer import build_operating_layer_snapshot
from devflow.control_room.training_mlx_projection import attach_training_run_to_task
from devflow.control_room.training_mlx_runner import model_slug


runner = CliRunner()


def test_attach_training_run_to_task_surfaces_result_in_operating_layer_snapshot(
    tmp_path: Path,
    monkeypatch,
) -> None:
    monkeypatch.chdir(tmp_path)
    create = runner.invoke(app, ["task", "create", "attach mlx evidence"])
    assert create.exit_code == 0, create.output

    run_id = "mlx-run-001"
    result_path = tmp_path / ".devflow" / "training" / run_id / "result.md"
    result_path.parent.mkdir(parents=True, exist_ok=True)
    result_path.write_text("# MLX Result\n\nAttached.\n", encoding="utf-8")

    attached = attach_training_run_to_task(tmp_path, "task-0001", run_id)

    assert attached == {
        "task_id": "task-0001",
        "run_id": run_id,
        "result_path": f".devflow/training/{run_id}/result.md",
        "log_path": None,
        "attached": True,
        "warnings": [],
    }

    snapshot = build_operating_layer_snapshot(tmp_path)
    task = next(item for item in snapshot.tasks if item.id == "task-0001")
    evidence = next(item for item in snapshot.evidence if item.task_id == "task-0001")

    assert task.result_path == f".devflow/training/{run_id}/result.md"
    assert f".devflow/training/{run_id}/result.md" in task.evidence_paths
    assert evidence.result_path == f".devflow/training/{run_id}/result.md"

    events_path = tmp_path / ".devflow" / "tasks" / "task-0001" / "events.jsonl"
    events = [
        json.loads(line)["event"]
        for line in events_path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    assert "training_mlx_attached" in events


def test_attach_training_run_to_task_prefers_adapter_reload_log_for_log_path(
    tmp_path: Path,
    monkeypatch,
) -> None:
    monkeypatch.chdir(tmp_path)
    create = runner.invoke(app, ["task", "create", "attach mlx reload evidence"])
    assert create.exit_code == 0, create.output

    run_id = "mlx-run-reload-log"
    model = "lmstudio-community/Qwen3.6-27B-MLX-4bit"
    model_dir = tmp_path / ".devflow" / "training" / run_id / "models" / model_slug(model)
    run_dir = tmp_path / ".devflow" / "training" / run_id
    run_dir.mkdir(parents=True, exist_ok=True)

    result_path = run_dir / "result.md"
    result_path.write_text("# MLX Result\n\nReload log preferred.\n", encoding="utf-8")
    model_dir.mkdir(parents=True, exist_ok=True)
    (model_dir / "load-smoke.log").write_text("load smoke", encoding="utf-8")
    (model_dir / "lora-smoke.log").write_text("lora smoke", encoding="utf-8")
    (model_dir / "lora-smoke-reload.log").write_text("reload smoke", encoding="utf-8")

    attached = attach_training_run_to_task(tmp_path, "task-0001", run_id)

    assert attached["attached"] is True
    assert (
        attached["log_path"]
        == f".devflow/training/{run_id}/models/{model_slug(model)}/lora-smoke-reload.log"
    )

    snapshot = build_operating_layer_snapshot(tmp_path)
    task = next(item for item in snapshot.tasks if item.id == "task-0001")
    assert task.log_path == attached["log_path"]


def test_attach_training_run_to_task_avoids_ambiguous_multi_model_log_path(
    tmp_path: Path,
    monkeypatch,
) -> None:
    monkeypatch.chdir(tmp_path)
    create = runner.invoke(app, ["task", "create", "attach mlx multi model evidence"])
    assert create.exit_code == 0, create.output

    run_id = "mlx-run-multi-model"
    run_dir = tmp_path / ".devflow" / "training" / run_id
    run_dir.mkdir(parents=True, exist_ok=True)
    (run_dir / "result.md").write_text("# MLX Result\n\nMulti-model.\n", encoding="utf-8")

    for model in ("lmstudio-community/Qwen3.6-27B-MLX-4bit", "lmstudio-community/Qwen3.6-27B-MLX-8bit"):
        model_dir = run_dir / "models" / model_slug(model)
        model_dir.mkdir(parents=True, exist_ok=True)
        (model_dir / "lora-smoke.log").write_text("lora smoke", encoding="utf-8")

    attached = attach_training_run_to_task(tmp_path, "task-0001", run_id)

    assert attached["attached"] is True
    assert attached["log_path"] is None

    snapshot = build_operating_layer_snapshot(tmp_path)
    task = next(item for item in snapshot.tasks if item.id == "task-0001")
    assert task.log_path is None
