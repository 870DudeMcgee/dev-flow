"""Tests for the DevFlow workspace management module.

Covers workspace state persistence, active workspace switching, recent list
management, and the native folder-picker dialog (mocked).
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest

from devflow.control_room import workspace as ws


@pytest.fixture(autouse=True)
def isolate_state(tmp_path: Path, monkeypatch):
    """Redirect workspace state to a temp dir so tests don't touch real state."""
    state_dir = tmp_path / "state"
    state_file = state_dir / "workspace-state.json"
    monkeypatch.setattr(ws, "_STATE_DIR", state_dir)
    monkeypatch.setattr(ws, "_STATE_FILE", state_file)
    yield


@pytest.fixture
def workspace_a(tmp_path: Path) -> Path:
    d = tmp_path / "project-a"
    d.mkdir()
    return d


@pytest.fixture
def workspace_b(tmp_path: Path) -> Path:
    d = tmp_path / "project-b"
    d.mkdir()
    return d


# ---------------------------------------------------------------------------
# State persistence
# ---------------------------------------------------------------------------

def test_empty_state_returns_none_active() -> None:
    """With no prior state, active workspace is None."""
    assert ws.get_active_workspace() is None
    assert ws.get_recent_workspaces() == []


def test_state_round_trips(workspace_a: Path) -> None:
    """set_active_workspace persists and get_active_workspace reads it back."""
    ws.set_active_workspace(workspace_a)
    assert ws.get_active_workspace() == str(workspace_a.resolve())


# ---------------------------------------------------------------------------
# set_active_workspace
# ---------------------------------------------------------------------------

def test_set_active_creates_devflow_dir(workspace_a: Path) -> None:
    """set_active_workspace creates .devflow/ inside the workspace."""
    ws.set_active_workspace(workspace_a)
    assert (workspace_a / ".devflow").is_dir()


def test_set_active_rejects_nonexistent(tmp_path: Path) -> None:
    """set_active_workspace raises FileNotFoundError for a missing directory."""
    with pytest.raises(FileNotFoundError):
        ws.set_active_workspace(tmp_path / "does-not-exist")


def test_set_active_rejects_file(tmp_path: Path) -> None:
    """set_active_workspace raises ValueError when path is a file, not a dir."""
    f = tmp_path / "file.txt"
    f.write_text("hello")
    with pytest.raises(ValueError, match="Not a directory"):
        ws.set_active_workspace(f)


def test_set_active_returns_info(workspace_a: Path) -> None:
    """set_active_workspace returns a dict with name and recent list."""
    result = ws.set_active_workspace(workspace_a)
    assert result["active"] == str(workspace_a.resolve())
    assert result["name"] == workspace_a.name
    assert isinstance(result["recent"], list)
    assert len(result["recent"]) >= 1


# ---------------------------------------------------------------------------
# Recent list management
# ---------------------------------------------------------------------------

def test_recent_list_promotes_to_top(workspace_a: Path, workspace_b: Path) -> None:
    """Setting a workspace promotes it to the top of the recent list."""
    ws.set_active_workspace(workspace_a)
    ws.set_active_workspace(workspace_b)
    recent = ws.get_recent_workspaces()
    assert recent[0]["path"] == str(workspace_b.resolve())
    assert recent[1]["path"] == str(workspace_a.resolve())


def test_recent_list_deduplicates(workspace_a: Path) -> None:
    """Setting the same workspace twice doesn't duplicate it."""
    ws.set_active_workspace(workspace_a)
    ws.set_active_workspace(workspace_a)
    recent = ws.get_recent_workspaces()
    paths = [r["path"] for r in recent]
    assert paths.count(str(workspace_a.resolve())) == 1


def test_remove_recent(workspace_a: Path, workspace_b: Path) -> None:
    """remove_recent_workspace removes from the list and clears active if it matches."""
    ws.set_active_workspace(workspace_a)
    ws.set_active_workspace(workspace_b)
    result = ws.remove_recent_workspace(str(workspace_a.resolve()))
    paths = [r["path"] for r in result["recent"]]
    assert str(workspace_a.resolve()) not in paths
    # Active is still workspace_b
    assert result["active"] == str(workspace_b.resolve())


