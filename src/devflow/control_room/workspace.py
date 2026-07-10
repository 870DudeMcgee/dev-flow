"""Workspace management for the DevFlow UI.

A workspace is the directory where you're building a product. DevFlow reads
pipeline runs and git status from it, and brainstorms create pipeline runs in it.

This module manages:
  - The *active* workspace (what the status board and chat operate on)
  - *Recent* workspaces (persisted machine-wide so they survive restarts)
  - A native Finder folder-picker dialog (macOS osascript)

Workspace state lives at ``~/.devflow/workspace-state.json`` so it is shared
across all server instances and survives restarts. Each workspace gets its own
``.devflow/pipeline-runs/`` directory inside it.
"""

from __future__ import annotations

import json
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional


# ---------------------------------------------------------------------------
# State persistence — machine-wide, outside any single workspace
# ---------------------------------------------------------------------------

_STATE_DIR = Path.home() / ".devflow"
_STATE_FILE = _STATE_DIR / "workspace-state.json"
_MAX_RECENT = 12


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _load_state() -> dict[str, Any]:
    """Load the machine-wide workspace state."""
    if not _STATE_FILE.exists():
        return {"recent": [], "active": None}
    try:
        data = json.loads(_STATE_FILE.read_text(encoding="utf-8"))
        if not isinstance(data, dict):
            return {"recent": [], "active": None}
        data.setdefault("recent", [])
        data.setdefault("active", None)
        return data
    except (json.JSONDecodeError, OSError):
        return {"recent": [], "active": None}


def _save_state(state: dict[str, Any]) -> None:
    """Persist the workspace state."""
    _STATE_DIR.mkdir(parents=True, exist_ok=True)
    _STATE_FILE.write_text(
        json.dumps(state, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def get_active_workspace() -> Optional[str]:
    """Return the active workspace path, or None if none set."""
    return _load_state().get("active")


def get_recent_workspaces() -> list[dict]:
    """Return recent workspaces as a list of {path, name, last_used, exists}.

    Workspaces that no longer exist on disk are flagged but kept so the user
    can see and remove them.
    """
    state = _load_state()
    recent = state.get("recent", [])
    result: list[dict] = []
    for entry in recent:
        path = str(entry.get("path", ""))
        p = Path(path)
        result.append({
            "path": path,
            "name": p.name if p.name else path,
            "last_used": entry.get("last_used", ""),
            "exists": p.exists(),
        })
    return result


def set_active_workspace(path: str | Path) -> dict:
    """Set the active workspace. Creates .devflow/ inside it if needed.

    Adds the workspace to the recent list (promoted to top).
    Returns a dict with the workspace info.
    """
    workspace = Path(path).expanduser().resolve()
    if not workspace.exists():
        raise FileNotFoundError(f"Workspace directory does not exist: {workspace}")
    if not workspace.is_dir():
        raise ValueError(f"Not a directory: {workspace}")

    # Ensure .devflow/ exists so pipeline runs can be written
    (workspace / ".devflow").mkdir(parents=True, exist_ok=True)

    state = _load_state()
    state["active"] = str(workspace)

    # Promote to top of recent list
    path_str = str(workspace)
    recent = [r for r in state.get("recent", []) if r.get("path") != path_str]
    recent.insert(0, {"path": path_str, "last_used": _now()})
    state["recent"] = recent[:_MAX_RECENT]

    _save_state(state)
    return {
        "active": str(workspace),
        "name": workspace.name,
        "recent": get_recent_workspaces(),
    }


def remove_recent_workspace(path: str) -> dict:
    """Remove a workspace from the recent list. Returns updated recent list."""
    state = _load_state()
    state["recent"] = [r for r in state.get("recent", []) if r.get("path") != path]
    if state.get("active") == path:
        state["active"] = None
    _save_state(state)
    return {"recent": get_recent_workspaces(), "active": state.get("active")}


def pick_folder_dialog() -> Optional[str]:
    """Open the native macOS Finder folder-picker and return the chosen path.

    Uses osascript to invoke choose folder. Returns None if the user cancels.
    On non-macOS platforms, returns None (the UI should offer manual entry).
    """
    script = (
        'set chosenFolder to choose folder with prompt '
        '"Select a workspace folder for your DevFlow project"'
        '\nreturn POSIX path of chosenFolder'
    )
    try:
        proc = subprocess.run(
            ["osascript", "-e", script],
            capture_output=True, text=True, timeout=120,
        )
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return None
    if proc.returncode != 0:
        # User cancelled or error
        return None
    result = proc.stdout.strip()
    if not result:
        return None
    # osascript returns a trailing slash on POSIX paths
    return result.rstrip("/")


def get_workspace_state() -> dict:
    """Return the full workspace state for the UI: active + recent."""
    state = _load_state()
    active = state.get("active")
    active_info = None
    if active:
        p = Path(active)
        active_info = {
            "path": active,
            "name": p.name,
            "exists": p.exists(),
        }
    return {
        "active": active_info,
        "recent": get_recent_workspaces(),
        "platform": _detect_platform(),
    }


def _detect_platform() -> str:
    """Detect the OS for UI hints (e.g. 'Finder' vs 'file dialog')."""
    import platform
    system = platform.system()
    if system == "Darwin":
        return "macos"
    if system == "Linux":
        return "linux"
    if system == "Windows":
        return "windows"
    return "unknown"


__all__ = [
    "get_active_workspace",
    "get_recent_workspaces",
    "set_active_workspace",
    "remove_recent_workspace",
    "pick_folder_dialog",
    "get_workspace_state",
]
