from __future__ import annotations

import json
import os
import re
import subprocess
import threading
import webbrowser
from datetime import datetime, timezone
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any, Callable
from urllib.parse import parse_qs, urlsplit

from devflow.control_room.brainstorm import (
    BrainstormError,
    escalate_brainstorm_session,
    run_brainstorm_message,
    start_brainstorm_from_idea,
)
from devflow.control_room.architecture_evidence import (
    ArtifactResolutionError,
    resolve_architecture_artifact,
)
from devflow.control_room.brainstorm_pipeline import (
    create_task_from_brainstorm,
    load_brainstorm_session_snapshot,
)
from devflow.control_room.builder_judge_loop import (
    DEFAULT_BUILDER_PROFILE,
    DEFAULT_JUDGE_PROFILE,
    DEFAULT_MAX_ROUNDS,
    DEFAULT_PASS_THRESHOLD,
    BuilderJudgeConfig,
    BuilderJudgeConfigError,
    BuilderJudgeRunError,
    get_builder_judge_run,
    project_builder_judge_run,
    run_builder_judge_loop,
    run_quality_gate,
)
from devflow.control_room.builder_judge_quality_gate import build_quality_gate_transcript_text
from devflow.control_room.builder_judge_async_runtime import (
    start_builder_judge_async_loop,
    start_workbench_implementation_async,
)
from devflow.control_room import builder_judge_runtime_registry as bj_runtime
from devflow.control_room.env_loader import load_hermes_env_file
from devflow.control_room.browser_action_executor import (
    ACTION_TIMEOUT_SECONDS,
    BrowserActionExecutionError,
    execute_browser_action,
)
from devflow.control_room.browser_action_policy import (
    resolve_browser_action_command,
)
from devflow.control_room.browse_projection import BrowsePathError, build_browse_payload
from devflow.control_room.agent_registry import (
    AgentRegistryError,
)
from devflow.control_room.local_model_ensure import (
    ensure_local_model_profile,
)
from devflow.control_room.local_model_server import (
    LocalModelServerError,
    ensure_local_model_server_for_profile,
)
from devflow.control_room.obsidian_cards import fetch_obsidian_cards_payload
from devflow.control_room.obsidian_task_bridge import (
    build_obsidian_scout_pack_preview,
    build_obsidian_task_preview,
    create_task_from_obsidian_card,
    create_tasks_from_obsidian_scout_pack,
)
from devflow.control_room.operating_layer_assets import APP_CSS, APP_JS, INDEX_HTML
from devflow.control_room.operating_layer import render_operating_layer_snapshot_json
from devflow.control_room.project_registry import ProjectRegistryError, resolve_project_root
from devflow.control_room.refactor_loop import (
    RefactorLoopError,
    load_refactor_run_status,
    require_refactor_approval,
    start_refactor_loop,
)
from devflow.control_room.unified_workbench import (
    WorkbenchError,
    create_workbench_project,
    implementation_config_from_package,
    new_workbench_loop_id,
    prepare_implementation_package,
    run_workbench_implementation,
    setup_gate,
)

BROWSE_MAX_DIRECTORY_ENTRIES = 120
BROWSE_MAX_FILE_BYTES = 64 * 1024


class OperatingLayerHTTPServer(ThreadingHTTPServer):
    def __init__(self, server_address: tuple[str, int], repo_root: Path) -> None:
        super().__init__(server_address, OperatingLayerRequestHandler)
        self.repo_root = repo_root.resolve()