def test_remove_recent_clears_active(workspace_a: Path) -> None:
    """Removing the active workspace clears the active pointer."""
    ws.set_active_workspace(workspace_a)
    result = ws.remove_recent_workspace(str(workspace_a.resolve()))
    assert result["active"] is None


# ---------------------------------------------------------------------------
# Workspace state (full payload)
# ---------------------------------------------------------------------------

def test_get_workspace_state_no_active() -> None:
    """get_workspace_state returns null active and empty recent when nothing is set."""
    state = ws.get_workspace_state()
    assert state["active"] is None
    assert state["recent"] == []


def test_get_workspace_state_with_active(workspace_a: Path) -> None:
    """get_workspace_state returns active info with name and exists flag."""
    ws.set_active_workspace(workspace_a)
    state = ws.get_workspace_state()
    assert state["active"] is not None
    assert state["active"]["name"] == workspace_a.name
    assert state["active"]["exists"] is True


def test_get_workspace_state_detects_missing(workspace_a: Path) -> None:
    """get_workspace_state flags a workspace whose folder was deleted."""
    ws.set_active_workspace(workspace_a)
    # Simulate deletion
    import shutil
    shutil.rmtree(workspace_a)
    state = ws.get_workspace_state()
    assert state["active"] is not None
    assert state["active"]["exists"] is False


def test_get_workspace_state_includes_platform() -> None:
    """get_workspace_state includes a platform field."""
    state = ws.get_workspace_state()
    assert "platform" in state
    assert state["platform"] in ("macos", "linux", "windows", "unknown")


# ---------------------------------------------------------------------------
# Folder picker dialog (mocked)
# ---------------------------------------------------------------------------

def test_pick_folder_dialog_returns_path(workspace_a: Path) -> None:
    """pick_folder_dialog returns the chosen path from osascript."""
    with patch("devflow.control_room.workspace.subprocess.run") as mock_run:
        mock_run.return_value = type("R", (), {
            "returncode": 0,
            "stdout": str(workspace_a) + "/\n",
            "stderr": "",
        })()
        result = ws.pick_folder_dialog()
    assert result == str(workspace_a)


def test_pick_folder_dialog_returns_none_on_cancel() -> None:
    """pick_folder_dialog returns None when user cancels (non-zero exit)."""
    with patch("devflow.control_room.workspace.subprocess.run") as mock_run:
        mock_run.return_value = type("R", (), {
            "returncode": 1,
            "stdout": "",
            "stderr": "User canceled",
        })()
        result = ws.pick_folder_dialog()
    assert result is None


def test_pick_folder_dialog_returns_none_on_timeout() -> None:
    """pick_folder_dialog returns None when osascript times out."""
    import subprocess
    with patch("devflow.control_room.workspace.subprocess.run", side_effect=subprocess.TimeoutExpired("osascript", 120)):
        result = ws.pick_folder_dialog()
    assert result is None


def test_pick_folder_dialog_returns_none_when_no_osascript() -> None:
    """pick_folder_dialog returns None when osascript isn't available."""
    with patch("devflow.control_room.workspace.subprocess.run", side_effect=FileNotFoundError):
        result = ws.pick_folder_dialog()
    assert result is None


# ---------------------------------------------------------------------------
# Page HTML sanity
# ---------------------------------------------------------------------------

def test_page_html_contains_workspace_picker() -> None:
    """The status page HTML includes the workspace picker elements."""
    from devflow.control_room.page import STATUS_PAGE_HTML
    assert "workspace-widget" in STATUS_PAGE_HTML
    assert "workspace-dropdown" in STATUS_PAGE_HTML
    assert "pickWorkspaceFolder" in STATUS_PAGE_HTML
    assert "/api/workspace" in STATUS_PAGE_HTML
    assert "/api/workspace/pick" in STATUS_PAGE_HTML
    assert "/api/workspace/set" in STATUS_PAGE_HTML
