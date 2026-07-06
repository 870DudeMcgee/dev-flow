"""Obsidian handler methods extracted from OperatingLayerRequestHandler.

Mixin providing the five obsidian-related HTTP handler methods.
The host class (OperatingLayerRequestHandler) must provide:
- ``self._send_json(payload, status)``
- ``self._send_json_error(message, status)``
- ``self._read_json_body() -> dict``
- ``self._payload_project_root(payload) -> Path``
- ``self.server.repo_root`` (Path)
"""

from __future__ import annotations

from http import HTTPStatus

from devflow.control_room.obsidian_cards import fetch_obsidian_cards_payload
from devflow.control_room.obsidian_task_bridge import (
    build_obsidian_scout_pack_preview,
    build_obsidian_task_preview,
    create_task_from_obsidian_card,
    create_tasks_from_obsidian_scout_pack,
)
from devflow.control_room.project_registry import ProjectRegistryError


class ObsidianHandlerMixin:
    """Obsidian route handlers, extracted as a mixin.

    Composed into OperatingLayerRequestHandler via multiple inheritance:
    ``class OperatingLayerRequestHandler(ObsidianHandlerMixin, BrainstormHandlerMixin, BaseHTTPRequestHandler)``
    """

    def _handle_obsidian_cards(self) -> None:
        self._send_json(fetch_obsidian_cards_payload(), HTTPStatus.OK)

    def _handle_obsidian_task_preview(self) -> None:
        try:
            payload = self._read_json_body()
            result = build_obsidian_task_preview(payload)
        except (ValueError, OSError) as exc:
            self._send_json_error(str(exc), HTTPStatus.BAD_REQUEST)
            return
        self._send_json(result, HTTPStatus.OK)

    def _handle_obsidian_task_create(self) -> None:
        try:
            payload = self._read_json_body()
            root = self._payload_project_root(payload)
            result = create_task_from_obsidian_card(root, payload)
        except (ProjectRegistryError, ValueError, OSError) as exc:
            self._send_json_error(str(exc), HTTPStatus.BAD_REQUEST)
            return
        self._send_json(result, HTTPStatus.OK)

    def _handle_obsidian_scout_pack_preview(self) -> None:
        try:
            payload = self._read_json_body()
            result = build_obsidian_scout_pack_preview(payload)
        except (ValueError, OSError) as exc:
            self._send_json_error(str(exc), HTTPStatus.BAD_REQUEST)
            return
        self._send_json(result, HTTPStatus.OK)

    def _handle_obsidian_scout_pack_create(self) -> None:
        try:
            payload = self._read_json_body()
            root = self._payload_project_root(payload)
            result = create_tasks_from_obsidian_scout_pack(root, payload)
        except (ProjectRegistryError, ValueError, OSError) as exc:
            self._send_json_error(str(exc), HTTPStatus.BAD_REQUEST)
            return
        self._send_json(result, HTTPStatus.OK)
