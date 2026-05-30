from __future__ import annotations

import json
import os
import shutil
import subprocess
import tempfile
from pathlib import Path

from typer.testing import CliRunner

from devflow.cli import app
from devflow.control_room.seed import validate_seed_contract


runner = CliRunner()

REQUIRED_SEED_PATHS = [
    ".devflow/project/project.yaml",
    ".devflow/project/vision.md",
    ".devflow/project/current-state.md",
    ".devflow/project/architecture.md",
    ".devflow/project/decisions.jsonl",
    ".devflow/project/open-questions.jsonl",
    ".devflow/project/glossary.md",
    ".devflow/goals/bootstrap-devflow-filesystem/goal.yaml",
    ".devflow/goals/bootstrap-devflow-filesystem/status.md",
    ".devflow/goals/bootstrap-devflow-filesystem/success.json",
    ".devflow/goals/bootstrap-devflow-filesystem/events.jsonl",
    ".devflow/goals/bootstrap-devflow-filesystem/questions.jsonl",
    ".devflow/goals/bootstrap-devflow-filesystem/decisions.jsonl",
    ".devflow/goals/bootstrap-devflow-filesystem/context/active.md",
    ".devflow/goals/bootstrap-devflow-filesystem/context/relevant-files.md",
    ".devflow/goals/bootstrap-devflow-filesystem/context/constraints.md",
    ".devflow/goals/bootstrap-devflow-filesystem/context/deferred-ideas.md",
    ".devflow/goals/bootstrap-devflow-filesystem/context/rejected-ideas.md",
    ".devflow/goals/bootstrap-devflow-filesystem/tasks/README.md",
    ".devflow/context/active/README.md",
    ".devflow/context/reference/README.md",
    ".devflow/context/archived/README.md",
    ".devflow/context/deprecated/README.md",
    ".devflow/context/rejected/README.md",
    ".devflow/layers/product/vision.md",
    ".devflow/layers/product/user-problems.md",
    ".devflow/layers/product/success-metrics.md",
    ".devflow/layers/architecture/system-map.md",
    ".devflow/layers/architecture/boundaries.md",
    ".devflow/layers/architecture/state-model.md",
    ".devflow/layers/architecture/contracts.md",
    ".devflow/layers/architecture/decisions.jsonl",
    ".devflow/layers/implementation/current-slice.md",
    ".devflow/layers/implementation/file-map.md",
    ".devflow/layers/implementation/known-gaps.md",
    ".devflow/layers/implementation/active-constraints.md",
    ".devflow/layers/verification/verification-strategy.md",
    ".devflow/layers/verification/commands.md",
    ".devflow/layers/verification/known-failures.md",
    ".devflow/layers/operations/workflow.md",
    ".devflow/layers/operations/agent-coordination.md",
    ".devflow/layers/operations/recovery.md",
    ".devflow/layers/operations/promotion.md",
    ".devflow/workers/registry.yaml",
    ".devflow/workers/profiles/README.md",
    ".devflow/models/registry.yaml",
    ".devflow/models/scoreboard.jsonl",
    ".devflow/locks/README.md",
    ".devflow/reports/README.md",
    ".devflow/reports/daily/README.md",
    ".devflow/reports/task-summaries/README.md",
    ".devflow/reports/model-scorecards/README.md",
    ".devflow/archive/README.md",
    ".devflow/archive/superseded/README.md",
    ".devflow/archive/experiments/README.md",
    ".devflow/archive/old-plans/README.md",
    ".devflow/tasks/README.md",
]

YAML_SEED_PATHS = [
    ".devflow/project/project.yaml",
    ".devflow/goals/bootstrap-devflow-filesystem/goal.yaml",
    ".devflow/workers/registry.yaml",
    ".devflow/models/registry.yaml",
]

JSON_SEED_PATHS = [
    ".devflow/goals/bootstrap-devflow-filesystem/success.json",
]

JSONL_SEED_PATHS = [
    ".devflow/project/decisions.jsonl",
    ".devflow/project/open-questions.jsonl",
    ".devflow/goals/bootstrap-devflow-filesystem/events.jsonl",
    ".devflow/goals/bootstrap-devflow-filesystem/questions.jsonl",
    ".devflow/goals/bootstrap-devflow-filesystem/decisions.jsonl",
    ".devflow/layers/architecture/decisions.jsonl",
    ".devflow/models/scoreboard.jsonl",
]


def test_checked_in_devflow_seed_contract_is_machine_readable() -> None:
    root = Path(__file__).resolve().parents[1]

    _assert_seed_paths(root)
    _assert_machine_readable_files(root)
    _assert_reports_are_non_authoritative(root)
    _assert_registries_make_no_availability_claims(root)
    assert validate_seed_contract(root) == []


