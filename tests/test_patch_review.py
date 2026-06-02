from __future__ import annotations

import json
from pathlib import Path

import pytest
from typer.testing import CliRunner

from devflow.cli import app
from tests.test_goal_task_creation import setup_temp_git_repo


runner = CliRunner()


def _create_task(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    setup_temp_git_repo(tmp_path)
    monkeypatch.chdir(tmp_path)
    result = runner.invoke(app, ["task", "create", "patch review task"])
    assert result.exit_code == 0, result.output


def _create_goal_task(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    setup_temp_git_repo(tmp_path)
    monkeypatch.chdir(tmp_path)
    (tmp_path / "goal.md").write_text("## Goal Brief\nPatch review.", encoding="utf-8")
    init_result = runner.invoke(app, ["goal", "init", "--from", "goal.md"])
    assert init_result.exit_code == 0, init_result.output
    create_result = runner.invoke(app, ["goal", "create-task", "G-0001", "TS-0001"])
    assert create_result.exit_code == 0, create_result.output


def _run_dir(tmp_path: Path, run_id: str = "run-1") -> Path:
    path = tmp_path / ".devflow" / "tasks" / "task-0001" / "local-model-runs" / run_id
    path.mkdir(parents=True, exist_ok=True)
    return path


def _write_proposal(
    tmp_path: Path,
    *,
    run_id: str = "run-1",
    has_patch_candidate: bool = True,
    classification: str = "patch_candidate",
    patch: str | None = None,
) -> Path:
    run_path = _run_dir(tmp_path, run_id)
    (run_path / "proposal.md").write_text("proposal marker", encoding="utf-8")
    (run_path / "proposal.json").write_text(
        json.dumps(
            {
                "schema_version": 1,
                "task_id": "task-0001",
                "run_id": run_id,
                "classification": classification,
                "has_patch_candidate": has_patch_candidate,
            },
            indent=2,
            sort_keys=True,
        ),
        encoding="utf-8",
    )
    if patch is not None:
        (run_path / "proposal.patch").write_text(patch, encoding="utf-8")
    return run_path


def _patch(path: str) -> str:
    return f"""diff --git a/{path} b/{path}
--- a/{path}
+++ b/{path}
@@ -1 +1 @@
-old
+new
"""


def _review_json(tmp_path: Path, run_id: str = "run-1") -> dict[str, object]:
    path = tmp_path / ".devflow" / "tasks" / "task-0001" / "local-model-runs" / run_id / "patch-review.json"
    return json.loads(path.read_text(encoding="utf-8"))


def test_no_patch_candidate_writes_review_without_source_mutation(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _create_task(tmp_path, monkeypatch)
    _write_proposal(tmp_path, has_patch_candidate=False, classification="advisory_only")
    task_yaml_before = (tmp_path / ".devflow" / "tasks" / "task-0001" / "task.yaml").read_text(encoding="utf-8")

    result = runner.invoke(app, ["task", "review-patch", "task-0001", "--run-id", "run-1"])

    assert result.exit_code == 0, result.output
    data = _review_json(tmp_path)
    assert data["review_status"] == "no_patch_candidate"
    assert data["risk"] == "low"
    assert (tmp_path / ".devflow" / "tasks" / "task-0001" / "task.yaml").read_text(encoding="utf-8") == task_yaml_before


def test_missing_local_model_run_fails_clearly(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _create_task(tmp_path, monkeypatch)

    result = runner.invoke(app, ["task", "review-patch", "task-0001"])

    assert result.exit_code != 0
    assert "No local model runs found" in result.output


def test_missing_proposal_json_fails_clearly(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _create_task(tmp_path, monkeypatch)
    _run_dir(tmp_path)

    result = runner.invoke(app, ["task", "review-patch", "task-0001", "--run-id", "run-1"])

    assert result.exit_code != 0
    assert "proposal.json not found" in result.output


def test_invalid_patch_is_not_applied(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _create_task(tmp_path, monkeypatch)
    _write_proposal(tmp_path, patch="this is not a diff")

    result = runner.invoke(app, ["task", "review-patch", "task-0001", "--run-id", "run-1"])

    assert result.exit_code == 0, result.output
    data = _review_json(tmp_path)
    assert data["review_status"] == "invalid_patch"
    assert data["risk"] == "medium"
    assert not (tmp_path / "this_should_not_exist.py").exists()


def test_low_risk_docs_patch(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _create_task(tmp_path, monkeypatch)
    _write_proposal(tmp_path, patch=_patch("docs/manual-test.md"))

    result = runner.invoke(app, ["task", "review-patch", "task-0001", "--run-id", "run-1"])

    assert result.exit_code == 0, result.output
    data = _review_json(tmp_path)
    assert data["review_status"] == "low_risk_candidate"
    assert data["risk"] == "low"
    assert data["files_touched"] == ["docs/manual-test.md"]
    assert data["hunk_count"] == 1


def test_normal_source_patch_requires_review(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _create_task(tmp_path, monkeypatch)
    _write_proposal(tmp_path, patch=_patch("src/devflow/control_room/example.py"))

    result = runner.invoke(app, ["task", "review-patch", "task-0001", "--run-id", "run-1"])

    assert result.exit_code == 0, result.output
    data = _review_json(tmp_path)
    assert data["review_status"] == "review_required"
    assert data["risk"] == "medium"


def test_dangerous_absolute_path(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _create_task(tmp_path, monkeypatch)
    patch = """--- /tmp/evil.py
+++ /tmp/evil.py
@@ -1 +1 @@
-old
+new
"""
    _write_proposal(tmp_path, patch=patch)

    result = runner.invoke(app, ["task", "review-patch", "task-0001", "--run-id", "run-1"])

    assert result.exit_code == 0, result.output
    data = _review_json(tmp_path)
    assert data["review_status"] == "dangerous_patch"
    assert data["risk"] == "critical"
    assert data["dangerous_paths"] == ["/tmp/evil.py"]


def test_dangerous_path_traversal(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _create_task(tmp_path, monkeypatch)
    _write_proposal(tmp_path, patch=_patch("../evil.py"))

    result = runner.invoke(app, ["task", "review-patch", "task-0001", "--run-id", "run-1"])

    assert result.exit_code == 0, result.output
    assert _review_json(tmp_path)["review_status"] == "dangerous_patch"


def test_dangerous_generated_path(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _create_task(tmp_path, monkeypatch)
    _write_proposal(tmp_path, patch=_patch(".devflow/tasks/task-0001/packet.json"))

    result = runner.invoke(app, ["task", "review-patch", "task-0001", "--run-id", "run-1"])

    assert result.exit_code == 0, result.output
    data = _review_json(tmp_path)
    assert data["review_status"] == "dangerous_patch"
    assert data["risk"] == "critical"


def test_high_risk_file_raises_risk_without_rejecting(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _create_task(tmp_path, monkeypatch)
    _write_proposal(tmp_path, patch=_patch("src/devflow/cli.py"))

    result = runner.invoke(app, ["task", "review-patch", "task-0001", "--run-id", "run-1"])

    assert result.exit_code == 0, result.output
    data = _review_json(tmp_path)
    assert data["review_status"] == "review_required"
    assert data["risk"] == "high"
    assert data["high_risk_files"] == ["src/devflow/cli.py"]


def test_slice_alignment_warns_for_undeclared_files(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _create_goal_task(tmp_path, monkeypatch)
    _write_proposal(tmp_path, patch=_patch("docs/manual-test.md"))

    result = runner.invoke(app, ["task", "review-patch", "task-0001", "--run-id", "run-1"])

    assert result.exit_code == 0, result.output
    data = _review_json(tmp_path)
    assert data["slice_alignment"]["status"] == "checked"
    assert "docs/manual-test.md" in data["slice_alignment"]["undeclared_touched_files"]
    assert "Patch touches files not declared in task slice metadata." in data["warnings"]


def test_task_show_displays_patch_review(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _create_task(tmp_path, monkeypatch)
    _write_proposal(tmp_path, patch=_patch("docs/manual-test.md"))
    result = runner.invoke(app, ["task", "review-patch", "task-0001", "--run-id", "run-1"])
    assert result.exit_code == 0, result.output

    show = runner.invoke(app, ["task", "show", "task-0001"])

    assert show.exit_code == 0, show.output
    assert "Patch Reviews:" in show.output
    assert "status: low_risk_candidate" in show.output
    assert "risk: low" in show.output


def test_generated_review_artifacts_excluded_from_future_packet(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _create_task(tmp_path, monkeypatch)
    _write_proposal(tmp_path, patch=_patch("docs/manual-test.md"))
    run_path = _run_dir(tmp_path)
    (run_path / "proposal.patch").write_text(_patch("docs/manual-test.md") + "\nUNIQUE_PATCH_TEXT", encoding="utf-8")
    review = runner.invoke(app, ["task", "review-patch", "task-0001", "--run-id", "run-1"])
    assert review.exit_code == 0, review.output

    packet = runner.invoke(app, ["task", "packet", "task-0001"])

    assert packet.exit_code == 0, packet.output
    assert "UNIQUE_PATCH_TEXT" not in packet.output
    assert "proposal marker" not in packet.output
    assert "Patch Candidate Review" not in packet.output


def test_idempotent_review_is_stable(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _create_task(tmp_path, monkeypatch)
    _write_proposal(tmp_path, patch=_patch("docs/manual-test.md"))
    first = runner.invoke(app, ["task", "review-patch", "task-0001", "--run-id", "run-1"])
    assert first.exit_code == 0, first.output
    first_json = _review_json(tmp_path)

    second = runner.invoke(app, ["task", "review-patch", "task-0001", "--run-id", "run-1"])

    assert second.exit_code == 0, second.output
    assert _review_json(tmp_path) == first_json
    run_path = _run_dir(tmp_path)
    assert sorted(path.name for path in run_path.iterdir()).count("patch-review.json") == 1


def test_no_source_workspace_or_task_state_mutation(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _create_task(tmp_path, monkeypatch)
    src_path = tmp_path / "src" / "devflow" / "control_room" / "example.py"
    src_path.parent.mkdir(parents=True, exist_ok=True)
    src_path.write_text("ORIGINAL = True\n", encoding="utf-8")
    workspace_path = tmp_path / ".devflow" / "workspaces" / "task-0001" / "workspace.txt"
    workspace_path.write_text("workspace original\n", encoding="utf-8")
    task_yaml = tmp_path / ".devflow" / "tasks" / "task-0001" / "task.yaml"
    verification_json = tmp_path / ".devflow" / "tasks" / "task-0001" / "verification.json"
    before = {
        "source": src_path.read_text(encoding="utf-8"),
        "workspace": workspace_path.read_text(encoding="utf-8"),
        "task": task_yaml.read_text(encoding="utf-8"),
        "verification": verification_json.read_text(encoding="utf-8"),
    }
    _write_proposal(tmp_path, patch=_patch("src/devflow/control_room/example.py"))

    result = runner.invoke(app, ["task", "review-patch", "task-0001", "--run-id", "run-1"])

    assert result.exit_code == 0, result.output
    assert src_path.read_text(encoding="utf-8") == before["source"]
    assert workspace_path.read_text(encoding="utf-8") == before["workspace"]
    assert task_yaml.read_text(encoding="utf-8") == before["task"]
    assert verification_json.read_text(encoding="utf-8") == before["verification"]


def test_no_network_or_model_imports() -> None:
    source = Path("src/devflow/control_room/patch_review.py").read_text(encoding="utf-8")
    forbidden = ["urllib", "requests", "httpx", "ollama", "openai", "socket"]
    assert not any(token in source for token in forbidden)


def test_latest_run_selection_prefers_latest_proposal_json(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _create_task(tmp_path, monkeypatch)
    _write_proposal(tmp_path, run_id="run-1", patch=_patch("docs/old.md"))
    _write_proposal(tmp_path, run_id="run-2", patch=_patch("docs/new.md"))

    result = runner.invoke(app, ["task", "review-patch", "task-0001"])

    assert result.exit_code == 0, result.output
    assert _review_json(tmp_path, "run-2")["files_touched"] == ["docs/new.md"]
    assert not (tmp_path / ".devflow" / "tasks" / "task-0001" / "local-model-runs" / "run-1" / "patch-review.json").exists()


def test_malformed_proposal_json_fails_clearly(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _create_task(tmp_path, monkeypatch)
    run_path = _run_dir(tmp_path)
    (run_path / "proposal.json").write_text("{not json", encoding="utf-8")

    result = runner.invoke(app, ["task", "review-patch", "task-0001", "--run-id", "run-1"])

    assert result.exit_code != 0
    assert "proposal.json is malformed" in result.output
