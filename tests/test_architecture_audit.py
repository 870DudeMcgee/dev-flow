from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest
from typer.testing import CliRunner

from devflow.cli import app
from devflow.control_room.architecture_audit import (
    GRAPHIFY_REQUIREMENT,
    ArchitectureAuditError,
    ArchitectureAuditResult,
    DiagnosticStatus,
    GraphMetrics,
    GraphifyStatus,
    HotspotRow,
    parse_graph_report_metrics,
    run_architecture_audit,
    scan_architecture_hotspots,
)


class RecordingRunner:
    def __init__(self, *, fail_install: bool = False) -> None:
        self.commands: list[list[str]] = []
        self.fail_install = fail_install

    def __call__(self, command: list[str], *, cwd: Path) -> subprocess.CompletedProcess[str]:
        self.commands.append(command)
        if command[:3] == [sys.executable, "-m", "pip"]:
            if self.fail_install:
                return subprocess.CompletedProcess(command, 1, "", "install failed")
            return subprocess.CompletedProcess(command, 0, "installed", "")
        if command[1:] == ["update", "."]:
            report = cwd / "graphify-out" / "GRAPH_REPORT.md"
            report.parent.mkdir(parents=True, exist_ok=True)
            report.write_text(_sample_graph_report(), encoding="utf-8")
            (report.parent / "graph.json").write_text("{}", encoding="utf-8")
            return subprocess.CompletedProcess(command, 0, "updated", "")
        if command[1:] == ["export", "callflow-html"]:
            artifact = cwd / "graphify-out" / "dev-flow-callflow.html"
            artifact.parent.mkdir(parents=True, exist_ok=True)
            artifact.write_text("<html></html>", encoding="utf-8")
            return subprocess.CompletedProcess(command, 0, "exported", "")
        if command[1:] == ["tree", "--label", "Dev-Flow"]:
            artifact = cwd / "graphify-out" / "GRAPH_TREE.html"
            artifact.parent.mkdir(parents=True, exist_ok=True)
            artifact.write_text("<html></html>", encoding="utf-8")
            return subprocess.CompletedProcess(command, 0, "tree", "")
        if command[1:] == ["diagnose", "multigraph", "--json"]:
            return subprocess.CompletedProcess(command, 0, '{"status":"ok","issue_count":0}', "")
        return subprocess.CompletedProcess(command, 0, "", "")


def _sample_graph_report() -> str:
    return """\
# Graph Report

| Metric | Value |
|---|---:|
| Files | 606 |
| Approximate words | 616,383 |
| Nodes | 8,356 |
| Edges | 19,765 |
| Communities | 507 |
| Shown communities | 456 |
| Thin omitted communities | 51 |
| Extracted edges | 81% |
| Inferred edges | 19% |
| Ambiguous edges | 0% |
"""


def test_missing_graphify_without_install_exits_with_guidance_and_no_commands(tmp_path: Path) -> None:
    runner = RecordingRunner()

    with pytest.raises(ArchitectureAuditError) as exc_info:
        run_architecture_audit(
            tmp_path,
            graphify_finder=lambda: None,
            command_runner=runner,
        )

    message = str(exc_info.value)
    assert "Graphify is not installed" in message
    assert "--install-graphify" in message
    assert GRAPHIFY_REQUIREMENT in message
    assert runner.commands == []


def test_install_graphify_uses_active_python_then_runs_audit(tmp_path: Path) -> None:
    runner = RecordingRunner()
    graphify_path = tmp_path / ".venv" / "bin" / "graphify"

    result = run_architecture_audit(
        tmp_path,
        install_graphify=True,
        graphify_finder=lambda: graphify_path,
        command_runner=runner,
    )

    assert runner.commands[0] == [sys.executable, "-m", "pip", "install", GRAPHIFY_REQUIREMENT]
    assert runner.commands[1:] == [
        [graphify_path.as_posix(), "update", "."],
        [graphify_path.as_posix(), "export", "callflow-html"],
        [graphify_path.as_posix(), "tree", "--label", "Dev-Flow"],
        [graphify_path.as_posix(), "diagnose", "multigraph", "--json"],
    ]
    assert result.graphify.install_status == "installed"
    assert result.graph_metrics.nodes == 8356
    assert result.diagnostic.status == "ok"


