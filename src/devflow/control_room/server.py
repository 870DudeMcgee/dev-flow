"""Pipeline status board — reads loop state from disk and serves it to the browser.

This status surface reads pipeline runs from disk and exposes bounded operator
controls. It never runs models itself. An approved dispatch may launch one
run-owned process group, and stop actions may signal only that recorded group;
shared model servers remain outside the browser process's control.

Routes:
  GET  /         → status board page (HTML)
  GET  /healthz  → health check
  GET  /api/status → all pipeline runs with current stage + recent events
  POST /api/operator-action → record an operator control request
"""

from __future__ import annotations

import json
import hashlib
import os
import signal
import socket
import subprocess
from datetime import datetime, timezone
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlsplit, parse_qs
from pathlib import Path
from devflow.loop.adapter import load_loop_state
from devflow.loop.models import LoopStage
from devflow.loop.pipeline_run import (
    append_pipeline_event,
    append_worker_feed_entry,
    load_pipeline_run,
    pipeline_runs_dir,
    read_execution_control,
    update_execution_control,
    _ensure_relative_to,
)
from devflow.loop.model_router import (
    _global_local_model_runtime_status,
    reclaim_stale_local_model_runtime_lock,
)
from devflow.control_room.git_status import git_status_snapshot
from devflow.control_room.page import STATUS_PAGE_HTML
from devflow.control_room.system_memory import memory_pressure_snapshot
from devflow.control_room import chat as chat_api
from devflow.control_room import workspace as workspace_api


# Static assets served alongside the status board (logo, etc.).
_STATIC_DIR = Path(__file__).resolve().parent / "static"
_IMAGE_CONTENT_TYPES = {
    ".png": "image/png",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".gif": "image/gif",
    ".webp": "image/webp",
    ".svg": "image/svg+xml",
    ".ico": "image/x-icon",
}


_WORKER_CATEGORY_LABELS = {
    "build": "Builder/Judge loop",
    "planning": "Planning loop",
    "operator": "Operator gates",
    "orchestrator": "Orchestrator/control",
    "verification": "Verification",
}


def _worker_category(role: str) -> str:
    if role in {"builder", "judge", "build_judge_loop"}:
        return "build"
    if role in {
        "planner", "planning_judge", "planning_judge_report",
        "frontier_bounded_packet_review", "frontier_orchestrator_replan_gate",
    }:
        return "planning"
    if role in {"operator_control", "frontier_orchestrator_control"}:
        return "operator"
    if role in {"verification", "test-runner", "verifier"}:
        return "verification"
    return "orchestrator"


def _stage_worker_category(stage: str) -> str:
    if stage in {"build_judge"}:
        return "build"
    if stage == "verification":
        return "verification"
    if stage in {"planning", "planning_judge"}:
        return "planning"
    if stage == "assignment":
        return "operator"
    return "orchestrator"


def _entry_stages(role: str) -> list[str]:
    """Map persisted worker roles to the stage controls they can truthfully explain."""
    if role == "planner":
        return ["spec", "planning"]
    if role in {
        "planning_judge", "planning_judge_report", "planning_loop",
        "frontier_bounded_packet_review", "frontier_orchestrator_replan_gate",
    }:
        return ["planning_judge"]
    if role in {"operator_control", "frontier_orchestrator_control", "packet_1_dispatch"}:
        return ["assignment"]
    if role in {"builder", "judge", "build_judge_loop"}:
        return ["build_judge"]
    if role in {"verification", "verifier", "test-runner"}:
        return ["verification"]
    if role in {"human_decision", "acceptance"}:
        return ["human_decision"]
    if role in {"brainstorm", "definition", "orient"}:
        return ["idea", "definition"]
    return []


def _content_payload(content: object) -> dict:
    if not isinstance(content, str) or not content.strip():
        return {}
    text = content.strip()
    if text.startswith("```"):
        lines = text.splitlines()
        if len(lines) >= 3:
            text = "\n".join(lines[1:-1])
            if text.lstrip().startswith("json"):
                text = text.lstrip()[4:].lstrip()
    try:
        value = json.loads(text)
    except (TypeError, json.JSONDecodeError):
        return {}
    return value if isinstance(value, dict) else {}


