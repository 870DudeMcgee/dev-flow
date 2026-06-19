from __future__ import annotations

import json
import subprocess
from pathlib import Path

from typer.testing import CliRunner

from devflow.cli import app
from devflow.control_room.persistence import get_task, save_task
from devflow.control_room.service import create_task
from devflow.control_room.supervisor_surface import (
    APPROVAL_REQUIRED_EVIDENCE_WRITING,
    APPROVAL_REQUIRED_GIT,
    APPROVAL_REQUIRED_TASK_STATE,
    APPROVAL_REQUIRED_WORKER_RUNTIME,
    FORBIDDEN_FOR_SUPERVISOR,
    PURE_READ_ONLY,
    classify_supervisor_command,
)


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


def test_evidence_writing_commands_are_not_pure_read_only() -> None:
    for command in (
        "devflow task review-patch task-0001",
        "devflow task patch-dry-run task-0001",
        "devflow task packet task-0001 --save",
        "devflow knowledge capture --from-task task-0001",
        "devflow idea capture rough idea",
        "devflow idea classify I-0001 --maturity goal_ready",
        "devflow idea promote I-0001 --to goal --rationale reviewed",
        "devflow idea park I-0001 --reason later",
        "devflow idea archive I-0001 --reason superseded",
    ):
        classification = classify_supervisor_command(command)
        assert classification["safety_class"] == APPROVAL_REQUIRED_EVIDENCE_WRITING
        assert classification["requires_human_approval"] is True
        assert classification["supervisor_may_auto_run"] is False
        assert classification["why_not_auto_runnable"]


def test_question_commands_are_classified_by_supervisor_policy() -> None:
    read_only_list = classify_supervisor_command("devflow question list")
    read_only_show = classify_supervisor_command("devflow question show Q-task-0001-abc123")
    answer = classify_supervisor_command('devflow question answer Q-task-0001-abc123 --answer "Use v2"')
    resolve = classify_supervisor_command('devflow question resolve Q-task-0001-abc123 --reason "stale"')

    assert read_only_list["safety_class"] == PURE_READ_ONLY
    assert read_only_show["safety_class"] == PURE_READ_ONLY
    assert answer["safety_class"] == APPROVAL_REQUIRED_EVIDENCE_WRITING
    assert resolve["safety_class"] == APPROVAL_REQUIRED_EVIDENCE_WRITING


