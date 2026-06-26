from __future__ import annotations

import tempfile
import os
import json
import subprocess
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typer.testing import CliRunner

from devflow.cli import app
from devflow.control_room.service import create_task, init_control_room, doctor

runner = CliRunner()

def test_doctor_strict_checks() -> None:
    old_cwd = Path.cwd()
    with tempfile.TemporaryDirectory() as tmp_dir:
        tmp_path = Path(tmp_dir)
        try:
            os.chdir(tmp_path)
            
            # Setup mock git repository
            subprocess.run(["git", "init"], cwd=tmp_path, capture_output=True)
            subprocess.run(["git", "config", "user.email", "test@example.com"], cwd=tmp_path, capture_output=True)
            subprocess.run(["git", "config", "user.name", "Test User"], cwd=tmp_path, capture_output=True)
            
            # Write a commit so the worktree is clean
            test_file = tmp_path / "hello.txt"
            test_file.write_text("Hello\n", encoding="utf-8")
            subprocess.run(["git", "add", "hello.txt"], cwd=tmp_path, capture_output=True)
            subprocess.run(["git", "commit", "-m", "initial commit"], cwd=tmp_path, capture_output=True)

            # Init control room
            init_control_room(tmp_path)

            # Normal doctor should pass
            res = runner.invoke(app, ["doctor"])
            assert res.exit_code == 0, res.output

            # Strict doctor should pass since worktree is clean and only approved runtime agents are enabled
            res_strict = runner.invoke(app, ["doctor", "--strict"])
            assert res_strict.exit_code == 0, res_strict.output
            assert "strict: only executable runtime agents enabled" in res_strict.output
            assert "strict: clean main worktree" in res_strict.output

            # 1. Test dirty worktree failure under strict mode
            test_file.write_text("modified dirty\n", encoding="utf-8")
            res_dirty = runner.invoke(app, ["doctor", "--strict"])
            assert res_dirty.exit_code == 1, res_dirty.output
            assert "uncommitted changes present" in res_dirty.output

            # Clean up dirty change
            subprocess.run(["git", "checkout", "--", "hello.txt"], cwd=tmp_path, capture_output=True)

            # 2. Test unstable enabled agent failure under strict mode
            # Let's write an agent registry that enables an unstable provider worker
            registry_path = tmp_path / ".devflow" / "agents" / "registry.yaml"
            registry_path.parent.mkdir(parents=True, exist_ok=True)
            registry_path.write_text("""version: 1
agents:
  unstable-agent:
    provider: openai
    model: gpt-4o
    adapter: openai_chat
    adapter_maturity: experimental_readonly
    role: implementation_worker
    tier: strong_local
    default_mode: workspace_write
    workspace: isolated_task_workspace
    can_see:
      - task_packet
    can_touch:
      - "<workspace>/**"
    cannot_touch:
      - "<main_checkout>/**"
      - ".git/**"
    can_run_shell: false
    can_use_network: true
    can_promote: false
    enabled: true
""", encoding="utf-8")

            res_unstable = runner.invoke(app, ["doctor", "--strict"])
            assert res_unstable.exit_code == 1, res_unstable.output
            assert "unstable: unstable-agent (openai_chat)" in res_unstable.output

        finally:
            os.chdir(old_cwd)


def test_doctor_strict_reports_task_artifact_gaps(tmp_path: Path) -> None:
    task = create_task(tmp_path, "strict artifact gaps")
    task_path = tmp_path / ".devflow" / "tasks" / task.id

    # Tampered workspace path that still points at an existing directory should fail strict mode.
    task_yaml = task_path / "task.yaml"
    task_yaml.write_text(
        task_yaml.read_text(encoding="utf-8").replace(
            f'workspace: ".devflow/workspaces/{task.id}"',
            f'workspace: "{tmp_path.as_posix()}"',
        ),
        encoding="utf-8",
    )

    # Present-but-invalid derived state should be reported; canonical task.yaml still wins.
    (task_path / "summary.json").write_text('{"task_id":"wrong-task","status":"created"}\n', encoding="utf-8")
    (task_path / "merge-readiness.json").write_text("not json\n", encoding="utf-8")

    # Missing logs and stale locks should be visible in strict mode.
    (task_path / "logs" / "verify.log").unlink()
    lock_dir = task_path / ".lock"
    lock_dir.mkdir()
    old_time = datetime.now(timezone.utc) - timedelta(hours=2)
    (lock_dir / "owner.json").write_text(
        json.dumps(
            {
                "task_id": task.id,
                "operation": "verify",
                "pid": 1,
                "host": "old-host",
                "acquired_at": old_time.isoformat(),
            }
        )
        + "\n",
        encoding="utf-8",
    )

    checks = doctor(tmp_path, strict=True)
    failed = {name: detail for name, ok, detail in checks if not ok}

    assert failed[f"strict: {task.id} workspace path"] == f"expected .devflow/workspaces/{task.id}"
    assert "task_id does not match" in failed[f"strict: {task.id} summary.json"]
    assert "invalid JSON" in failed[f"strict: {task.id} merge-readiness.json"]
    assert failed[f"strict: {task.id} verify.log"] == str(task_path / "logs" / "verify.log")
    assert "stale lock" in failed[f"strict: {task.id} task lock"]