def _semantic_outcome(event: str, payload: dict) -> tuple[str, str]:
    decision = str(
        payload.get("judge_decision")
        or payload.get("decision")
        or payload.get("status")
        or payload.get("last_decision")
        or payload.get("planning_decision")
        or ""
    ).strip().lower()
    if event in {"failed", "blocked", "loop_exhausted"}:
        return "failed", decision or event
    if event == "cancelled":
        return "cancelled", decision or event
    if payload.get("build_cap_exhausted") is True:
        return "failed", decision or "build cap exhausted"
    if decision in {"failed", "failure", "rejected", "block", "blocked"}:
        return "failed", decision
    if decision in {"revise", "needs_review", "escalate_to_user"}:
        return "needs_attention", decision
    if decision in {"approve", "approved", "passed", "pass", "success", "succeeded"}:
        return "passed", decision
    if event == "started":
        return "running", ""
    if event in {"operator_action_requested", "awaiting_operator_dispatch"}:
        return "needs_attention", ""
    if event == "completed":
        return "completed", ""
    return "neutral", ""


def _human_role(role: str) -> str:
    return role.replace("_", " ").strip().title() or "Worker"


def _entry_summary(role: str, event: str, payload: dict, outcome: str, decision: str) -> str:
    rounds = payload.get("build_rounds") or payload.get("max_rounds")
    if role in {"packet_1_dispatch", "build_judge_loop"} and outcome == "failed":
        suffix = f" after {rounds} rounds" if rounds else ""
        return f"Builder/Judge failed{suffix}"
    if role in {"planning_judge", "planning_judge_report"} and decision:
        verb = "approved" if outcome == "passed" else decision.replace("_", " ")
        return f"Planning judge {verb}"
    if role == "judge" and decision:
        return f"Judge {decision.replace('_', ' ')}"
    if event == "started":
        return f"{_human_role(role)} started"
    if event == "completed":
        return f"{_human_role(role)} finished"
    return f"{_human_role(role)} · {event.replace('_', ' ')}"


def _project_worker_feed(run_id: str, stage: str, feed: list[dict]) -> dict:
    """Project append-only worker evidence into stable operator-facing loops."""
    entries: list[dict] = []
    duplicate_counts: dict[str, int] = {}
    for raw_index, rec in enumerate(feed):
        if not isinstance(rec, dict):
            continue
        role = str(rec.get("role") or "worker")
        event = str(rec.get("event") or "unknown")
        content = str(rec.get("content") or "")
        reasoning_content = str(rec.get("reasoning_content") or "")
        payload = _content_payload(content)
        outcome, decision = _semantic_outcome(event, payload)
        # Streaming entries get a STABLE fingerprint: exclude the volatile
        # content (which grows on every delta) and timestamp so the entry_id
        # stays constant while the live output grows. This lets the viewer
        # keep its selection locked on the active streaming card.
        if event == "streaming":
            fingerprint_source = {
                "event": "streaming",
                "role": role,
                "model": rec.get("model", ""),
            }
        else:
            fingerprint_source = {
                "timestamp": rec.get("timestamp", ""),
                "event": event,
                "role": role,
                "model": rec.get("model", ""),
                "content": content,
            }
        digest = hashlib.sha1(
            json.dumps(fingerprint_source, sort_keys=True, ensure_ascii=False).encode("utf-8")
        ).hexdigest()[:12]
        duplicate_counts[digest] = duplicate_counts.get(digest, 0) + 1
        entry_id = f"{run_id}:feed:{digest}:{duplicate_counts[digest]}"
        next_action = str(
            payload.get("next_safe_action")
            or payload.get("planning_next_action")
            or ""
        )
        entries.append({
            "entry_id": entry_id,
            "source_index": raw_index,
            "timestamp": str(rec.get("timestamp") or ""),
            "event": event,
            "execution_status": event,
            "outcome": outcome,
            "decision": decision,
            "category": _worker_category(role),
            "stages": _entry_stages(role),
            "role": role,
            "model": str(rec.get("model") or ""),
            "summary": _entry_summary(role, event, payload, outcome, decision),
            "next_safe_action": next_action,
            "content": content[:64000],
            "system_prompt": str(rec.get("system_prompt") or "")[:1000],
            "user_prompt": str(rec.get("user_prompt") or "")[:4000],
            "usage": rec.get("usage") or {},
            "requested_max_tokens": rec.get("requested_max_tokens"),
            "finish_reason": str(rec.get("finish_reason") or ""),
            "token_cap_reached": bool(rec.get("token_cap_reached")),
            "reasoning_content": reasoning_content[:64000] if reasoning_content else "",
        })

    loops: list[dict] = []
    current_by_category: dict[str, dict] = {}
    category_counts: dict[str, int] = {}
    for entry in entries:
        category = entry["category"]
        starts_loop = (
            entry["event"] == "started"
            and entry["role"] in {"planner", "builder", "verification", "test-runner"}
        )
        if category not in current_by_category or starts_loop:
            category_counts[category] = category_counts.get(category, 0) + 1
            attempt = category_counts[category]
            first_entry_token = entry["entry_id"].rsplit(":", 2)[1]
            loop = {
                "loop_id": f"{run_id}:{category}:{first_entry_token}",
                "category": category,
                "label": _WORKER_CATEGORY_LABELS.get(category, "Worker loop"),
                "attempt": attempt,
                "entries": [],
            }
            loops.append(loop)
            current_by_category[category] = loop
        current_by_category[category]["entries"].append(entry)

    for loop in loops:
        loop_entries = loop["entries"]
        outcomes = [item["outcome"] for item in loop_entries]
        if "failed" in outcomes:
            loop_outcome = "failed"
        elif "needs_attention" in outcomes:
            loop_outcome = "needs_attention"
        elif "passed" in outcomes:
            loop_outcome = "passed"
        else:
            loop_outcome = next(
                (item["outcome"] for item in reversed(loop_entries) if item["outcome"] not in {"neutral", "running"}),
                "running" if "running" in outcomes else "neutral",
            )
        last_summary = next((item for item in reversed(loop_entries) if item["event"] != "started"), loop_entries[-1])
        last_next_action = next((item["next_safe_action"] for item in reversed(loop_entries) if item["next_safe_action"]), "")
        loop.update({
            "outcome": loop_outcome,
            "summary": last_summary["summary"],
            "next_safe_action": last_next_action,
            "started_at": loop_entries[0]["timestamp"],
            "ended_at": loop_entries[-1]["timestamp"],
            "event_count": len(loop_entries),
            "roles": list(dict.fromkeys(item["role"] for item in loop_entries)),
            "models": list(dict.fromkeys(item["model"] for item in loop_entries if item["model"])),
        })

    desired_category = _stage_worker_category(stage)
    current = next((loop for loop in reversed(loops) if loop["category"] == desired_category), None)
    if current is None and loops:
        current = loops[-1]
    current_id = current["loop_id"] if current else ""
    for loop in loops:
        loop["is_current"] = loop["loop_id"] == current_id
    return {"entries": entries, "loops": loops, "current": current}