def test_install_graphify_flag_installs_even_when_graphify_is_already_available(tmp_path: Path) -> None:
    runner = RecordingRunner()
    graphify_path = tmp_path / ".venv" / "bin" / "graphify"

    result = run_architecture_audit(
        tmp_path,
        install_graphify=True,
        graphify_finder=lambda: graphify_path,
        command_runner=runner,
    )

    assert runner.commands[0] == [sys.executable, "-m", "pip", "install", GRAPHIFY_REQUIREMENT]
    assert runner.commands[1] == [graphify_path.as_posix(), "update", "."]
    assert result.graphify.install_status == "installed"


def test_install_failure_returns_useful_error_and_does_not_run_audit(tmp_path: Path) -> None:
    runner = RecordingRunner(fail_install=True)

    with pytest.raises(ArchitectureAuditError) as exc_info:
        run_architecture_audit(
            tmp_path,
            install_graphify=True,
            graphify_finder=lambda: None,
            command_runner=runner,
        )

    assert "Failed to install Graphify" in str(exc_info.value)
    assert "install failed" in str(exc_info.value)
    assert runner.commands == [[sys.executable, "-m", "pip", "install", GRAPHIFY_REQUIREMENT]]


def test_parse_graph_report_metrics_from_markdown_table() -> None:
    metrics = parse_graph_report_metrics(_sample_graph_report())

    assert metrics.files == 606
    assert metrics.approximate_words == 616383
    assert metrics.nodes == 8356
    assert metrics.edges == 19765
    assert metrics.communities == 507
    assert metrics.shown_communities == 456
    assert metrics.thin_omitted_communities == 51
    assert metrics.extracted_edge_percent == 81
    assert metrics.inferred_edge_percent == 19
    assert metrics.ambiguous_edge_percent == 0


def test_parse_graph_report_metrics_from_graphify_summary_bullets() -> None:
    metrics = parse_graph_report_metrics(
        """\
# Graph Report - Dev-Flow  (2026-06-27)

## Corpus Check
- 662 files \u00b7 ~666,512 words

## Summary
- 9061 nodes \u00b7 21711 edges \u00b7 549 communities (491 shown, 58 thin omitted)
- Extraction: 81% EXTRACTED \u00b7 19% INFERRED \u00b7 0% AMBIGUOUS \u00b7 INFERRED: 4076 edges (avg confidence: 0.73)
"""
    )

    assert metrics.files == 662
    assert metrics.approximate_words == 666512
    assert metrics.nodes == 9061
    assert metrics.edges == 21711
    assert metrics.communities == 549
    assert metrics.shown_communities == 491
    assert metrics.thin_omitted_communities == 58
    assert metrics.extracted_edge_percent == 81
    assert metrics.inferred_edge_percent == 19
    assert metrics.ambiguous_edge_percent == 0


