from __future__ import annotations

import tempfile
import os
import subprocess
from pathlib import Path
from typer.testing import CliRunner

from devflow.cli import app
from devflow.control_room.service import init_control_room, doctor

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

            # Strict doctor should pass since worktree is clean and only stable agents (manual-codex-worker) are enabled
            res_strict = runner.invoke(app, ["doctor", "--strict"])
            assert res_strict.exit_code == 0, res_strict.output
            assert "strict: only stable runtime agents enabled" in res_strict.output
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
