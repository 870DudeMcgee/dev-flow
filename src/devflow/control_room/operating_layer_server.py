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
    list_builder_judge_loops,
    run_builder_judge_loop,
    run_quality_gate,
)
from devflow.control_room.env_loader import load_hermes_env_file
from devflow.control_room.browser_action_policy import (
    promotion_task_id_from_command,
    resolve_browser_action_command,
)
from devflow.control_room.operating_layer_assets import APP_CSS, APP_JS, INDEX_HTML
from devflow.control_room.operating_layer import render_operating_layer_snapshot_json
from devflow.control_room.project_registry import ProjectRegistryError, resolve_project_root
from devflow.control_room.supervisor_surface import classify_supervisor_command


ACTION_TIMEOUT_SECONDS = 20
ACTION_OUTPUT_LIMIT = 12000

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
        if request.path == "/api/brainstorm/start-from-idea":
            self._handle_start_from_idea()
            return
        if request.path == "/api/brainstorm/create-task":
            self._handle_brainstorm_create_task()
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
        try:
            browser_action = resolve_browser_action_command(payload, command, classification)
        except ValueError as exc:
            self._send_json_error(str(exc), HTTPStatus.BAD_REQUEST)
            return
        if browser_action is None:
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
            args = browser_action.args
            context_path = _write_promotion_context(root, command, payload) if browser_action.writes_promotion_context else None
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
                input="y\n" if browser_action.writes_promotion_context else None,
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
            from devflow.control_room.agent_catalog import build_agent_catalog
            from devflow.control_room.agent_registry import (
                is_hermes_subscription_agent,
                is_local_openai_compatible_provider,
                is_remote_advisory_agent,
                load_agent_registry,
                load_provider_registry,
            )
            from devflow.control_room.local_model_inventory import build_local_model_inventory
            catalog = build_agent_catalog(root)
            profile_by_id = {
                profile["id"]: profile
                for profile in catalog.get("profiles", [])
                if isinstance(profile, dict) and profile.get("id")
            }
            availability_by_profile = {
                profile["id"]: profile.get("availability", {})
                for profile in catalog.get("profiles", [])
                if isinstance(profile, dict) and profile.get("id")
            }
            registry = load_agent_registry(root)
            providers = load_provider_registry(root)
            agents = []
            for agent in registry.enabled_agents():
                provider = providers.providers.get(agent.provider)
                if not provider:
                    continue
                is_remote = is_remote_advisory_agent(agent, provider=provider)
                is_hermes_subscription = is_hermes_subscription_agent(agent, provider=provider)
                is_ollama = provider.provider == "ollama" or agent.adapter == "ollama_chat"
                is_local_endpoint = is_local_openai_compatible_provider(provider)
                is_local = is_ollama or is_local_endpoint
                if not is_remote and not is_local and not is_hermes_subscription:
                    continue
                availability = availability_by_profile.get(agent.id, {})
                if is_local and availability.get("status") in {"missing", "unavailable"}:
                    continue
                catalog_profile = profile_by_id.get(agent.id, {})
                agents.append({
                    "id": agent.id,
                    "model": agent.model,
                    "label": agent.model_role_name or agent.id,
                    "purpose": agent.purpose or "",
                    "tier": agent.tier,
                    "secondary_roles": agent.secondary_roles,
                    "provider": agent.provider,
                    "adapter": catalog_profile.get("adapter") or agent.adapter,
                    "role": catalog_profile.get("role") or agent.role,
                    "authority": catalog_profile.get("authority"),
                    "is_local": is_local,
                    "availability": availability,
                    "runtime_contract": catalog_profile.get("runtime_contract", {}),
                })
            self._send_json(
                {
                    "agents": agents,
                    "local_model_inventory": build_local_model_inventory(catalog),
                },
                HTTPStatus.OK,
            )
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


def _write_promotion_context(root: Path, command: str, payload: dict[str, object]) -> str | None:
    note = payload.get("context_note")
    if not isinstance(note, str) or not note.strip():
        return None
    task_id = promotion_task_id_from_command(command)
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