def test_hotspot_scan_ranks_files_and_excludes_generated_legacy_paths(tmp_path: Path) -> None:
    target = tmp_path / "src" / "devflow" / "control_room" / "operating_layer_server.py"
    target.parent.mkdir(parents=True)
    target.write_text(
        "\n".join(
            [
                "from devflow.control_room.service import create_task",
                "from .task_packet import build_agent_packet",
                "class Surface:",
                "    pass",
                "def a():",
                "    pass",
                "def b():",
                "    pass",
            ]
            + ["value = 1"] * 80
        )
        + "\n",
        encoding="utf-8",
    )
    small = tmp_path / "src" / "devflow" / "control_room" / "small.py"
    small.write_text("def only():\n    pass\n", encoding="utf-8")
    legacy = tmp_path / "src" / "devflow" / "_legacy" / "giant.py"
    legacy.parent.mkdir(parents=True)
    legacy.write_text(("x = 1\n" * 500), encoding="utf-8")
    generated = tmp_path / "graphify-out" / "generated.py"
    generated.parent.mkdir()
    generated.write_text(("x = 1\n" * 500), encoding="utf-8")
    cache = tmp_path / "src" / "__pycache__" / "cached.py"
    cache.parent.mkdir()
    cache.write_text("x = 1\n", encoding="utf-8")

    hotspots = scan_architecture_hotspots(tmp_path, limit=5)

    assert hotspots[0].path == "src/devflow/control_room/operating_layer_server.py"
    assert hotspots[0].lines == 88
    assert hotspots[0].definition_count == 3
    assert hotspots[0].local_import_count == 2
    assert hotspots[0].known_boundary_target is True
    paths = {row.path for row in hotspots}
    assert "src/devflow/_legacy/giant.py" not in paths
    assert "graphify-out/generated.py" not in paths
    assert "src/__pycache__/cached.py" not in paths


def test_write_doc_renders_concise_checkpoint(tmp_path: Path) -> None:
    runner = RecordingRunner()

    result = run_architecture_audit(
        tmp_path,
        write_doc=True,
        graphify_finder=lambda: tmp_path / ".venv" / "bin" / "graphify",
        command_runner=runner,
    )

    checkpoint = tmp_path / "docs" / "architecture" / "control-room-architecture-audit.md"
    text = checkpoint.read_text(encoding="utf-8")
    assert result.checkpoint_path == checkpoint
    assert "# Control-Room Architecture Audit" in text
    assert "Graphify is evidence, not authority." in text
    assert "Generated Graphify artifacts are local by default" in text
    assert "Recommended Cleanup Targets" in text
    assert "graphify-out/GRAPH_REPORT.md" in text


def test_cli_architecture_audit_json_returns_stable_shape(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.chdir(tmp_path)

    def fake_run(*args: object, **kwargs: object) -> ArchitectureAuditResult:
        return ArchitectureAuditResult(
            graphify=GraphifyStatus(available=True, path="/tmp/graphify", install_status="not_requested"),
            graph_metrics=GraphMetrics(nodes=1, edges=2, communities=3),
            diagnostic=DiagnosticStatus(status="ok", issue_count=0, raw={"status": "ok"}),
            hotspots=[
                HotspotRow(
                    path="src/devflow/cli.py",
                    lines=100,
                    definition_count=10,
                    local_import_count=5,
                    score=450,
                    known_boundary_target=True,
                )
            ],
            generated_artifact_paths=["graphify-out/GRAPH_REPORT.md"],
            recommended_cleanup_targets=["src/devflow/cli.py"],
        )

    monkeypatch.setattr("devflow.control_room.architecture_audit.run_architecture_audit", fake_run)

    result = CliRunner().invoke(app, ["architecture", "audit", "--json"])

    assert result.exit_code == 0
    payload = json.loads(result.output)
    assert payload["graphify"]["available"] is True
    assert payload["graph_metrics"]["nodes"] == 1
    assert payload["diagnostic"]["status"] == "ok"
    assert payload["hotspots"][0]["path"] == "src/devflow/cli.py"
    assert payload["recommended_cleanup_targets"] == ["src/devflow/cli.py"]


def test_cli_architecture_audit_missing_graphify_prints_install_hint(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(tmp_path)

    def fake_run(*args: object, **kwargs: object) -> ArchitectureAuditResult:
        raise ArchitectureAuditError(
            "Graphify is not installed. Run 'devflow architecture audit --install-graphify' "
            f"to install {GRAPHIFY_REQUIREMENT}."
        )

    monkeypatch.setattr("devflow.control_room.architecture_audit.run_architecture_audit", fake_run)

    result = CliRunner().invoke(app, ["architecture", "audit"])

    assert result.exit_code == 1
    assert "Graphify is not installed" in result.output
    assert "--install-graphify" in result.output
