"""End-to-end tests for the deterministic V2 loop harness."""
from __future__ import annotations

import json
from pathlib import Path

from typer.testing import CliRunner

from devflow.cli import app
from devflow.control_room.pipeline_run import pipeline_runs_dir
from devflow.loop.e2e_harness import EXPECTED_STAGE_CHAIN, run_e2e_loop_harness
from devflow.loop.models import LoopStage


REQUIRED_EVIDENCE_FILES = {
    "loop-state.json",
    "orient-result.json",
    "fixture-spec.md",
    "fixture-plan.md",
    "planning-judge.json",
    "builder-judge-link.json",
    "verification-receipt-fixture-verification.json",
    "human-decision-fixture-human-acceptance.json",
}


def _create_fixture_target(root: Path, target_file: str = "src/main.py") -> str:
    target = root / target_file
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text("def main() -> str:\n    return 'ok'\n", encoding="utf-8")
    return target_file


def test_run_e2e_loop_harness_reaches_complete(tmp_path: Path) -> None:
    target_file = _create_fixture_target(tmp_path)

    report = run_e2e_loop_harness(tmp_path, target_file=target_file)

    assert report.final_stage == LoopStage.complete
    assert report.expected_stage_chain == EXPECTED_STAGE_CHAIN
    assert report.observed_stage_chain == EXPECTED_STAGE_CHAIN
    assert REQUIRED_EVIDENCE_FILES <= set(report.evidence_files)

    run_dir = pipeline_runs_dir(tmp_path) / report.run_id
    assert run_dir.is_dir()
    for file_name in REQUIRED_EVIDENCE_FILES:
        assert (run_dir / file_name).exists(), file_name


def test_run_e2e_loop_harness_rejects_missing_target(tmp_path: Path) -> None:
    missing_target = "src/missing.py"

    try:
        run_e2e_loop_harness(tmp_path, target_file=missing_target)
    except FileNotFoundError as exc:
        assert missing_target in str(exc)
    else:
        raise AssertionError("Expected missing fixture target to raise FileNotFoundError")

    assert not pipeline_runs_dir(tmp_path).exists()


def test_loop_spine_fixture_cli_json(tmp_path: Path, monkeypatch) -> None:
    target_file = _create_fixture_target(tmp_path)
    monkeypatch.chdir(tmp_path)
    runner = CliRunner()

    result = runner.invoke(app, ["loop", "spine-fixture", "--target-file", target_file, "--json"])

    assert result.exit_code == 0, result.output
    data = json.loads(result.output)
    assert data["final_stage"] == "complete"
    assert data["target_file"] == target_file
    assert data["observed_stage_chain"] == [stage.value for stage in EXPECTED_STAGE_CHAIN]
    assert REQUIRED_EVIDENCE_FILES <= set(data["evidence_files"])


def test_loop_spine_fixture_cli_missing_target_fails(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    runner = CliRunner()

    result = runner.invoke(app, ["loop", "spine-fixture", "--target-file", "src/missing.py", "--json"])

    assert result.exit_code == 1
    assert "Fixture target file does not exist" in result.output
