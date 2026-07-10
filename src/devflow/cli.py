"""V2-only DevFlow command surface.

DevFlow's interactive work happens in Hermes. This CLI exposes the read-only
pipeline status board and a deterministic loop-fixture harness for regression
verification; it deliberately has no compatibility path to retired code.
"""
from __future__ import annotations

import json
from pathlib import Path

import typer

from devflow.control_room.command import status_app
from devflow.loop.e2e_harness import run_e2e_loop_harness

app = typer.Typer(
    help="DevFlow V2 pipeline tools.",
    no_args_is_help=True,
)
loop_app = typer.Typer(
    help="Deterministic V2 loop verification tools.",
    no_args_is_help=True,
)
app.add_typer(status_app, name="status")
app.add_typer(loop_app, name="loop")


@loop_app.command("spine-fixture")
def loop_spine_fixture(
    target_file: str = typer.Option(
        "src/devflow/loop/models.py",
        "--target-file",
        help="Existing file, relative to the current repository root.",
    ),
    json_output: bool = typer.Option(False, "--json", help="Emit the verification report as JSON."),
) -> None:
    """Run the deterministic V2 stage-chain fixture without model calls."""
    try:
        report = run_e2e_loop_harness(Path.cwd(), target_file=target_file)
    except FileNotFoundError as exc:
        typer.echo(f"Fixture target file does not exist: {exc}", err=True)
        raise typer.Exit(code=1) from exc

    payload = {
        "run_id": report.run_id,
        "final_stage": report.final_stage.value,
        "expected_stage_chain": [stage.value for stage in report.expected_stage_chain],
        "observed_stage_chain": [stage.value for stage in report.observed_stage_chain],
        "evidence_files": report.evidence_files,
        "target_file": report.target_file,
        "verification_command": report.verification_command,
    }
    if json_output:
        typer.echo(json.dumps(payload, indent=2, sort_keys=True))
        return

    typer.echo(f"run_id: {payload['run_id']}")
    typer.echo(f"final_stage: {payload['final_stage']}")
    typer.echo(f"target_file: {payload['target_file']}")
    typer.echo(f"evidence_files: {len(report.evidence_files)}")


def main() -> None:
    """Run the V2-only DevFlow CLI."""
    app()


if __name__ == "__main__":
    main()