def test_question_summary_reaches_supervisor_packet(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    task = create_task(tmp_path, "supervisor question")
    agent_dir = tmp_path / ".devflow" / "tasks" / task.id / "agents" / "devflow-manual-codex-worker"
    agent_dir.mkdir(parents=True, exist_ok=True)
    (agent_dir / "questions.jsonl").write_text(
        (
            '{"type":"blocked_question","task_id":"task-0001",'
            '"agent_id":"devflow-manual-codex-worker","question":"Which branch should I inspect?"}\n'
        ),
        encoding="utf-8",
    )

    packet = _read_json(_invoke_read_only(tmp_path, ["supervisor", "packet", "--json"]))

    assert packet["questions"]["counts"]["open"] == 1
    assert packet["questions"]["next_safe_action"].startswith("devflow question answer Q-task-0001-")
    assert ".devflow/tasks/task-0001/agents/devflow-manual-codex-worker/questions.jsonl" in packet["evidence_paths"]


def test_worker_runtime_commands_are_approval_required() -> None:
    for command in (
        "devflow task run task-0001 --worker shell -- pytest",
        "devflow task local task-0001 --agent qwen-planner",
        "devflow task local-review task-0001",
        "devflow task verify task-0001 --shell pytest",
        "devflow supervise --once",
    ):
        classification = classify_supervisor_command(command)
        assert classification["safety_class"] == APPROVAL_REQUIRED_WORKER_RUNTIME
        assert classification["requires_human_approval"] is True
        assert classification["supervisor_may_auto_run"] is False


def test_task_state_commands_are_approval_required() -> None:
    for command in (
        "devflow task create example",
        "devflow task close task-0001 --outcome duplicate --reason covered",
        "devflow task finalize task-0001",
        "devflow task cleanup task-0001",
        "devflow task cleanup task-0001 --preview",
        "devflow task cleanup task-0001 --apply",
        "devflow task prune-closed --preview --older-than 30d",
        "devflow task prune-closed --apply --older-than 30d",
        "devflow task apply-patch task-0001",
    ):
        classification = classify_supervisor_command(command)
        assert classification["safety_class"] == APPROVAL_REQUIRED_TASK_STATE
        assert classification["requires_human_approval"] is True
        assert classification["supervisor_may_auto_run"] is False


def test_preview_and_dry_run_commands_remain_non_promoting_read_only() -> None:
    for command in (
        "devflow task cleanup task-0001 --dry-run",
        "devflow task promote-preview task-0001",
    ):
        classification = classify_supervisor_command(command)
        assert classification["safety_class"] == PURE_READ_ONLY
        assert classification["requires_human_approval"] is False
        assert classification["supervisor_may_auto_run"] is True


def test_idea_read_only_commands_are_supervisor_safe() -> None:
    for command in (
        "devflow idea list",
        "devflow idea show I-0001",
    ):
        classification = classify_supervisor_command(command)
        assert classification["requires_human_approval"] is False
        assert classification["supervisor_may_auto_run"] is True


def test_idea_park_requires_evidence_writing_approval() -> None:
    classification = classify_supervisor_command("devflow idea park I-0001 --reason 'not now'")

    assert classification["safety_class"] == APPROVAL_REQUIRED_EVIDENCE_WRITING
    assert classification["requires_human_approval"] is True
    assert classification["supervisor_may_auto_run"] is False


def test_idea_bridge_dry_run_commands_are_supervisor_safe() -> None:
    for command in (
        "devflow idea create-goal I-0001 --dry-run",
        "devflow idea create-task I-0001 --dry-run",
    ):
        classification = classify_supervisor_command(command)
        assert classification["safety_class"] == PURE_READ_ONLY
        assert classification["requires_human_approval"] is False
        assert classification["supervisor_may_auto_run"] is True


def test_idea_bridge_creation_commands_are_task_state_mutations() -> None:
    for command in (
        "devflow idea create-goal I-0001",
        "devflow idea create-task I-0001",
    ):
        classification = classify_supervisor_command(command)
        assert classification["safety_class"] == APPROVAL_REQUIRED_TASK_STATE
        assert classification["requires_human_approval"] is True
        assert classification["supervisor_may_auto_run"] is False


def test_git_and_promotion_commands_are_approval_required_or_forbidden() -> None:
    for command in (
        "devflow task promote task-0001",
        "devflow push-main",
        "devflow sync-main",
        "devflow branch archive devflow/task-0001",
        "devflow worktree prune --apply",
        "devflow task finalize task-0001 --commit",
    ):
        classification = classify_supervisor_command(command)
        assert classification["safety_class"] == APPROVAL_REQUIRED_GIT
        assert classification["requires_human_approval"] is True
        assert classification["supervisor_may_auto_run"] is False

    direct_git = classify_supervisor_command("git commit -am unsafe")
    assert direct_git["safety_class"] == FORBIDDEN_FOR_SUPERVISOR
    assert direct_git["supervisor_may_auto_run"] is False


def test_unknown_commands_default_to_forbidden_for_supervisor() -> None:
    classification = classify_supervisor_command("devflow task teleport task-0001")
    assert classification["safety_class"] == FORBIDDEN_FOR_SUPERVISOR
    assert classification["requires_human_approval"] is True
    assert classification["supervisor_may_auto_run"] is False
    assert classification["why_not_auto_runnable"]


def test_supervisor_policy_json_is_versioned_and_declares_boundaries(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    create_task(tmp_path, "policy context")

    payload = _read_json(_invoke_read_only(tmp_path, ["supervisor", "policy", "--json"]))

    assert payload["schema_version"] == 1
    assert payload["policy_id"] == "devflow-supervisor-policy"
    assert "devflow status --json" in payload["allowed_commands"]
    assert "devflow dashboard --json" in payload["allowed_commands"]
    assert "devflow project list" in payload["allowed_commands"]
    assert "devflow supervisor policy --json" in payload["allowed_commands"]
    assert "devflow supervisor packet --json" in payload["allowed_commands"]
    assert "devflow supervisor route-message --json" in payload["allowed_commands"]
    assert "devflow hermes imessage-check --json" in payload["allowed_commands"]
    assert "devflow task promote-preview" in payload["allowed_commands"]
    assert payload["allowed_commands"] == payload["pure_read_only"]
    for command in (
        "devflow task review-patch",
        "devflow task patch-dry-run",
        "devflow task verify",
        "devflow task create",
        "devflow task cleanup --preview",
        "devflow task prune-closed --preview",
        "devflow knowledge capture",
    ):
        assert command not in payload["allowed_commands"]
    assert "devflow task apply-patch" in payload["commands_requiring_human_approval"]
    assert "devflow project create" in payload["commands_requiring_human_approval"]
    assert "devflow project connect-github" in payload["commands_requiring_human_approval"]
    assert "devflow task review-patch" in payload["approval_required_evidence_writing"]
    assert "devflow task patch-dry-run" in payload["approval_required_evidence_writing"]
    assert "devflow idea park" in payload["approval_required_evidence_writing"]
    assert "devflow task verify" in payload["approval_required_worker_runtime"]
    assert "devflow task create" in payload["approval_required_task_state"]
    assert "devflow project create" in payload["approval_required_task_state"]
    assert "devflow project connect-github" in payload["approval_required_git"]
    assert "devflow task cleanup --preview" in payload["approval_required_task_state"]
    assert "devflow task prune-closed --preview" in payload["approval_required_task_state"]
    assert "devflow task prune-closed --apply" in payload["approval_required_task_state"]
    assert "devflow task cleanup --dry-run" in payload["allowed_commands"]
    assert "devflow knowledge capture" in payload["approval_required_evidence_writing"]
    assert "any command not recognized by the supervisor policy" in payload["forbidden_for_supervisor"]
    assert payload["operator_layer"]["hermes_role"] == "external operator/chat/scheduling layer"
    assert payload["operator_layer"]["read_only_default"] is True
    assert "scheduled read-only briefs" in payload["operator_layer"]["may"]
    assert "task state" in payload["operator_layer"]["devflow_source_of_truth_for"]
    assert "directly edit .devflow" in payload["operator_layer"]["must_not"]
    assert "spawn unbounded parallel workers" in payload["operator_layer"]["must_not"]
    assert "promotion" in payload["operator_layer"]["human_approval_required_for"]
    assert payload["operator_layer"]["browser_allowed_mutations"] == [
        "idea capture",
        "task creation",
        "shell worker execution",
        "model/provider onboarding",
        "task verification",
        "task promotion",
    ]
    assert "non-shell worker execution" in payload["operator_layer"]["browser_blocked_mutations"]
    assert "local/provider model execution" in payload["operator_layer"]["browser_blocked_mutations"]
    assert payload["telegram_routing"]["provider"] == "local"
    assert payload["telegram_routing"]["default_model"] == "gemma4:latest"
    assert payload["telegram_routing"]["footer_required"] is True
    assert payload["telegram_routing"]["routes"]["implementation"]["model"] is None
    assert payload["path_authority"]["josh_canonical_checkout"] == "<repo-root>"
    assert "actual repo root" in payload["path_authority"]["portable_guidance"]
    assert "/Users/jewelbait/Desktop/DevFlow" in payload["path_authority"]["prohibited_checkout_paths"]


def test_task_next_action_json_covers_patch_gate_and_closed_states(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)

    no_evidence = create_task(tmp_path, "empty active task")
    payload = _read_json(_invoke_read_only(tmp_path, ["task", "next-action", no_evidence.id, "--json"]))
    assert payload["next_safe_action"] == (
        f"request human approval before running devflow task run {no_evidence.id} --worker shell -- <command>"
    )
    assert payload["recommended_action"] == "run worker or provide patch evidence"
    assert payload["safety_class"] == APPROVAL_REQUIRED_WORKER_RUNTIME
    assert payload["requires_human_approval"] is True
    assert payload["why_not_auto_runnable"]
    assert payload["confidence"] == "high"

    proposal_task = create_task(tmp_path, "proposal without review")
    _write_qwopus_patch(tmp_path, proposal_task.id)
    payload = _read_json(_invoke_read_only(tmp_path, ["task", "next-action", proposal_task.id, "--json"]))
    review_command = f"devflow task review-patch {proposal_task.id} --agent qwopus-implementer"
    assert payload["next_safe_action"] == f"request human approval before running {review_command}"
    assert payload["recommended_action"] == f"run {review_command}"
    assert payload["recommended_command"] == review_command
    assert payload["safety_class"] == APPROVAL_REQUIRED_EVIDENCE_WRITING
    assert payload["requires_human_approval"] is True
    assert review_command not in payload["allowed_commands"]
    assert review_command in payload["commands_requiring_human_approval"]
    assert payload["why_not_auto_runnable"]
    assert "proposal.patch" in " ".join(payload["evidence_considered"])

    reviewed_task = create_task(tmp_path, "reviewed without dry-run")
    _write_local_run(tmp_path, reviewed_task.id, review=True)
    payload = _read_json(_invoke_read_only(tmp_path, ["task", "next-action", reviewed_task.id, "--json"]))
    dry_run_command = f"devflow task patch-dry-run {reviewed_task.id}"
    assert payload["next_safe_action"] == f"request human approval before running {dry_run_command}"
    assert payload["recommended_command"] == dry_run_command
    assert payload["safety_class"] == APPROVAL_REQUIRED_EVIDENCE_WRITING
    assert payload["requires_human_approval"] is True

    dry_run_task = create_task(tmp_path, "dry-run ready")
    _write_local_run(tmp_path, dry_run_task.id, review=True, dry_run=True)
    payload = _read_json(_invoke_read_only(tmp_path, ["task", "next-action", dry_run_task.id, "--json"]))
    assert payload["next_safe_action"] == f"request human approval before running devflow task apply-patch {dry_run_task.id}"
    assert payload["recommended_action"] == f"human approval required before devflow task apply-patch {dry_run_task.id}"
    assert payload["safety_class"] == APPROVAL_REQUIRED_TASK_STATE
    assert payload["requires_human_approval"] is True

    failed = create_task(tmp_path, "verification failed")
    run_result = runner.invoke(app, ["task", "run", failed.id, "--shell", "echo done"])
    assert run_result.exit_code == 0, run_result.output
    verify_failed = runner.invoke(app, ["task", "verify", failed.id, "--shell", "exit 3"])
    assert verify_failed.exit_code == 3, verify_failed.output
    payload = _read_json(_invoke_read_only(tmp_path, ["task", "next-action", failed.id, "--json"]))
    assert payload["next_safe_action"] == "inspect verification evidence and fix task branch/workspace"
    assert payload["safety_class"] == PURE_READ_ONLY
    assert payload["requires_human_approval"] is False
    assert f"devflow task review {failed.id}" in payload["allowed_commands"]
    assert payload["confidence"] == "high"

    closed = create_task(tmp_path, "closed rejected")
    close_result = runner.invoke(app, ["task", "close", closed.id, "--outcome", "rejected", "--reason", "not needed"])
    assert close_result.exit_code == 0, close_result.output
    payload = _read_json(_invoke_read_only(tmp_path, ["task", "next-action", closed.id, "--json"]))
    assert payload["next_safe_action"] == "no action; task is closed or non-promotable"
    assert payload["safety_class"] == PURE_READ_ONLY
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
    assert payload["next_action"]["next_safe_action"] == (
        f"request human approval before running devflow task patch-dry-run {task.id}"
    )
    assert payload["next_action"]["recommended_command"] == f"devflow task patch-dry-run {task.id}"
    assert payload["next_action"]["safety_class"] == APPROVAL_REQUIRED_EVIDENCE_WRITING
    assert payload["commands_safe_to_run"] == []
    assert f"devflow task patch-dry-run {task.id}" in payload["commands_requiring_human_approval"]

    human = _invoke_read_only(tmp_path, ["task", "review", task.id])
    assert "Forbidden/bypass actions" in human.output
    assert "Evidence paths" in human.output
    assert "Commands safe to run" in human.output


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
    closed_failed = create_task(tmp_path, "closed failed dogfood evidence")
    assert runner.invoke(app, ["task", "run", closed_failed.id, "--shell", "echo done"]).exit_code == 0
    assert runner.invoke(app, ["task", "verify", closed_failed.id, "--shell", "exit 5"]).exit_code == 5
    close_failed = runner.invoke(
        app,
        ["task", "close", closed_failed.id, "--outcome", "evidence-only", "--reason", "dogfood evidence captured"],
    )
    assert close_failed.exit_code == 0, close_failed.output

    status = _read_json(_invoke_read_only(tmp_path, ["status", "--json"]))
    assert status["schema_version"] == 1
    assert status["active_task_count"] == 3
    assert status["closed_task_count"] == 2
    assert status["review_ready_task_count"] == 1
    assert status["verification_failed_task_count"] == 1
    assert status["scheduler"]["counts"]["needs_retry"] == 1
    by_id = {task["id"]: task for task in status["tasks"]}
    assert by_id[active.id]["recommended_action"] == "run worker or provide patch evidence"
    assert by_id[active.id]["safety_class"] == APPROVAL_REQUIRED_WORKER_RUNTIME
    assert by_id[active.id]["requires_human_approval"] is True
    assert by_id[review_ready.id]["has_proposal_patch"] is True
    assert by_id[failed.id]["verification_status"] == "failed"
    assert by_id[closed_failed.id]["active"] is False

    packet = _read_json(_invoke_read_only(tmp_path, ["supervisor", "packet", "--json"]))
    assert packet["schema_version"] == 1
    assert packet["project"]["repo_root"] == str(tmp_path)
    assert packet["repo"]["root"] == str(tmp_path)
    assert packet["counts"]["active_tasks"] == 3
    assert packet["active_task_count"] == 3
    assert packet["review_queue"] == packet["tasks_needing_review"]
    assert review_ready.id in [task["id"] for task in packet["tasks_needing_review"]]
    assert failed.id in [task["id"] for task in packet["tasks_blocked"]]
    assert packet["policy"]["policy_id"] == "devflow-supervisor-policy"
    assert packet["policy_summary"]["hermes_role"] == "external operator/chat/scheduling layer"
    assert "devflow hermes imessage-check --json" in packet["suggested_read_only_commands"]
    assert "devflow task verify" in packet["suggested_approval_required_commands"]
    assert packet["path_authority"]["josh_canonical_checkout"] == "<repo-root>"
    assert packet["next_safe_action"]
    assert "next_recommended_safe_actions" not in packet
    assert packet["next_recommended_actions"]
    review_action = next(
        action
        for action in packet["next_recommended_actions"]
        if action["recommended_command"] == f"devflow task review-patch {review_ready.id} --agent qwopus-implementer"
    )
    assert review_action["safety_class"] == APPROVAL_REQUIRED_EVIDENCE_WRITING
    assert review_action["requires_human_approval"] is True
    assert review_action["why_not_auto_runnable"]
    assert review_action["allowed_commands"] == []


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
    assert next_action["next_safe_action"] == "request human approval before running devflow task promote task-0001"
    assert next_action["recommended_action"] == "human approval required before devflow task promote task-0001"
    assert next_action["recommended_command"] == "devflow task promote task-0001"
    assert next_action["safety_class"] == APPROVAL_REQUIRED_GIT
    assert next_action["requires_human_approval"] is True

    status = _read_json(_invoke_read_only(tmp_path, ["status", "--json"]))
    task_record = status["tasks"][0]
    assert task_record["mode"] == "git-worktree"
    assert task_record["promotion_readiness"] == "ready"
    assert task_record["safety_class"] == APPROVAL_REQUIRED_GIT
    assert task_record["requires_human_approval"] is True
    assert task_record["commands_requiring_human_approval"] == ["devflow task promote task-0001"]
    assert task_record["worker_lane"]["workspace_mode"] == "git-worktree"
    assert task_record["worker_lane"]["worker_branch"] == "devflow/task-0001/shell"
    assert task_record["worker_lane"]["readiness_status"] == "ready"
    assert task_record["worker_lane"]["next_safe_action"] == "devflow task promote task-0001"

    packet = _read_json(_invoke_read_only(tmp_path, ["supervisor", "packet", "--json"]))
    assert packet["tasks_promotion_ready"][0]["id"] == "task-0001"
    packet_task = packet["tasks"][0]
    assert packet_task["worker_lane"]["workspace_mode"] == "git-worktree"
    assert packet_task["worker_lane"]["worker_branch"] == "devflow/task-0001/shell"
    assert packet_task["worker_lane"]["readiness_status"] == "ready"
    assert packet_task["worker_lane"]["next_safe_action"] == "devflow task promote task-0001"
    assert ".devflow/tasks/task-0001/workers/shell/git.json" in packet_task["evidence_paths"]
    assert ".devflow/tasks/task-0001/workers/shell/promotion-preview.json" in packet["evidence_paths"]


def test_local_worker_lane_summary_reaches_supervisor_surfaces(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    task = create_task(tmp_path, "local worker lane")
    _write_qwopus_patch(tmp_path, task.id)

    status = _read_json(_invoke_read_only(tmp_path, ["status", "--json"]))
    task_record = status["tasks"][0]
    assert task_record["local_worker_lane"]["lane_type"] == "local-patch-worker"
    assert task_record["local_worker_lane"]["worker_id"] == "qwopus-implementer"
    assert task_record["local_worker_lane"]["readiness_status"] == "needs_review"
    assert (
        task_record["local_worker_lane"]["next_safe_action"]
        == "devflow task review-patch task-0001 --agent qwopus-implementer"
    )

    packet = _read_json(_invoke_read_only(tmp_path, ["supervisor", "packet", "--json"]))
    packet_task = packet["tasks"][0]
    assert packet_task["local_worker_lane"]["lane_type"] == "local-patch-worker"
    assert ".devflow/tasks/task-0001/agents/qwopus-implementer/run.json" in packet_task["evidence_paths"]


def test_scheduler_summary_reaches_supervisor_packet(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    create_task(tmp_path, "scheduler retry")
    task = get_task(tmp_path, "task-0001")
    task.status = "worker_failed"
    save_task(tmp_path / ".devflow" / "tasks" / task.id, task)

    packet = _read_json(_invoke_read_only(tmp_path, ["supervisor", "packet", "--json"]))

    assert packet["scheduler"]["counts"]["needs_retry"] == 1
    assert packet["scheduler"]["next_safe_action"] == 'devflow scheduler retry task-0001 --reason "<reason>"'
    assert ".devflow/tasks/task-0001/task.yaml" in packet["evidence_paths"]


def test_supervisor_safe_json_commands_parse_and_do_not_mutate(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    create_task(tmp_path, "operator json")

    for args in (
        ["status", "--json"],
        ["dashboard", "--json"],
        ["supervisor", "policy", "--json"],
        ["supervisor", "packet", "--json"],
        ["hermes", "imessage-check", "--json"],
    ):
        payload = _read_json(_invoke_read_only(tmp_path, list(args)))
        if args[0] == "dashboard":
            assert payload["project"]["root"] == str(tmp_path)
            assert "tasks" in payload
        elif args[0] == "hermes":
            assert payload["schema_version"] == 1
            assert payload["integration"] == "hermes-imessage"
            assert payload["privacy_boundary"]["reads_message_contents"] is False
            assert payload["privacy_boundary"]["sends_messages"] is False
            assert "chat.db" in payload["privacy_boundary"]["never_reads"]
        else:
            assert payload["schema_version"] == 1


def test_hermes_imessage_check_is_read_only_supervisor_command() -> None:
    classification = classify_supervisor_command("devflow hermes imessage-check --json")

    assert classification["safety_class"] == PURE_READ_ONLY
    assert classification["requires_human_approval"] is False
    assert classification["supervisor_may_auto_run"] is True


def test_telegram_route_message_is_read_only_supervisor_command() -> None:
    classification = classify_supervisor_command('devflow supervisor route-message "status" --json')

    assert classification["safety_class"] == PURE_READ_ONLY
    assert classification["requires_human_approval"] is False
    assert classification["supervisor_may_auto_run"] is True


def test_project_commands_are_classified_for_operator_approval() -> None:
    project_list = classify_supervisor_command("devflow project list")
    project_create = classify_supervisor_command("devflow project create telegram-smoke-test --source-control none")
    project_connect = classify_supervisor_command(
        "devflow project connect-github telegram-smoke-test --remote-url https://github.com/example/repo"
    )

    assert project_list["safety_class"] == PURE_READ_ONLY
    assert project_list["supervisor_may_auto_run"] is True
    assert project_create["safety_class"] == APPROVAL_REQUIRED_TASK_STATE
    assert project_create["requires_human_approval"] is True
    assert project_connect["safety_class"] == APPROVAL_REQUIRED_GIT
    assert project_connect["requires_human_approval"] is True


def test_goal_lifecycle_commands_are_approval_required_state_changes() -> None:
    for command in (
        "devflow goal activate G-0001 --reason ready",
        "devflow goal pause G-0001 --reason waiting",
        "devflow goal block G-0001 --reason blocked",
        "devflow goal complete G-0001 --reason done",
        "devflow goal archive G-0001 --reason superseded",
    ):
        classification = classify_supervisor_command(command)
        assert classification["safety_class"] == APPROVAL_REQUIRED_TASK_STATE
        assert classification["requires_human_approval"] is True
        assert classification["supervisor_may_auto_run"] is False


def test_hermes_docs_and_skill_flag_quarantined_checkout_path() -> None:
    root = Path(__file__).resolve().parents[1]
    docs = [
        root / "README.md",
        root / "AGENTS.md",
        root / "docs" / "agent-handoff.md",
        root / "docs" / "integrations" / "hermes-operator-layer.md",
        root / "docs" / "integrations" / "hermes-command-allowlist.md",
        root / "docs" / "integrations" / "hermes-imessage-exploration.md",
        root / "docs" / "integrations" / "hermes-local-parallelism.md",
        root / "docs" / "integrations" / "hermes-telegram-mac-mini-rollout.md",
        root / "skills" / "hermes" / "devflow" / "SKILL.md",
    ]
    for path in docs:
        body = path.read_text(encoding="utf-8")
        assert "/Users/jewelbait/Desktop/Local AI Dev Team" not in body
        assert "/Users/jewelbait/Desktop/DevFlow" in body
        assert "<repo-root>" in body or "actual local path" in body
        assert "quarantined" in body or "Prohibited old checkout" in body or "Forbidden" in body


def test_hermes_imessage_and_parallelism_docs_define_safe_boundaries() -> None:
    root = Path(__file__).resolve().parents[1]
    imessage = (root / "docs" / "integrations" / "hermes-imessage-exploration.md").read_text(encoding="utf-8")
    parallel = (root / "docs" / "integrations" / "hermes-local-parallelism.md").read_text(encoding="utf-8")
    skill = (root / "skills" / "hermes" / "devflow" / "SKILL.md").read_text(encoding="utf-8")

    assert "BlueBubbles" in imessage
    assert "imsg" in imessage
    assert "read-only/status" in imessage
    assert "Do not read chat.db" in imessage
    assert "Do not send a test message" in imessage
    assert "Dev-Flow status" in imessage
    assert "Push it" in imessage
    assert "I approve this exact Dev-Flow command" in imessage

    for level in ("Level 0", "Level 1", "Level 2", "Level 3", "Level 4", "Level 5"):
        assert level in parallel
    assert "one task per worker" in parallel
    assert "one worktree/branch per writer" in parallel
    assert "no shared write target" in parallel
    assert "no auto-promotion" in parallel
    assert "devflow dogfood local-parallel --workers 2 --profile qwopus --dry-run" in parallel

    assert "iMessage-specific response discipline" in skill
    assert "Morning Dev-Flow Brief" in skill
    assert "never promote, push, merge, delete, or directly edit" in skill
