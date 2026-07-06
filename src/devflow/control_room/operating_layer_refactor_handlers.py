"""Refactor handler methods extracted from OperatingLayerRequestHandler."""
from __future__ import annotations

from devflow.control_room.refactor_loop import (
    RefactorLoopError,
    load_refactor_run_status,
    require_refactor_approval,
    start_refactor_loop,
)
from devflow.control_room.project_registry import ProjectRegistryError
from http import HTTPStatus


class RefactorHandlerMixin:
    def _handle_refactor_start(self) -> None:
        try:
            payload = self._read_json_body()
            require_refactor_approval(payload)
            root = self._payload_project_root(payload)
            worker = str(payload["worker"])
            result = start_refactor_loop(root, worker=worker)
        except (RefactorLoopError, ProjectRegistryError, OSError, ValueError) as exc:
            self._send_json_error(str(exc), HTTPStatus.BAD_REQUEST)
            return
        except Exception as exc:
            self._send_json_error(f"Refactor loop failed: {exc}", HTTPStatus.INTERNAL_SERVER_ERROR)
            return
        self._send_json(result, HTTPStatus.OK)

    def _handle_refactor_status(self, query: dict[str, list[str]]) -> None:
        try:
            root = self._query_project_root(query)
            run_id = (query.get("run_id") or [None])[0]
            loop_slug = (query.get("loop_slug") or [None])[0]
            payload = load_refactor_run_status(root, run_id=run_id, loop_slug=loop_slug)
        except RefactorLoopError as exc:
            status = HTTPStatus.NOT_FOUND if "not found" in str(exc) else HTTPStatus.BAD_REQUEST
            self._send_json_error(str(exc), status)
            return
        except (ProjectRegistryError, OSError, ValueError) as exc:
            self._send_json_error(str(exc), HTTPStatus.BAD_REQUEST)
            return
        self._send_json(payload, HTTPStatus.OK)
