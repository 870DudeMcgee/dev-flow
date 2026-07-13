"""Deterministic, source-backed orientation for DevFlow sessions.

This module deliberately checks local indexes without starting model lanes or
calling an LLM.  It is the safe first orientation gate; callers may escalate
only when its returned packet says that grounding is incomplete.
"""
from __future__ import annotations

import json
from pathlib import Path
import shutil
import subprocess
from typing import Callable


class ContextQualityService:
    """Merge Context Map, Graphify, and codebase-memory freshness evidence."""

    def __init__(self, index_status: Callable[[Path], dict] | None = None) -> None:
        self._index_status = index_status or self._codebase_memory_status

    @staticmethod
    def _codebase_memory_status(root: Path) -> dict:
        """Read index status without calling Agent Proxy or starting a model lane."""
        binary = shutil.which("codebase-memory-mcp")
        if binary is None:
            return {"status": "unavailable", "reason": "codebase-memory-mcp is not installed"}
        try:
            projects = subprocess.run(
                [binary, "cli", "list_projects", "{}"],
                capture_output=True, text=True, timeout=10, check=True,
            )
            data = json.loads(projects.stdout)
            project = next(
                (item for item in data.get("projects", []) if item.get("root_path") == str(root)),
                None,
            )
            if not isinstance(project, dict) or not project.get("name"):
                return {"status": "unavailable", "reason": "project is not indexed"}
            result = subprocess.run(
                [binary, "cli", "index_status", json.dumps({"project": project["name"]})],
                capture_output=True, text=True, timeout=10, check=True,
            )
            status = json.loads(result.stdout)
            return status if isinstance(status, dict) else {"status": "unavailable"}
        except (OSError, ValueError, subprocess.SubprocessError, json.JSONDecodeError) as exc:
            return {"status": "unavailable", "reason": str(exc)}

    @staticmethod
    def _load_json(path: Path) -> dict | None:
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return None
        return data if isinstance(data, dict) else None

    def orient(self, goal: str, repo: Path | str | None = None, web_policy: str = "forbid") -> dict:
        """Return a compact grounded-or-blocked packet without hidden model starts."""
        if not isinstance(goal, str) or not goal.strip():
            raise ValueError("goal must be a nonblank string")
        if web_policy not in {"forbid", "allowed", "required"}:
            raise ValueError("web_policy must be forbid, allowed, or required")
        root = Path(repo or Path.cwd()).resolve()
        source_path = root / ".context-map" / "source-index.json"
        graph_path = root / ".context-map" / "graphify-freshness.json"
        source = self._load_json(source_path)
        graph = self._load_json(graph_path)
        files = source.get("files") if isinstance(source, dict) else None
        source_ready = isinstance(files, list) and bool(files)
        cbm = self._index_status(root)
        cbm_ready = isinstance(cbm, dict) and cbm.get("status") == "ready"
        graph_ready = isinstance(graph, dict)
        providers = {
            "context_map": {"status": "ready" if source_ready else "unavailable", "path": str(source_path)},
            "graphify": {"status": "ready" if graph_ready else "unavailable", "path": str(graph_path)},
            "agent_proxy": cbm if isinstance(cbm, dict) else {"status": "unavailable"},
        }
        grounded = source_ready and (cbm_ready or graph_ready)
        return {
            "schema_version": 1,
            "status": "grounded" if grounded else "blocked",
            "goal": goal.strip(),
            "repo_root": str(root),
            "web_policy": web_policy,
            "providers": providers,
            "next_action": (
                {"instruction": "Use compact local index evidence; web research is required."}
                if web_policy == "required"
                else {"instruction": "Refresh the unavailable local index before dispatching workers."}
                if not grounded
                else {"instruction": "Dispatch only anchored, bounded work packets."}
            ),
        }


__all__ = ["ContextQualityService"]
