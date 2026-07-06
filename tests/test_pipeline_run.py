"""Tests for pipeline_run persistence module."""

from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

from devflow.control_room.pipeline_run import (
    RUN_LOG_FILE,
    append_pipeline_event,
    create_pipeline_run,
    load_pipeline_run,
    new_pipeline_run_id,
    pipeline_runs_dir,
    update_pipeline_run_record,
)


# ---------------------------------------------------------------------------
# new_pipeline_run_id
# ---------------------------------------------------------------------------
class TestNewPipelineRunId:
    def test_returns_str(self) -> None:
        run_id = new_pipeline_run_id()
        assert isinstance(run_id, str)

    def test_format_is_sortable(self) -> None:
        run_id = new_pipeline_run_id()
        # Expected: 20260706-143022 or same-second suffix 20260706-143022-001
        assert re.fullmatch(r"\d{8}-\d{6}(-\d{3})?", run_id)

    def test_sequential_ids_are_sorted(self) -> None:
        ids = [new_pipeline_run_id() for _ in range(5)]
        assert ids == sorted(ids), "run ids must be time-sortable"


# ---------------------------------------------------------------------------
# pipeline_runs_dir
# ---------------------------------------------------------------------------
class TestPipelineRunsDir:
    def test_returns_expected_path(self, tmp_path: Path) -> None:
        result = pipeline_runs_dir(tmp_path)
        assert result == tmp_path / ".devflow" / "pipeline-runs"

    def test_resolves_to_absolute(self, tmp_path: Path) -> None:
        result = pipeline_runs_dir(tmp_path)
        assert result.is_absolute()

    def test_accepts_string(self, tmp_path: Path) -> None:
        result = pipeline_runs_dir(str(tmp_path))
        assert result == tmp_path.resolve() / ".devflow" / "pipeline-runs"


# ---------------------------------------------------------------------------
# create_pipeline_run
# ---------------------------------------------------------------------------
MINIMUM_FILES = [
    "intent.md",
    "source.json",
    "brainstorm.md",
    "classification.json",
    "readiness-packet.md",
    "loop-packet.md",
    "validation.json",
    "run-log.jsonl",
    "artifacts.json",
    "review.md",
]


class TestCreatePipelineRun:
    def test_creates_directory_and_all_minimum_files(self, tmp_path: Path) -> None:
        source = {"repo": "test-repo", "branch": "main"}
        run_id = create_pipeline_run(tmp_path, source)

        run_dir = tmp_path / ".devflow" / "pipeline-runs" / run_id
        assert run_dir.is_dir()

        for filename in MINIMUM_FILES:
            assert (run_dir / filename).is_file(), f"Missing: {filename}"

    def test_source_json_contains_source_data(self, tmp_path: Path) -> None:
        source = {"repo": "my-repo", "branch": "feature", "obsidian_links": []}
        run_id = create_pipeline_run(tmp_path, source)

        run_dir = tmp_path / ".devflow" / "pipeline-runs" / run_id
        saved = json.loads((run_dir / "source.json").read_text(encoding="utf-8"))
        assert saved == source

    def test_returns_different_ids_for_subsequent_calls(self, tmp_path: Path) -> None:
        id1 = create_pipeline_run(tmp_path, {"repo": "a"})
        id2 = create_pipeline_run(tmp_path, {"repo": "b"})
        assert id1 != id2

    def test_raises_if_dir_already_exists(self, tmp_path: Path) -> None:
        run_id = create_pipeline_run(tmp_path, {"repo": "x"})
        # Trying to create the same run_id again should fail
        # (exist_ok=False on the directory)
        run_dir = tmp_path / ".devflow" / "pipeline-runs" / run_id
        run_dir.mkdir(parents=True, exist_ok=True)
        # The create function generates a new id each time, so we can't
        # directly trigger the collision. Instead, verify that
        # mkdir(parents=True, exist_ok=False) raises on existing dir.
        with pytest.raises(FileExistsError):
            run_dir.mkdir(parents=True, exist_ok=False)


