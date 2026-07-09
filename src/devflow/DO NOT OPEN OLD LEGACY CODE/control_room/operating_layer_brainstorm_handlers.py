"""Brainstorm handler methods extracted from OperatingLayerRequestHandler.

Mixin providing the six brainstorm-related HTTP handler methods.
The host class (OperatingLayerRequestHandler) must provide:
- ``self._send_json(payload, status)``
- ``self._send_json_error(message, status)``
- ``self._read_json_body() -> dict``
- ``self.server.repo_root`` (Path)
"""

from __future__ import annotations

from http import HTTPStatus

from devflow.legacy.control_room.operating_layer_brainstorm_routes import (
    BRAINSTORM_POST_BAD_REQUEST_ERRORS,
    BrainstormRouteBadRequest,
    build_brainstorm_sessions_payload,
    build_brainstorm_transcript_payload,
    build_intent_summary_payload,
    classify_brainstorm_payload,
    create_brainstorm_task_payload,
    escalate_brainstorm_payload,
    run_brainstorm_message_payload,
    start_brainstorm_from_idea_payload,
)


class BrainstormHandlerMixin:
    """Brainstorm route handlers, extracted as a mixin.

    Composed into OperatingLayerRequestHandler via multiple inheritance:
    ``class OperatingLayerRequestHandler(BrainstormHandlerMixin, BaseHTTPRequestHandler)``
    """

    def _handle_brainstorm_sessions(self) -> None:
        try:
            self._send_json(build_brainstorm_sessions_payload(self.server.repo_root), HTTPStatus.OK)
        except Exception as exc:
            self._send_json_error(str(exc), HTTPStatus.INTERNAL_SERVER_ERROR)

    def _handle_brainstorm_transcript(self, query: dict[str, list[str]]) -> None:
        try:
            payload = build_brainstorm_transcript_payload(self.server.repo_root, query)
        except BrainstormRouteBadRequest as exc:
            self._send_json_error(str(exc), HTTPStatus.BAD_REQUEST)
            return
        except Exception as exc:
            self._send_json_error(str(exc), HTTPStatus.INTERNAL_SERVER_ERROR)
            return
        self._send_json(payload, HTTPStatus.OK)

    def _handle_brainstorm_message(self) -> None:
        try:
            payload = self._read_json_body()
            result = run_brainstorm_message_payload(self.server.repo_root, payload)
        except BRAINSTORM_POST_BAD_REQUEST_ERRORS as exc:
            self._send_json_error(str(exc), HTTPStatus.BAD_REQUEST)
            return
        self._send_json(result, HTTPStatus.OK)

    def _handle_brainstorm_escalation(self) -> None:
        try:
            payload = self._read_json_body()
            result = escalate_brainstorm_payload(self.server.repo_root, payload)
        except BRAINSTORM_POST_BAD_REQUEST_ERRORS as exc:
            self._send_json_error(str(exc), HTTPStatus.BAD_REQUEST)
            return
        self._send_json(result, HTTPStatus.OK)

    def _handle_start_from_idea(self) -> None:
        try:
            payload = self._read_json_body()
            result = start_brainstorm_from_idea_payload(self.server.repo_root, payload)
        except BRAINSTORM_POST_BAD_REQUEST_ERRORS as exc:
            self._send_json_error(str(exc), HTTPStatus.BAD_REQUEST)
            return
        self._send_json(result, HTTPStatus.OK)

    def _handle_brainstorm_create_task(self) -> None:
        try:
            payload = self._read_json_body()
            result = create_brainstorm_task_payload(self.server.repo_root, payload)
        except BRAINSTORM_POST_BAD_REQUEST_ERRORS as exc:
            self._send_json_error(str(exc), HTTPStatus.BAD_REQUEST)
            return
        self._send_json(result, HTTPStatus.OK)

    def _handle_brainstorm_classify(self) -> None:
        try:
            payload = self._read_json_body()
            result = classify_brainstorm_payload(self.server.repo_root, payload)
        except BRAINSTORM_POST_BAD_REQUEST_ERRORS as exc:
            self._send_json_error(str(exc), HTTPStatus.BAD_REQUEST)
            return
        self._send_json(result, HTTPStatus.OK)

    def _handle_brainstorm_intent_summary(self) -> None:
        try:
            payload = self._read_json_body()
            result = build_intent_summary_payload(self.server.repo_root, payload)
        except BRAINSTORM_POST_BAD_REQUEST_ERRORS as exc:
            self._send_json_error(str(exc), HTTPStatus.BAD_REQUEST)
            return
        self._send_json(result, HTTPStatus.OK)
