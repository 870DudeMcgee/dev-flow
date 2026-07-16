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
from devflow.loop.pipeline_run import pipeline_runs_dir
from devflow.loop.workflow_ledger import is_canonical_workflow_run
from devflow.obsidian.projection import extract_projection
from devflow.obsidian.render import render_all
from devflow.obsidian.vault import write_vault_projection

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
obsidian_app = typer.Typer(
    help="Obsidian Command Center projection tools.",
    no_args_is_help=True,
)
app.add_typer(status_app, name="status")
app.add_typer(loop_app, name="loop")
app.add_typer(models_app, name="models")
app.add_typer(obsidian_app, name="obsidian")


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


@obsidian_app.command("run")
def obsidian_run(
    run_id: str = typer.Argument(..., help="Canonical run ID to project."),
    root: Path = typer.Option(
        Path("."),
        "--root",
        help="Repository root that owns the .devflow/pipeline-runs/ directory.",
    ),
    vault: Path = typer.Option(
        Path("."),
        "--vault",
        help="Obsidian vault root where .generated/ views are written.",
    ),
    json_output: bool = typer.Option(False, "--json", help="Emit the result as JSON."),
) -> None:
    """Project one canonical run into the Obsidian Command Center."""

    try:
        if not is_canonical_workflow_run(root, run_id):
            typer.echo(
                f"Run {run_id!r} is not canonical (missing workflow-definition.json).",
                err=True,
            )
            raise typer.Exit(code=1)

        state = extract_projection(root, run_id)
        views = render_all(state)
        result = write_vault_projection(vault, run_id, views)
    except Exception as exc:
        typer.echo(f"Obsidian projection failed: {exc}", err=True)
        raise typer.Exit(code=1) from exc

    if json_output:
        typer.echo(
            json.dumps(
                {
                    "run_id": run_id,
                    "health": state.health.value,
                    "phase": state.current_phase,
                    "progress_percent": state.progress_percent,
                    "files_written": list(result.files_written),
                    "bytes_written": result.bytes_written,
                    "vault_dir": result.vault_dir,
                },
                indent=2,
                sort_keys=True,
            )
        )
    else:
        typer.echo(f"Projected run {run_id} → {result.vault_dir}")
        typer.echo(f"  Health: {state.health.value} · Phase: {state.current_phase}")
        typer.echo(f"  Progress: {state.progress_percent}%")
        typer.echo(f"  Files: {len(result.files_written)}")


@obsidian_app.command("list")
def obsidian_list(
    root: Path = typer.Option(
        Path("."),
        "--root",
        help="Repository root that owns the .devflow/pipeline-runs/ directory.",
    ),
    json_output: bool = typer.Option(False, "--json", help="Emit the result as JSON."),
) -> None:
    """List canonical run IDs available for projection."""

    runs_dir = pipeline_runs_dir(root)
    canonical_runs: list[dict[str, str]] = []

    if runs_dir.is_dir():
        for child in sorted(runs_dir.iterdir()):
            if not child.is_dir():
                continue
            rid = child.name
            if is_canonical_workflow_run(root, rid):
                try:
                    state = extract_projection(root, rid)
                    canonical_runs.append(
                        {
                            "run_id": rid,
                            "health": state.health.value,
                            "phase": state.current_phase,
                            "progress": f"{state.progress_percent}%",
                        }
                    )
                except Exception:
                    canonical_runs.append(
                        {"run_id": rid, "health": "Error", "phase": "unknown", "progress": "?"}
                    )

    if json_output:
        typer.echo(json.dumps({"runs": canonical_runs}, indent=2, sort_keys=True))
    else:
        if not canonical_runs:
            typer.echo("No canonical runs found.")
            return
        typer.echo(f"Found {len(canonical_runs)} canonical run(s):")
        for r in canonical_runs:
            typer.echo(
                f"  {r['run_id']:<24} {r['health']:<20} {r['phase']:<24} {r['progress']}"
            )


def main() -> None:
    """Run the V2-only DevFlow CLI."""
    app()


if __name__ == "__main__":
    main()
