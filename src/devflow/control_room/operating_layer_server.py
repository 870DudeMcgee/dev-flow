from __future__ import annotations

import json
import os
import shlex
import subprocess
import sys
import threading
import webbrowser
from datetime import datetime, timezone
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Callable
from urllib.parse import parse_qs, urlsplit

from devflow.control_room.brainstorm import (
    BrainstormError,
    escalate_brainstorm_session,
    run_brainstorm_message,
)
from devflow.control_room.brainstorm_pipeline import load_brainstorm_pipeline_detail
from devflow.control_room.builder_judge_loop import (
    DEFAULT_BUILDER_PROFILE,
    DEFAULT_JUDGE_PROFILE,
    DEFAULT_MAX_ROUNDS,
    DEFAULT_PASS_THRESHOLD,
    BuilderJudgeConfig,
    BuilderJudgeConfigError,
    BuilderJudgeRunError,
    get_builder_judge_run,
    list_builder_judge_loops,
    run_builder_judge_loop,
    run_quality_gate,
)
from devflow.control_room.env_loader import load_hermes_env_file
from devflow.control_room.operating_layer_assets import APP_CSS, APP_JS, INDEX_HTML
from devflow.control_room.operating_layer import render_operating_layer_snapshot_json
from devflow.control_room.project_registry import ProjectRegistryError, resolve_project_root
from devflow.control_room.supervisor_surface import (
    APPROVAL_REQUIRED_EVIDENCE_WRITING,
    APPROVAL_REQUIRED_GIT,
    APPROVAL_REQUIRED_TASK_STATE,
    APPROVAL_REQUIRED_WORKER_RUNTIME,
    PURE_READ_ONLY,
    classify_supervisor_command,
)


ACTION_TIMEOUT_SECONDS = 20
ACTION_OUTPUT_LIMIT = 12000
ACTION_APPROVAL_PHRASE = "I approve this exact Dev-Flow command"

# In-memory registry of running builder-judge loops (loop_id → BuilderJudgeRun)
_bj_running_loops: dict[str, dict] = {}
_bj_threads: dict[str, threading.Thread] = {}


class OperatingLayerHTTPServer(ThreadingHTTPServer):
    def __init__(self, server_address: tuple[str, int], repo_root: Path) -> None:
        super().__init__(server_address, OperatingLayerRequestHandler)
        self.repo_root = repo_root.resolve()