def test_doctor_strict_reports_malformed_manual_agent_evidence(tmp_path: Path) -> None:
    task = create_task(tmp_path, "manual evidence gaps")
    task_path = tmp_path / ".devflow" / "tasks" / task.id
    task_yaml = task_path / "task.yaml"
    task_yaml.write_text(
        task_yaml.read_text(encoding="utf-8").replace(
            "worker: shell",
            "worker: devflow-manual-codex-worker",
        ),
        encoding="utf-8",
    )
    agent_dir = task_path / "agents" / "devflow-manual-codex-worker"
    agent_dir.mkdir(parents=True)
    (agent_dir / "worker_failed.json").write_text("not json\n", encoding="utf-8")
    (agent_dir / "questions.jsonl").write_text("{bad json}\n", encoding="utf-8")

    checks = doctor(tmp_path, strict=True)
    failed = {name: detail for name, ok, detail in checks if not ok}

    assert "invalid JSON" in failed[f"strict: {task.id} devflow-manual-codex-worker worker_failed.json"]
    assert "line 1: invalid JSON" in failed[f"strict: {task.id} devflow-manual-codex-worker questions.jsonl"]


def test_doctor_strict_reports_promoted_task_without_promotion_event(tmp_path: Path) -> None:
    task = create_task(tmp_path, "promoted consistency")
    task_path = tmp_path / ".devflow" / "tasks" / task.id
    task_yaml = task_path / "task.yaml"
    task_yaml.write_text(
        task_yaml.read_text(encoding="utf-8").replace('status: "created"', 'status: "promoted"'),
        encoding="utf-8",
    )

    checks = doctor(tmp_path, strict=True)
    failed = {name: detail for name, ok, detail in checks if not ok}

    assert failed[f"strict: {task.id} promoted consistency"] == "missing task_promoted event"


def test_init_and_strict_doctor_print_trusted_local_warning(tmp_path: Path) -> None:
    old_cwd = Path.cwd()
    try:
        os.chdir(tmp_path)
        init_result = runner.invoke(app, ["init"])
        assert init_result.exit_code == 0
        assert "shell execution is path-isolated, not sandboxed" in init_result.output

        doctor_result = runner.invoke(app, ["doctor", "--strict"])
        assert "shell execution is path-isolated, not sandboxed" in doctor_result.output
    finally:
        os.chdir(old_cwd)


def test_doctor_macos_hidden_flag(tmp_path: Path) -> None:
    import sys
    if sys.platform != "darwin":
        return

    init_control_room(tmp_path)

    # Make a dummy site packages dir inside tmp_path
    site_packages = tmp_path / "venv" / "lib" / "site-packages"
    site_packages.mkdir(parents=True, exist_ok=True)

    sys.path.append(str(site_packages))
    try:
        checks = doctor(tmp_path)
        assert not any(name.startswith("python path hygiene") for name, ok, detail in checks)

        # Now set hidden flag on the venv dir
        venv_dir = tmp_path / "venv"
        subprocess.run(["chflags", "hidden", str(venv_dir)], check=True)
        try:
            checks_hidden = doctor(tmp_path)
            hidden_checks = [c for c in checks_hidden if c[0].startswith("python path hygiene")]
            assert len(hidden_checks) == 1
            # The hidden flag breaks `import devflow`, so the doctor must report
            # it as a real failure (ok=False), not a benign "ok".
            assert hidden_checks[0][1] is False
            assert "macOS hidden flag set on" in hidden_checks[0][2]
            assert "devflow doctor --repair" in hidden_checks[0][2]
        finally:
            subprocess.run(["chflags", "nohidden", str(venv_dir)], check=True)
    finally:
        sys.path.remove(str(site_packages))