class OperatingLayerRequestHandler(BaseHTTPRequestHandler):
    server: OperatingLayerHTTPServer

    def do_HEAD(self) -> None:
        request = urlsplit(self.path)
        path = request.path
        if path in {"/", "/index.html"}:
            self._send_text_headers(INDEX_HTML, "text/html; charset=utf-8")
            return
        if path == "/app.css":
            self._send_text_headers(APP_CSS, "text/css; charset=utf-8")
            return
        if path == "/app.js":
            self._send_text_headers(APP_JS, "application/javascript; charset=utf-8")
            return
        self.send_error(HTTPStatus.NOT_FOUND)

    def do_GET(self) -> None:
        request = urlsplit(self.path)
        path = request.path
        if path in {"/", "/index.html"}:
            self._send_text(INDEX_HTML, "text/html; charset=utf-8")
            return
        if path == "/app.css":
            self._send_text(APP_CSS, "text/css; charset=utf-8")
            return
        if path == "/app.js":
            self._send_text(APP_JS, "application/javascript; charset=utf-8")
            return
        if path == "/api/snapshot":
            query = parse_qs(request.query)
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
            return
        if path == "/api/agents":
            self._handle_agents_list()
            return
        if path == "/api/obsidian/cards":
            self._handle_obsidian_cards()
            return
        if path == "/architecture/artifact":
            query = parse_qs(request.query)
            self._handle_architecture_artifact(query)
            return
        if path == "/api/browse":
            query = parse_qs(request.query)
            self._handle_browse(query)
            return
        if path == "/api/repo/set":
            self._handle_repo_set()
            return
        if path == "/api/brainstorm/sessions":
            self._handle_brainstorm_sessions()
            return
        if path == "/api/brainstorm/transcript":
            query = parse_qs(request.query)
            self._handle_brainstorm_transcript(query)
            return
        if path == "/api/builder-judge/list":
            self._handle_builder_judge_list()
            return
        if path == "/api/builder-judge/status":
            query = parse_qs(request.query)
            self._handle_builder_judge_status(query)
            return
        if path == "/api/refactor/status":
            query = parse_qs(request.query)
            self._handle_refactor_status(query)
            return
        if path == "/healthz":
            self._send_text(json.dumps({"status": "ok"}) + "\n", "application/json; charset=utf-8")
            return
        self.send_error(HTTPStatus.NOT_FOUND)

    def do_POST(self) -> None:
        request = urlsplit(self.path)
        if request.path == "/api/brainstorm/message":
            self._handle_brainstorm_message()
            return
        if request.path == "/api/brainstorm/escalate":
            self._handle_brainstorm_escalation()
            return
        if request.path == "/api/brainstorm/start-from-idea":
            self._handle_start_from_idea()
            return
        if request.path == "/api/brainstorm/create-task":
            self._handle_brainstorm_create_task()
            return
        if request.path == "/api/obsidian/task-preview":
            self._handle_obsidian_task_preview()
            return
        if request.path == "/api/obsidian/task-create":
            self._handle_obsidian_task_create()
            return
        if request.path == "/api/obsidian/scout-pack-preview":
            self._handle_obsidian_scout_pack_preview()
            return
        if request.path == "/api/obsidian/scout-pack-create":
            self._handle_obsidian_scout_pack_create()
            return
        if request.path == "/api/builder-judge/start":
            self._handle_builder_judge_start()
            return
        if request.path == "/api/builder-judge/quality-gate":
            self._handle_builder_judge_quality_gate()
            return
        if request.path == "/api/workbench/project":
            self._handle_workbench_project()
            return
        if request.path == "/api/workbench/implement":
            self._handle_workbench_implement()
            return
        if request.path == "/api/gates/setup":
            self._handle_gates_setup()
            return
        if request.path == "/api/local-model/ensure":
            self._handle_local_model_ensure()
            return
        if request.path == "/api/refactor/start":
            self._handle_refactor_start()
            return
        if request.path == "/api/task/write-context":
            self._handle_task_write_context()
            return
        if request.path == "/api/repo/set":
            self._handle_repo_set()
            return
        if request.path != "/api/actions/run":
            self.send_error(HTTPStatus.NOT_FOUND)
            return

        try:
            payload = self._read_json_body()
        except ValueError as exc:
            self._send_action_error(str(exc), HTTPStatus.BAD_REQUEST, "invalid_json", exc)
            return

        command = payload.get("command")
        if not isinstance(command, str) or not command.strip():
            self._send_action_error("command is required", HTTPStatus.BAD_REQUEST, "missing_command", ValueError("command is required"))
            return

        try:
            response = execute_browser_action(
                payload,
                self.server.repo_root,
                resolve_command=resolve_browser_action_command,
            )
        except BrowserActionExecutionError as exc:
            self._send_action_error(
                exc.message,
                exc.status,
                exc.error_code,
                exc.cause,
                retriable=exc.retriable,
            )
            return

        self._send_json(response.payload, response.status)

    def _handle_brainstorm_sessions(self) -> None:
        try:
            root = self.server.repo_root
            sessions_dir = root / ".devflow" / "brainstorms"
            sessions = []
            if sessions_dir.exists():
                for entry in sorted(sessions_dir.iterdir(), key=lambda e: e.stat().st_mtime if e.is_dir() else 0, reverse=True):
                    if not entry.is_dir():
                        continue
                    transcript = entry / "transcript.jsonl"
                    if not transcript.exists():
                        continue
                    first_user_msg = ""
                    msg_count = 0
                    has_spec = (entry / "spec.md").exists()
                    has_plan = (entry / "plan.md").exists()
                    has_implementation = (entry / "implementation.md").exists()
                    for line in transcript.read_text(encoding="utf-8").splitlines():
                        if not line.strip():
                            continue
                        try:
                            rec = json.loads(line)
                        except json.JSONDecodeError:
                            continue
                        if isinstance(rec, dict):
                            msg_count += 1
                            if not first_user_msg and rec.get("role") == "user" and rec.get("kind") == "message":
                                first_user_msg = str(rec.get("content", ""))[:80]
                    sessions.append({
                        "session_id": entry.name,
                        "message_count": msg_count,
                        "preview": first_user_msg or "(no messages)",
                        "has_spec": has_spec,
                        "has_plan": has_plan,
                        "has_implementation": has_implementation,
                        "modified_at": datetime.fromtimestamp(entry.stat().st_mtime, tz=timezone.utc).isoformat().replace("+00:00", "Z"),
                    })
            self._send_json({"sessions": sessions}, HTTPStatus.OK)
        except Exception as exc:
            self._send_json_error(str(exc), HTTPStatus.INTERNAL_SERVER_ERROR)

    def _handle_brainstorm_transcript(self, query: dict[str, list[str]]) -> None:
        try:
            root = self.server.repo_root
            session_id = (query.get("session_id") or [None])[0]
            if not session_id:
                self._send_json_error("session_id query parameter is required", HTTPStatus.BAD_REQUEST)
                return
            snapshot = load_brainstorm_session_snapshot(root, session_id=session_id)
            payload = snapshot.model_dump(mode="json")
            self._send_json(payload, HTTPStatus.OK)
        except Exception as exc:
            self._send_json_error(str(exc), HTTPStatus.INTERNAL_SERVER_ERROR)

    def log_message(self, format: str, *args: object) -> None:
        return

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

    def _handle_agents_list(self) -> None:
        try:
            root = self.server.repo_root
            from devflow.control_room.agent_catalog import build_agent_catalog
            from devflow.control_room.local_model_inventory import build_local_model_inventory
            from devflow.control_room.local_model_readiness import build_local_model_readiness_plan

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

    def _handle_obsidian_cards(self) -> None:
        self._send_json(fetch_obsidian_cards_payload(), HTTPStatus.OK)

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

    def _handle_brainstorm_message(self) -> None:
        try:
            payload = self._read_json_body()
            root = self._payload_project_root(payload)
            message = payload.get("message")
            if not isinstance(message, str):
                raise BrainstormError("message is required")
            session_id = payload.get("session_id")
            if session_id is not None and not isinstance(session_id, str):
                raise BrainstormError("session_id must be a string")
            profile_id = payload.get("profile_id")
            if profile_id is not None and not isinstance(profile_id, str):
                raise BrainstormError("profile_id must be a string")
            result = run_brainstorm_message(root=root, message=message, session_id=session_id, profile_id=profile_id)
        except (BrainstormError, ProjectRegistryError, OSError, ValueError) as exc:
            self._send_json_error(str(exc), HTTPStatus.BAD_REQUEST)
            return
        self._send_json(result, HTTPStatus.OK)

    def _handle_brainstorm_escalation(self) -> None:
        try:
            payload = self._read_json_body()
            root = self._payload_project_root(payload)
            session_id = payload.get("session_id")
            stage = payload.get("stage")
            title = payload.get("title")
            if not isinstance(session_id, str):
                raise BrainstormError("session_id is required")
            if not isinstance(stage, str):
                raise BrainstormError("stage is required")
            if title is not None and not isinstance(title, str):
                raise BrainstormError("title must be a string")
            definition_of_done = payload.get("definition_of_done")
            if definition_of_done is not None and not isinstance(definition_of_done, str):
                raise BrainstormError("definition_of_done must be a string")
            profile_id = payload.get("profile_id")
            if profile_id is not None and not isinstance(profile_id, str):
                raise BrainstormError("profile_id must be a string")
            use_model = payload.get("use_model")
            if use_model is not None and not isinstance(use_model, bool):
                raise BrainstormError("use_model must be a boolean")
            result = escalate_brainstorm_session(
                root=root, session_id=session_id, stage=stage, title=title,
                definition_of_done=definition_of_done,
                profile_id=profile_id, use_model=use_model,
            )
        except (BrainstormError, ProjectRegistryError, OSError, ValueError) as exc:
            self._send_json_error(str(exc), HTTPStatus.BAD_REQUEST)
            return
        self._send_json(result, HTTPStatus.OK)

    def _handle_start_from_idea(self) -> None:
        try:
            payload = self._read_json_body()
            root = self.server.repo_root
            idea_id_raw = payload.get("idea_id")
            if not isinstance(idea_id_raw, str):
                raise BrainstormError("idea_id is required and must be a string")
            idea_id = idea_id_raw.strip().upper()
            if not re.fullmatch(r"I-[0-9]{4}", idea_id):
                raise BrainstormError(f"idea_id must match I-NNNN pattern, got: {idea_id_raw!r}")
            profile_id = payload.get("profile_id")
            if isinstance(profile_id, str) and not profile_id.strip():
                profile_id = None
            result = start_brainstorm_from_idea(root, idea_id)
            if result.get("status") == "reuse":
                result["session_id"] = result["session_id"]  # keep original existing name
        except (BrainstormError, ProjectRegistryError, OSError, ValueError) as exc:
            self._send_json_error(str(exc), HTTPStatus.BAD_REQUEST)
            return
        self._send_json(result, HTTPStatus.OK)

    def _handle_brainstorm_create_task(self) -> None:
        try:
            payload = self._read_json_body()
            root = self._payload_project_root(payload)
            session_id = payload.get("session_id")
            title = payload.get("title")
            if not isinstance(session_id, str):
                raise BrainstormError("session_id is required and must be a string")
            if not isinstance(title, str) or not title.strip():
                raise BrainstormError("title is required and must be a non-empty string")
            definition_of_done = payload.get("definition_of_done")
            if definition_of_done is not None and not isinstance(definition_of_done, str):
                raise BrainstormError("definition_of_done must be a string")
            source_idea_id = payload.get("source_idea_id")
            if source_idea_id is not None and not isinstance(source_idea_id, str):
                raise BrainstormError("source_idea_id must be a string")
            result = create_task_from_brainstorm(
                root=root,
                session_id=session_id,
                stage="implementation",
                title=title,
                definition_of_done=definition_of_done or None,
                source_idea_id=source_idea_id or None,
            )
        except (BrainstormError, ProjectRegistryError, OSError, ValueError) as exc:
            self._send_json_error(str(exc), HTTPStatus.BAD_REQUEST)
            return
        self._send_json(result, HTTPStatus.OK)

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

    def _handle_builder_judge_start(self) -> None:
        try:
            payload = self._read_json_body()
            root = self._payload_project_root(payload)
            definition_of_done = payload.get("definition_of_done")
            if not isinstance(definition_of_done, str) or not definition_of_done.strip():
                raise ValueError("definition_of_done is required")
            starting_point = payload.get("starting_point")
            if starting_point is not None and not isinstance(starting_point, str):
                raise ValueError("starting_point must be a string")
            builder_profile_id = payload.get("builder_profile_id")
            if builder_profile_id is not None and not isinstance(builder_profile_id, str):
                raise ValueError("builder_profile_id must be a string")
            judge_profile_id = payload.get("judge_profile_id")
            if judge_profile_id is not None and not isinstance(judge_profile_id, str):
                raise ValueError("judge_profile_id must be a string")
            pass_threshold_raw = payload.get("pass_threshold")
            pass_threshold = int(pass_threshold_raw) if isinstance(pass_threshold_raw, (int, float, str)) else None
            max_rounds_raw = payload.get("max_rounds")
            max_rounds = int(max_rounds_raw) if isinstance(max_rounds_raw, (int, float, str)) else None
            escalate_raw = payload.get("escalate_on_max_rounds")
            escalate_on_max_rounds = bool(escalate_raw) if escalate_raw is not None else True
            async_mode = bool(payload.get("async", True))

            config = BuilderJudgeConfig(
                definition_of_done=definition_of_done,
                starting_point=starting_point or None,
                builder_profile_id=builder_profile_id or DEFAULT_BUILDER_PROFILE,
                judge_profile_id=judge_profile_id or DEFAULT_JUDGE_PROFILE,
                pass_threshold=pass_threshold if pass_threshold is not None else DEFAULT_PASS_THRESHOLD,
                max_rounds=max_rounds if max_rounds is not None else DEFAULT_MAX_ROUNDS,
                escalate_on_max_rounds=escalate_on_max_rounds,
            )
        except ValueError as exc:
            self._send_action_error(str(exc), HTTPStatus.BAD_REQUEST, "validation_error", exc)
            return
        except (BuilderJudgeConfigError, BuilderJudgeRunError, ProjectRegistryError) as exc:
            self._send_action_error(str(exc), HTTPStatus.BAD_REQUEST, "validation_error", exc)
            return
        except OSError as exc:
            self._send_action_error(str(exc), HTTPStatus.INTERNAL_SERVER_ERROR, "os_error", exc, retriable=True)
            return

        except Exception as exc:
            self._send_action_error(f"Builder-judge config failed: {exc}", HTTPStatus.INTERNAL_SERVER_ERROR, "internal_error", exc, retriable=True)
            return

        # Validate config before starting
        from devflow.control_room.builder_judge_loop import _validate_config, _generate_loop_id
        try:
            _validate_config(config)
        except BuilderJudgeConfigError as exc:
            self._send_action_error(str(exc), HTTPStatus.BAD_REQUEST, "validation_error", exc)
            return

        if async_mode:
            loop_id = _generate_loop_id()
            start_payload = start_builder_judge_async_loop(
                root,
                config,
                loop_id=loop_id,
                run_loop=run_builder_judge_loop,
            )
            self._send_json(start_payload, HTTPStatus.OK)
        else:
            # Synchronous mode (for CLI or testing)
            try:
                run = run_builder_judge_loop(root, config)
                result = project_builder_judge_run(run, root=root)
            except (BuilderJudgeConfigError, BuilderJudgeRunError, ProjectRegistryError, ValueError) as exc:
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
            root = self.server.repo_root
            loops = bj_runtime._bj_list_visible_loops(root)
        except (OSError, ValueError) as exc:
            self._send_json_error(str(exc), HTTPStatus.BAD_REQUEST)
            return
        self._send_json({"loops": loops}, HTTPStatus.OK)

    def _handle_builder_judge_status(self, query: dict[str, list[str]]) -> None:
        loop_id = (query.get("loop_id") or [None])[0]
        if not loop_id:
            self._send_json_error("loop_id is required", HTTPStatus.BAD_REQUEST)
            return
        try:
            root = self.server.repo_root
        except (OSError, ValueError) as exc:
            self._send_json_error(str(exc), HTTPStatus.BAD_REQUEST)
            return
        # Check in-memory registry first (for running loops)
        run_data = bj_runtime._bj_get_running_loop(loop_id)
        if run_data is not None:
            # If still running, also try to read incremental file state
            if run_data.get("status") == "running":
                file_run = get_builder_judge_run(root, loop_id)
                if file_run and len(file_run.get("rounds", [])) > len(run_data.get("rounds", [])):
                    self._send_json(file_run, HTTPStatus.OK)
                    return
            self._send_json(run_data, HTTPStatus.OK)
            return
        # Fall back to file
        try:
            run = get_builder_judge_run(root, loop_id)
        except (OSError, ValueError) as exc:
            self._send_json_error(str(exc), HTTPStatus.BAD_REQUEST)
            return
        if run is None:
            self._send_json_error(f"Loop not found: {loop_id}", HTTPStatus.NOT_FOUND)
            return
        self._send_json(run, HTTPStatus.OK)

    def _handle_builder_judge_quality_gate(self) -> None:
        """Run a builder-judge quality gate for brainstorm→spec or spec→plan."""
        try:
            payload = self._read_json_body()
            root = self._payload_project_root(payload)
            session_id = payload.get("session_id")
            if not isinstance(session_id, str) or not session_id.strip():
                raise ValueError("session_id is required")
            stage = payload.get("stage")
            if not isinstance(stage, str) or stage not in ("spec", "plan"):
                raise ValueError("stage must be 'spec' or 'plan'")
            transcript_text = build_quality_gate_transcript_text(root, session_id)

            builder_profile_id = payload.get("builder_profile_id") or DEFAULT_BUILDER_PROFILE
            judge_profile_id = payload.get("judge_profile_id") or DEFAULT_JUDGE_PROFILE
            pass_threshold = int(payload.get("pass_threshold", DEFAULT_PASS_THRESHOLD))
            max_rounds = int(payload.get("max_rounds", 3))

            run = run_quality_gate(
                root,
                stage=stage,
                transcript_text=transcript_text,
                builder_profile_id=builder_profile_id,
                judge_profile_id=judge_profile_id,
                pass_threshold=pass_threshold,
                max_rounds=max_rounds,
            )
            result = project_builder_judge_run(run, root=root)
        except (BuilderJudgeConfigError, BuilderJudgeRunError, ProjectRegistryError, OSError, ValueError) as exc:
            self._send_json_error(str(exc), HTTPStatus.BAD_REQUEST)
            return
        except Exception as exc:
            self._send_json_error(f"Quality gate failed: {exc}", HTTPStatus.INTERNAL_SERVER_ERROR)
            return
        self._send_json(result, HTTPStatus.OK)

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

    def _payload_project_root(self, payload: dict[str, object]) -> Path:
        project_id = payload.get("project")
        root = self.server.repo_root
        if isinstance(project_id, str) and project_id.strip():
            root = resolve_project_root(self.server.repo_root, project_id.strip()).root
        return root

    def _query_project_root(self, query: dict[str, list[str]]) -> Path:
        project_id = (query.get("project") or [None])[0]
        root = self.server.repo_root
        if isinstance(project_id, str) and project_id.strip():
            root = resolve_project_root(self.server.repo_root, project_id.strip()).root
        return root

    def _read_json_body(self) -> dict[str, object]:
        length_header = self.headers.get("Content-Length")
        try:
            length = int(length_header or "0")
        except ValueError as exc:
            raise ValueError("invalid Content-Length") from exc
        if length <= 0:
            raise ValueError("JSON body is required")
        raw = self.rfile.read(length)
        try:
            payload = json.loads(raw.decode("utf-8"))
        except json.JSONDecodeError as exc:
            raise ValueError("invalid JSON body") from exc
        if not isinstance(payload, dict):
            raise ValueError("JSON object body is required")
        return payload

    def _send_text(self, body: str, content_type: str) -> None:
        encoded = body.encode("utf-8")
        self._send_text_headers(body, content_type)
        try:
            self.wfile.write(encoded)
        except (BrokenPipeError, ConnectionResetError):
            return

    def _send_text_headers(self, body: str, content_type: str) -> None:
        encoded = body.encode("utf-8")
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", content_type)
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Length", str(len(encoded)))
        self.end_headers()

    def _send_artifact(self, body: bytes, content_type: str) -> None:
        # Architecture evidence artifacts are served inline-only with strict,
        # no-sniff, no-store headers. Graphify HTML is rendered inside a
        # sandboxed iframe on the client; we never expose arbitrary path reads.
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", content_type)
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Disposition", "inline")
        self.send_header("Content-Security-Policy", "sandbox; default-src 'none'")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        try:
            self.wfile.write(body)
        except (BrokenPipeError, ConnectionResetError):
            return

    def _send_json(self, payload: dict[str, object], status: HTTPStatus) -> None:
        body = json.dumps(payload) + "\n"
        encoded = body.encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Length", str(len(encoded)))
        self.end_headers()
        try:
            self.wfile.write(encoded)
        except (BrokenPipeError, ConnectionResetError):
            return

    def _send_json_error(self, message: str, status: HTTPStatus) -> None:
        body = json.dumps({"error": message}) + "\n"
        encoded = body.encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Length", str(len(encoded)))
        self.end_headers()
        try:
            self.wfile.write(encoded)
        except (BrokenPipeError, ConnectionResetError):
            return

    def _send_action_error(
        self,
        message: str,
        status: HTTPStatus,
        error_code: str,
        exc: Exception,
        retriable: bool = False,
    ) -> None:
        self._send_json(
            {
                "error": message,
                "error_code": error_code,
                "error_type": type(exc).__name__,
                "retriable": bool(retriable),
            },
            status,
        )

