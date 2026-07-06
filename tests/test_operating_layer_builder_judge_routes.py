from __future__ import annotations

import json
import threading
from http import HTTPStatus
from http.client import HTTPConnection
from pathlib import Path

import pytest

import devflow.control_room.operating_layer_builder_judge_routes as builder_judge_routes
from devflow.control_room import builder_judge_runtime_registry as bj_runtime
from devflow.control_room.operating_layer_server import OperatingLayerHTTPServer
from tests.helpers import setup_temp_git_repo


def _write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, sort_keys=True, indent=2) + "\n", encoding="utf-8")


def _serve_operating_layer(root: Path) -> tuple[OperatingLayerHTTPServer, threading.Thread, str, int]:
    server = OperatingLayerHTTPServer(("127.0.0.1", 0), root)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    host, port = server.server_address
    return server, thread, host, port


def _clear_builder_judge_state() -> None:
    with bj_runtime._bj_state_lock:
        bj_runtime._bj_running_loops.clear()
        bj_runtime._bj_threads.clear()


class _FakeBuilderJudgeRun:
    def __init__(self, loop_id: str, status: str, *, next_safe_action: str = "") -> None:
        self.loop_id = loop_id
        self.status = status
        self.next_safe_action = next_safe_action

    def model_dump(self, *, mode: str) -> dict[str, object]:
        assert mode == "json"
        return {
            "loop_id": self.loop_id,
            "run_id": f"{self.loop_id}-run",
            "status": self.status,
            "started_at": "2026-06-29T00:00:00Z",
            "finished_at": "2026-06-29T00:00:01Z",
            "evidence_path": f".devflow/builder-judge-loops/{self.loop_id}/run.json",
            "next_safe_action": self.next_safe_action,
            "rounds": [{"round_number": 1, "score": 90, "passed": self.status == "passed"}],
            "config": {
                "definition_of_done": "A short test artifact",
                "builder_profile_id": "builder-a",
                "judge_profile_id": "judge-a",
            },
        }


def _post_json(host: str, port: int, path: str, payload: dict[str, object]) -> tuple[int, dict]:
    connection = HTTPConnection(host, port, timeout=5)
    connection.request(
        "POST",
        path,
        body=json.dumps(payload),
        headers={"Content-Type": "application/json"},
    )
    response = connection.getresponse()
    body = response.read().decode("utf-8")
    parsed = json.loads(body) if body else {}
    return response.status, parsed


def _get_raw(host: str, port: int, path: str) -> tuple[int, bytes, dict]:
    connection = HTTPConnection(host, port, timeout=5)
    connection.request("GET", path)
    response = connection.getresponse()
    body = response.read()
    headers = {k.lower(): v for k, v in response.getheaders()}
    return response.status, body, headers


def test_builder_judge_api_read_payloads_include_loop_envelope(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _clear_builder_judge_state()
    raw_run = {
        "loop_id": "bj-file",
        "run_id": "run-file",
        "status": "passed",
        "started_at": "2026-01-01T00:00:00Z",
        "finished_at": "2026-01-01T00:01:00Z",
        "evidence_path": ".devflow/builder-judge-loops/bj-file/run.json",
        "next_safe_action": "Review the final draft.",
        "rounds": [{"round_number": 1, "score": 91, "passed": True}],
        "config": {
            "definition_of_done": "A short test artifact",
            "builder_profile_id": "builder-a",
            "judge_profile_id": "judge-a",
        },
    }
    run_path = tmp_path / ".devflow" / "builder-judge-loops" / "bj-file" / "run.json"
    _write_json(run_path, raw_run)

    class FakeRun:
        status = "passed"

        def __init__(self, loop_id: str) -> None:
            self.loop_id = loop_id

        def model_dump(self, *, mode: str) -> dict:
            assert mode == "json"
            return {
                "loop_id": self.loop_id,
                "run_id": f"{self.loop_id}-run",
                "status": "passed",
                "evidence_path": f".devflow/builder-judge-loops/{self.loop_id}/run.json",
                "next_safe_action": "Review the final draft.",
                "rounds": [],
                "config": {
                    "definition_of_done": "A short test artifact",
                    "builder_profile_id": "builder-a",
                    "judge_profile_id": "judge-a",
                },
            }

    def fake_run_builder(root: Path, config, *, loop_id: str | None = None, write_evidence: bool = True) -> FakeRun:
        return FakeRun(loop_id or "bj-start")

    def fake_quality_gate(root: Path, **kwargs) -> FakeRun:
        return FakeRun("qg-spec-test")

    monkeypatch.setattr("devflow.control_room.builder_judge_loop._generate_loop_id", lambda: "bj-start")
    monkeypatch.setattr(builder_judge_routes, "run_builder_judge_loop", fake_run_builder)
    monkeypatch.setattr(builder_judge_routes, "run_quality_gate", fake_quality_gate)
    transcript_dir = tmp_path / ".devflow" / "brainstorms" / "session-1"
    transcript_dir.mkdir(parents=True)
    transcript_dir.joinpath("transcript.jsonl").write_text(
        json.dumps({"role": "user", "content": "Build a tiny artifact."}) + "\n",
        encoding="utf-8",
    )

    server, thread, host, port = _serve_operating_layer(tmp_path)
    try:
        conn = HTTPConnection(host, port, timeout=5)
        start_body = {
            "definition_of_done": "A short test artifact",
            "builder_profile_id": "builder-a",
            "judge_profile_id": "judge-a",
            "async": True,
        }
        conn.request(
            "POST",
            "/api/builder-judge/start",
            body=json.dumps(start_body),
            headers={"Content-Type": "application/json"},
        )
        start_payload = json.loads(conn.getresponse().read().decode("utf-8"))
        assert start_payload["loop_family"] == "builder_judge"
        assert start_payload["status_label"]

        conn = HTTPConnection(host, port, timeout=5)
        conn.request("GET", "/api/builder-judge/status?loop_id=bj-file")
        status_payload = json.loads(conn.getresponse().read().decode("utf-8"))
        assert status_payload["loop_family"] == "builder_judge"
        assert status_payload["status_label"] == "Passed"
        assert status_payload["evidence_path"] == raw_run["evidence_path"]

        conn = HTTPConnection(host, port, timeout=5)
        conn.request("GET", "/api/builder-judge/list")
        list_payload = json.loads(conn.getresponse().read().decode("utf-8"))
        assert list_payload["loops"][0]["loop_family"] == "builder_judge"
        assert list_payload["loops"][0]["status_label"] == "Passed"

        conn = HTTPConnection(host, port, timeout=5)
        conn.request(
            "POST",
            "/api/builder-judge/quality-gate",
            body=json.dumps({"session_id": "session-1", "stage": "spec"}),
            headers={"Content-Type": "application/json"},
        )
        quality_payload = json.loads(conn.getresponse().read().decode("utf-8"))
        assert quality_payload["loop_family"] == "builder_judge"
        assert quality_payload["status_label"] == "Passed"
        assert quality_payload["evidence_path"] == ".devflow/builder-judge-loops/qg-spec-test/run.json"
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)
        _clear_builder_judge_state()


