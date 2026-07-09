
"""Gates and local model handler mixin for operating layer request handlers."""
from __future__ import annotations

from devflow.legacy.control_room.architecture_evidence import ArtifactResolutionError, resolve_architecture_artifact
from devflow.legacy.control_room.agent_registry import AgentRegistryError
from devflow.legacy.control_room.local_model_ensure import ensure_local_model_profile
from devflow.legacy.control_room.local_model_server import LocalModelServerError, ensure_local_model_server_for_profile
from devflow.legacy.control_room.project_registry import ProjectRegistryError, resolve_project_root
from devflow.legacy.control_room.unified_workbench import WorkbenchError, setup_gate
from http import HTTPStatus
from pathlib import Path


class GatesLocalModelHandlerMixin:
    def _handle_gates_setup(self) -> None:
        try:
            payload = self._read_json_body()
            root = self._payload_project_root(payload)
            result = setup_gate(root, payload)
        except (WorkbenchError, ProjectRegistryError, OSError, ValueError) as exc:
            self._send_json_error(str(exc), HTTPStatus.BAD_REQUEST)
            return
        except Exception as exc:
            self._send_json_error(f"Gate setup failed: {exc}", HTTPStatus.INTERNAL_SERVER_ERROR)
            return
        self._send_json(result, HTTPStatus.OK)

    def _handle_local_model_ensure(self) -> None:
        try:
            payload = self._read_json_body()
            root = self._payload_project_root(payload)
            profile_id = payload.get("profile_id")
            if not isinstance(profile_id, str) or not profile_id.strip():
                self._send_action_error("profile_id is required", HTTPStatus.BAD_REQUEST, "validation_error", ValueError("profile_id is required"))
                return
            result = ensure_local_model_profile(
                root,
                profile_id.strip(),
                ensure_server=ensure_local_model_server_for_profile,
            )
        except KeyError as exc:
            message = str(exc.args[0]) if exc.args else str(exc)
            self._send_action_error(message, HTTPStatus.NOT_FOUND, "missing_profile", exc, retriable=False)
            return
        except LocalModelServerError as exc:
            self._send_action_error(str(exc), HTTPStatus.CONFLICT, "local_model_server_error", exc, retriable=True)
            return
        except (ProjectRegistryError, ValueError, AgentRegistryError) as exc:
            self._send_action_error(str(exc), HTTPStatus.BAD_REQUEST, "validation_error", exc)
            return
        except OSError as exc:
            self._send_action_error(str(exc), HTTPStatus.INTERNAL_SERVER_ERROR, "os_error", exc, retriable=True)
            return
        except Exception as exc:
            self._send_action_error(f"Local model ensure failed: {exc}", HTTPStatus.INTERNAL_SERVER_ERROR, "internal_error", exc, retriable=True)
            return

        self._send_json(result, HTTPStatus.OK)

    def _handle_architecture_artifact(self, query: dict[str, list[str]]) -> None:
        artifact_id = (query.get("id") or [None])[0]
        project_id = (query.get("project") or [None])[0]
        try:
            root = self.server.repo_root
            if project_id:
                root = resolve_project_root(self.server.repo_root, project_id).root
        except ProjectRegistryError as exc:
            self._send_json_error(str(exc), HTTPStatus.BAD_REQUEST)
            return
        try:
            resolved = resolve_architecture_artifact(root, artifact_id or "")
        except ArtifactResolutionError as exc:
            self._send_json_error(str(exc), HTTPStatus(exc.status))
            return
        try:
            body = Path(resolved.absolute_path).read_bytes()
        except OSError:
            self._send_json_error("artifact is unavailable", HTTPStatus.NOT_FOUND)
            return
        self._send_artifact(body, resolved.content_type)
