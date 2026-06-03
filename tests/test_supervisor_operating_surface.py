from __future__ import annotations

import json
import subprocess
from pathlib import Path

from typer.testing import CliRunner

from devflow.cli import app
from devflow.control_room.service import create_task


runner = CliRunner()


def _read_json(result) -> dict:
    assert result.exit_code == 0, result.output
    return json.loads(result.output)


def _snapshot(root: Path) -> dict[str, bytes]:
    files: dict[str, bytes] = {}
    for path in sorted(root.rglob("*")):
        if path.is_file() and ".git" not in path.parts:
            files[path.relative_to(root).as_posix()] = path.read_bytes()
    return files


def _git_snapshot(root: Path) -> dict[str, str]:
    if not (root / ".git").exists():
        return {}

    def git(*args: str) -> str:
        result = subprocess.run(["git", *args], cwd=root, capture_output=True, text=True, check=True)
        return result.stdout

    return {
        "head": git("rev-parse", "HEAD").strip(),
        "branch": git("branch", "--show-current").strip(),
        "refs": git("show-ref", "--heads"),
        "status": git("status", "--short"),
    }


def _invoke_read_only(root: Path, args: list[str]):
    before = _snapshot(root)
    before_git = _git_snapshot(root)
    result = runner.invoke(app, args)
    after = _snapshot(root)
    after_git = _git_snapshot(root)
    assert after == before
    assert after_git == before_git
    assert result.exit_code == 0, result.output
    return result


def _write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, sort_keys=True, indent=2) + "\n", encoding="utf-8")


def _write_qwopus_patch(root: Path, task_id: str, patch: str = "diff --git a/a.txt b/a.txt\n") -> Path:
    agent_dir = root / ".devflow" / "tasks" / task_id / "agents" / "qwopus-implementer"
    agent_dir.mkdir(parents=True, exist_ok=True)
    (agent_dir / "proposal.patch").write_text(patch, encoding="utf-8")
    _write_json(
        agent_dir / "run.json",
        {
            "schema_version": 1,
            "task_id": task_id,
            "status": "success",
            "proposal_patch_found": True,
            "proposal_patch_byte_length": len(patch),
        },
    )
    return agent_dir / "proposal.patch"


def _write_local_run(root: Path, task_id: str, *, review: bool = False, dry_run: bool = False) -> Path:
    run_dir = root / ".devflow" / "tasks" / task_id / "local-model-runs" / "agent-qwopus-implementer"
    run_dir.mkdir(parents=True, exist_ok=True)
    patch_rel = f".devflow/tasks/{task_id}/local-model-runs/agent-qwopus-implementer/proposal.patch"
    review_rel = f".devflow/tasks/{task_id}/local-model-runs/agent-qwopus-implementer/patch-review.json"
    (run_dir / "proposal.patch").write_text("diff --git a/a.txt b/a.txt\n", encoding="utf-8")
    if review:
        _write_json(
            run_dir / "patch-review.json",
            {
                "schema_version": 1,
                "task_id": task_id,
                "run_id": "agent-qwopus-implementer",
                "patch_path": patch_rel,
                "review_status": "low_risk_candidate",
                "risk": "low",
                "files_touched": ["a.txt"],
            },
        )
        (run_dir / "patch-review.md").write_text("Patch review\n", encoding="utf-8")
    if dry_run:
        _write_json(
            run_dir / "patch-dry-run.json",
            {
                "schema_version": 1,
                "task_id": task_id,
                "run_id": "agent-qwopus-implementer",
                "proposal_patch_path": patch_rel,
                "patch_review_path": review_rel,
                "dry_run_status": "would_apply_cleanly",
                "risk": "low",
                "hunks_matched": 1,
                "hunks_failed": 0,
            },
        )
        (run_dir / "patch-dry-run.md").write_text("Patch dry-run\n", encoding="utf-8")
    return run_dir