class StatusServer(ThreadingHTTPServer):
    def __init__(self, server_address: tuple[str, int], repo_root: Path) -> None:
        super().__init__(server_address, StatusRequestHandler)
        # Restore last active workspace if one was set, otherwise use the
        # directory the server was launched from.
        active = workspace_api.get_active_workspace()
        if active and Path(active).exists():
            self.repo_root = Path(active).resolve()
        else:
            self.repo_root = repo_root.resolve()
        self.socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)


class StatusRequestHandler(BaseHTTPRequestHandler):
    server: "StatusServer"  # type: ignore[assignment]

    def _send_text(self, text: str, content_type: str, status: int = 200) -> None:
        body = text.encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-cache")
        self.end_headers()
        self.wfile.write(body)

    def _send_json(self, payload: dict, status: int = 200) -> None:
        self._send_text(
            json.dumps(payload, ensure_ascii=False) + "\n",
            "application/json; charset=utf-8",
            status,
        )

    def _send_page(self) -> None:
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Cache-Control", "no-store, no-cache, must-revalidate")
        self.send_header("Pragma", "no-cache")
        self.end_headers()
        self.wfile.write(STATUS_PAGE_HTML.encode("utf-8"))

    def _send_healthz(self) -> None:
        self._send_json({"status": "ok"})

    def _handle_status(self) -> None:
        """Read all pipeline runs from disk and return their current state."""
        root = self.server.repo_root
        runs_dir = pipeline_runs_dir(root)
        runs: list[dict] = []

        runtime_lock = _global_local_model_runtime_status(root)
        if runs_dir.exists():
            for entry in sorted(runs_dir.iterdir(), key=lambda e: e.name, reverse=True):
                if not entry.is_dir():
                    continue
                try:
                    data = load_pipeline_run(root, entry.name)
                except Exception:
                    continue
                run_info = _extract_run_info(entry.name, data)
                run_info["can_reclaim_lock"] = bool(
                    runtime_lock
                    and runtime_lock.state == "stale"
                    and runtime_lock.task_id == entry.name
                )
                runs.append(run_info)

        self._send_json({"runs": runs, "repo": str(root)})

    def _handle_memory(self) -> None:
        """Return the compact system memory signal used by the header graph."""
        self._send_json(memory_pressure_snapshot())

    def _handle_git(self) -> None:
        """Return the compact Git status signal used by the header badge."""
        self._send_json(git_status_snapshot(self.server.repo_root))

    def _handle_artifact(self, query: dict) -> None:
        """Serve the raw text content of a single artifact file from a run dir."""
        run_id = (query.get("run") or [""])[0]
        file_name = (query.get("file") or [""])[0]
        if not run_id or not file_name:
            self.send_error(HTTPStatus.BAD_REQUEST, "Missing run or file")
            return
        # Path-traversal guard
        if "/" in file_name or "\\" in file_name or ".." in file_name:
            self.send_error(HTTPStatus.BAD_REQUEST, "Invalid file name")
            return
        try:
            run_dir = pipeline_runs_dir(self.server.repo_root) / run_id
            target = (run_dir / file_name).resolve()
            _ensure_relative_to(target, run_dir.resolve())
        except (ValueError, OSError) as exc:
            self.send_error(HTTPStatus.NOT_FOUND, str(exc))
            return
        if not target.is_file():
            self.send_error(HTTPStatus.NOT_FOUND, "Artifact not found")
            return
        try:
            text = target.read_text(encoding="utf-8", errors="replace")
        except OSError as exc:
            self.send_error(HTTPStatus.INTERNAL_SERVER_ERROR, str(exc))
            return
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", "text/plain; charset=utf-8")
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(text.encode("utf-8"))

    def _handle_static(self, rel_path: str) -> None:
        """Serve a read-only asset from the control_room/static directory."""
        if not rel_path or "/" in rel_path or "\\" in rel_path or ".." in rel_path:
            self.send_error(HTTPStatus.BAD_REQUEST, "Invalid static path")
            return
        try:
            target = (_STATIC_DIR / rel_path).resolve()
            if not str(target).startswith(str(_STATIC_DIR.resolve())):
                self.send_error(HTTPStatus.BAD_REQUEST, "Invalid static path")
                return
        except (ValueError, OSError) as exc:
            self.send_error(HTTPStatus.NOT_FOUND, str(exc))
            return
        if not target.is_file():
            self.send_error(HTTPStatus.NOT_FOUND, "Asset not found")
            return
        content_type = _IMAGE_CONTENT_TYPES.get(target.suffix.lower(), "application/octet-stream")
        try:
            data = target.read_bytes()
        except OSError as exc:
            self.send_error(HTTPStatus.INTERNAL_SERVER_ERROR, str(exc))
            return
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", content_type)
        self.send_header("Cache-Control", "public, max-age=3600")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def _handle_operator_action(self) -> None:
        """Record an operator button click without launching hidden work."""
        try:
            length = int(self.headers.get("Content-Length", "0") or "0")
        except ValueError:
            self.send_error(HTTPStatus.BAD_REQUEST, "Invalid Content-Length")
            return
        if length <= 0 or length > 8192:
            self.send_error(HTTPStatus.BAD_REQUEST, "Invalid request body")
            return
        try:
            payload = json.loads(self.rfile.read(length).decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError):
            self.send_error(HTTPStatus.BAD_REQUEST, "Invalid JSON")
            return
        try:
            record = record_operator_action(
                self.server.repo_root,
                str(payload.get("run_id") or ""),
                str(payload.get("action") or ""),
                note=str(payload.get("note") or ""),
            )
        except ValueError as exc:
            self.send_error(HTTPStatus.BAD_REQUEST, str(exc))
            return
        except FileNotFoundError as exc:
            self.send_error(HTTPStatus.NOT_FOUND, str(exc))
            return
        self._send_json({"status": "recorded", "action": record})

    # -----------------------------------------------------------------------
    # Chat endpoints
    # -----------------------------------------------------------------------
    def _handle_chat_models(self) -> None:
        """Return the list of models available for the chat surface."""
        self._send_json({"models": chat_api.list_chat_models()})

    def _handle_chat_sessions(self) -> None:
        """Return all chat sessions."""
        self._send_json({"sessions": chat_api.list_chat_sessions(self.server.repo_root)})

    def _handle_chat_transcript(self, query: dict) -> None:
        """Return the conversation history for a chat session."""
        session_id = (query.get("session") or [""])[0]
        if not session_id:
            self.send_error(HTTPStatus.BAD_REQUEST, "Missing session")
            return
        try:
            transcript = chat_api.get_transcript(self.server.repo_root, session_id)
        except Exception as exc:
            self.send_error(HTTPStatus.INTERNAL_SERVER_ERROR, str(exc))
            return
        self._send_json({
            "session_id": session_id,
            "messages": transcript,
            "model": chat_api._get_session_model(self.server.repo_root, session_id),
        })

    def _handle_chat_start(self) -> None:
        """Start a new chat session."""
        try:
            length = int(self.headers.get("Content-Length", "0") or "0")
        except ValueError:
            self.send_error(HTTPStatus.BAD_REQUEST, "Invalid Content-Length")
            return
        if length <= 0 or length > 16384:
            self.send_error(HTTPStatus.BAD_REQUEST, "Invalid request body")
            return
        try:
            payload = json.loads(self.rfile.read(length).decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError):
            self.send_error(HTTPStatus.BAD_REQUEST, "Invalid JSON")
            return
        intent = str(payload.get("intent") or "").strip()
        model = str(payload.get("model") or "").strip() or None
        if not intent:
            self.send_error(HTTPStatus.BAD_REQUEST, "Missing intent")
            return
        try:
            result = chat_api.start_chat_session(
                self.server.repo_root, intent=intent, model=model,
            )
        except Exception as exc:
            self.send_error(HTTPStatus.INTERNAL_SERVER_ERROR, str(exc))
            return
        self._send_json(result)

    def _handle_chat_send(self) -> None:
        """Send a message and return the assistant's response."""
        try:
            length = int(self.headers.get("Content-Length", "0") or "0")
        except ValueError:
            self.send_error(HTTPStatus.BAD_REQUEST, "Invalid Content-Length")
            return
        if length <= 0 or length > 65536:
            self.send_error(HTTPStatus.BAD_REQUEST, "Invalid request body")
            return
        try:
            payload = json.loads(self.rfile.read(length).decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError):
            self.send_error(HTTPStatus.BAD_REQUEST, "Invalid JSON")
            return
        session_id = str(payload.get("session_id") or "").strip()
        message = str(payload.get("message") or "").strip()
        model = str(payload.get("model") or "").strip() or None
        if not session_id:
            self.send_error(HTTPStatus.BAD_REQUEST, "Missing session_id")
            return
        if not message:
            self.send_error(HTTPStatus.BAD_REQUEST, "Missing message")
            return
        try:
            result = chat_api.send_message(
                self.server.repo_root,
                session_id=session_id,
                message=message,
                model=model,
            )
        except ValueError as exc:
            self.send_error(HTTPStatus.BAD_REQUEST, str(exc))
            return
        except Exception as exc:
            self.send_error(HTTPStatus.INTERNAL_SERVER_ERROR, str(exc))
            return
        self._send_json(result)

    # -----------------------------------------------------------------------
    # Workspace endpoints
    # -----------------------------------------------------------------------
    def _handle_workspace_state(self) -> None:
        """Return the active workspace + recent list."""
        self._send_json(workspace_api.get_workspace_state())

    def _handle_workspace_pick(self) -> None:
        """Open the native Finder dialog and set the chosen folder as active.

        This blocks until the user picks or cancels. Returns the new workspace
        state, or a cancellation indicator.
        """
        chosen = workspace_api.pick_folder_dialog()
        if not chosen:
            self._send_json({"cancelled": True, **workspace_api.get_workspace_state()})
            return
        try:
            result = workspace_api.set_active_workspace(chosen)
        except (FileNotFoundError, ValueError) as exc:
            self.send_error(HTTPStatus.BAD_REQUEST, str(exc))
            return
        # Switch the server's repo_root so all other endpoints read from here
        self.server.repo_root = Path(chosen).resolve()
        self._send_json(result)

    def _handle_workspace_set(self) -> None:
        """Set the active workspace from a path string in the POST body."""
        try:
            length = int(self.headers.get("Content-Length", "0") or "0")
        except ValueError:
            self.send_error(HTTPStatus.BAD_REQUEST, "Invalid Content-Length")
            return
        if length <= 0 or length > 4096:
            self.send_error(HTTPStatus.BAD_REQUEST, "Invalid request body")
            return
        try:
            payload = json.loads(self.rfile.read(length).decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError):
            self.send_error(HTTPStatus.BAD_REQUEST, "Invalid JSON")
            return
        path = str(payload.get("path") or "").strip()
        if not path:
            self.send_error(HTTPStatus.BAD_REQUEST, "Missing path")
            return
        try:
            result = workspace_api.set_active_workspace(path)
        except FileNotFoundError as exc:
            self.send_error(HTTPStatus.NOT_FOUND, str(exc))
            return
        except ValueError as exc:
            self.send_error(HTTPStatus.BAD_REQUEST, str(exc))
            return
        self.server.repo_root = Path(path).expanduser().resolve()
        self._send_json(result)

    def _handle_workspace_remove(self) -> None:
        """Remove a workspace from the recent list."""
        try:
            length = int(self.headers.get("Content-Length", "0") or "0")
        except ValueError:
            self.send_error(HTTPStatus.BAD_REQUEST, "Invalid Content-Length")
            return
        if length <= 0 or length > 4096:
            self.send_error(HTTPStatus.BAD_REQUEST, "Invalid request body")
            return
        try:
            payload = json.loads(self.rfile.read(length).decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError):
            self.send_error(HTTPStatus.BAD_REQUEST, "Invalid JSON")
            return
        path = str(payload.get("path") or "").strip()
        if not path:
            self.send_error(HTTPStatus.BAD_REQUEST, "Missing path")
            return
        result = workspace_api.remove_recent_workspace(path)
        self._send_json(result)

    def do_GET(self) -> None:
        parsed = urlsplit(self.path)
        path = parsed.path
        query = parse_qs(parsed.query)
        if path in ("/", "/index.html"):
            self._send_page()
        elif path == "/healthz":
            self._send_healthz()
        elif path == "/api/status":
            self._handle_status()
        elif path == "/api/memory":
            self._handle_memory()
        elif path == "/api/git":
            self._handle_git()
        elif path == "/api/artifact":
            self._handle_artifact(query)
        elif path.startswith("/static/"):
            self._handle_static(path[len("/static/"):])
        elif path == "/api/chat/models":
            self._handle_chat_models()
        elif path == "/api/chat/sessions":
            self._handle_chat_sessions()
        elif path == "/api/chat/transcript":
            self._handle_chat_transcript(query)
        elif path == "/api/workspace":
            self._handle_workspace_state()
        else:
            self.send_error(HTTPStatus.NOT_FOUND)

    def do_POST(self) -> None:
        parsed = urlsplit(self.path)
        if parsed.path == "/api/operator-action":
            self._handle_operator_action()
        elif parsed.path == "/api/chat/start":
            self._handle_chat_start()
        elif parsed.path == "/api/chat/send":
            self._handle_chat_send()
        elif parsed.path == "/api/workspace/pick":
            self._handle_workspace_pick()
        elif parsed.path == "/api/workspace/set":
            self._handle_workspace_set()
        elif parsed.path == "/api/workspace/remove":
            self._handle_workspace_remove()
        else:
            self.send_error(HTTPStatus.NOT_FOUND)

    def log_message(self, format: str, *args) -> None:
        pass


