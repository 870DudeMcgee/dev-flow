from __future__ import annotations

import os
import sys
import yaml
from pathlib import Path
import pytest
from typer.testing import CliRunner

from devflow.control_room.goals import create_goal_from_markdown, render_goal_summary, goal_dir
from devflow.cli import app


def test_goal_scaffold_creation(tmp_path: Path) -> None:
    # 1. Create a dummy markdown brief
    brief_path = tmp_path / "my_goal_brief.md"
    brief_content = "## Goal Objective\nImplement robust planning scaffold vertical slice."
    brief_path.write_text(brief_content, encoding="utf-8")

    # 2. Call create_goal_from_markdown
    record = create_goal_from_markdown(tmp_path, brief_path)

    assert record.id == "G-0001"
    
    g_dir = goal_dir(tmp_path, "G-0001")
    assert g_dir.exists()

    # 3. Check that all 10 artifacts exist
    expected_files = [
        "goal.md",
        "grill.md",
        "prd.md",
        "decisions.yaml",
        "open-questions.yaml",
        "out-of-scope.md",
        "context-pointers.yaml",
        "task-slices.yaml",
        "risks.md",
        "handoff.md",
    ]
    for fn in expected_files:
        assert (g_dir / fn).exists(), f"{fn} was not created"

    # 4. Check goal.md content and metadata
    goal_md_text = (g_dir / "goal.md").read_text(encoding="utf-8")
    assert f"# Goal: G-0001" in goal_md_text
    assert brief_content in goal_md_text

    # 5. Check task-slices.yaml contents
    slices_data = yaml.safe_load((g_dir / "task-slices.yaml").read_text(encoding="utf-8"))
    assert "task_slices" in slices_data
    task_slices = slices_data["task_slices"]
    assert len(task_slices) >= 1
    
    slice_0 = task_slices[0]
    required_fields = [
        "task_id",
        "title",
        "summary",
        "slice_type",
        "acceptance_criteria",
        "required_artifacts",
        "blocked_by",
        "blocks",
        "parallel_safe",
        "shared_files",
        "workspace_isolation_required",
        "promotion_requires",
        "risk",
        "execution_mode",
        "context_budget",
        "verification_policy",
        "human_checkpoint_required",
        "checkpoint_reason",
        "promotion_allowed",
    ]
    for field in required_fields:
        assert field in slice_0, f"Field '{field}' missing from task slice"

    assert slice_0["execution_mode"] == "HITL"
    assert slice_0["promotion_allowed"] is False
    assert slice_0["human_checkpoint_required"] is True


def test_stale_context_pointers_filter(tmp_path: Path) -> None:
    # 1. Create docs directory and files
    docs_dir = tmp_path / "docs"
    docs_dir.mkdir(parents=True)
    
    archive_dir = docs_dir / "archive"
    archive_dir.mkdir()

    active_doc = docs_dir / "current-architecture.md"
    active_doc.write_text("Active architecture docs", encoding="utf-8")

    stale_doc = archive_dir / "old-plan.md"
    stale_doc.write_text("Obsolete plan files", encoding="utf-8")

    brief_path = tmp_path / "brief.md"
    brief_path.write_text("Brief", encoding="utf-8")

    # 2. Scaffolding
    create_goal_from_markdown(tmp_path, brief_path, goal_id="G-0001")

    # 3. Read context pointers
    pointers_file = goal_dir(tmp_path, "G-0001") / "context-pointers.yaml"
    assert pointers_file.exists()
    pointers = yaml.safe_load(pointers_file.read_text(encoding="utf-8"))

    # Assert active doc is in required_context
    assert "docs/current-architecture.md" in pointers["required_context"]

    # Assert stale doc is NOT in required_context
    assert "docs/archive/old-plan.md" not in pointers["required_context"]

    # Assert stale doc is in stale_or_archived_context and warnings
    assert "docs/archive/old-plan.md" in pointers["stale_or_archived_context"]
    assert any("warning: docs path contains archive" in w and "docs/archive/old-plan.md" in w for w in pointers["warnings"])


def test_goal_cli_commands(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    # Set up brief
    brief_path = tmp_path / "brief.md"
    brief_path.write_text("CLI brief description", encoding="utf-8")

    # Monkeypatch Cwd to tmp_path
    monkeypatch.chdir(tmp_path)

    runner = CliRunner()
    
    # 1. Test init
    result_init = runner.invoke(app, ["goal", "init", "--from", "brief.md"])
    assert result_init.exit_code == 0
    assert "Initialized Goal G-0001" in result_init.output
    assert ".devflow/goals/G-0001/" in result_init.output

    # 2. Test show
    result_show = runner.invoke(app, ["goal", "show", "G-0001"])
    assert result_show.exit_code == 0
    assert "Goal ID:      G-0001" in result_show.output
    assert "goal.md" in result_show.output
    assert "prd.md" in result_show.output
    assert "task-slices.yaml" in result_show.output


def test_local_model_smoke_script_syntax_and_imports() -> None:
    smoke_path = Path("scripts/local_model_smoke.py")
    assert smoke_path.exists()

    # Syntax check
    import py_compile
    py_compile.compile(str(smoke_path), doraise=True)

    # Read and inspect source
    source = smoke_path.read_text(encoding="utf-8")
    
    # Verify no transformers or torch imports
    assert "import transformers" not in source
    assert "from transformers" not in source
    assert "import torch" not in source
    assert "from torch" not in source

    # Verify no hardcoded Qwopus (model_id must be read dynamically from environment)
    # The default shouldn't be hardcoded to Qwopus in a way that blocks execution or doesn't fallback
    assert "Jackrong/Qwopus3.6-35B-A3B-v1-GGUF" in source  # can exist in instructions/help text
    assert 'model_id = "Jackrong/Qwopus3.6-35B-A3B-v1-GGUF:Q4_K_M"' not in source  # should not be hardcoded default
    
    # Verify execution fails clearly if LOCAL_MODEL_ID is missing
    runner = CliRunner()
    # Run the script via python subprocess
    import subprocess
    env = os.environ.copy()
    if "LOCAL_MODEL_ID" in env:
        del env["LOCAL_MODEL_ID"]

    result = subprocess.run(
        [sys.executable, str(smoke_path)],
        capture_output=True,
        text=True,
        env=env
    )
    assert result.returncode == 1
    assert "Error: LOCAL_MODEL_ID environment variable is missing." in result.stderr