def find_listening_pids(port: int) -> list[int]:
    """Return PIDs of processes listening on ``port`` (TCP). macOS/Linux via lsof.

    Returns an empty list if lsof is unavailable or nothing is listening.
    """
    try:
        result = subprocess.run(
            ["lsof", "-ti", f"tcp:{port}", "-sTCP:LISTEN"],
            capture_output=True,
            text=True,
            timeout=10,
        )
    except (FileNotFoundError, subprocess.SubprocessError):
        return []
    pids: list[int] = []
    for line in result.stdout.split():
        try:
            pids.append(int(line.strip()))
        except ValueError:
            continue
    # Never report our own process as a stale listener.
    return [pid for pid in dict.fromkeys(pids) if pid != os.getpid()]


def stop_listening_processes(port: int, *, timeout_seconds: float = 5.0) -> list[int]:
    """Terminate processes listening on ``port``. Sends SIGTERM, then SIGKILL if
    a process does not exit within ``timeout_seconds``. Returns the PIDs acted on.

    This is intentionally scoped to the single TCP port, so it only ever touches a
    stale operating-layer server, never unrelated processes.
    """
    import signal
    import time

    pids = find_listening_pids(port)
    if not pids:
        return []
    for pid in pids:
        try:
            os.kill(pid, signal.SIGTERM)
        except (ProcessLookupError, PermissionError):
            pass
    deadline = time.monotonic() + timeout_seconds
    while time.monotonic() < deadline:
        if not find_listening_pids(port):
            return pids
        time.sleep(0.2)
    # Escalate to SIGKILL for anything still holding the port.
    for pid in find_listening_pids(port):
        try:
            os.kill(pid, signal.SIGKILL)
        except (ProcessLookupError, PermissionError):
            pass
    return pids