def test_builder_judge_async_start_status_and_list_are_consistent_under_concurrency(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    setup_temp_git_repo(tmp_path)
    _clear_builder_judge_state()
    started = threading.Event()
    release = threading.Event()

    def fake_run_builder(
        root: Path,
        config,
        *,
        loop_id: str | None = None,
        write_evidence: bool = True,
    ) -> _FakeBuilderJudgeRun:
        started.set()
        release.wait(timeout=5)
        return _FakeBuilderJudgeRun(loop_id or "bj-race", "passed")

    monkeypatch.setattr("devflow.control_room.builder_judge_loop._generate_loop_id", lambda: "bj-race")
    monkeypatch.setattr(builder_judge_routes, "run_builder_judge_loop", fake_run_builder)

    server, thread, host, port = _serve_operating_layer(tmp_path)
    try:
        status, start_payload = _post_json(
            host,
            port,
            "/api/builder-judge/start",
            {
                "definition_of_done": "A short test artifact",
                "builder_profile_id": "builder-a",
                "judge_profile_id": "judge-a",
                "async": True,
            },
        )
        assert status == HTTPStatus.OK
        assert start_payload["loop_id"] == "bj-race"
        assert start_payload["status"] == "running"
        assert started.wait(timeout=5)
        with bj_runtime._bj_state_lock:
            assert bj_runtime._bj_threads["bj-race"].is_alive()

        barrier = threading.Barrier(6)
        results: list[tuple[str, int, dict[str, object]]] = []

        def _request(path: str) -> None:
            barrier.wait(timeout=5)
            response_status, body, _headers = _get_raw(host, port, path)
            results.append((path, response_status, json.loads(body.decode("utf-8"))))

        request_threads = [
            threading.Thread(target=_request, args=("/api/builder-judge/status?loop_id=bj-race",), daemon=True)
            for _ in range(3)
        ] + [
            threading.Thread(target=_request, args=("/api/builder-judge/list",), daemon=True)
            for _ in range(3)
        ]
        for request_thread in request_threads:
            request_thread.start()
        for request_thread in request_threads:
            request_thread.join(timeout=5)

        assert len(results) == 6
        for path, response_status, payload in results:
            assert response_status == HTTPStatus.OK
            if path.endswith("/status?loop_id=bj-race"):
                assert payload["loop_id"] == "bj-race"
                assert payload["status"] == "running"
            else:
                assert any(loop["loop_id"] == "bj-race" and loop["status"] == "running" for loop in payload["loops"])

        release.set()
        final_payload = None
        for _ in range(100):
            status_code, body, _headers = _get_raw(host, port, "/api/builder-judge/status?loop_id=bj-race")
            final_payload = json.loads(body.decode("utf-8"))
            if final_payload.get("status") == "passed":
                assert status_code == HTTPStatus.OK
                break
            threading.Event().wait(0.05)
        assert final_payload is not None
        assert final_payload["status"] == "passed"

        status_code, body, _headers = _get_raw(host, port, "/api/builder-judge/list")
        assert status_code == HTTPStatus.OK
        list_payload = json.loads(body.decode("utf-8"))
        assert any(loop["loop_id"] == "bj-race" and loop["status"] == "passed" for loop in list_payload["loops"])
    finally:
        release.set()
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)
        _clear_builder_judge_state()