def test_supervisor_policy_json_is_versioned_and_declares_boundaries(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    create_task(tmp_path, "policy context")

    payload = _read_json(_invoke_read_only(tmp_path, ["supervisor", "policy", "--json"]))

    assert payload["schema_version"] == 1
    assert payload["policy_id"] == "devflow-supervisor-policy"
    assert "devflow status --json" in payload["allowed_commands"]
    assert "devflow task apply-patch" in payload["commands_requiring_human_approval"]
    assert "promoting without human approval" in payload["forbidden_actions"]


def test_task_next_action_json_covers_patch_gate_and_closed_states(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)

    no_evidence = create_task(tmp_path, "empty active task")
    payload = _read_json(_invoke_read_only(tmp_path, ["task", "next-action", no_evidence.id, "--json"]))
    assert payload["next_safe_action"] == "run worker or provide patch evidence"
    assert payload["confidence"] == "high"

    proposal_task = create_task(tmp_path, "proposal without review")
    _write_qwopus_patch(tmp_path, proposal_task.id)
    payload = _read_json(_invoke_read_only(tmp_path, ["task", "next-action", proposal_task.id, "--json"]))
    assert payload["next_safe_action"] == f"run devflow task review-patch {proposal_task.id} --agent qwopus-implementer"
    assert payload["requires_human_approval"] is False
    assert "proposal.patch" in " ".join(payload["evidence_considered"])

    reviewed_task = create_task(tmp_path, "reviewed without dry-run")
    _write_local_run(tmp_path, reviewed_task.id, review=True)
    payload = _read_json(_invoke_read_only(tmp_path, ["task", "next-action", reviewed_task.id, "--json"]))
    assert payload["next_safe_action"] == f"run devflow task patch-dry-run {reviewed_task.id}"

    dry_run_task = create_task(tmp_path, "dry-run ready")
    _write_local_run(tmp_path, dry_run_task.id, review=True, dry_run=True)
    payload = _read_json(_invoke_read_only(tmp_path, ["task", "next-action", dry_run_task.id, "--json"]))
    assert payload["next_safe_action"] == f"human approval required before devflow task apply-patch {dry_run_task.id}"
    assert payload["requires_human_approval"] is True

    failed = create_task(tmp_path, "verification failed")
    run_result = runner.invoke(app, ["task", "run", failed.id, "--shell", "echo done"])
    assert run_result.exit_code == 0, run_result.output
    verify_failed = runner.invoke(app, ["task", "verify", failed.id, "--shell", "exit 3"])
    assert verify_failed.exit_code == 3, verify_failed.output
    payload = _read_json(_invoke_read_only(tmp_path, ["task", "next-action", failed.id, "--json"]))
    assert payload["next_safe_action"] == "inspect verification evidence and fix task branch/workspace"
    assert payload["confidence"] == "high"

    closed = create_task(tmp_path, "closed rejected")
    close_result = runner.invoke(app, ["task", "close", closed.id, "--outcome", "rejected", "--reason", "not needed"])
    assert close_result.exit_code == 0, close_result.output
    payload = _read_json(_invoke_read_only(tmp_path, ["task", "next-action", closed.id, "--json"]))
    assert payload["next_safe_action"] == "no action; task is closed or non-promotable"
    assert payload["allowed_commands"] == []


def test_task_review_json_cites_evidence_paths_and_tolerates_missing_artifacts(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    task = create_task(tmp_path, "review me")
    _write_qwopus_patch(tmp_path, task.id)
    _write_local_run(tmp_path, task.id, review=True)
    verification = tmp_path / ".devflow" / "tasks" / task.id / "verification.json"
    verification.unlink()

    payload = _read_json(_invoke_read_only(tmp_path, ["task", "review", task.id, "--json"]))

    assert payload["schema_version"] == 1
    assert payload["task"]["id"] == task.id
    assert payload["patch_proposal"]["has_proposal_patch"] is True
    assert payload["patch_review"]["status"] == "low_risk_candidate"
    assert payload["verification"]["status"] == "unknown"
    assert payload["promotion_preview"]["status"] == "unknown"
    assert f".devflow/tasks/{task.id}/task.yaml" in payload["evidence_paths"]
    assert f".devflow/tasks/{task.id}/agents/qwopus-implementer/proposal.patch" in payload["evidence_paths"]
    assert payload["next_action"]["next_safe_action"] == f"run devflow task patch-dry-run {task.id}"

    human = _invoke_read_only(tmp_path, ["task", "review", task.id])
    assert "Forbidden/bypass actions" in human.output
    assert "Evidence paths" in human.output


def test_status_json_and_supervisor_packet_summarize_state_read_only(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    active = create_task(tmp_path, "active")
    review_ready = create_task(tmp_path, "needs patch review")
    _write_qwopus_patch(tmp_path, review_ready.id)

    failed = create_task(tmp_path, "failed verification")
    assert runner.invoke(app, ["task", "run", failed.id, "--shell", "echo done"]).exit_code == 0
    assert runner.invoke(app, ["task", "verify", failed.id, "--shell", "exit 4"]).exit_code == 4

    closed = create_task(tmp_path, "closed duplicate")
    close_result = runner.invoke(app, ["task", "close", closed.id, "--outcome", "duplicate", "--reason", "covered elsewhere"])
    assert close_result.exit_code == 0, close_result.output

    status = _read_json(_invoke_read_only(tmp_path, ["status", "--json"]))
    assert status["schema_version"] == 1
    assert status["active_task_count"] == 3
    assert status["closed_task_count"] == 1
    assert status["review_ready_task_count"] == 1
    assert status["verification_failed_task_count"] == 1
    by_id = {task["id"]: task for task in status["tasks"]}
    assert by_id[active.id]["next_safe_action"] == "run worker or provide patch evidence"
    assert by_id[review_ready.id]["has_proposal_patch"] is True
    assert by_id[failed.id]["verification_status"] == "failed"

    packet = _read_json(_invoke_read_only(tmp_path, ["supervisor", "packet", "--json"]))
    assert packet["schema_version"] == 1
    assert packet["project"]["repo_root"] == str(tmp_path)
    assert review_ready.id in [task["id"] for task in packet["tasks_needing_review"]]
    assert failed.id in [task["id"] for task in packet["tasks_blocked"]]
    assert packet["policy"]["policy_id"] == "devflow-supervisor-policy"
    assert packet["next_recommended_safe_actions"]


def test_git_native_promotion_ready_task_is_reported_without_mutating_refs(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    subprocess.run(["git", "init", "-b", "main"], cwd=tmp_path, check=True)
    subprocess.run(["git", "config", "user.email", "test@example.com"], cwd=tmp_path, check=True)
    subprocess.run(["git", "config", "user.name", "Test User"], cwd=tmp_path, check=True)
    (tmp_path / "base.txt").write_text("base\n", encoding="utf-8")
    subprocess.run(["git", "add", "base.txt"], cwd=tmp_path, check=True)
    subprocess.run(["git", "commit", "-m", "init"], cwd=tmp_path, check=True)

    created = runner.invoke(app, ["task", "create", "--git-worktree", "git ready"])
    assert created.exit_code == 0, created.output
    run = runner.invoke(
        app,
        [
            "task",
            "run",
            "task-0001",
            "--worker",
            "shell",
            "--",
            "/bin/sh",
            "-c",
            "printf 'ready\\n' > ready.txt && git add ready.txt && git commit -m ready",
        ],
    )
    assert run.exit_code == 0, run.output
    verify = runner.invoke(app, ["task", "verify", "task-0001", "--", "/bin/sh", "-c", "test -f ready.txt"])
    assert verify.exit_code == 0, verify.output
    preview = runner.invoke(app, ["task", "promote-preview", "task-0001"])
    assert preview.exit_code == 0, preview.output

    next_action = _read_json(_invoke_read_only(tmp_path, ["task", "next-action", "task-0001", "--json"]))
    assert next_action["next_safe_action"] == "human approval required before devflow task promote task-0001"
    assert next_action["requires_human_approval"] is True

    status = _read_json(_invoke_read_only(tmp_path, ["status", "--json"]))
    task_record = status["tasks"][0]
    assert task_record["mode"] == "git-worktree"
    assert task_record["promotion_readiness"] == "ready"
    assert task_record["commands_requiring_human_approval"] == ["devflow task promote task-0001"]

    packet = _read_json(_invoke_read_only(tmp_path, ["supervisor", "packet", "--json"]))
    assert packet["tasks_promotion_ready"][0]["id"] == "task-0001"
    assert ".devflow/tasks/task-0001/workers/shell/promotion-preview.json" in packet["evidence_paths"]