def check_server_health(host: str, port: int, *, timeout_seconds: float = 5.0) -> dict[str, Any]:
    """Probe a running operating-layer server. Unlike ``/healthz`` (a static
    'ok'), this also fetches ``/api/snapshot`` and confirms it returns parseable,
    non-empty JSON — the data path the browser UI actually depends on.

    Returns a dict with ``healthz_ok``, ``snapshot_ok``, ``snapshot_bytes``,
    ``overall_ok``, and ``detail``.
    """
    import urllib.error
    import urllib.request

    base = f"http://{host}:{port}"
    result: dict[str, Any] = {
        "healthz_ok": False,
        "snapshot_ok": False,
        "snapshot_bytes": 0,
        "overall_ok": False,
        "detail": "",
    }

    def _get(path: str) -> tuple[int, bytes]:
        req = urllib.request.Request(base + path, method="GET")
        with urllib.request.urlopen(req, timeout=timeout_seconds) as resp:
            return resp.status, resp.read()

    try:
        status, body = _get("/healthz")
        result["healthz_ok"] = status == 200 and b"ok" in body
    except (urllib.error.URLError, OSError) as exc:
        result["detail"] = f"server not reachable on {base}: {exc}"
        return result

    try:
        status, body = _get("/api/snapshot")
        result["snapshot_bytes"] = len(body)
        if status != 200:
            result["detail"] = f"/api/snapshot returned HTTP {status}"
        elif not body.strip():
            result["detail"] = "/api/snapshot returned an empty body (stale or crashed server)"
        else:
            try:
                json.loads(body)
                result["snapshot_ok"] = True
            except json.JSONDecodeError as exc:
                result["detail"] = f"/api/snapshot returned non-JSON: {exc}"
    except (urllib.error.URLError, OSError) as exc:
        result["detail"] = f"/api/snapshot request failed: {exc}"

    result["overall_ok"] = bool(result["healthz_ok"] and result["snapshot_ok"])
    if result["overall_ok"] and not result["detail"]:
        result["detail"] = f"healthz ok, snapshot ok ({result['snapshot_bytes']} bytes)"
    return result


def run_operating_layer_server(
    repo_root: Path,
    *,
    host: str = "127.0.0.1",
    port: int = 8765,
    open_browser: bool = False,
    ready_callback: Callable[[OperatingLayerHTTPServer], None] | None = None,
) -> None:
    load_hermes_env_file()
    server = OperatingLayerHTTPServer((host, port), repo_root)
    if ready_callback:
        ready_callback(server)
    url = f"http://{server.server_address[0]}:{server.server_address[1]}"
    if open_browser:
        threading.Timer(0.1, lambda: webbrowser.open(url)).start()
    try:
        server.serve_forever()
    finally:
        server.server_close()