class OperatingLayerRequestHandler(BaseHTTPRequestHandler):
    server: OperatingLayerHTTPServer

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
        if request.path == "/api/builder-judge/start":
            self._handle_builder_judge_start()
            return
        if request.path == "/api/builder-judge/quality-gate":
            self._handle_builder_judge_quality_gate()
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
            self._send_json_error(str(exc), HTTPStatus.BAD_REQUEST)
            return

        command = payload.get("command")
        if not isinstance(command, str) or not command.strip():
            self._send_json_error("command is required", HTTPStatus.BAD_REQUEST)
            return

        classification = classify_supervisor_command(command)
        approved_idea_capture = False
        approved_idea_evidence = False
        approved_task_creation = False
        approved_task_close = False
        approved_cleanup_preview = False
        approved_shell_worker_run = False
        approved_verification = False
        approved_promotion = False
        approved_agent_add_provider = False
        approved_agent_add_model = False
        approved_agent_propose_patch = False
        if classification["safety_class"] != PURE_READ_ONLY:
            try:
                approved_idea_capture = _is_approved_idea_capture(payload, command, classification)
                approved_idea_evidence = _is_approved_idea_evidence(payload, command, classification)
                approved_task_creation = _is_approved_task_creation(payload, command, classification)
                approved_task_close = _is_approved_task_close(payload, command, classification)
                approved_cleanup_preview = _is_approved_cleanup_preview(payload, command, classification)
                approved_shell_worker_run = _is_approved_shell_worker_run(payload, command, classification)
                approved_verification = _is_approved_task_verification(payload, command, classification)
                approved_promotion = _is_approved_task_promotion(payload, command, classification)
                approved_agent_add_provider = _is_approved_agent_add_provider(payload, command, classification)
                approved_agent_add_model = _is_approved_agent_add_model(payload, command, classification)
                approved_agent_propose_patch = _is_approved_agent_propose_patch(payload, command, classification)
            except ValueError as exc:
                self._send_json_error(str(exc), HTTPStatus.BAD_REQUEST)
                return
        if classification["safety_class"] != PURE_READ_ONLY and not (
            approved_idea_capture
            or approved_idea_evidence
            or approved_task_creation
            or approved_task_close
            or approved_cleanup_preview
            or approved_shell_worker_run
            or approved_verification
            or approved_promotion
            or approved_agent_add_provider
            or approved_agent_add_model
            or approved_agent_propose_patch
        ):
            self._send_json(
                {
                    "executed": False,
                    "requires_human_approval": bool(classification["requires_human_approval"]),
                    "classification": classification,
                    "message": classification["why_not_auto_runnable"]
                    or "command is not supervisor-safe for browser execution",
                },
                HTTPStatus.CONFLICT,
            )
            return

        project_id = payload.get("project")
        try:
            root = self.server.repo_root
            if isinstance(project_id, str) and project_id.strip():
                root = resolve_project_root(self.server.repo_root, project_id.strip()).root
            if approved_idea_capture:
                args = _approved_idea_capture_command_args(command)
            elif approved_idea_evidence:
                args = _approved_idea_evidence_command_args(command)
            elif approved_task_creation:
                args = _approved_task_creation_command_args(command)
            elif approved_task_close:
                args = _approved_task_close_command_args(command)
            elif approved_cleanup_preview:
                args = _approved_cleanup_preview_command_args(command)
            elif approved_agent_add_provider:
                args = _approved_agent_add_provider_command_args(command)
            elif approved_agent_add_model:
                args = _approved_agent_add_model_command_args(command)
            elif approved_agent_propose_patch:
                args = _approved_agent_propose_patch_command_args(command)
            elif approved_shell_worker_run:
                args = _approved_shell_worker_run_command_args(command)
            elif approved_verification:
                args = _approved_task_verification_command_args(command)
            elif approved_promotion:
                args = _approved_task_promotion_command_args(command)
            else:
                args = _supervisor_read_only_command_args(command)
            context_path = _write_promotion_context(root, command, payload) if approved_promotion else None
        except (ProjectRegistryError, OSError, ValueError) as exc:
            self._send_json_error(str(exc), HTTPStatus.BAD_REQUEST)
            return

        env = _devflow_subprocess_env()
        try:
            completed = subprocess.run(
                args,
                cwd=root,
                env=env,
                text=True,
                input="y\n" if approved_promotion else None,
                capture_output=True,
                timeout=ACTION_TIMEOUT_SECONDS,
                check=False,
            )
        except subprocess.TimeoutExpired as exc:
            self._send_json(
                {
                    "executed": True,
                    "timed_out": True,
                    "exit_code": None,
                    "classification": classification,
                    "stdout": _truncate_text(exc.stdout or ""),
                    "stderr": _truncate_text(exc.stderr or f"Command timed out after {ACTION_TIMEOUT_SECONDS}s"),
                    "output_truncated": _output_was_truncated(exc.stdout or "", exc.stderr or ""),
                },
                HTTPStatus.REQUEST_TIMEOUT,
            )
            return

        stdout = completed.stdout or ""
        stderr = completed.stderr or ""
        self._send_json(
            {
                "executed": True,
                "timed_out": False,
                "exit_code": completed.returncode,
                "requires_human_approval": bool(classification["requires_human_approval"]),
                "classification": classification,
                "stdout": _truncate_text(stdout),
                "stderr": _truncate_text(stderr),
                "output_truncated": _output_was_truncated(stdout, stderr),
                "context_path": context_path,
            },
            HTTPStatus.OK,
        )

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
                    messages: list[dict[str, object]] = []
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
            transcript_path = root / ".devflow" / "brainstorms" / session_id / "transcript.jsonl"
            if not transcript_path.exists():
                pipeline = load_brainstorm_pipeline_detail(root, session_id=session_id, records=[])
                self._send_json(
                    {
                        "session_id": session_id,
                        "messages": [],
                        "spec": None,
                        "plan": None,
                        "implementation": None,
                        "pipeline": pipeline.model_dump(mode="json"),
                    },
                    HTTPStatus.OK,
                )
                return
            messages: list[dict[str, object]] = []
            for line in transcript_path.read_text(encoding="utf-8").splitlines():
                if not line.strip():
                    continue
                try:
                    rec = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if isinstance(rec, dict):
                    messages.append(rec)
            session_dir = transcript_path.parent
            spec_content = None
            spec_path = session_dir / "spec.md"
            if spec_path.exists():
                spec_content = spec_path.read_text(encoding="utf-8")
            plan_content = None
            plan_path = session_dir / "plan.md"
            if plan_path.exists():
                plan_content = plan_path.read_text(encoding="utf-8")
            implementation_content = None
            implementation_path = session_dir / "implementation.md"
            if implementation_path.exists():
                implementation_content = implementation_path.read_text(encoding="utf-8")
            pipeline = load_brainstorm_pipeline_detail(root, session_id=session_id, records=messages)
            self._send_json({
                "session_id": session_id,
                "messages": messages,
                "spec": spec_content,
                "plan": plan_content,
                "implementation": implementation_content,
                "pipeline": pipeline.model_dump(mode="json"),
            }, HTTPStatus.OK)
        except Exception as exc:
            self._send_json_error(str(exc), HTTPStatus.INTERNAL_SERVER_ERROR)

    def log_message(self, format: str, *args: object) -> None:
        return

    def _handle_browse(self, query: dict[str, list[str]]) -> None:
        try:
            raw_path = (query.get("path") or [None])[0]
            if raw_path is None or raw_path == "~":
                browse_path = Path.home()
            else:
                browse_path = Path(raw_path).expanduser().resolve()

            # If it's a file, return its content
            if browse_path.is_file():
                try:
                    content = browse_path.read_text(encoding="utf-8")
                    self._send_json({"path": str(browse_path), "content": content, "is_file": True}, HTTPStatus.OK)
                except UnicodeDecodeError:
                    self._send_json({"path": str(browse_path), "content": "(binary file)", "is_file": True}, HTTPStatus.OK)
                return

            if not browse_path.is_dir():
                self._send_json_error(f"Not a directory: {browse_path}", HTTPStatus.BAD_REQUEST)
                return
            entries = []
            for entry in sorted(browse_path.iterdir(), key=lambda e: (not e.is_dir(), e.name.lower())):
                if entry.name.startswith("."):
                    continue
                is_dir = entry.is_dir()
                has_devflow = is_dir and (entry / ".devflow").is_dir()
                entries.append({
                    "name": entry.name,
                    "path": str(entry),
                    "is_dir": is_dir,
                    "has_devflow": has_devflow,
                })
            self._send_json({
                "current_path": str(browse_path),
                "parent_path": str(browse_path.parent) if browse_path != browse_path.parent else None,
                "entries": entries,
            }, HTTPStatus.OK)
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
            from devflow.control_room.agent_registry import (
                is_remote_advisory_agent,
                load_agent_registry,
                load_provider_registry,
            )
            registry = load_agent_registry(root)
            providers = load_provider_registry(root)
            agents = []
            for agent in registry.enabled_agents():
                provider = providers.providers.get(agent.provider)
                if not provider:
                    continue
                is_remote = is_remote_advisory_agent(agent, provider=provider)
                is_ollama = provider.provider == "ollama" or agent.adapter == "ollama_chat"
                if not is_remote and not is_ollama:
                    continue
                agents.append({
                    "id": agent.id,
                    "model": agent.model,
                    "label": agent.model_role_name or agent.id,
                    "purpose": agent.purpose or "",
                    "tier": agent.tier,
                    "secondary_roles": agent.secondary_roles,
                    "provider": agent.provider,
                    "is_local": is_ollama,
                })
            self._send_json({"agents": agents}, HTTPStatus.OK)
        except Exception as exc:
            self._send_json_error(str(exc), HTTPStatus.INTERNAL_SERVER_ERROR)

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
        except (BuilderJudgeConfigError, BuilderJudgeRunError, ProjectRegistryError, OSError, ValueError) as exc:
            self._send_json_error(str(exc), HTTPStatus.BAD_REQUEST)
            return
        except Exception as exc:
            self._send_json_error(f"Builder-judge config failed: {exc}", HTTPStatus.INTERNAL_SERVER_ERROR)
            return

        # Validate config before starting
        from devflow.control_room.builder_judge_loop import _validate_config, _generate_loop_id
        try:
            _validate_config(config)
        except BuilderJudgeConfigError as exc:
            self._send_json_error(str(exc), HTTPStatus.BAD_REQUEST)
            return

        if async_mode:
            # Start in background thread, return immediately
            loop_id = _generate_loop_id()

            def _run_bj_loop():
                try:
                    run = run_builder_judge_loop(root, config, loop_id=loop_id)
                    _bj_running_loops[loop_id] = run.model_dump(mode="json")
                except Exception as exc:
                    _bj_running_loops[loop_id] = {
                        "loop_id": loop_id,
                        "status": "failed",
                        "error": str(exc),
                        "rounds": [],
                        "config": config.model_dump(mode="json"),
                        "started_at": datetime.now(timezone.utc).isoformat(),
                        "finished_at": datetime.now(timezone.utc).isoformat(),
                        "stop_reason": "background_thread_error",
                        "next_safe_action": str(exc),
                    }

            thread = threading.Thread(target=_run_bj_loop, daemon=True)
            _bj_threads[loop_id] = thread
            _bj_running_loops[loop_id] = {
                "loop_id": loop_id,
                "run_id": "",
                "status": "running",
                "config": config.model_dump(mode="json"),
                "rounds": [],
                "started_at": datetime.now(timezone.utc).isoformat(),
                "finished_at": None,
                "stop_reason": "",
                "next_safe_action": "",
            }
            thread.start()

            self._send_json(_bj_running_loops[loop_id], HTTPStatus.OK)
        else:
            # Synchronous mode (for CLI or testing)
            try:
                run = run_builder_judge_loop(root, config)
                result = run.model_dump(mode="json")
            except (BuilderJudgeConfigError, BuilderJudgeRunError, ProjectRegistryError, OSError, ValueError) as exc:
                self._send_json_error(str(exc), HTTPStatus.BAD_REQUEST)
                return
            except Exception as exc:
                self._send_json_error(f"Builder-judge loop failed: {exc}", HTTPStatus.INTERNAL_SERVER_ERROR)
                return
            self._send_json(result, HTTPStatus.OK)

    def _handle_builder_judge_list(self) -> None:
        try:
            root = self.server.repo_root
            loops = list_builder_judge_loops(root)
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
        if loop_id in _bj_running_loops:
            run_data = _bj_running_loops[loop_id]
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

            # Read brainstorm transcript
            from devflow.control_room.brainstorm import _read_transcript, _session_dir
            transcript_path = _session_dir(root, session_id) / "transcript.jsonl"
            records = _read_transcript(transcript_path)
            if not records:
                raise ValueError(f"brainstorm session has no transcript: {session_id}")

            # Build transcript text for the builder
            transcript_lines = []
            for record in records:
                role = str(record.get("role") or "unknown")
                content = str(record.get("content") or "").strip()
                if content:
                    transcript_lines.append(f"### {role.title()}\n\n{content}\n")
            transcript_text = "\n".join(transcript_lines)

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
            result = run.model_dump(mode="json")
        except (BuilderJudgeConfigError, BuilderJudgeRunError, ProjectRegistryError, OSError, ValueError) as exc:
            self._send_json_error(str(exc), HTTPStatus.BAD_REQUEST)
            return
        except Exception as exc:
            self._send_json_error(f"Quality gate failed: {exc}", HTTPStatus.INTERNAL_SERVER_ERROR)
            return
        self._send_json(result, HTTPStatus.OK)

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
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", content_type)
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Length", str(len(encoded)))
        self.end_headers()
        try:
            self.wfile.write(encoded)
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