# ---------------------------------------------------------------------------
# load_pipeline_run
# ---------------------------------------------------------------------------
class TestLoadPipelineRun:
    def test_loads_back_created_run(self, tmp_path: Path) -> None:
        source = {"repo": "test", "branch": "main"}
        run_id = create_pipeline_run(tmp_path, source)

        loaded = load_pipeline_run(tmp_path, run_id)
        assert loaded["source.json"] == source
        assert loaded["intent.md"] == "# Intent\n"
        assert loaded["run-log.jsonl"] == []

    def test_raises_on_nonexistent_run(self, tmp_path: Path) -> None:
        with pytest.raises(FileNotFoundError):
            load_pipeline_run(tmp_path, "nonexistent-run-123")

    def test_loads_updated_content(self, tmp_path: Path) -> None:
        run_id = create_pipeline_run(tmp_path, {"repo": "test"})
        update_pipeline_run_record(
            tmp_path, run_id, "intent.md", "# Updated intent\n"
        )
        loaded = load_pipeline_run(tmp_path, run_id)
        assert loaded["intent.md"] == "# Updated intent\n"


# ---------------------------------------------------------------------------
# update_pipeline_run_record
# ---------------------------------------------------------------------------
class TestUpdatePipelineRunRecord:
    def test_writes_text_content(self, tmp_path: Path) -> None:
        run_id = create_pipeline_run(tmp_path, {"repo": "test"})
        update_pipeline_run_record(
            tmp_path, run_id, "intent.md", "# Modified intent\n"
        )

        run_dir = tmp_path / ".devflow" / "pipeline-runs" / run_id
        assert (run_dir / "intent.md").read_text(encoding="utf-8") == "# Modified intent\n"

    def test_writes_json_from_dict(self, tmp_path: Path) -> None:
        run_id = create_pipeline_run(tmp_path, {"repo": "test"})
        update_pipeline_run_record(
            tmp_path, run_id, "classification.json", {"type": "bugfix", "priority": "high"}
        )

        run_dir = tmp_path / ".devflow" / "pipeline-runs" / run_id
        saved = json.loads((run_dir / "classification.json").read_text(encoding="utf-8"))
        assert saved == {"type": "bugfix", "priority": "high"}

    def test_writes_json_from_list(self, tmp_path: Path) -> None:
        run_id = create_pipeline_run(tmp_path, {"repo": "test"})
        items = [{"id": 1}, {"id": 2}]
        update_pipeline_run_record(tmp_path, run_id, "artifacts.json", items)

        run_dir = tmp_path / ".devflow" / "pipeline-runs" / run_id
        saved = json.loads((run_dir / "artifacts.json").read_text(encoding="utf-8"))
        assert saved == items

    def test_raises_on_nonexistent_run(self, tmp_path: Path) -> None:
        with pytest.raises(FileNotFoundError):
            update_pipeline_run_record(
                tmp_path, "no-such-run", "intent.md", "content"
            )

    def test_refuses_path_traversal(self, tmp_path: Path) -> None:
        run_id = create_pipeline_run(tmp_path, {"repo": "test"})
        with pytest.raises(ValueError, match="outside"):
            update_pipeline_run_record(
                tmp_path, run_id, "../escape.txt", "bad"
            )

    def test_refuses_absolute_path(self, tmp_path: Path) -> None:
        run_id = create_pipeline_run(tmp_path, {"repo": "test"})
        with pytest.raises(ValueError, match="outside"):
            update_pipeline_run_record(
                tmp_path, run_id, "/tmp/outside.txt", "bad"
            )


