"""Pipeline status board — reads loop state from disk and serves it to the browser.

This is a read-only status surface: it never writes to pipeline runs or
triggers work. It just shows what's happening. The brainstorm and pipeline
orchestration happen in Hermes (the frontier model conversation); this board
is the operator's window into that activity.

Routes:
  GET  /         → status board page (HTML)
  GET  /healthz  → health check
  GET  /api/status → all pipeline runs with current stage + recent events
"""

from __future__ import annotations

import json
import socket
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlsplit, parse_qs
from pathlib import Path
from devflow.loop.pipeline_run import load_pipeline_run, pipeline_runs_dir, _ensure_relative_to
from devflow.control_room.page import STATUS_PAGE_HTML
from devflow.control_room.system_memory import memory_pressure_snapshot


class StatusServer(ThreadingHTTPServer):
    def __init__(self, server_address: tuple[str, int], repo_root: Path) -> None:
        super().__init__(server_address, StatusRequestHandler)
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
        self._send_text(STATUS_PAGE_HTML, "text/html; charset=utf-8")

    def _send_healthz(self) -> None:
        self._send_json({"status": "ok"})

    def _handle_status(self) -> None:
        """Read all pipeline runs from disk and return their current state."""
        root = self.server.repo_root
        runs_dir = pipeline_runs_dir(root)
        runs: list[dict] = []

        if runs_dir.exists():
            for entry in sorted(runs_dir.iterdir(), key=lambda e: e.name, reverse=True):
                if not entry.is_dir():
                    continue
                try:
                    data = load_pipeline_run(root, entry.name)
                except Exception:
                    continue
                run_info = _extract_run_info(entry.name, data)
                runs.append(run_info)

        self._send_json({"runs": runs, "repo": str(root)})

    def _handle_memory(self) -> None:
        """Return the compact system memory signal used by the header graph."""
        self._send_json(memory_pressure_snapshot())

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
        elif path == "/api/artifact":
            self._handle_artifact(query)
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

    # Worker feed — actual model outputs for the live feed panel
    feed_entries: list[dict] = []
    feed = data.get("worker-feed.jsonl") or []
    if isinstance(feed, list):
        for rec in feed[-30:]:  # last 30 entries
            if isinstance(rec, dict):
                feed_entries.append({
                    "timestamp": rec.get("timestamp", ""),
                    "event": rec.get("event", ""),
                    "role": rec.get("role", ""),
                    "model": rec.get("model", ""),
                    "content": (rec.get("content") or "")[:4000],
                    "system_prompt": (rec.get("system_prompt") or "")[:300],
                    "user_prompt": (rec.get("user_prompt") or "")[:500],
                    "usage": rec.get("usage") or {},
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
    print(f"DevFlow Pipeline Status Board → http://{host}:{port}")
    print(f"  repo: {repo_root}")
    print("  Press Ctrl+C to stop.")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nShutting down...")
        server.shutdown()