def _supervisor_read_only_command_args(command: str) -> list[str]:
    tokens = shlex.split(command)
    return _devflow_command_args_from_tokens(tokens)


def _approved_idea_capture_command_args(command: str) -> list[str]:
    tokens = shlex.split(command)
    normalized = _normalize_devflow_command_tokens(tokens)
    if len(normalized) < 4 or normalized[1:3] != ["idea", "capture"]:
        raise ValueError("only approved idea capture may run from the operating layer")
    allowed_value_options = {"--title", "--source", "--tag"}
    index = 3
    idea_texts: list[str] = []
    while index < len(normalized):
        token = normalized[index]
        if token in allowed_value_options:
            if index + 1 >= len(normalized) or normalized[index + 1].startswith("-"):
                raise ValueError(f"approved browser idea capture requires a value after {token}")
            if token == "--title" and _is_placeholder_text(normalized[index + 1], field="title"):
                raise ValueError("approved browser idea capture requires a concrete title when --title is used")
            index += 2
            continue
        if token.startswith("-"):
            raise ValueError("approved browser idea capture allows only --title, --source, and --tag")
        idea_texts.append(token)
        index += 1
    if len(idea_texts) != 1:
        raise ValueError("approved browser idea capture requires one quoted idea body")
    if _is_placeholder_text(idea_texts[0], field="idea"):
        raise ValueError("approved browser idea capture requires concrete brainstorm text")
    return _devflow_command_args_from_tokens(tokens)