# ---------------------------------------------------------------------------
# Run-info extraction
# ---------------------------------------------------------------------------

STAGE_ORDER = [
    "idea", "definition", "spec", "planning", "planning_judge",
    "assignment", "build_judge", "verification", "human_decision", "complete",
]

STAGE_LABELS = {
    "idea": "Brainstorm",
    "definition": "Definition",
    "spec": "Spec",
    "planning": "Planning",
    "planning_judge": "Plan Judge",
    "assignment": "Assignment",
    "build_judge": "Build + Judge",
    "verification": "Verification",
    "human_decision": "Human Decision",
    "complete": "Complete",
    "blocked": "Blocked",
}


ALLOWED_OPERATOR_ACTIONS = {
    "dispatch_packet_1": "Operator requested Builder/Judge dispatch for packet 1.",
    "hold_redirect": "Operator requested a hold/redirect before dispatch.",
    "stop_after_step": "Operator requested cancellation after the current role step.",
    "stop_now": "Operator requested immediate cancellation of the run-owned dispatcher.",
    "reclaim_stale_lock": "Operator requested validated stale local-model lock reclaim.",
}


def record_operator_action(
    root: Path | str,
    run_id: str,
    action: str,
    *,
    note: str = "",
) -> dict:
    """Persist an operator control request for Hermes/orchestrator follow-up.

    This records intent only. The status server must not launch model calls or
    subprocesses because the operator needs visible, bounded orchestration
    rather than hidden work from the browser process.
    """
    root = Path(root).resolve()
    if not run_id:
        raise ValueError("Missing run_id")
    if action not in ALLOWED_OPERATOR_ACTIONS:
        raise ValueError(f"Unsupported operator action: {action}")
    run_dir = pipeline_runs_dir(root) / run_id
    if not run_dir.is_dir():
        raise FileNotFoundError(f"Pipeline run not found: {run_id}")
    target = (run_dir / "operator-actions.jsonl").resolve()
    _ensure_relative_to(target, run_dir.resolve())
    record: dict[str, object] = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "run_id": run_id,
        "action": action,
        "label": ALLOWED_OPERATOR_ACTIONS[action],
        "note": note,
    }
    with open(str(target), "a", encoding="utf-8") as fh:
        fh.write(json.dumps(record, ensure_ascii=False) + "\n")
    append_pipeline_event(root, run_id, {
        "event": "operator_action_requested",
        "action": action,
    })
    append_worker_feed_entry(root, run_id, {
        "event": "operator_action_requested",
        "role": "operator_control",
        "model": "human-operator",
        "content": json.dumps(record, indent=2, ensure_ascii=False),
    })
    if action == "dispatch_packet_1":
        record["dispatch"] = start_operator_packet_dispatch(root, run_id)
    elif action == "stop_after_step":
        record["control"] = update_execution_control(
            root, run_id, status="cancelling", cancel_mode="after_step"
        )
    elif action == "stop_now":
        record["control"] = stop_owned_dispatch(root, run_id)
    elif action == "reclaim_stale_lock":
        status = _global_local_model_runtime_status(root)
        if status is None:
            record["reclaimed"] = False
        else:
            if status.task_id and status.task_id != run_id:
                raise ValueError(
                    f"Refusing to reclaim a lock owned by another run: {status.task_id}"
                )
            record["reclaimed"] = reclaim_stale_local_model_runtime_lock(
                root, provider=status.provider, model=status.model
            )
    return record


