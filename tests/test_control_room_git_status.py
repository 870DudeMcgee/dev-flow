from __future__ import annotations

import http.client
import json
import subprocess
import threading
from pathlib import Path

from devflow.control_room.git_status import git_status_snapshot
from devflow.control_room.server import StatusServer


def _git(repo: Path, *args: str) -> None:
    subprocess.run(["git", "-C", str(repo), *args], check=True, capture_output=True, text=True)


def test_git_status_snapshot_reports_dirty_counts(tmp_path: Path) -> None:
    _git(tmp_path, "init")
    _git(tmp_path, "config", "user.email", "devflow@example.invalid")
    _git(tmp_path, "config", "user.name", "DevFlow Test")
    tracked = tmp_path / "tracked.txt"
    tracked.write_text("one\n", encoding="utf-8")
    _git(tmp_path, "add", "tracked.txt")
    _git(tmp_path, "commit", "-m", "initial")

    tracked.write_text("two\n", encoding="utf-8")
    (tmp_path / "new.txt").write_text("new\n", encoding="utf-8")

    payload = git_status_snapshot(tmp_path)

    assert payload["available"] is True
    assert payload["repo_name"] == tmp_path.name
    assert payload["state"] == "dirty"
    assert payload["label"] == "2 changes"
    assert payload["unstaged"] == 1
    assert payload["untracked"] == 1
    assert payload["pushed"] is False


def test_git_status_endpoint_returns_probe_payload(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(
        "devflow.control_room.server.git_status_snapshot",
        lambda root: {"available": True, "repo_name": "DevFlow", "branch": "main", "state": "clean"},
    )
    server = StatusServer(("127.0.0.1", 0), tmp_path)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        conn = http.client.HTTPConnection("127.0.0.1", server.server_port, timeout=5)
        conn.request("GET", "/api/git")
        resp = conn.getresponse()
        body = resp.read().decode("utf-8")
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)

    assert resp.status == 200
    assert json.loads(body) == {"available": True, "repo_name": "DevFlow", "branch": "main", "state": "clean"}