def _approved_idea_evidence_command_args(command: str) -> list[str]:
    tokens = shlex.split(command)
    normalized = _normalize_devflow_command_tokens(tokens)
    if len(normalized) != 6 or normalized[1] != "idea" or normalized[2] not in {"park", "archive"}:
        raise ValueError("only approved idea park/archive may run from the operating layer")
    idea_id = normalized[3]
    if not idea_id or idea_id.startswith("-"):
        raise ValueError("approved idea park/archive requires an idea id")
    if normalized[4] != "--reason":
        raise ValueError("approved idea park/archive requires exactly --reason")
    reason = normalized[5]
    if _is_placeholder_text(reason, field="reason") or len(reason.strip()) < 3:
        raise ValueError("approved idea park/archive requires a concrete reason")
    return _devflow_command_args_from_tokens(tokens)


def _approved_task_creation_command_args(command: str) -> list[str]:
    tokens = shlex.split(command)
    normalized = _normalize_devflow_command_tokens(tokens)
    if len(normalized) < 4 or normalized[1:3] != ["task", "create"]:
        raise ValueError("only approved task creation may run from the operating layer")
    allowed_flags = {"--git-worktree"}
    allowed_value_options = {"--project", "--definition-of-done"}
    index = 3
    titles: list[str] = []
    while index < len(normalized):
        token = normalized[index]
        if token in allowed_flags:
            index += 1
            continue
        if token in allowed_value_options:
            if index + 1 >= len(normalized) or normalized[index + 1].startswith("-"):
                if token == "--project":
                    raise ValueError("approved browser task creation requires a project id after --project")
                raise ValueError("approved browser task creation requires definition text after --definition-of-done")
            if token == "--definition-of-done" and _is_placeholder_text(normalized[index + 1], field="definition-of-done"):
                raise ValueError("approved browser task creation requires concrete definition-of-done text")
            index += 2
            continue
        if token.startswith("-"):
            raise ValueError("approved browser task creation allows only --project, --git-worktree, and --definition-of-done")
        titles.append(token)
        index += 1
    if len(titles) != 1:
        raise ValueError("approved browser task creation requires one quoted task title")
    if _is_placeholder_text(titles[0], field="title"):
        raise ValueError("approved browser task creation requires a concrete task title")
    return _devflow_command_args_from_tokens(tokens)


