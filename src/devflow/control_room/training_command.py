from __future__ import annotations

import json
from pathlib import Path

import typer

from devflow.control_room.training_dataset import (
    DEFAULT_MAX_EXAMPLES,
    DEFAULT_RUN_ID,
    prepare_gemma4_training_dataset,
)
from devflow.control_room.training_mlx_matrix import write_trainability_matrix
from devflow.control_room.training_mlx_projection import attach_training_run_to_task
from devflow.control_room.training_mlx_runner import (
    DEFAULT_MLX_RUN_ID,
    prepare_mlx_training_data,
    run_load_smoke,
    run_lora_smoke,
)


training_app = typer.Typer(help="Prepare local-only training datasets and dry-run manifests")
mlx_app = typer.Typer(help="Run local Apple MLX training smoke evidence")


@training_app.command("prepare-gemma4-e4b")
def prepare_gemma4_e4b_command(
    run_id: str = typer.Option(DEFAULT_RUN_ID, "--run-id", help="Training prep run ID."),
    max_examples: int = typer.Option(DEFAULT_MAX_EXAMPLES, "--max-examples", min=1, help="Maximum examples to export."),
    json_output: bool = typer.Option(False, "--json", help="Print the training prep result as JSON."),
) -> None:
    """Write a local-only Gemma 4 E4B dataset export and dry-run training manifest."""
    result = prepare_gemma4_training_dataset(Path.cwd(), run_id=run_id, max_examples=max_examples)
    if json_output:
        typer.echo(json.dumps(result, indent=2, sort_keys=True))
        return

    typer.echo(f"Prepared local-only training export: {result['run_id']}")
    typer.echo(f"example_count: {result['example_count']}")
    for key, value in result["output_paths"].items():
        typer.echo(f"{key}: {value}")
    for warning in result["warnings"]:
        typer.echo(f"warning: {warning}")


@mlx_app.command("prepare")
def mlx_prepare_command(
    run_id: str = typer.Option(DEFAULT_MLX_RUN_ID, "--run-id", help="MLX training run ID."),
    max_examples: int = typer.Option(DEFAULT_MAX_EXAMPLES, "--max-examples", min=1, help="Maximum examples to export."),
    json_output: bool = typer.Option(False, "--json", help="Print the MLX prep result as JSON."),
) -> None:
    """Write MLX-LM-compatible local text training data."""
    result = prepare_mlx_training_data(Path.cwd(), run_id=run_id, max_examples=max_examples)
    _echo_result(result, json_output=json_output)


@mlx_app.command("load-smoke")
def mlx_load_smoke_command(
    model: str = typer.Option(..., "--model", help="MLX/Hugging Face model ID or local path."),
    run_id: str = typer.Option(DEFAULT_MLX_RUN_ID, "--run-id", help="MLX training run ID."),
    dry_run: bool = typer.Option(False, "--dry-run", help="Write planned command evidence without executing MLX."),
    timeout_seconds: int = typer.Option(
        1800,
        "--timeout-seconds",
        min=1,
        help="Maximum seconds for real smoke execution.",
    ),
    json_output: bool = typer.Option(False, "--json", help="Print the smoke result as JSON."),
) -> None:
    """Run or plan a bounded MLX-LM generation smoke."""
    result = run_load_smoke(Path.cwd(), model=model, run_id=run_id, dry_run=dry_run, timeout_seconds=timeout_seconds)
    _echo_result(result, json_output=json_output)


@mlx_app.command("lora-smoke")
def mlx_lora_smoke_command(
    model: str = typer.Option(..., "--model", help="MLX/Hugging Face model ID or local path."),
    run_id: str = typer.Option(DEFAULT_MLX_RUN_ID, "--run-id", help="MLX training run ID."),
    iters: int = typer.Option(1, "--iters", min=1, help="LoRA training iterations."),
    dry_run: bool = typer.Option(False, "--dry-run", help="Write planned command evidence without executing MLX."),
    timeout_seconds: int = typer.Option(
        1800,
        "--timeout-seconds",
        min=1,
        help="Maximum seconds for real smoke execution.",
    ),
    json_output: bool = typer.Option(False, "--json", help="Print the smoke result as JSON."),
) -> None:
    """Run or plan a one-iteration MLX-LM LoRA smoke."""
    result = run_lora_smoke(
        Path.cwd(),
        model=model,
        run_id=run_id,
        iters=iters,
        dry_run=dry_run,
        timeout_seconds=timeout_seconds,
    )
    _echo_result(result, json_output=json_output)


@mlx_app.command("matrix")
def mlx_matrix_command(
    run_id: str = typer.Option(DEFAULT_MLX_RUN_ID, "--run-id", help="MLX training run ID."),
    models: Path | None = typer.Option(None, "--models", help="Model manifest JSON path."),
    dry_run: bool = typer.Option(False, "--dry-run", help="Render the matrix without writing matrix/result files."),
    task_id: str | None = typer.Option(
        None,
        "--task-id",
        help="Attach written result.md to an existing Dev-Flow task.",
    ),
    json_output: bool = typer.Option(False, "--json", help="Print the matrix result as JSON."),
) -> None:
    """Write or preview the MLX trainability matrix from smoke evidence."""
    result = write_trainability_matrix(Path.cwd(), run_id, manifest_path=models, dry_run=dry_run)
    if task_id and not dry_run:
        result["task_attachment"] = attach_training_run_to_task(Path.cwd(), task_id, run_id)
    _echo_result(result, json_output=json_output)


training_app.add_typer(mlx_app, name="mlx")


def _echo_result(result: dict, *, json_output: bool) -> None:
    if json_output:
        typer.echo(json.dumps(result, indent=2, sort_keys=True))
        return
    for key, value in result.items():
        if isinstance(value, (dict, list)):
            typer.echo(f"{key}: {json.dumps(value, sort_keys=True)}")
        else:
            typer.echo(f"{key}: {value}")