def test_devflow_init_creates_and_repairs_seed_without_overwriting_user_files() -> None:
    old_cwd = Path.cwd()
    with tempfile.TemporaryDirectory() as tmp:
        try:
            os.chdir(tmp)
            result = runner.invoke(app, ["init"])
            assert result.exit_code == 0, result.output
            _assert_seed_paths(Path.cwd())
            _assert_machine_readable_files(Path.cwd())
            _assert_reports_are_non_authoritative(Path.cwd())
            _assert_registries_make_no_availability_claims(Path.cwd())

            project_yaml = Path(".devflow/project/project.yaml")
            user_edited_content = project_yaml.read_text(encoding="utf-8") + "user_note: keep this edit\n"
            project_yaml.write_text(user_edited_content, encoding="utf-8")
            Path(".devflow/models/scoreboard.jsonl").unlink()

            second = runner.invoke(app, ["init"])
            assert second.exit_code == 0, second.output
            assert project_yaml.read_text(encoding="utf-8") == user_edited_content
            assert Path(".devflow/models/scoreboard.jsonl").exists()
        finally:
            os.chdir(old_cwd)


def test_seed_schema_validation_reports_contract_drift() -> None:
    old_cwd = Path.cwd()
    with tempfile.TemporaryDirectory() as tmp:
        try:
            os.chdir(tmp)
            result = runner.invoke(app, ["init"])
            assert result.exit_code == 0, result.output

            Path(".devflow/models/registry.yaml").write_text(
                "version: 1\n"
                "authority: claimed available\n"
                "models:\n"
                "  - model_id: fake-frontier\n"
                "    enabled: true\n",
                encoding="utf-8",
            )
            Path(".devflow/goals/bootstrap-devflow-filesystem/success.json").write_text(
                '{"goal_id": "wrong", "criteria": []}\n',
                encoding="utf-8",
            )

            errors = validate_seed_contract(Path.cwd())
            assert ".devflow/models/registry.yaml: models must be an empty placeholder list" in errors
            assert ".devflow/goals/bootstrap-devflow-filesystem/success.json: goal_id must be bootstrap-devflow-filesystem" in errors
            assert ".devflow/goals/bootstrap-devflow-filesystem/success.json: criteria must be a non-empty list" in errors
        finally:
            os.chdir(old_cwd)


def test_devflow_doctor_reports_seed_schema_drift() -> None:
    old_cwd = Path.cwd()
    with tempfile.TemporaryDirectory() as tmp:
        try:
            os.chdir(tmp)
            result = runner.invoke(app, ["init"])
            assert result.exit_code == 0, result.output
            Path(".devflow/workers/registry.yaml").write_text(
                "version: 1\n"
                "authority: claimed available\n"
                "workers:\n"
                "  - worker_id: fake-worker\n"
                "    enabled: true\n",
                encoding="utf-8",
            )

            doctor = runner.invoke(app, ["doctor"])
            assert doctor.exit_code == 1
            assert "missing: seed contract" in doctor.output
            assert ".devflow/workers/registry.yaml: workers must be an empty placeholder list" in doctor.output
        finally:
            os.chdir(old_cwd)


def _assert_seed_paths(root: Path) -> None:
    missing = [path for path in REQUIRED_SEED_PATHS if not (root / path).exists()]
    assert missing == []


def _assert_machine_readable_files(root: Path) -> None:
    ruby = shutil.which("ruby")
    assert ruby is not None, "Ruby/Psych is required to validate seeded YAML without adding PyYAML."
    yaml_result = subprocess.run(
        [ruby, "-ryaml", "-e", "ARGV.each { |path| YAML.load_file(path) }", *YAML_SEED_PATHS],
        cwd=root,
        text=True,
        capture_output=True,
        check=False,
    )
    assert yaml_result.returncode == 0, yaml_result.stderr

    for path in JSON_SEED_PATHS:
        json.loads((root / path).read_text(encoding="utf-8"))

    for path in JSONL_SEED_PATHS:
        for line in (root / path).read_text(encoding="utf-8").splitlines():
            if line.strip():
                json.loads(line)


def _assert_reports_are_non_authoritative(root: Path) -> None:
    content = (root / ".devflow/reports/README.md").read_text(encoding="utf-8").lower()
    assert "derived" in content
    assert "never authoritative" in content


def _assert_registries_make_no_availability_claims(root: Path) -> None:
    workers = (root / ".devflow/workers/registry.yaml").read_text(encoding="utf-8").lower()
    models = (root / ".devflow/models/registry.yaml").read_text(encoding="utf-8").lower()
    assert "workers: []" in workers
    assert "no worker availability is claimed" in workers
    assert "models: []" in models
    assert "no model availability" in models