def _approved_task_close_command_args(command: str) -> list[str]:
    tokens = shlex.split(command)
    normalized = _normalize_devflow_command_tokens(tokens)
    if len(normalized) < 4 or normalized[1:3] != ["task", "close"]:
        raise ValueError("only approved task close may run from the operating layer")
    task_id = normalized[3]
    if not task_id or task_id.startswith("-"):
        raise ValueError("task close command requires a task id")
    values = _parse_exact_options(
        normalized[4:],
        value_options={"--outcome", "--reason"},
        flags=set(),
        command_label="approved task close",
    )
    for option, field in (("--outcome", "outcome"), ("--reason", "reason")):
        value = values.get(option, "")
        if _is_placeholder_text(value, field=field) or len(value.strip()) < 3:
            raise ValueError(f"approved task close requires a concrete {field}")
    return _devflow_command_args_from_tokens(tokens)


def _approved_cleanup_preview_command_args(command: str) -> list[str]:
    tokens = shlex.split(command)
    normalized = _normalize_devflow_command_tokens(tokens)
    if len(normalized) != 5 or normalized[1:3] != ["task", "cleanup"]:
        raise ValueError("only approved cleanup preview may run from the operating layer")
    task_id = normalized[3]
    if not task_id or task_id.startswith("-"):
        raise ValueError("cleanup preview command requires a task id")
    if normalized[4] != "--preview":
        raise ValueError("browser cleanup is limited to --preview")
    return _devflow_command_args_from_tokens(tokens)


def _approved_shell_worker_run_command_args(command: str) -> list[str]:
    tokens = shlex.split(command)
    normalized = _normalize_devflow_command_tokens(tokens)
    if len(normalized) < 6 or normalized[1:3] != ["task", "run"]:
        raise ValueError("only approved shell worker runs may run from the operating layer")
    task_id = normalized[3]
    if not task_id or task_id.startswith("-"):
        raise ValueError("shell worker run requires a task id")
    if "--" not in normalized:
        raise ValueError("approved browser shell worker run requires a command after '--'")
    separator = normalized.index("--")
    options = normalized[4:separator]
    command_tokens = normalized[separator + 1 :]
    worker = None
    index = 0
    while index < len(options):
        token = options[index]
        if token == "--worker":
            if index + 1 >= len(options):
                raise ValueError("approved browser shell worker run requires --worker shell")
            worker = options[index + 1]
            index += 2
            continue
        if token == "--project":
            if index + 1 >= len(options) or options[index + 1].startswith("-"):
                raise ValueError("approved browser shell worker run requires a project id after --project")
            index += 2
            continue
        if token == "--timeout-seconds":
            if index + 1 >= len(options) or not options[index + 1].isdigit():
                raise ValueError("approved browser shell worker run requires a numeric --timeout-seconds value")
            index += 2
            continue
        raise ValueError("approved browser shell worker run allows only --project, --worker shell, and --timeout-seconds")
    if worker != "shell":
        raise ValueError("browser worker execution is limited to --worker shell")
    shell_command = " ".join(command_tokens).strip()
    if _is_placeholder_text(shell_command, field="command"):
        raise ValueError("approved browser shell worker run requires a concrete command")
    if _looks_like_provider_or_local_model_command(command_tokens):
        raise ValueError("provider and local-model commands cannot run from the browser shell-worker path")
    return _devflow_command_args_from_tokens(tokens)


