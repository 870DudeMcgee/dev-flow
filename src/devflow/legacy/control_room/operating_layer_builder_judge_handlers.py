"""Builder-judge handler methods extracted from OperatingLayerRequestHandler."""
from __future__ import annotations

from http import HTTPStatus

from devflow.legacy.control_room.operating_layer_builder_judge_routes import (
    BUILDER_JUDGE_QUALITY_GATE_BAD_REQUEST_ERRORS,
    BUILDER_JUDGE_READ_BAD_REQUEST_ERRORS,
    BUILDER_JUDGE_START_VALIDATION_ERRORS,
    BuilderJudgeRouteNotFound,
    build_builder_judge_list_payload,
    build_builder_judge_quality_gate_payload,
    build_builder_judge_start_payload,
    build_builder_judge_status_payload,
)


class BuilderJudgeHandlerMixin:
    def _handle_builder_judge_start(self) -> None:
        try:
            payload = self._read_json_body()
            result = build_builder_judge_start_payload(self.server.repo_root, payload)
        except BUILDER_JUDGE_START_VALIDATION_ERRORS as exc:
            self._send_action_error(str(exc), HTTPStatus.BAD_REQUEST, "validation_error", exc)
            return
        except OSError as exc:
            self._send_action_error(str(exc), HTTPStatus.INTERNAL_SERVER_ERROR, "os_error", exc, retriable=True)
            return
        except Exception as exc:
            self._send_action_error(f"Builder-judge loop failed: {exc}", HTTPStatus.INTERNAL_SERVER_ERROR, "internal_error", exc, retriable=True)
            return
        self._send_json(result, HTTPStatus.OK)

    def _handle_builder_judge_list(self) -> None:
        try:
            result = build_builder_judge_list_payload(self.server.repo_root)
        except BUILDER_JUDGE_READ_BAD_REQUEST_ERRORS as exc:
            self._send_json_error(str(exc), HTTPStatus.BAD_REQUEST)
            return
        self._send_json(result, HTTPStatus.OK)

    def _handle_builder_judge_status(self, query: dict[str, list[str]]) -> None:
        try:
            result = build_builder_judge_status_payload(self.server.repo_root, query)
        except BuilderJudgeRouteNotFound as exc:
            self._send_json_error(str(exc), HTTPStatus.NOT_FOUND)
            return
        except BUILDER_JUDGE_READ_BAD_REQUEST_ERRORS as exc:
            self._send_json_error(str(exc), HTTPStatus.BAD_REQUEST)
            return
        self._send_json(result, HTTPStatus.OK)

    def _handle_builder_judge_quality_gate(self) -> None:
        """Run a builder-judge quality gate for brainstorm→spec or spec→plan."""
        try:
            payload = self._read_json_body()
            result = build_builder_judge_quality_gate_payload(self.server.repo_root, payload)
        except BUILDER_JUDGE_QUALITY_GATE_BAD_REQUEST_ERRORS as exc:
            self._send_json_error(str(exc), HTTPStatus.BAD_REQUEST)
            return
        except Exception as exc:
            self._send_json_error(f"Quality gate failed: {exc}", HTTPStatus.INTERNAL_SERVER_ERROR)
            return
        self._send_json(result, HTTPStatus.OK)