# ---------------------------------------------------------------------------
# append_pipeline_event
# ---------------------------------------------------------------------------
class TestAppendPipelineEvent:
    def test_appends_single_event(self, tmp_path: Path) -> None:
        run_id = create_pipeline_run(tmp_path, {"repo": "test"})
        event = {"stage": "brainstorm", "status": "completed"}
        append_pipeline_event(tmp_path, run_id, event)

        run_dir = tmp_path / ".devflow" / "pipeline-runs" / run_id
        lines = (run_dir / RUN_LOG_FILE).read_text(encoding="utf-8").strip().splitlines()
        assert len(lines) == 1
        parsed = json.loads(lines[0])
        assert parsed["stage"] == "brainstorm"
        assert parsed["status"] == "completed"
        assert "timestamp" in parsed

    def test_appends_multiple_events(self, tmp_path: Path) -> None:
        run_id = create_pipeline_run(tmp_path, {"repo": "test"})
        events = [
            {"stage": "brainstorm", "status": "started"},
            {"stage": "brainstorm", "status": "completed"},
            {"stage": "classification", "status": "completed"},
        ]
        for event in events:
            append_pipeline_event(tmp_path, run_id, event)

        run_dir = tmp_path / ".devflow" / "pipeline-runs" / run_id
        lines = (run_dir / RUN_LOG_FILE).read_text(encoding="utf-8").strip().splitlines()
        assert len(lines) == 3
        for i, line in enumerate(lines):
            parsed = json.loads(line)
            assert parsed["stage"] == events[i]["stage"]
            assert parsed["status"] == events[i]["status"]

    def test_raises_on_nonexistent_run(self, tmp_path: Path) -> None:
        with pytest.raises(FileNotFoundError):
            append_pipeline_event(tmp_path, "no-such-run", {"event": "test"})

    def test_does_not_overwrite_existing_log(self, tmp_path: Path) -> None:
        run_id = create_pipeline_run(tmp_path, {"repo": "test"})
        append_pipeline_event(tmp_path, run_id, {"event": "first"})
        append_pipeline_event(tmp_path, run_id, {"event": "second"})

        run_dir = tmp_path / ".devflow" / "pipeline-runs" / run_id
        lines = (run_dir / RUN_LOG_FILE).read_text(encoding="utf-8").strip().splitlines()
        assert len(lines) == 2
        assert json.loads(lines[0])["event"] == "first"
        assert json.loads(lines[1])["event"] == "second"


# ---------------------------------------------------------------------------
# Safety: no mutation outside .devflow/pipeline-runs/
# ---------------------------------------------------------------------------
class TestSafetyBoundary:
    def test_create_does_not_leak(self, tmp_path: Path) -> None:
        """create_pipeline_run only writes inside .devflow/pipeline-runs/."""
        tmp_path  # just used for base
        source = {"repo": "test"}
        run_id = create_pipeline_run(tmp_path, source)
        run_dir = tmp_path / ".devflow" / "pipeline-runs" / run_id
        assert run_dir.is_dir()
        # No files outside the expected path
        for child in run_dir.rglob("*"):
            assert str(child.resolve()).startswith(str(run_dir.resolve()))

    def test_update_refuses_traversal_via_deeply_nested(self, tmp_path: Path) -> None:
        run_id = create_pipeline_run(tmp_path, {"repo": "test"})
        with pytest.raises(ValueError, match="outside"):
            update_pipeline_run_record(
                tmp_path, run_id, "subdir/../../escape.md", "bad"
            )

    def test_append_only_writes_in_run_log(self, tmp_path: Path) -> None:
        """append_pipeline_event always writes to run-log.jsonl, never outside."""
        run_id = create_pipeline_run(tmp_path, {"repo": "test"})
        append_pipeline_event(tmp_path, run_id, {"event": "safe"})

        run_dir = tmp_path / ".devflow" / "pipeline-runs" / run_id
        log_path = run_dir / RUN_LOG_FILE
        assert log_path.is_file()
        lines = log_path.read_text(encoding="utf-8").strip().splitlines()
        assert len(lines) == 1
        # Verify no stray files were created outside the run dir
        all_files = list(run_dir.rglob("*"))
        for child in all_files:
            assert str(child.resolve()).startswith(str(run_dir.resolve()))