def _approved_task_verification_command_args(command: str) -> list[str]:
    tokens = shlex.split(command)
    normalized = _normalize_devflow_command_tokens(tokens)
    if len(normalized) < 5 or normalized[1:3] != ["task", "verify"]:
        raise ValueError("only approved task verification may run from the operating layer")
    task_id = normalized[3]
    if not task_id or task_id.startswith("-"):
        raise ValueError("task verification command requires a task id")
    if "--shell" not in normalized:
        raise ValueError('approved browser verification requires --shell "<command>"')
    shell_index = normalized.index("--shell")
    if shell_index + 1 >= len(normalized):
        raise ValueError('approved browser verification requires --shell "<command>"')
    shell_command = normalized[shell_index + 1].strip()
    if not shell_command or shell_command == "<command>":
        raise ValueError("approved browser verification requires a concrete shell command")
    return _devflow_command_args_from_tokens(tokens)


def _approved_task_promotion_command_args(command: str) -> list[str]:
    tokens = shlex.split(command)
    normalized = _normalize_devflow_command_tokens(tokens)
    if len(normalized) < 4 or normalized[1:3] != ["task", "promote"]:
        raise ValueError("only approved task promotion may run from the operating layer")
    task_id = normalized[3]
    if not task_id or task_id.startswith("-"):
        raise ValueError("task promotion command requires a task id")
    allowed_options = {"--project"}
    index = 4
    while index < len(normalized):
        token = normalized[index]
        if token not in allowed_options:
            raise ValueError("approved browser promotion allows only the optional --project flag")
        if token == "--project":
            if index + 1 >= len(normalized) or normalized[index + 1].startswith("-"):
                raise ValueError("approved browser promotion requires a project id after --project")
            index += 2
            continue
        index += 1
    return _devflow_command_args_from_tokens(tokens)


def _approved_agent_add_provider_command_args(command: str) -> list[str]:
    tokens = shlex.split(command)
    normalized = _normalize_devflow_command_tokens(tokens)
    if len(normalized) < 4 or normalized[1:3] != ["agent", "add-provider"]:
        raise ValueError("only approved agent add-provider may run from the operating layer")
    provider_id = normalized[3]
    if _is_placeholder_text(provider_id, field="provider"):
        raise ValueError("approved provider onboarding requires a concrete provider id")
    values = _parse_exact_options(
        normalized[4:],
        value_options={"--adapter", "--base-url", "--api-key-env", "--timeout-seconds"},
        flags={"--json"},
        command_label="approved provider onboarding",
    )
    if "--adapter" not in values or "--base-url" not in values:
        raise ValueError("approved provider onboarding requires --adapter and --base-url")
    if _is_placeholder_text(values["--adapter"], field="adapter"):
        raise ValueError("approved provider onboarding requires a concrete adapter")
    if _is_placeholder_text(values["--base-url"], field="url"):
        raise ValueError("approved provider onboarding requires a concrete base URL")
    if "--timeout-seconds" in values and not values["--timeout-seconds"].isdigit():
        raise ValueError("approved provider onboarding requires a numeric --timeout-seconds value")
    return _devflow_command_args_from_tokens(tokens)


def _approved_agent_add_model_command_args(command: str) -> list[str]:
    tokens = shlex.split(command)
    normalized = _normalize_devflow_command_tokens(tokens)
    if len(normalized) < 3 or normalized[1:3] != ["agent", "add-model"]:
        raise ValueError("only approved agent add-model may run from the operating layer")
    values = _parse_exact_options(
        normalized[3:],
        value_options={"--provider", "--model", "--authority", "--role", "--profile-id"},
        flags={"--json"},
        command_label="approved model onboarding",
    )
    for option in ("--provider", "--model", "--authority", "--role"):
        if option not in values:
            raise ValueError(f"approved model onboarding requires {option}")
    if values["--authority"] not in {"read-only", "advisory", "patch-proposer", "disabled"}:
        raise ValueError("approved model onboarding authority must be read-only, advisory, patch-proposer, or disabled")
    for option, field in (("--provider", "provider"), ("--model", "model"), ("--role", "role")):
        if _is_placeholder_text(values[option], field=field):
            raise ValueError(f"approved model onboarding requires a concrete {field}")
    return _devflow_command_args_from_tokens(tokens)


def _approved_agent_propose_patch_command_args(command: str) -> list[str]:
    tokens = shlex.split(command)
    normalized = _normalize_devflow_command_tokens(tokens)
    if len(normalized) < 3 or normalized[1:3] != ["agent", "propose-patch"]:
        raise ValueError("only approved agent propose-patch may run from the operating layer")
    values = _parse_exact_options(
        normalized[3:],
        value_options={"--task", "--profile"},
        flags={"--json"},
        command_label="approved patch-proposal model run",
    )
    if "--task" not in values or "--profile" not in values:
        raise ValueError("approved patch proposal requires --task and --profile")
    if _is_placeholder_text(values["--task"], field="task-id") or _is_placeholder_text(values["--profile"], field="profile"):
        raise ValueError("approved patch proposal requires concrete task and profile ids")
    return _devflow_command_args_from_tokens(tokens)


