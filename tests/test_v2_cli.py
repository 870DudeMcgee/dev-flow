"""Regression coverage for the V2-only command surface."""
from __future__ import annotations

import importlib
import json
import sys
from pathlib import Path

from typer.testing import CliRunner


def _create_fixture_target(root: Path, target_file: str = "src/main.py") -> str:
    target = root / target_file
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text("def main() -> str:\n    return 'ok'\n", encoding="utf-8")
    return target_file


def test_cli_import_does_not_load_legacy_namespace() -> None:
    retired_namespace = "devflow." + "legacy"
    sys.modules.pop("devflow.cli", None)
    for module_name in list(sys.modules):
        if module_name == retired_namespace or module_name.startswith(f"{retired_namespace}."):
            sys.modules.pop(module_name)

    importlib.import_module("devflow.cli")

    assert not any(
        module_name == retired_namespace or module_name.startswith(f"{retired_namespace}.")
        for module_name in sys.modules
    )


def test_v2_cli_exposes_status_and_deterministic_loop_fixture(tmp_path: Path, monkeypatch) -> None:
    from devflow.cli import app

    target_file = _create_fixture_target(tmp_path)
    monkeypatch.chdir(tmp_path)
    runner = CliRunner()

    help_result = runner.invoke(app, ["--help"])
    result = runner.invoke(app, ["loop", "spine-fixture", "--target-file", target_file, "--json"])

    assert help_result.exit_code == 0, help_result.output
    assert "status" in help_result.output
    assert "operating-layer" not in help_result.output
    assert result.exit_code == 0, result.output
    assert json.loads(result.output)["final_stage"] == "complete"