def test_builder_judge_start_validation_returns_action_error_envelope(
    tmp_path: Path,
) -> None:
    setup_temp_git_repo(tmp_path)

    server, thread, host, port = _serve_operating_layer(tmp_path)
    try:
        status, payload = _post_json(host, port, "/api/builder-judge/start", {})
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)

    assert status == HTTPStatus.BAD_REQUEST
    assert payload["error"] == "definition_of_done is required"
    assert payload["error_code"] == "validation_error"
    assert payload["error_type"] == "ValueError"
    assert payload["retriable"] is False


def test_builder_judge_completed_thread_entries_are_bounded(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    setup_temp_git_repo(tmp_path)
    _clear_builder_judge_state()
    monkeypatch.setattr(bj_runtime, "_bj_completed_thread_retention", 1)
    loop_ids = iter(["bj-one", "bj-two"])

    def fake_run_builder(
        root: Path,
        config,
        *,
        loop_id: str | None = None,
        write_evidence: bool = True,
    ) -> _FakeBuilderJudgeRun:
        return _FakeBuilderJudgeRun(loop_id or "bj-loop", "passed")

    monkeypatch.setattr(builder_judge_routes, "run_builder_judge_loop", fake_run_builder)
    monkeypatch.setattr("devflow.control_room.builder_judge_loop._generate_loop_id", lambda: next(loop_ids))

    server, thread, host, port = _serve_operating_layer(tmp_path)
    try:
        for expected_loop_id in ("bj-one", "bj-two"):
            status, start_payload = _post_json(
                host,
                port,
                "/api/builder-judge/start",
                {
                    "definition_of_done": "A short test artifact",
                    "builder_profile_id": "builder-a",
                    "judge_profile_id": "judge-a",
                    "async": True,
                },
            )
            assert status == HTTPStatus.OK
            assert start_payload["loop_id"] == expected_loop_id
            for _ in range(100):
                status_code, body, _headers = _get_raw(
                    host,
                    port,
                    f"/api/builder-judge/status?loop_id={expected_loop_id}",
                )
                payload = json.loads(body.decode("utf-8"))
                if payload.get("status") == "passed":
                    assert status_code == HTTPStatus.OK
                    break
                threading.Event().wait(0.02)
            else:
                pytest.fail(f"loop {expected_loop_id} never reached passed")

        with bj_runtime._bj_state_lock:
            assert list(bj_runtime._bj_threads) == ["bj-two"]
            assert all(not thread_obj.is_alive() for thread_obj in bj_runtime._bj_threads.values())
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)
        _clear_builder_judge_state()


def test_builder_judge_background_failure_stays_visible_in_status_and_list(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    setup_temp_git_repo(tmp_path)
    _clear_builder_judge_state()
    started = threading.Event()
    release = threading.Event()

    def fake_run_builder(
        root: Path,
        config,
        *,
        loop_id: str | None = None,
        write_evidence: bool = True,
    ) -> _FakeBuilderJudgeRun:
        started.set()
        release.wait(timeout=5)
        raise RuntimeError("boom")

    monkeypatch.setattr("devflow.control_room.builder_judge_loop._generate_loop_id", lambda: "bj-fail")
    monkeypatch.setattr(builder_judge_routes, "run_builder_judge_loop", fake_run_builder)

    server, thread, host, port = _serve_operating_layer(tmp_path)
    try:
        status, start_payload = _post_json(
            host,
            port,
            "/api/builder-judge/start",
            {
                "definition_of_done": "A short test artifact",
                "builder_profile_id": "builder-a",
                "judge_profile_id": "judge-a",
                "async": True,
            },
        )
        assert status == HTTPStatus.OK
        assert start_payload["loop_id"] == "bj-fail"
        assert start_payload["status"] == "running"
        assert started.wait(timeout=5)

        release.set()
        failed_payload = None
        for _ in range(100):
            status_code, body, _headers = _get_raw(host, port, "/api/builder-judge/status?loop_id=bj-fail")
            failed_payload = json.loads(body.decode("utf-8"))
            if failed_payload.get("status") == "failed":
                assert status_code == HTTPStatus.OK
                break
            threading.Event().wait(0.05)
        assert failed_payload is not None
        assert failed_payload["status"] == "failed"
        assert failed_payload["stop_reason"] == "background_thread_error"
        assert failed_payload["next_safe_action"] == "boom"

        status_code, body, _headers = _get_raw(host, port, "/api/builder-judge/list")
        assert status_code == HTTPStatus.OK
        list_payload = json.loads(body.decode("utf-8"))
        assert any(loop["loop_id"] == "bj-fail" and loop["status"] == "failed" for loop in list_payload["loops"])
    finally:
        release.set()
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)
        _clear_builder_judge_state()
