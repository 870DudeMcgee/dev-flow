from __future__ import annotations

import json
from pathlib import Path
import shutil

import pytest
from typer.testing import CliRunner

from devflow.cli import app
from tests.helpers import setup_temp_git_repo


runner = CliRunner()


def _create_task(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    setup_temp_git_repo(tmp_path)
    monkeypatch.chdir(tmp_path)
    result = runner.invoke(app, ["task", "create", "patch dry-run task"])
    assert result.exit_code == 0, result.output


def _workspace(tmp_path: Path) -> Path:
    return tmp_path / ".devflow" / "workspaces" / "task-0001"


def _run_dir(tmp_path: Path, run_id: str = "run-1") -> Path:
    path = tmp_path / ".devflow" / "tasks" / "task-0001" / "local-model-runs" / run_id
    path.mkdir(parents=True, exist_ok=True)
    return path


def _write_run(
    tmp_path: Path,
    *,
    run_id: str = "run-1",
    patch: str | None = None,
    review_status: str = "low_risk_candidate",
    risk: str = "low",
    warnings: list[str] | None = None,
    high_risk_files: list[str] | None = None,
) -> Path:
    run_path = _run_dir(tmp_path, run_id)
    (run_path / "proposal.json").write_text(
        json.dumps(
            {
                "schema_version": 1,
                "task_id": "task-0001",
                "run_id": run_id,
                "classification": "patch_candidate",
                "has_patch_candidate": patch is not None,
            },
            indent=2,
            sort_keys=True,
        ),
        encoding="utf-8",
    )
    if patch is not None:
        (run_path / "proposal.patch").write_text(patch, encoding="utf-8")
    (run_path / "patch-review.json").write_text(
        json.dumps(
            {
                "schema_version": 1,
                "task_id": "task-0001",
                "run_id": run_id,
                "review_status": review_status,
                "risk": risk,
                "files_touched": [],
                "hunk_count": 1,
                "warnings": warnings or [],
                "high_risk_files": high_risk_files or [],
            },
            indent=2,
            sort_keys=True,
        ),
        encoding="utf-8",
    )
    return run_path


def _modify_patch(path: str, old: str = "old", new: str = "new") -> str:
    return f"""diff --git a/{path} b/{path}
--- a/{path}
+++ b/{path}
@@ -1 +1 @@
-{old}
+{new}
"""


def _new_file_patch(path: str) -> str:
    return f"""diff --git a/{path} b/{path}
--- /dev/null
+++ b/{path}
@@ -0,0 +1 @@
+new
"""


def _append_beyond_eof_patch(path: str) -> str:
    return f"""diff --git a/{path} b/{path}
--- a/{path}
+++ b/{path}
@@ -200,0 +201,2 @@
+new
+lines
"""


def _off_by_one_context_patch(path: str) -> str:
    return f"""diff --git a/{path} b/{path}
--- a/{path}
+++ b/{path}
@@ -2,3 +2,4 @@
 - one
 - two
 - three
+- four
"""


def _mode_change_patch(path: str) -> str:
    return f"""diff --git a/{path} b/{path}
old mode 100644
new mode 100755
--- a/{path}
+++ b/{path}
@@ -1 +1 @@
-old
+new
"""


def _mismatched_hunk_count_patch(path: str) -> str:
    return f"""diff --git a/{path} b/{path}
--- a/{path}
+++ b/{path}
@@ -1 +1 @@
-old
+new
+extra
"""


def _delete_patch(path: str) -> str:
    return f"""diff --git a/{path} b/{path}
--- a/{path}
+++ /dev/null
@@ -1 +0,0 @@
-old
"""


def _dry_run_json(tmp_path: Path, run_id: str = "run-1") -> dict[str, object]:
    path = tmp_path / ".devflow" / "tasks" / "task-0001" / "local-model-runs" / run_id / "patch-dry-run.json"
    return json.loads(path.read_text(encoding="utf-8"))


def _write_workspace_file(tmp_path: Path, path: str, text: str) -> Path:
    file_path = _workspace(tmp_path) / path
    file_path.parent.mkdir(parents=True, exist_ok=True)
    file_path.write_text(text, encoding="utf-8")
    return file_path


def test_agent_patch_dry_run_uses_normalized_agent_run(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _create_task(tmp_path, monkeypatch)
    _write_workspace_file(tmp_path, "docs/agent.md", "old\n")
    agent_dir = tmp_path / ".devflow" / "tasks" / "task-0001" / "agents" / "qwopus-implementer"
    agent_dir.mkdir(parents=True)
    (agent_dir / "proposal.patch").write_text(_modify_patch("docs/agent.md"), encoding="utf-8")
    review = runner.invoke(app, ["task", "review-patch", "task-0001", "--agent", "qwopus-implementer"])
    assert review.exit_code == 0, review.output

    result = runner.invoke(app, ["task", "patch-dry-run", "task-0001", "--agent", "qwopus-implementer"])

    assert result.exit_code == 0, result.output
    assert "Run: agent-qwopus-implementer" in result.output
    data = _dry_run_json(tmp_path, "agent-qwopus-implementer")
    assert data["dry_run_status"] == "would_apply_cleanly"
    assert data["files_would_modify"] == ["docs/agent.md"]
    assert _workspace(tmp_path).joinpath("docs/agent.md").read_text(encoding="utf-8") == "old\n"


def test_missing_local_model_run_fails_clearly(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _create_task(tmp_path, monkeypatch)

    result = runner.invoke(app, ["task", "patch-dry-run", "task-0001"])

    assert result.exit_code != 0
    assert "No local model runs found" in result.output


def test_missing_patch_review_fails_clearly(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _create_task(tmp_path, monkeypatch)
    run_path = _run_dir(tmp_path)
    (run_path / "proposal.patch").write_text(_modify_patch("docs/a.md"), encoding="utf-8")

    result = runner.invoke(app, ["task", "patch-dry-run", "task-0001", "--run-id", "run-1"])

    assert result.exit_code != 0
    assert "patch-review.json not found" in result.output


@pytest.mark.parametrize("review_status", ["dangerous_patch", "invalid_patch", "no_patch_candidate"])
def test_rejected_review_status_writes_rejected_dry_run_without_matching(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    review_status: str,
) -> None:
    _create_task(tmp_path, monkeypatch)
    workspace_file = _write_workspace_file(tmp_path, "docs/a.md", "different\n")
    before = workspace_file.read_text(encoding="utf-8")
    _write_run(tmp_path, patch=_modify_patch("docs/a.md"), review_status=review_status, risk="critical")

    result = runner.invoke(app, ["task", "patch-dry-run", "task-0001", "--run-id", "run-1"])

    assert result.exit_code == 0, result.output
    data = _dry_run_json(tmp_path)
    assert data["dry_run_status"] == "rejected_by_patch_review"
    assert data["hunks_checked"] == 0
    assert workspace_file.read_text(encoding="utf-8") == before


def test_workspace_missing_is_controlled(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _create_task(tmp_path, monkeypatch)
    _write_run(tmp_path, patch=_modify_patch("docs/a.md"))
    shutil.rmtree(_workspace(tmp_path))

    result = runner.invoke(app, ["task", "patch-dry-run", "task-0001", "--run-id", "run-1"])

    assert result.exit_code == 0, result.output
    assert _dry_run_json(tmp_path)["dry_run_status"] == "workspace_missing"


def test_invalid_patch_is_recorded(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _create_task(tmp_path, monkeypatch)
    _write_run(tmp_path, patch="not a patch", review_status="review_required", risk="medium")

    result = runner.invoke(app, ["task", "patch-dry-run", "task-0001", "--run-id", "run-1"])

    assert result.exit_code == 0, result.output
    data = _dry_run_json(tmp_path)
    assert data["dry_run_status"] == "invalid_patch"
    assert data["risk"] == "medium"


def test_new_file_patch_would_create_without_mutation(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _create_task(tmp_path, monkeypatch)
    target = _workspace(tmp_path) / "docs" / "new-file.md"
    _write_run(tmp_path, patch=_new_file_patch("docs/new-file.md"))

    result = runner.invoke(app, ["task", "patch-dry-run", "task-0001", "--run-id", "run-1"])

    assert result.exit_code == 0, result.output
    data = _dry_run_json(tmp_path)
    assert data["dry_run_status"] == "would_create_files"
    assert data["files_would_create"] == ["docs/new-file.md"]
    assert not target.exists()


def test_existing_file_patch_would_apply_cleanly_without_mutation(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _create_task(tmp_path, monkeypatch)
    workspace_file = _write_workspace_file(tmp_path, "docs/existing.md", "old\n")
    before = workspace_file.read_text(encoding="utf-8")
    _write_run(tmp_path, patch=_modify_patch("docs/existing.md"))

    result = runner.invoke(app, ["task", "patch-dry-run", "task-0001", "--run-id", "run-1"])

    assert result.exit_code == 0, result.output
    data = _dry_run_json(tmp_path)
    assert data["dry_run_status"] == "would_apply_cleanly"
    assert data["hunks_checked"] == 1
    assert data["hunks_matched"] == 1
    assert data["hunks_failed"] == 0
    assert workspace_file.read_text(encoding="utf-8") == before


def test_missing_target_file(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _create_task(tmp_path, monkeypatch)
    _write_run(tmp_path, patch=_modify_patch("docs/missing.md"))

    result = runner.invoke(app, ["task", "patch-dry-run", "task-0001", "--run-id", "run-1"])

    assert result.exit_code == 0, result.output
    data = _dry_run_json(tmp_path)
    assert data["dry_run_status"] == "missing_target_file"
    assert data["files_missing"] == ["docs/missing.md"]


def test_hunk_mismatch(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _create_task(tmp_path, monkeypatch)
    _write_workspace_file(tmp_path, "docs/existing.md", "different\n")
    _write_run(tmp_path, patch=_modify_patch("docs/existing.md"))

    result = runner.invoke(app, ["task", "patch-dry-run", "task-0001", "--run-id", "run-1"])

    assert result.exit_code == 0, result.output
    data = _dry_run_json(tmp_path)
    assert data["dry_run_status"] == "hunk_mismatch"
    assert data["hunks_failed"] == 1


def test_append_hunk_beyond_eof_is_rejected(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _create_task(tmp_path, monkeypatch)
    _write_workspace_file(tmp_path, "docs/existing.md", "one\ntwo\n")
    _write_run(tmp_path, patch=_append_beyond_eof_patch("docs/existing.md"))

    result = runner.invoke(app, ["task", "patch-dry-run", "task-0001", "--run-id", "run-1"])

    assert result.exit_code == 0, result.output
    data = _dry_run_json(tmp_path)
    assert data["dry_run_status"] == "hunk_mismatch"
    assert data["hunks_failed"] == 1
    assert data["hunk_results"][0]["old_start"] == 200


def test_unique_context_hunk_can_match_off_by_one_header(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _create_task(tmp_path, monkeypatch)
    _write_workspace_file(tmp_path, "docs/existing.md", "intro\n\n- one\n- two\n- three\n")
    _write_run(tmp_path, patch=_off_by_one_context_patch("docs/existing.md"))

    result = runner.invoke(app, ["task", "patch-dry-run", "task-0001", "--run-id", "run-1"])

    assert result.exit_code == 0, result.output
    data = _dry_run_json(tmp_path)
    assert data["dry_run_status"] == "would_apply_cleanly"
    assert data["hunks_matched"] == 1


def test_unsupported_apply_metadata_is_invalid_patch(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _create_task(tmp_path, monkeypatch)
    _write_workspace_file(tmp_path, "docs/existing.md", "old\n")
    _write_run(tmp_path, patch=_mode_change_patch("docs/existing.md"))

    result = runner.invoke(app, ["task", "patch-dry-run", "task-0001", "--run-id", "run-1"])

    assert result.exit_code == 0, result.output
    data = _dry_run_json(tmp_path)
    assert data["dry_run_status"] == "invalid_patch"
    assert "Unsupported metadata: old mode" in data["warnings"][0]


def test_mismatched_hunk_counts_are_invalid_patch(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _create_task(tmp_path, monkeypatch)
    _write_workspace_file(tmp_path, "docs/existing.md", "old\n")
    _write_run(tmp_path, patch=_mismatched_hunk_count_patch("docs/existing.md"))

    result = runner.invoke(app, ["task", "patch-dry-run", "task-0001", "--run-id", "run-1"])

    assert result.exit_code == 0, result.output
    data = _dry_run_json(tmp_path)
    assert data["dry_run_status"] == "invalid_patch"
    assert data["hunks_checked"] == 0
    assert "Malformed hunk line counts" in data["warnings"][0]


def test_deletion_patch_preview_does_not_delete_file(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _create_task(tmp_path, monkeypatch)
    workspace_file = _write_workspace_file(tmp_path, "docs/delete.md", "old\n")
    _write_run(tmp_path, patch=_delete_patch("docs/delete.md"))

    result = runner.invoke(app, ["task", "patch-dry-run", "task-0001", "--run-id", "run-1"])

    assert result.exit_code == 0, result.output
    data = _dry_run_json(tmp_path)
    assert data["dry_run_status"] == "would_apply_cleanly"
    assert data["files_would_delete"] == ["docs/delete.md"]
    assert workspace_file.exists()


@pytest.mark.parametrize("target", ["../evil.py", ".devflow/tasks/task-0001/packet.json"])
def test_dangerous_target_path_independently_rejected(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    target: str,
) -> None:
    _create_task(tmp_path, monkeypatch)
    _write_run(tmp_path, patch=_modify_patch(target), review_status="low_risk_candidate", risk="low")

    result = runner.invoke(app, ["task", "patch-dry-run", "task-0001", "--run-id", "run-1"])

    assert result.exit_code == 0, result.output
    data = _dry_run_json(tmp_path)
    assert data["dry_run_status"] == "invalid_patch"
    assert data["risk"] == "critical"


def test_high_risk_review_keeps_high_risk_and_warning(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _create_task(tmp_path, monkeypatch)
    _write_workspace_file(tmp_path, "src/devflow/cli.py", "old\n")
    _write_run(
        tmp_path,
        patch=_modify_patch("src/devflow/cli.py"),
        review_status="review_required",
        risk="high",
        high_risk_files=["src/devflow/cli.py"],
    )

    result = runner.invoke(app, ["task", "patch-dry-run", "task-0001", "--run-id", "run-1"])

    assert result.exit_code == 0, result.output
    data = _dry_run_json(tmp_path)
    assert data["dry_run_status"] == "would_modify_with_warnings"
    assert data["risk"] == "high"


def test_latest_and_run_id_selection(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _create_task(tmp_path, monkeypatch)
    _write_workspace_file(tmp_path, "docs/a.md", "old\n")
    _write_workspace_file(tmp_path, "docs/b.md", "old\n")
    _write_run(tmp_path, run_id="run-a", patch=_modify_patch("docs/a.md"))
    _write_run(tmp_path, run_id="run-b", patch=_modify_patch("docs/b.md"))

    latest = runner.invoke(app, ["task", "patch-dry-run", "task-0001"])
    specific = runner.invoke(app, ["task", "patch-dry-run", "task-0001", "--run-id", "run-a"])

    assert latest.exit_code == 0, latest.output
    assert specific.exit_code == 0, specific.output
    assert _dry_run_json(tmp_path, "run-b")["files_checked"] == ["docs/b.md"]
    assert _dry_run_json(tmp_path, "run-a")["files_checked"] == ["docs/a.md"]


def test_task_show_displays_dry_run_summary(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _create_task(tmp_path, monkeypatch)
    _write_workspace_file(tmp_path, "docs/existing.md", "old\n")
    _write_run(tmp_path, patch=_modify_patch("docs/existing.md"))
    dry_run = runner.invoke(app, ["task", "patch-dry-run", "task-0001", "--run-id", "run-1"])
    assert dry_run.exit_code == 0, dry_run.output

    show = runner.invoke(app, ["task", "show", "task-0001"])

    assert show.exit_code == 0, show.output
    assert "Patch Dry-runs:" in show.output
    assert "status: would_apply_cleanly" in show.output
    assert "risk: low" in show.output
    assert "hunks: 1 matched / 0 failed" in show.output


def test_generated_dry_run_artifacts_excluded_from_future_packet(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _create_task(tmp_path, monkeypatch)
    _write_workspace_file(tmp_path, "docs/existing.md", "old\n")
    run_path = _write_run(tmp_path, patch=_modify_patch("docs/existing.md") + "\nUNIQUE_DRY_RUN_PATCH")
    dry_run = runner.invoke(app, ["task", "patch-dry-run", "task-0001", "--run-id", "run-1"])
    assert dry_run.exit_code == 0, dry_run.output
    (run_path / "patch-dry-run.md").write_text("UNIQUE_DRY_RUN_MARKER", encoding="utf-8")

    packet = runner.invoke(app, ["task", "packet", "task-0001"])

    assert packet.exit_code == 0, packet.output
    assert "UNIQUE_DRY_RUN_MARKER" not in packet.output
    assert "UNIQUE_DRY_RUN_PATCH" not in packet.output
    assert "local-model-runs" not in packet.output


def test_idempotent_and_no_task_or_workspace_mutation(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _create_task(tmp_path, monkeypatch)
    workspace_file = _write_workspace_file(tmp_path, "docs/existing.md", "old\n")
    task_yaml = tmp_path / ".devflow" / "tasks" / "task-0001" / "task.yaml"
    verification_json = tmp_path / ".devflow" / "tasks" / "task-0001" / "verification.json"
    before = {
        "workspace": workspace_file.read_text(encoding="utf-8"),
        "task": task_yaml.read_text(encoding="utf-8"),
        "verification": verification_json.read_text(encoding="utf-8"),
    }
    _write_run(tmp_path, patch=_modify_patch("docs/existing.md"))

    first = runner.invoke(app, ["task", "patch-dry-run", "task-0001", "--run-id", "run-1"])
    first_json = _dry_run_json(tmp_path)
    second = runner.invoke(app, ["task", "patch-dry-run", "task-0001", "--run-id", "run-1"])

    assert first.exit_code == 0, first.output
    assert second.exit_code == 0, second.output
    assert _dry_run_json(tmp_path) == first_json
    assert workspace_file.read_text(encoding="utf-8") == before["workspace"]
    assert task_yaml.read_text(encoding="utf-8") == before["task"]
    assert verification_json.read_text(encoding="utf-8") == before["verification"]


def test_no_network_model_or_heavy_imports() -> None:
    source = Path("src/devflow/legacy/control_room/patch_dry_run.py").read_text(encoding="utf-8")
    forbidden = ["urllib", "requests", "local_model_client", "transformers", "torch", "llama_cpp", "openai"]
    assert not any(token in source for token in forbidden)


def test_malformed_patch_review_fails_without_traceback(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _create_task(tmp_path, monkeypatch)
    run_path = _run_dir(tmp_path)
    (run_path / "proposal.patch").write_text(_modify_patch("docs/a.md"), encoding="utf-8")
    (run_path / "patch-review.json").write_text("{not json", encoding="utf-8")

    result = runner.invoke(app, ["task", "patch-dry-run", "task-0001", "--run-id", "run-1"])

    assert result.exit_code != 0
    assert "patch-review.json is malformed" in result.output
    assert "Traceback" not in result.output


def test_missing_proposal_patch_fails_without_traceback(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _create_task(tmp_path, monkeypatch)
    _write_run(tmp_path, patch=None, review_status="low_risk_candidate", risk="low")

    result = runner.invoke(app, ["task", "patch-dry-run", "task-0001", "--run-id", "run-1"])

    assert result.exit_code != 0
    assert "proposal.patch not found" in result.output
    assert "Traceback" not in result.output
