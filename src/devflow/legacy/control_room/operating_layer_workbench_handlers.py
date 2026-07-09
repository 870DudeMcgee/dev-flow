
"""Workbench handler mixin for operating layer request handlers."""
from __future__ import annotations

from http import HTTPStatus

from devflow.legacy.control_room.builder_judge_loop import (
    DEFAULT_BUILDER_PROFILE,
    DEFAULT_JUDGE_PROFILE,
    DEFAULT_PASS_THRESHOLD,
    BuilderJudgeConfigError,
    BuilderJudgeRunError,
    run_builder_judge_loop,
)
from devflow.legacy.control_room.builder_judge_async_runtime import start_workbench_implementation_async
from devflow.legacy.control_room.unified_workbench import (
    WorkbenchError,
    create_workbench_project,
    implementation_config_from_package,
    new_workbench_loop_id,
    prepare_implementation_package,
    run_workbench_implementation,
)
from devflow.legacy.control_room.project_registry import ProjectRegistryError


class WorkbenchHandlerMixin:
    def _handle_workbench_project(self) -> None:
        try:
            payload = self._read_json_body()
            result = create_workbench_project(payload)
        except (WorkbenchError, ProjectRegistryError, OSError, ValueError) as exc:
            self._send_json_error(str(exc), HTTPStatus.BAD_REQUEST)
            return
        except Exception as exc:
            self._send_json_error(f"Workbench project create failed: {exc}", HTTPStatus.INTERNAL_SERVER_ERROR)
            return
        self._send_json(result, HTTPStatus.OK)

    def _handle_workbench_implement(self) -> None:
        try:
            payload = self._read_json_body()
            root = self._payload_project_root(payload)
            session_id = payload.get("session_id")
            if not isinstance(session_id, str) or not session_id.strip():
                raise WorkbenchError("session_id is required")
            title = payload.get("title")
            if title is not None and not isinstance(title, str):
                raise WorkbenchError("title must be a string")
            definition_of_done = payload.get("definition_of_done")
            if definition_of_done is not None and not isinstance(definition_of_done, str):
                raise WorkbenchError("definition_of_done must be a string")
            builder_profile_id = payload.get("builder_profile_id")
            if builder_profile_id is not None and not isinstance(builder_profile_id, str):
                raise WorkbenchError("builder_profile_id must be a string")
            judge_profile_id = payload.get("judge_profile_id")
            if judge_profile_id is not None and not isinstance(judge_profile_id, str):
                raise WorkbenchError("judge_profile_id must be a string")
            pass_threshold_raw = payload.get("pass_threshold")
            pass_threshold = int(pass_threshold_raw) if isinstance(pass_threshold_raw, (int, float, str)) else DEFAULT_PASS_THRESHOLD
            max_rounds_raw = payload.get("max_rounds")
            max_rounds = int(max_rounds_raw) if isinstance(max_rounds_raw, (int, float, str)) else 3
            async_mode = bool(payload.get("async", True))

            if not async_mode:
                result = run_workbench_implementation(
                    root,
                    session_id=session_id,
                    title=title or None,
                    definition_of_done=definition_of_done or None,
                    builder_profile_id=builder_profile_id or DEFAULT_BUILDER_PROFILE,
                    judge_profile_id=judge_profile_id or DEFAULT_JUDGE_PROFILE,
                    pass_threshold=pass_threshold,
                    max_rounds=max_rounds,
                )
                self._send_json(result.model_dump(mode="json"), HTTPStatus.OK)
                return

            package = prepare_implementation_package(
                root,
                session_id=session_id,
                title=title or None,
                definition_of_done=definition_of_done or None,
            )
            config = implementation_config_from_package(
                package,
                builder_profile_id=builder_profile_id or DEFAULT_BUILDER_PROFILE,
                judge_profile_id=judge_profile_id or DEFAULT_JUDGE_PROFILE,
                pass_threshold=pass_threshold,
                max_rounds=max_rounds,
            )
            loop_id = new_workbench_loop_id()
        except WorkbenchError as exc:
            self._send_action_error(str(exc), HTTPStatus.CONFLICT, "workbench_conflict", exc, retriable=False)
            return
        except (BuilderJudgeConfigError, BuilderJudgeRunError, ProjectRegistryError, ValueError) as exc:
            self._send_action_error(str(exc), HTTPStatus.BAD_REQUEST, "validation_error", exc)
            return
        except OSError as exc:
            self._send_action_error(str(exc), HTTPStatus.INTERNAL_SERVER_ERROR, "os_error", exc, retriable=True)
            return
        except Exception as exc:
            self._send_action_error(f"Workbench implement failed: {exc}", HTTPStatus.INTERNAL_SERVER_ERROR, "internal_error", exc, retriable=True)
            return

        running_payload = start_workbench_implementation_async(
            root,
            session_id=session_id,
            loop_id=loop_id,
            package=package,
            config=config,
            run_loop=run_builder_judge_loop,
        )
        self._send_json(running_payload, HTTPStatus.OK)