def _parse_exact_options(
    tokens: list[str],
    *,
    value_options: set[str],
    flags: set[str],
    command_label: str,
) -> dict[str, str]:
    values: dict[str, str] = {}
    index = 0
    while index < len(tokens):
        token = tokens[index]
        if token in flags:
            index += 1
            continue
        if token in value_options:
            if index + 1 >= len(tokens) or tokens[index + 1].startswith("-"):
                raise ValueError(f"{command_label} requires a value after {token}")
            values[token] = tokens[index + 1]
            index += 2
            continue
        if token.startswith("-"):
            allowed = ", ".join(sorted(value_options | flags))
            raise ValueError(f"{command_label} allows only {allowed}")
        raise ValueError(f"{command_label} does not allow positional value '{token}'")
    return values


def _write_promotion_context(root: Path, command: str, payload: dict[str, object]) -> str | None:
    note = payload.get("context_note")
    if not isinstance(note, str) or not note.strip():
        return None
    _approved_task_promotion_command_args(command)
    task_id = _promotion_task_id(command)
    task_path = root / ".devflow" / "tasks" / task_id
    if not task_path.is_dir():
        raise ValueError(f"task not found for promotion context: {task_id}")
    cleaned = note.strip()
    if len(cleaned) > 4000:
        cleaned = cleaned[:4000].rstrip() + "\n\n[truncated]"
    context_path = task_path / "promotion-context.md"
    timestamp = datetime.now(timezone.utc).isoformat()
    entry = (
        f"\n## {timestamp}\n\n"
        f"- command: `{command}`\n"
        f"- source: operating-layer approval\n\n"
        f"{cleaned}\n"
    )
    if context_path.exists():
        with context_path.open("a", encoding="utf-8") as handle:
            handle.write(entry)
    else:
        context_path.write_text("# Human Promotion Context\n" + entry, encoding="utf-8")
    return context_path.relative_to(root).as_posix()


def _promotion_task_id(command: str) -> str:
    normalized = _normalize_devflow_command_tokens(shlex.split(command))
    if len(normalized) < 4:
        raise ValueError("task promotion command requires a task id")
    return normalized[3]


def _is_approved_idea_capture(payload: dict[str, object], command: str, classification: dict[str, object]) -> bool:
    if classification["safety_class"] != APPROVAL_REQUIRED_EVIDENCE_WRITING:
        return False
    try:
        _approved_idea_capture_command_args(command)
    except ValueError:
        return False
    return _approval_payload_matches(payload, command)


def _is_approved_idea_evidence(payload: dict[str, object], command: str, classification: dict[str, object]) -> bool:
    if classification["safety_class"] != APPROVAL_REQUIRED_EVIDENCE_WRITING:
        return False
    try:
        _approved_idea_evidence_command_args(command)
    except ValueError:
        return False
    return _approval_payload_matches(payload, command)


def _is_approved_task_creation(payload: dict[str, object], command: str, classification: dict[str, object]) -> bool:
    if classification["safety_class"] != APPROVAL_REQUIRED_TASK_STATE:
        return False
    try:
        _approved_task_creation_command_args(command)
    except ValueError:
        return False
    return _approval_payload_matches(payload, command)


def _is_approved_task_close(payload: dict[str, object], command: str, classification: dict[str, object]) -> bool:
    if classification["safety_class"] != APPROVAL_REQUIRED_TASK_STATE:
        return False
    try:
        _approved_task_close_command_args(command)
    except ValueError:
        return False
    return _approval_payload_matches(payload, command)


def _is_approved_cleanup_preview(payload: dict[str, object], command: str, classification: dict[str, object]) -> bool:
    if classification["safety_class"] != APPROVAL_REQUIRED_TASK_STATE:
        return False
    try:
        _approved_cleanup_preview_command_args(command)
    except ValueError:
        return False
    return _approval_payload_matches(payload, command)


def _is_approved_shell_worker_run(payload: dict[str, object], command: str, classification: dict[str, object]) -> bool:
    if classification["safety_class"] != APPROVAL_REQUIRED_WORKER_RUNTIME:
        return False
    try:
        _approved_shell_worker_run_command_args(command)
    except ValueError:
        return False
    return _approval_payload_matches(payload, command)


def _is_approved_task_verification(payload: dict[str, object], command: str, classification: dict[str, object]) -> bool:
    if classification["safety_class"] != APPROVAL_REQUIRED_WORKER_RUNTIME:
        return False
    try:
        _approved_task_verification_command_args(command)
    except ValueError:
        return False
    return _approval_payload_matches(payload, command)


def _is_approved_task_promotion(payload: dict[str, object], command: str, classification: dict[str, object]) -> bool:
    if classification["safety_class"] != APPROVAL_REQUIRED_GIT:
        return False
    try:
        _approved_task_promotion_command_args(command)
    except ValueError:
        return False
    return _approval_payload_matches(payload, command)


