
"""Mixin for handling actions, agents, and task context operations in the operating layer."""

from __future__ import annotations

from http import HTTPStatus

from devflow.legacy.control_room.browser_action_executor import (
    BrowserActionExecutionError,
    execute_browser_action,
)
from devflow.legacy.control_room.browser_action_policy import resolve_browser_action_command
from devflow.legacy.control_room.agent_catalog import build_agent_catalog
from devflow.legacy.control_room.local_model_inventory import build_local_model_inventory
from devflow.legacy.control_room.local_model_readiness import build_local_model_readiness_plan


class ActionsAgentsTaskContextHandlerMixin:
    """Mixin providing handlers for actions, agents, and task context operations."""

    def _handle_actions_run(self) -> None:
        """Handle running a browser action."""
        try:
            payload = self._read_json_body()
        except ValueError as exc:
            self._send_action_error(str(exc), HTTPStatus.BAD_REQUEST, "invalid_json", exc)
            return

        command = payload.get("command")
        if not isinstance(command, str) or not command.strip():
            self._send_action_error(
                "command is required",
                HTTPStatus.BAD_REQUEST,
                "missing_command",
                ValueError("command is required"),
            )
            return

        try:
            response = execute_browser_action(
                payload,
                self.server.repo_root,
                resolve_command=resolve_browser_action_command,
            )
        except BrowserActionExecutionError as exc:
            self._send_action_error(
                str(exc),
                exc.status,
                exc.error_code,
                exc.cause,
                retriable=exc.retriable,
            )
            return

        self._send_json(response.payload, response.status)

    def _handle_agents_list(self) -> None:
        """Handle listing available agents and their readiness."""
        try:
            root = self.server.repo_root
            catalog = build_agent_catalog(root)
            inventory = build_local_model_inventory(catalog)
            agents = [
                agent
                for agent in catalog.get("hermes_agents", [])
                if isinstance(agent, dict) and agent.get("id")
            ]
            self._send_json(
                {
                    "agents": agents,
                    "local_model_inventory": inventory,
                    "local_model_readiness": build_local_model_readiness_plan(
                        root,
                        agent_catalog=catalog,
                        inventory=inventory,
                    ),
                },
                HTTPStatus.OK,
            )
        except Exception as exc:
            self._send_json_error(str(exc), HTTPStatus.INTERNAL_SERVER_ERROR)

    def _handle_task_write_context(self) -> None:
        """Write implementation context markdown into a task workspace."""
        try:
            payload = self._read_json_body()
            task_id = payload.get("task_id")
            if not isinstance(task_id, str) or not task_id.strip():
                raise ValueError("task_id is required")
            context = payload.get("context")
            if not isinstance(context, str) or not context.strip():
                raise ValueError("context is required")
            root = self._payload_project_root(payload)
            workspace = root / ".devflow" / "workspaces" / task_id
            workspace.mkdir(parents=True, exist_ok=True)
            context_path = workspace / "implementation-context.md"
            context_path.write_text(context, encoding="utf-8")
        except (OSError, ValueError) as exc:
            self._send_json_error(str(exc), HTTPStatus.BAD_REQUEST)
            return
        self._send_json({"status": "ok", "path": str(context_path)}, HTTPStatus.OK)