def _pid_is_alive(pid: int) -> bool:
    if pid <= 0:
        return False
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    return True


def stop_owned_dispatch(root: Path, run_id: str) -> dict:
    """Signal only the process group recorded for this pipeline run."""
    control = read_execution_control(root, run_id)
    pid = int(control.get("pid") or 0)
    process_group = int(control.get("process_group") or pid or 0)
    script = str(control.get("script") or "")
    if pid > 0 and _pid_is_alive(pid):
        command = subprocess.run(
            ["ps", "-p", str(pid), "-o", "command="],
            capture_output=True, text=True,
        ).stdout.strip()
        if not script or script not in command:
            raise ValueError("Refusing to stop a process whose command no longer matches this run")
        os.killpg(process_group, signal.SIGTERM)
        return update_execution_control(
            root, run_id, status="cancelling", cancel_mode="immediate",
            stop_signal="SIGTERM",
        )
    return update_execution_control(
        root, run_id, status="cancelled", cancel_mode="immediate",
        active_role=None,
    )


def start_operator_packet_dispatch(root: Path, run_id: str) -> dict:
    """Start the approved packet-1 dispatcher for an assignment-stage run."""
    state = load_loop_state(root, run_id)
    if state.stage != LoopStage.assignment:
        return {
            "started": False,
            "reason": f"run is at {state.stage.value}, not assignment",
        }
    run_dir = pipeline_runs_dir(root) / run_id
    script = run_dir / "run_dispatch_packet_1.py"
    if not script.is_file():
        return {
            "started": False,
            "reason": "run_dispatch_packet_1.py is missing",
        }
    log_path = run_dir / "packet-1-dispatch-server.log"
    with open(str(log_path), "ab") as log:
        proc = subprocess.Popen(
            ["env", "PYTHONPATH=src:.", ".venv/bin/python", str(script.relative_to(root))],
            cwd=str(root),
            stdout=log,
            stderr=subprocess.STDOUT,
            stdin=subprocess.DEVNULL,
            start_new_session=True,
        )
    control = update_execution_control(
        root, run_id,
        status="running", cancel_mode=None, pid=proc.pid,
        process_group=proc.pid, script=str(script.relative_to(root)),
        log=str(log_path.relative_to(root)),
        started_at=datetime.now(timezone.utc).isoformat(),
    )
    append_worker_feed_entry(root, run_id, {
        "event": "server_dispatch_started",
        "role": "operator_control",
        "model": "status-board",
        "content": json.dumps({
            "pid": proc.pid,
            "script": str(script.relative_to(root)),
            "log": str(log_path.relative_to(root)),
        }, indent=2),
    })
    return {
        "started": True,
        "pid": proc.pid,
        "log": str(log_path.relative_to(root)),
        "control": control,
    }


