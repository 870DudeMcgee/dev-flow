import json
from pathlib import Path

import typer


architecture_app = typer.Typer(help="Run architecture evidence workflows")


@architecture_app.command("audit")
def architecture_audit_command(
    install_graphify: bool = typer.Option(
        False,
        "--install-graphify",
        help="Install graphifyy in the active Python environment before running the audit.",
    ),
    write_doc: bool = typer.Option(
        False,
        "--write-doc",
        help="Write docs/architecture/control-room-architecture-audit.md.",
    ),
    json_output: bool = typer.Option(False, "--json", help="Print architecture audit result as JSON."),
) -> None:
    """Run Graphify and local hotspot evidence for architecture cleanup decisions."""
    from devflow.legacy.control_room import architecture_audit

    try:
        result = architecture_audit.run_architecture_audit(
            Path.cwd(), install_graphify=install_graphify, write_doc=write_doc
        )
    except architecture_audit.ArchitectureAuditError as exc:
        typer.echo(f"Error: {exc}", err=True)
        raise typer.Exit(code=1) from exc

    if json_output:
        typer.echo(json.dumps(result.model_dump(mode="json"), indent=2, sort_keys=True))
        return
    for line in architecture_audit.render_architecture_audit_lines(result):
        typer.echo(line)
