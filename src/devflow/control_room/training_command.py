from __future__ import annotations

import json
from pathlib import Path

import typer

from devflow.control_room.training_dataset import (
    DEFAULT_MAX_EXAMPLES,
    DEFAULT_RUN_ID,
    prepare_gemma4_training_dataset,
)


training_app = typer.Typer(help="Prepare local-only training datasets and dry-run manifests")


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