def _extract_run_info(run_id: str, data: dict) -> dict:
    """Extract a compact status payload from a pipeline run's files."""
    # Loop state
    state_raw = data.get("loop-state.json")
    stage = "idea"
    if isinstance(state_raw, dict):
        stage = state_raw.get("stage", "idea")

    # Source info
    source = data.get("source.json") or {}
    source_repo = ""
    if isinstance(source, dict):
        source_repo = str(source.get("repo", ""))

    # Intent
    intent_raw = data.get("intent.md") or ""
    intent = ""
    if isinstance(intent_raw, str):
        # Strip the "# Intent\n\n" prefix
        lines = intent_raw.strip().splitlines()
        intent = "\n".join(lines[2:]).strip() if len(lines) > 2 else intent_raw.strip()

    # Run log (events)
    run_log = data.get("run-log.jsonl") or []
    events: list[dict] = []
    if isinstance(run_log, list):
        for rec in run_log[-20:]:  # last 20 events
            if isinstance(rec, dict):
                events.append({
                    "timestamp": rec.get("timestamp", ""),
                    "event": rec.get("event", ""),
                })

    # Artifacts present — list ALL non-empty files in the run dir
    artifacts_present: list[str] = []
    for key, val in data.items():
        if key in ("loop-state.json", "source.json", "run-log.jsonl"):
            continue
        if isinstance(val, str) and val.strip():
            artifacts_present.append(key)
        elif isinstance(val, (dict, list)) and val:
            artifacts_present.append(key)

    # Worker activity — read from loop-state.json
    workers: list[dict] = []
    receipts: list[dict] = []
    if isinstance(state_raw, dict):
        for a in (state_raw.get("assignments") or []):
            if isinstance(a, dict):
                workers.append({
                    "task_id": a.get("task_id", a.get("id", "task")),
                    "worker": a.get("worker_id") or a.get("worker", "unknown"),
                    "role": a.get("role", "builder"),
                    "status": a.get("status", "active"),
                })
        for b in (state_raw.get("builder_judge_runs") or []):
            if isinstance(b, dict):
                workers.append({
                    "task_id": b.get("run_id", b.get("task_id", "build")),
                    "worker": b.get("worker_id") or b.get("model", "builder"),
                    "role": "build_judge",
                    "status": b.get("status", "active"),
                })
        for v in (state_raw.get("verification_receipts") or []):
            if isinstance(v, dict):
                receipts.append({
                    "verifier": v.get("verifier", "test-runner"),
                    "status": v.get("status", "unknown"),
                    "passed": v.get("passed", None),
                })

    control = data.get("execution-control.json") or {}
    if not isinstance(control, dict):
        control = {}
    execution_status = str(control.get("status") or "idle")

    # Worker feed — preserve raw evidence while projecting truthful operator state.
    feed_entries: list[dict] = []
    worker_projection: dict = {"entries": [], "loops": [], "current": None}
    feed = data.get("worker-feed.jsonl") or []
    if isinstance(feed, list):
        source_feed = [rec for rec in feed[-200:] if isinstance(rec, dict)]
        live_output = data.get("worker-live.json")
        if isinstance(live_output, dict) and (
            live_output.get("content") or live_output.get("reasoning_content")
        ):
            source_feed.append({
                **live_output,
                "event": live_output.get("event") or "streaming",
                "timestamp": live_output.get("updated_at", ""),
            })
        worker_projection = _project_worker_feed(run_id, stage, source_feed)
        feed_entries = worker_projection["entries"][-200:]

        if execution_status in {"", "idle", "running"} and source_feed:
            latest_started_index = next(
                (i for i in range(len(source_feed) - 1, -1, -1)
                 if source_feed[i].get("event") == "started"),
                -1,
            )
            if latest_started_index >= 0:
                started = source_feed[latest_started_index]
                role = started.get("role")
                finished = any(
                    rec.get("role") == role
                    and rec.get("event") in {"completed", "failed", "cancelled"}
                    for rec in source_feed[latest_started_index + 1:]
                )
                heartbeat_value = (
                    control.get("heartbeat_at")
                    or (live_output.get("updated_at") if isinstance(live_output, dict) else None)
                    or started.get("timestamp")
                )
                try:
                    heartbeat = datetime.fromisoformat(str(heartbeat_value))
                    if heartbeat.tzinfo is None:
                        heartbeat = heartbeat.replace(tzinfo=timezone.utc)
                    stale_seconds = (
                        datetime.now(timezone.utc) - heartbeat
                    ).total_seconds()
                except (TypeError, ValueError):
                    stale_seconds = 0
                if not finished and stale_seconds > 90:
                    execution_status = "stalled"

    if execution_status == "cancelling":
        pid = int(control.get("pid") or 0)
        if pid and not _pid_is_alive(pid):
            execution_status = "cancelled"
    if execution_status == "stalled" and worker_projection.get("current"):
        worker_projection["current"].update({
            "outcome": "stalled",
            "summary": "Worker stopped reporting progress",
            "next_safe_action": "Inspect partial output and process ownership before retrying.",
        })

    return {
        "run_id": run_id,
        "stage": stage,
        "stage_label": STAGE_LABELS.get(stage, stage),
        "stage_index": STAGE_ORDER.index(stage) if stage in STAGE_ORDER else 0,
        "total_stages": len(STAGE_ORDER),
        "intent": intent[:200],
        "repo": source_repo,
        "events": events,
        "artifacts": artifacts_present,
        "workers": workers,
        "receipts": receipts,
        "worker_feed": feed_entries,
        "worker_projection": worker_projection,
        "execution_status": execution_status,
        "execution_control": control,
        "can_reclaim_lock": False,
        "has_brainstorm": bool(
            data.get("brainstorm.md") and
            isinstance(data.get("brainstorm.md"), str) and
            data.get("brainstorm.md", "").strip()
        ),
    }


def run_server(
    repo_root: Path,
    *,
    host: str = "127.0.0.1",
    port: int = 8770,
) -> None:
    """Start the status board server. Blocks until interrupted."""
    server = StatusServer((host, port), repo_root)
    print(f"DevFlow Pipeline Status Board → http://{host}:{server.server_port}")
    print(f"  repo: {repo_root}")
    print("  Press Ctrl+C to stop.")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nShutting down...")
        server.shutdown()
