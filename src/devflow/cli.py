"""V2-only DevFlow command surface.

DevFlow's brainstorm interaction is available through Hermes and the unified
browser surface. This CLI starts that browser surface and exposes a deterministic
loop-fixture harness for regression verification; it deliberately has no
compatibility path to retired code.
"""
from __future__ import annotations

import json
from pathlib import Path

import typer

from devflow.control_room.command import status_app
from devflow.control_room.model_catalog import model_catalog_snapshot
from devflow.loop.e2e_harness import run_e2e_loop_harness
from devflow.loop.model_catalog import load_free_cloud_catalog, refresh_free_cloud_catalog
from devflow.loop.model_catalog_markdown import (
    render_model_catalog_markdown,
    update_model_dashboard,
)

app = typer.Typer(
    help="DevFlow V2 pipeline tools.",
    no_args_is_help=True,
)
loop_app = typer.Typer(
    help="Deterministic V2 loop verification tools.",
    no_args_is_help=True,
)
models_app = typer.Typer(
    help="Live model catalog tools.",
    no_args_is_help=True,
)
app.add_typer(status_app, name="status")
app.add_typer(loop_app, name="loop")
app.add_typer(models_app, name="models")


@models_app.command("refresh")
def models_refresh(
    root: Path = typer.Option(
        Path("."),
        "--root",
        help="Repository root that owns the generated .devflow catalog.",
    ),
    obsidian_dashboard: Path | None = typer.Option(
        None,
        "--obsidian-dashboard",
        help="Optional Obsidian note that receives the generated read-only inventory block.",
    ),
    json_output: bool = typer.Option(False, "--json", help="Emit the refresh result as JSON."),
) -> None:
    """Refresh the free-cloud catalog; stay silent when nothing changed."""

    try:
        result = refresh_free_cloud_catalog(root)
        dashboard_changed = False
        if obsidian_dashboard is not None:
            dashboard_changed = update_model_dashboard(
                obsidian_dashboard,
                render_model_catalog_markdown(
                    load_free_cloud_catalog(root),
                    model_catalog_snapshot(root),
                ),
            )
    except Exception as exc:
        typer.echo(f"Model catalog refresh failed: {exc}", err=True)
        raise typer.Exit(code=1) from exc

    payload = {
        "changed": result.changed,
        "model_count": result.model_count,
        "added": list(result.added),
        "removed": list(result.removed),
        "modified": list(result.modified),
        "current_path": str(result.current_path),
        "dashboard_changed": dashboard_changed,
        "history_path": str(result.history_path) if result.history_path else None,
    }
    if json_output:
        typer.echo(json.dumps(payload, indent=2, sort_keys=True))
    elif result.changed:
        typer.echo(
            "Free-cloud catalog changed: "
            f"{result.model_count} models "
            f"(+{len(result.added)} -{len(result.removed)} ~{len(result.modified)})."
        )



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
