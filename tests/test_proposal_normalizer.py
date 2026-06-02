from __future__ import annotations

import json
from pathlib import Path

import pytest
import yaml
from typer.testing import CliRunner

from devflow.cli import app
from tests.test_goal_task_creation import setup_temp_git_repo


runner = CliRunner()


def _create_task(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    setup_temp_git_repo(tmp_path)
    monkeypatch.chdir(tmp_path)
    result = runner.invoke(app, ["task", "create", "normal task"])
    assert result.exit_code == 0, result.output


def _write_response(tmp_path: Path, run_id: str, text: str) -> Path:
    run_dir = tmp_path / ".devflow" / "tasks" / "task-0001" / "local-model-runs" / run_id
    run_dir.mkdir(parents=True, exist_ok=True)
    response = run_dir / "response.md"
    response.write_text(text, encoding="utf-8")
    return run_dir


def _proposal_json(tmp_path: Path, run_id: str) -> dict[str, object]:
    path = tmp_path / ".devflow" / "tasks" / "task-0001" / "local-model-runs" / run_id / "proposal.json"
    return json.loads(path.read_text(encoding="utf-8"))


def test_normalize_latest_advisory_response_writes_evidence_without_task_mutation(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _create_task(monkeypatch, tmp_path)
    _write_response(tmp_path, "run-1", "This is useful advisory evidence about the task.")
    task_yaml_before = (tmp_path / ".devflow" / "tasks" / "task-0001" / "task.yaml").read_text(encoding="utf-8")

    result = runner.invoke(app, ["task", "normalize-proposal", "task-0001"])

    assert result.exit_code == 0, result.output
    assert "classification: advisory_only" in result.output
    run_dir = tmp_path / ".devflow" / "tasks" / "task-0001" / "local-model-runs" / "run-1"
    assert (run_dir / "proposal.md").exists()
    assert (run_dir / "proposal.json").exists()
    assert not (run_dir / "proposal.patch").exists()
    assert yaml.safe_load(task_yaml_before)["status"] == "created"
    assert (tmp_path / ".devflow" / "tasks" / "task-0001" / "task.yaml").read_text(encoding="utf-8") == task_yaml_before


def test_normalize_specific_run_id(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _create_task(monkeypatch, tmp_path)
    _write_response(tmp_path, "run-1", "Older advisory evidence.")
    _write_response(tmp_path, "run-2", "Newer advisory evidence.")

    result = runner.invoke(app, ["task", "normalize-proposal", "task-0001", "--run-id", "run-1"])

    assert result.exit_code == 0, result.output
    assert (tmp_path / ".devflow" / "tasks" / "task-0001" / "local-model-runs" / "run-1" / "proposal.json").exists()
    assert not (tmp_path / ".devflow" / "tasks" / "task-0001" / "local-model-runs" / "run-2" / "proposal.json").exists()
    assert _proposal_json(tmp_path, "run-1")["run_id"] == "run-1"


def test_blocker_question_classification_uses_review_next_action(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _create_task(monkeypatch, tmp_path)
    _write_response(tmp_path, "run-1", "## Questions\n\nBlocked. I need clarification before continuing.")

    result = runner.invoke(app, ["task", "normalize-proposal", "task-0001"])

    assert result.exit_code == 0, result.output
    data = _proposal_json(tmp_path, "run-1")
    assert data["classification"] == "blocker_question"
    assert data["next_action"]["command"] == "devflow task show task-0001"
    assert "apply" not in data["next_action"]["command"]
    assert "verify" not in data["next_action"]["command"]
    assert "promote" not in data["next_action"]["command"]


def test_implementation_plan_classification(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _create_task(monkeypatch, tmp_path)
    _write_response(
        tmp_path,
        "run-1",
        "## Proposed Approach\nUse the normalizer.\n\n## Files Likely Affected\nsrc/devflow/control_room/proposal_normalizer.py\n\n## Verification Plan\nRun focused tests.",
    )

    result = runner.invoke(app, ["task", "normalize-proposal", "task-0001"])

    assert result.exit_code == 0, result.output
    assert _proposal_json(tmp_path, "run-1")["classification"] == "implementation_plan"


def test_fenced_diff_patch_candidate_extraction_and_validation(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _create_task(monkeypatch, tmp_path)
    patch = """diff --git a/src/example.py b/src/example.py
--- a/src/example.py
+++ b/src/example.py
@@ -1 +1 @@
-old
+new
"""
    _write_response(tmp_path, "run-1", f"Here is a patch:\n\n```diff\n{patch}```")

    result = runner.invoke(app, ["task", "normalize-proposal", "task-0001"])

    assert result.exit_code == 0, result.output
    run_dir = tmp_path / ".devflow" / "tasks" / "task-0001" / "local-model-runs" / "run-1"
    assert _proposal_json(tmp_path, "run-1")["classification"] == "patch_candidate"
    assert (run_dir / "proposal.patch").read_text(encoding="utf-8") == patch
    validation = json.loads((run_dir / "validation.json").read_text(encoding="utf-8"))
    assert validation["valid"] is True
    assert validation["files_touched"] == ["src/example.py"]


def test_raw_diff_patch_candidate_extraction(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _create_task(monkeypatch, tmp_path)
    patch = """--- a/tests/example.txt
+++ b/tests/example.txt
@@ -1 +1 @@
-old
+new
"""
    _write_response(tmp_path, "run-1", f"Patch follows:\n{patch}")

    result = runner.invoke(app, ["task", "normalize-proposal", "task-0001"])

    assert result.exit_code == 0, result.output
    assert (tmp_path / ".devflow" / "tasks" / "task-0001" / "local-model-runs" / "run-1" / "proposal.patch").read_text(
        encoding="utf-8"
    ) == patch


@pytest.mark.parametrize("unsafe_path", ["../outside.py", ".git/config", ".devflow/workspaces/task-0001/file.txt"])
def test_patch_validation_rejects_dangerous_paths(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, unsafe_path: str
) -> None:
    _create_task(monkeypatch, tmp_path)
    source_file = tmp_path / "source.txt"
    source_file.write_text("unchanged\n", encoding="utf-8")
    patch = f"""diff --git a/{unsafe_path} b/{unsafe_path}
--- a/{unsafe_path}
+++ b/{unsafe_path}
@@ -1 +1 @@
-old
+new
"""
    _write_response(tmp_path, "run-1", f"```diff\n{patch}```")

    result = runner.invoke(app, ["task", "normalize-proposal", "task-0001"])

    assert result.exit_code == 0, result.output
    validation = json.loads(
        (tmp_path / ".devflow" / "tasks" / "task-0001" / "local-model-runs" / "run-1" / "validation.json").read_text(
            encoding="utf-8"
        )
    )
    assert validation["valid"] is False
    assert validation["warnings"]
    assert source_file.read_text(encoding="utf-8") == "unchanged\n"


def test_no_source_or_task_state_mutation(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _create_task(monkeypatch, tmp_path)
    source_file = tmp_path / "src" / "existing.py"
    source_file.parent.mkdir()
    source_file.write_text("old\n", encoding="utf-8")
    _write_response(
        tmp_path,
        "run-1",
        """```diff
--- a/src/existing.py
+++ b/src/existing.py
@@ -1 +1 @@
-old
+new
```""",
    )
    task_yaml_before = (tmp_path / ".devflow" / "tasks" / "task-0001" / "task.yaml").read_text(encoding="utf-8")
    verification_before = (tmp_path / ".devflow" / "tasks" / "task-0001" / "verification.json").read_text(encoding="utf-8")

    result = runner.invoke(app, ["task", "normalize-proposal", "task-0001"])

    assert result.exit_code == 0, result.output
    assert source_file.read_text(encoding="utf-8") == "old\n"
    assert (tmp_path / ".devflow" / "tasks" / "task-0001" / "task.yaml").read_text(encoding="utf-8") == task_yaml_before
    assert (tmp_path / ".devflow" / "tasks" / "task-0001" / "verification.json").read_text(encoding="utf-8") == verification_before


def test_task_show_displays_normalized_proposal_evidence(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _create_task(monkeypatch, tmp_path)
    _write_response(tmp_path, "run-1", "This is useful advisory evidence about the task.")
    assert runner.invoke(app, ["task", "normalize-proposal", "task-0001"]).exit_code == 0

    result = runner.invoke(app, ["task", "show", "task-0001"])

    assert result.exit_code == 0, result.output
    assert "Normalized Proposals:" in result.output
    assert "classification: advisory_only" in result.output


def test_missing_local_model_run_fails_clearly(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _create_task(monkeypatch, tmp_path)

    result = runner.invoke(app, ["task", "normalize-proposal", "task-0001"])

    assert result.exit_code != 0
    assert "No local model runs found" in result.output


def test_missing_response_md_fails_clearly(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _create_task(monkeypatch, tmp_path)
    (tmp_path / ".devflow" / "tasks" / "task-0001" / "local-model-runs" / "run-1").mkdir(parents=True)

    result = runner.invoke(app, ["task", "normalize-proposal", "task-0001", "--run-id", "run-1"])

    assert result.exit_code != 0
    assert "response.md not found" in result.output


def test_generated_proposal_artifacts_excluded_from_future_packets(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _create_task(monkeypatch, tmp_path)
    _write_response(tmp_path, "run-1", "This is useful advisory evidence about the task.")
    assert runner.invoke(app, ["task", "normalize-proposal", "task-0001"]).exit_code == 0

    result = runner.invoke(app, ["task", "packet", "task-0001"])

    assert result.exit_code == 0, result.output
    assert "proposal.json" not in result.output
    assert "proposal.patch" not in result.output
    assert "local-model-runs" not in result.output


def test_normalize_has_no_live_model_or_heavy_ml_imports(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _create_task(monkeypatch, tmp_path)
    _write_response(tmp_path, "run-1", "This is useful advisory evidence about the task.")

    result = runner.invoke(app, ["task", "normalize-proposal", "task-0001"])

    assert result.exit_code == 0, result.output
    source = Path(__file__).parents[1] / "src" / "devflow" / "control_room" / "proposal_normalizer.py"
    text = source.read_text(encoding="utf-8")
    assert "urllib" not in text
    for forbidden in ["transformers", "torch", "llama_cpp", "openai"]:
        assert forbidden not in text


def test_normalize_is_idempotent(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _create_task(monkeypatch, tmp_path)
    _write_response(tmp_path, "run-1", "This is useful advisory evidence about the task.")

    first = runner.invoke(app, ["task", "normalize-proposal", "task-0001"])
    proposal_first = (tmp_path / ".devflow" / "tasks" / "task-0001" / "local-model-runs" / "run-1" / "proposal.md").read_text(
        encoding="utf-8"
    )
    second = runner.invoke(app, ["task", "normalize-proposal", "task-0001"])
    proposal_second = (tmp_path / ".devflow" / "tasks" / "task-0001" / "local-model-runs" / "run-1" / "proposal.md").read_text(
        encoding="utf-8"
    )

    assert first.exit_code == 0, first.output
    assert second.exit_code == 0, second.output
    assert proposal_second == proposal_first
