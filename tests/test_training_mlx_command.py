import json
from pathlib import Path

from typer.testing import CliRunner

from devflow.cli import app
from devflow.control_room.persistence import get_task
from devflow.control_room.training_mlx_runner import model_slug


runner = CliRunner()


def test_training_mlx_prepare_cli_json_output(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    _write_minimal_training_sources(tmp_path)

    result = runner.invoke(app, ["training", "mlx", "prepare", "--run-id", "mlx-cli", "--json"])

    assert result.exit_code == 0, result.output
    payload = json.loads(result.output)
    assert payload["run_id"] == "mlx-cli"
    assert payload["output_paths"]["train_jsonl"] == ".devflow/training/mlx-cli/data/train.jsonl"
    assert (tmp_path / payload["output_paths"]["train_jsonl"]).exists()


def test_training_mlx_smoke_commands_support_dry_run_json(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)

    load = runner.invoke(
        app,
        [
            "training",
            "mlx",
            "load-smoke",
            "--model",
            "lmstudio-community/Qwen3.6-27B-MLX-4bit",
            "--run-id",
            "mlx-cli",
            "--dry-run",
            "--json",
        ],
    )
    assert load.exit_code == 0, load.output
    load_payload = json.loads(load.output)
    assert load_payload["status"] == "dry_run"
    assert load_payload["command"][:6] == ["uvx", "--python", "3.12", "--from", "mlx-lm[train]", "mlx_lm.generate"]

    lora = runner.invoke(
        app,
        [
            "training",
            "mlx",
            "lora-smoke",
            "--model",
            "lmstudio-community/Qwen3.6-27B-MLX-4bit",
            "--run-id",
            "mlx-cli",
            "--iters",
            "1",
            "--dry-run",
            "--json",
        ],
    )
    assert lora.exit_code == 0, lora.output
    lora_payload = json.loads(lora.output)
    assert lora_payload["status"] == "dry_run"
    assert "--adapter-path" in lora_payload["command"]


def test_training_mlx_matrix_dry_run_cli_json_does_not_write_result(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    manifest = tmp_path / "models.json"
    manifest.write_text(json.dumps({"models": ["lmstudio-community/Qwen3.6-27B-MLX-4bit"]}), encoding="utf-8")

    result = runner.invoke(
        app,
        ["training", "mlx", "matrix", "--run-id", "mlx-cli", "--models", str(manifest), "--dry-run", "--json"],
    )

    assert result.exit_code == 0, result.output
    payload = json.loads(result.output)
    assert payload["dry_run"] is True
    assert payload["rows"][0]["model"] == "lmstudio-community/Qwen3.6-27B-MLX-4bit"
    assert not (tmp_path / ".devflow" / "training" / "mlx-cli" / "result.md").exists()


def test_training_mlx_matrix_can_attach_written_result_to_task(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    create = runner.invoke(app, ["task", "create", "mlx training evidence"])
    assert create.exit_code == 0, create.output

    run_id = "mlx-cli"
    model = "lmstudio-community/Qwen3.6-27B-MLX-4bit"
    model_dir = tmp_path / ".devflow" / "training" / run_id / "models" / model_slug(model)
    model_dir.mkdir(parents=True, exist_ok=True)
    (model_dir / "load-smoke.log").write_text("load", encoding="utf-8")

    result = runner.invoke(
        app, ["training", "mlx", "matrix", "--run-id", run_id, "--task-id", "task-0001", "--json"]
    )

    assert result.exit_code == 0, result.output
    payload = json.loads(result.output)
    assert payload["task_attachment"]["attached"] is True
    assert payload["task_attachment"]["log_path"] == f".devflow/training/{run_id}/models/{model_slug(model)}/load-smoke.log"
    assert get_task(tmp_path, "task-0001").result_path == ".devflow/training/mlx-cli/result.md"


def _write_minimal_training_sources(root: Path) -> None:
    (root / "AGENTS.md").write_text("# Agent rules\nKeep work grounded.\n", encoding="utf-8")
    (root / "README.md").write_text("# Dev-Flow\nLocal-first control room.\n", encoding="utf-8")
