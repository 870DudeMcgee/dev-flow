"""Mixin for operating layer browse, snapshot, and repo set handlers."""
from __future__ import annotations

from http import HTTPStatus
from pathlib import Path

from devflow.legacy.control_room.browse_projection import BrowsePathError, build_browse_payload
from devflow.legacy.control_room.operating_layer import render_operating_layer_snapshot_json
from devflow.legacy.control_room.project_registry import ProjectRegistryError, resolve_project_root

BROWSE_MAX_DIRECTORY_ENTRIES = 120
BROWSE_MAX_FILE_BYTES = 64 * 1024


class BrowseSnapshotRepoHandlerMixin:
    def _handle_snapshot(self, query: dict[str, list[str]]) -> None:
        project_id = (query.get("project") or [None])[0]
        try:
            root = self.server.repo_root
            if project_id:
                root = resolve_project_root(self.server.repo_root, project_id).root
        except ProjectRegistryError as exc:
            self._send_json_error(str(exc), HTTPStatus.BAD_REQUEST)
            return
        self._send_text(
            render_operating_layer_snapshot_json(root, project_id=project_id),
            "application/json; charset=utf-8",
        )

    def _handle_browse(self, query: dict[str, list[str]]) -> None:
        try:
            raw_path = (query.get("path") or [None])[0]
            payload = build_browse_payload(
                raw_path,
                max_file_bytes=BROWSE_MAX_FILE_BYTES,
                max_directory_entries=BROWSE_MAX_DIRECTORY_ENTRIES,
            )
            self._send_json(payload, HTTPStatus.OK)
        except BrowsePathError as exc:
            self._send_json_error(str(exc), HTTPStatus.BAD_REQUEST)
        except Exception as exc:
            self._send_json_error(str(exc), HTTPStatus.INTERNAL_SERVER_ERROR)

    def _handle_repo_set(self) -> None:
        try:
            payload = self._read_json_body()
            raw_path = payload.get("path")
            if not isinstance(raw_path, str) or not raw_path.strip():
                self._send_json_error("path is required", HTTPStatus.BAD_REQUEST)
                return
            new_root = Path(raw_path).expanduser().resolve()
            if not new_root.is_dir():
                self._send_json_error(f"Directory does not exist: {new_root}", HTTPStatus.BAD_REQUEST)
                return
            self.server.repo_root = new_root
            has_devflow = (new_root / ".devflow").is_dir()
            self._send_json({
                "path": str(new_root),
                "name": new_root.name,
                "has_devflow": has_devflow,
            }, HTTPStatus.OK)
        except (OSError, ValueError) as exc:
            self._send_json_error(str(exc), HTTPStatus.BAD_REQUEST)
            return