def _is_approved_agent_add_provider(payload: dict[str, object], command: str, classification: dict[str, object]) -> bool:
    if classification["safety_class"] != APPROVAL_REQUIRED_TASK_STATE:
        return False
    try:
        _approved_agent_add_provider_command_args(command)
    except ValueError:
        return False
    return _approval_payload_matches(payload, command)


def _is_approved_agent_add_model(payload: dict[str, object], command: str, classification: dict[str, object]) -> bool:
    if classification["safety_class"] != APPROVAL_REQUIRED_TASK_STATE:
        return False
    try:
        _approved_agent_add_model_command_args(command)
    except ValueError:
        return False
    return _approval_payload_matches(payload, command)


def _is_approved_agent_propose_patch(payload: dict[str, object], command: str, classification: dict[str, object]) -> bool:
    if classification["safety_class"] != APPROVAL_REQUIRED_WORKER_RUNTIME:
        return False
    try:
        _approved_agent_propose_patch_command_args(command)
    except ValueError:
        return False
    return _approval_payload_matches(payload, command)


def _approval_payload_matches(payload: dict[str, object], command: str) -> bool:
    if payload.get("human_approved") is not True:
        return False
    if payload.get("approval_phrase") != ACTION_APPROVAL_PHRASE:
        return False
    if payload.get("approved_command") != command:
        return False
    return True


def _is_placeholder_text(value: str, *, field: str) -> bool:
    normalized = " ".join(value.strip().lower().split())
    placeholders = {
        "",
        "...",
        "todo",
        "tbd",
        "placeholder",
        f"<{field}>",
        field,
    }
    if field == "command":
        placeholders.update({"your command", "run command", "shell command"})
    if field == "idea":
        placeholders.update({"your idea", "rough idea", "brainstorm", "brainstorm here"})
    if field == "title":
        placeholders.update({"task title", "untitled", "new task"})
    if field == "definition-of-done":
        placeholders.update({"definition of done", "done criteria", "completion criteria", "your definition of done"})
    if field in {"provider", "model", "profile", "task-id", "adapter", "url", "role"}:
        placeholders.update({
            f"<{field}>",
            field.replace("-", " "),
            f"your {field}",
            f"{field} id",
            f"{field}-id",
        })
    return normalized in placeholders


def _looks_like_provider_or_local_model_command(command_tokens: list[str]) -> bool:
    if not command_tokens:
        return False
    lowered = [token.lower() for token in command_tokens]
    joined = " ".join(lowered)
    if lowered[:3] == ["devflow", "task", "local"]:
        return True
    if lowered[:3] == ["devflow", "agent", "run"]:
        return True
    if lowered[:3] == ["devflow", "agent", "advise"]:
        return True
    if lowered[:3] == ["devflow", "agent", "propose-patch"]:
        return True
    if lowered[:3] == ["devflow", "agent", "add-model"]:
        return True
    if lowered[:3] == ["devflow", "agent", "add-provider"]:
        return True
    provider_markers = (
        "ollama",
        "openai",
        "anthropic",
        "gemini",
        "claude",
        "aider",
        "opencode",
        "qwen",
        "qwopus",
        "gemma",
    )
    return any(marker in joined for marker in provider_markers)


def _devflow_command_args_from_tokens(tokens: list[str]) -> list[str]:
    normalized = _normalize_devflow_command_tokens(tokens)
    if not normalized:
        raise ValueError("command is required")
    if normalized[0] == "devflow":
        return [sys.executable, "-m", "devflow", *normalized[1:]]
    raise ValueError("only devflow commands may run from the operating layer")


def _normalize_devflow_command_tokens(tokens: list[str]) -> list[str]:
    if tokens and tokens[0] == "run":
        tokens = tokens[1:]
    if not tokens:
        return []
    if len(tokens) >= 4 and tokens[1:3] == ["-m", "devflow.cli"]:
        return ["devflow", *tokens[3:]]
    return tokens


def _devflow_subprocess_env() -> dict[str, str]:
    env = os.environ.copy()
    src_root = Path(__file__).resolve().parents[2]
    existing = env.get("PYTHONPATH")
    env["PYTHONPATH"] = f"{src_root}{os.pathsep}{existing}" if existing else src_root.as_posix()
    return env


def _truncate_text(value: str) -> str:
    if len(value) <= ACTION_OUTPUT_LIMIT:
        return value
    return value[:ACTION_OUTPUT_LIMIT] + "\n...[truncated]"


def _output_was_truncated(stdout: str, stderr: str) -> bool:
    return len(stdout) > ACTION_OUTPUT_LIMIT or len(stderr) > ACTION_OUTPUT_LIMIT
