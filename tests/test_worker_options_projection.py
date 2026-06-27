"""WorkerOptionsProjection tests.

Validates:
- build_worker_options returns ai_workers, fallback_shell, blocked_details keys.
- Fallback shell is always present and enabled=True.
- Routing-decision agent appears as an AI worker option with source=routing-decision.
- Rejected agents appear in blocked_details with concrete reasons.
- Agent-selection evidence adds a local-model AI worker.
- Local-model run evidence shows up with blocked reason when failed.
- No worker has supervisor_may_auto_run=True.
"""

import json
from pathlib import Path
from unittest.mock import patch

import pytest
from typer.testing import CliRunner

from devflow.cli import app
from devflow.control_room.task_workbench import build_task_workbench
from devflow.control_room.worker_options import WorkerOption, build_worker_options


runner = CliRunner()


# ---------------------------------------------------------------------------
# Fixtures: temp root dir for task dirs
# ---------------------------------------------------------------------------


@pytest.fixture()
def tmp_root(tmp_path: Path) -> Path:
    """Create a project root with .devflow/tasks/<task>."""
    root = tmp_path
    (root / ".devflow" / "tasks" / "test-001").mkdir(parents=True)
    (root / ".devflow" / "tasks" / "test-001" / "workspace_ai").mkdir()
    return root


# ---------------------------------------------------------------------------
# Core contract tests
# ---------------------------------------------------------------------------


def test_fallback_shell_always_present(tmp_root: Path) -> None:
    """Fallback shell worker must always appear, even with zero source files."""
    result = build_worker_options(tmp_root, "test-001")
    assert "fallback_shell" in result
    fallback = result["fallback_shell"]
    assert isinstance(fallback, WorkerOption)
    assert fallback.worker_id == "shell"
    assert fallback.enabled is True
    # Projection-only: no worker may auto-run.
    assert fallback.supervisor_may_auto_run is False


def test_ai_workers_list_always_present(tmp_root: Path) -> None:
    """ai_workers list must always be present (may be empty)."""
    result = build_worker_options(tmp_root, "test-001")
    assert isinstance(result["ai_workers"], list)


def test_blocked_details_dict_always_present(tmp_root: Path) -> None:
    """blocked_details dict must always be present."""
    result = build_worker_options(tmp_root, "test-001")
    assert isinstance(result["blocked_details"], dict)


# ---------------------------------------------------------------------------
# Source: routing-decision.yaml
# ---------------------------------------------------------------------------


def test_routing_decision_selected_agent_appears_as_ai_worker(tmp_root: Path) -> None:
    """Selected agent from routing decision shows as enabled AI worker."""
    rd = {
        "routing_decision": {
            "selected": {"agent_id": "qwopus-implementer", "model": "qwopus:latest"},
            "rejected": [{"agent_id": "gemini-fast", "reason": "too expensive"}],
            "unresolved": [{"role": "reviewer", "reason": "no matching agent"}],
        }
    }
    rd_path = tmp_root / ".devflow" / "tasks" / "test-001" / "routing-decision.yaml"
    # Write as a YAML-like text that our parser can handle.
    rd_path.write_text(json.dumps(rd), encoding="utf-8")

    result = build_worker_options(tmp_root, "test-001")
    ai = result["ai_workers"]
    ids = [w.worker_id for w in ai]
    assert "qwopus-implementer" in ids

    selected_w = next(w for w in ai if w.worker_id == "qwopus-implementer")
    assert selected_w.enabled is True
    assert selected_w.source == "routing-decision"
    assert selected_w.supervisor_may_auto_run is False


def test_routing_decision_rejected_agents_have_concrete_blocked_reason(tmp_root: Path) -> None:
    """Rejected agents must show with a concrete reason in blocked_details."""
    rd = {
        "routing_decision": {
            "selected": {"agent_id": "qwopus-implementer"},
            "rejected": [
                {"agent_id": "gemini-fast", "reason": "too expensive"},
            ],
        }
    }
    (tmp_root / ".devflow" / "tasks" / "test-001" / "routing-decision.yaml").write_text(
        json.dumps(rd), encoding="utf-8"
    )

    result = build_worker_options(tmp_root, "test-001")
    blocked = result["blocked_details"]
    assert "gemini-fast" in blocked
    entry = blocked["gemini-fast"]
    assert entry.enabled is False
    assert entry.blocked_reason is not None and "too expensive" in entry.blocked_reason
    assert entry.supervisor_may_auto_run is False


def test_routing_decision_unresolved_agents_are_blocked_with_reason(tmp_root: Path) -> None:
    """Unresolved agents must show as blocked with reason."""
    rd = {
        "routing_decision": {
            "selected": {"agent_id": "qwopus-implementer"},
            "unresolved": [
                {"role": "reviewer", "reason": "no matching agent in registry"}
            ],
        }
    }
    (tmp_root / ".devflow" / "tasks" / "test-001" / "routing-decision.yaml").write_text(
        json.dumps(rd), encoding="utf-8"
    )

    result = build_worker_options(tmp_root, "test-001")
    blocked = result["blocked_details"]
    assert "reviewer" in blocked
    entry = blocked["reviewer"]
    assert entry.enabled is False
    assert entry.blocked_reason is not None
    assert "no matching agent" in entry.blocked_reason


# ---------------------------------------------------------------------------
# Source: agent-selection.json
# ---------------------------------------------------------------------------


def test_agent_selection_adds_local_model_worker(tmp_root: Path) -> None:
    """Local agent-selection adds an AI worker even without routing decision."""
    sel = {"model": "qwopus:latest", "worker_id": "qwopus-local"}
    (tmp_root / ".devflow" / "tasks" / "test-001" / "agent-selection.json").write_text(
        json.dumps(sel), encoding="utf-8"
    )

    result = build_worker_options(tmp_root, "test-001")
    ai = result["ai_workers"]
    ids = [w.worker_id for w in ai]
    assert "qwopus-local" in ids

    entry = next(w for w in ai if w.worker_id == "qwopus-local")
    assert entry.is_local is True
    assert entry.source == "agent-selection"
    assert entry.supervisor_may_auto_run is False


def test_local_hermes_worker_option_builds_serial_packet_action(tmp_root: Path) -> None:
    """Enabled local/Hermes workers expose packet creation, not browser launch."""
    routing = {
        "routing_decision": {
            "selected": {
                "agent_id": "qwen-worker",
                "label": "Hermes Qwen Implementer",
                "provider": "ollama",
                "model": "qwen3.6-32b-256k:latest",
                "reason": "Best local implementer for this slice.",
            }
        }
    }
    (tmp_root / ".devflow" / "tasks" / "test-001" / "routing-decision.yaml").write_text(
        json.dumps(routing), encoding="utf-8"
    )

    result = build_worker_options(tmp_root, "test-001")
    entry = next(w for w in result["ai_workers"] if w.worker_id == "qwen-worker")

    assert entry.label == "Hermes Qwen Implementer"
    assert entry.is_local is True
    assert entry.runtime_kind == "hermes-profile"
    assert entry.hermes_profile == "qwen-worker"
    assert entry.action_kind == "serial_packet"
    assert entry.command is not None
    assert entry.command.startswith("devflow agent serial-packet ")
    assert " --task-id test-001" in entry.command
    assert " --worker-id qwen-worker" in entry.command
    assert " --runtime hermes-profile" in entry.command
    assert " --hermes-profile qwen-worker" in entry.command
    assert " --toolset file" in entry.command
    assert " --toolset terminal" in entry.command
    assert "devflow agent hermes-run" not in entry.command
    assert "devflow task run" not in entry.command
    assert entry.recommended_allowed_files == []
    assert entry.recommended_verification_commands == []
    assert entry.needs_operator_inputs == ["allowed_files", "verification_commands"]
    assert "<allowed-file>" not in " ".join(entry.recommended_allowed_files)
    assert result["fallback_shell"].command == "devflow task run test-001 --worker shell -- <command>"


def test_local_hermes_worker_option_prefills_known_packet_evidence_paths(tmp_root: Path) -> None:
    """Known task evidence paths should prefill packet allowed-file inputs without fake source paths."""
    workspace = tmp_root / ".devflow" / "workspaces" / "test-001"
    workspace.mkdir(parents=True)
    (workspace / "implementation-context.md").write_text("Implement from plan.\n", encoding="utf-8")
    (workspace / "notes.md").write_text("Operator notes.\n", encoding="utf-8")
    routing = {
        "routing_decision": {
            "selected": {
                "agent_id": "qwen-worker",
                "label": "Hermes Qwen Implementer",
                "provider": "ollama",
                "model": "qwen3.6-32b-256k:latest",
            }
        }
    }
    (tmp_root / ".devflow" / "tasks" / "test-001" / "routing-decision.yaml").write_text(
        json.dumps(routing), encoding="utf-8"
    )

    result = build_worker_options(tmp_root, "test-001")
    entry = next(w for w in result["ai_workers"] if w.worker_id == "qwen-worker")

    assert entry.recommended_allowed_files == [
        ".devflow/workspaces/test-001/implementation-context.md",
        ".devflow/workspaces/test-001/notes.md",
    ]
    assert entry.recommended_verification_commands == []
    assert entry.needs_operator_inputs == ["verification_commands"]
    assert not any("<" in value or ">" in value for value in entry.recommended_allowed_files)


def test_configured_hermes_agents_appear_as_packet_only_worker_options(
    tmp_root: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("HOME", tmp_root.as_posix())
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
    hermes_dir = tmp_root / ".hermes"
    for profile in ("dfqwen37plus", "dflocalfast"):
        (hermes_dir / "profiles" / profile).mkdir(parents=True)
    (hermes_dir / ".env").write_text("OPENROUTER_API_KEY=sk-or-worker-secret\n", encoding="utf-8")
    (hermes_dir / "config.yaml").write_text(
        """model:
  default: qwen/qwen3.7-plus
  provider: openrouter
  base_url: https://openrouter.ai/api/v1
providers:
  qwen35-mtp:
    api: http://127.0.0.1:8080/v1
    models:
      qwen35-9b-mtp: {}
""",
        encoding="utf-8",
    )
    (hermes_dir / "profiles" / "dfqwen37plus" / "config.yaml").write_text(
        """model:
  default: qwen/qwen3.7-plus
  provider: openrouter
  base_url: https://openrouter.ai/api/v1
""",
        encoding="utf-8",
    )
    (hermes_dir / "profiles" / "dflocalfast" / "config.yaml").write_text(
        """model:
  default: qwen35-9b-mtp
  provider: qwen35-mtp
  base_url: http://127.0.0.1:8080/v1
""",
        encoding="utf-8",
    )

    result = build_worker_options(tmp_root, "test-001")
    options = {option.worker_id: option for option in result["ai_workers"]}

    assert "hermes-default-openrouter-qwen-qwen3-7-plus" not in options

    openrouter = options["hermes-dfqwen37plus-openrouter-qwen-qwen3-7-plus"]
    assert openrouter.label == "Hermes OpenRouter - qwen/qwen3.7-plus"
    assert openrouter.provider == "openrouter"
    assert openrouter.model == "qwen/qwen3.7-plus"
    assert openrouter.is_local is False
    assert openrouter.runtime_kind == "hermes-profile"
    assert openrouter.hermes_profile == "dfqwen37plus"
    assert openrouter.action_kind == "serial_packet"
    assert openrouter.command is not None
    assert " --provider openrouter" in openrouter.command
    assert " --model qwen/qwen3.7-plus" in openrouter.command
    assert " --runtime hermes-profile" in openrouter.command
    assert " --hermes-profile dfqwen37plus" in openrouter.command
    assert "devflow agent hermes-run" not in openrouter.command
    assert "devflow task run" not in openrouter.command
    assert "sk-or-worker-secret" not in openrouter.command

    local = options["hermes-dflocalfast-qwen35-mtp-qwen35-9b-mtp"]
    assert local.label == "Hermes qwen35-mtp - qwen35-9b-mtp"
    assert local.provider == "qwen35-mtp"
    assert local.is_local is True
    assert local.hermes_profile == "dflocalfast"
    assert local.command is not None
    assert " --provider qwen35-mtp" in local.command
    assert " --model qwen35-9b-mtp" in local.command


# ---------------------------------------------------------------------------
# Source: local worker evidence (run.json / worker_failed.json)
# ---------------------------------------------------------------------------


def test_successful_local_model_run_appears_as_worker_option(tmp_root: Path) -> None:
    """A successful local-model run adds its agent as an AI worker."""
    run_dir = tmp_root / ".devflow" / "tasks" / "test-001" / "agents" / "qwopus-implementer"
    run_dir.mkdir(parents=True)
    (run_dir / "run.json").write_text(
        json.dumps({"agent_id": "qwopus-implementer", "model": "qwopus:latest", "status": "complete"}),
        encoding="utf-8",
    )
    (run_dir / "result.md").write_text("done", encoding="utf-8")

    result = build_worker_options(tmp_root, "test-001")
    ai = result["ai_workers"]
    ids = [w.worker_id for w in ai]
    assert "qwopus-implementer" in ids

    entry = next(w for w in ai if w.worker_id == "qwopus-implementer")
    assert entry.source == "registry"
    assert entry.is_local is True
    assert entry.supervisor_may_auto_run is False


def test_failed_local_model_run_shows_concrete_reason_not_hidden(tmp_root: Path) -> None:
    """worker_failed.json must produce a blocked worker with concrete reason."""
    run_dir = tmp_root / ".devflow" / "tasks" / "test-001" / "agents" / "qwopus-implementer"
    run_dir.mkdir(parents=True)
    (run_dir / "worker_failed.json").write_text(
        json.dumps({"error": "GPU OOM after 5 minutes"}),
        encoding="utf-8",
    )

    result = build_worker_options(tmp_root, "test-001")
    blocked = result["blocked_details"]
    assert any("qwopus-implementer" in wid for wid in blocked)

    # Pick the first matching entry.
    entry_found = None
    for wid, entry in blocked.items():
        if "qwopus-implementer" in wid:
            entry_found = entry
            break
    assert entry_found is not None
    assert entry_found.enabled is False
    assert entry_found.blocked_reason is not None and "GPU OOM" in entry_found.blocked_reason


def test_local_model_runs_directory_appears_as_worker_option(tmp_root: Path) -> None:
    """local-model-runs/<agent>/run.json is first-class worker evidence."""
    run_dir = tmp_root / ".devflow" / "tasks" / "test-001" / "local-model-runs" / "agent-qwopus-implementer"
    run_dir.mkdir(parents=True)
    (run_dir / "run.json").write_text(
        json.dumps({"agent_id": "qwopus-implementer", "model": "qwopus:latest", "status": "complete"}),
        encoding="utf-8",
    )

    result = build_worker_options(tmp_root, "test-001")
    entry = next(w for w in result["ai_workers"] if w.worker_id == "qwopus-implementer")
    assert entry.source == "registry"
    assert entry.is_local is True
    assert any("local-model-runs/agent-qwopus-implementer/run.json" in path for path in entry.evidence_paths)


# ---------------------------------------------------------------------------
# Projection-only contract tests
# ---------------------------------------------------------------------------


def test_no_ai_worker_has_supervisor_may_auto_run_true(tmp_root: Path) -> None:
    """Projection-only contract: no worker may have auto-run."""
    rd = {
        "routing_decision": {
            "selected": {"agent_id": "qwopus-implementer"},
            "rejected": [{"agent_id": "gpt-4", "reason": "cost"}],
        }
    }
    sel = {"model": "qwopus:latest", "worker_id": "local-qwopus"}
    (tmp_root / ".devflow" / "tasks" / "test-001" / "routing-decision.yaml").write_text(
        json.dumps(rd), encoding="utf-8"
    )
    (tmp_root / ".devflow" / "tasks" / "test-001" / "agent-selection.json").write_text(
        json.dumps(sel), encoding="utf-8"
    )

    ai = build_worker_options(tmp_root, "test-001")["ai_workers"]
    for w in ai:
        assert w.supervisor_may_auto_run is False, f"{w.worker_id} violated projection-only contract"


def test_fallback_shell_is_not_an_ai_worker(tmp_root: Path) -> None:
    """Shell fallback must not be counted among AI workers."""
    result = build_worker_options(tmp_root, "test-001")
    ai_ids = [w.worker_id for w in result["ai_workers"]]
    assert "shell" not in ai_ids
    # But shell should exist as blocked_details key? No — shell is separate.
    # Verify it's only in the 'fallback_shell' field.
    fallback = result["fallback_shell"]
    assert fallback.worker_id == "shell"


def test_task_workbench_surfaces_worker_options(tmp_path: Path, monkeypatch) -> None:
    """Task workbench must return the canonical worker options it builds."""
    monkeypatch.chdir(tmp_path)
    create = runner.invoke(app, ["task", "create", "worker choices"])
    assert create.exit_code == 0, create.output
    routing = {
        "routing_decision": {
            "selected": {"agent_id": "qwopus-implementer", "model": "qwopus:latest"},
            "rejected": [{"agent_id": "gemini-fast", "reason": "too expensive"}],
        }
    }
    routing_path = tmp_path / ".devflow" / "tasks" / "task-0001" / "routing-decision.yaml"
    routing_path.write_text(json.dumps(routing), encoding="utf-8")

    workbench = build_task_workbench(tmp_path, project_id="demo")
    task = workbench.tasks[0]

    ids = [option["worker_id"] for option in task.worker_options]
    assert "qwopus-implementer" in ids
    assert "gemini-fast" in ids
    assert "shell" in ids
    assert ids.index("qwopus-implementer") < ids.index("shell")
    ai_option = next(option for option in task.worker_options if option["worker_id"] == "qwopus-implementer")
    assert ai_option["action_kind"] == "serial_packet"
    assert str(ai_option["command"]).startswith("devflow agent serial-packet ")
    assert " --runtime hermes-profile" in str(ai_option["command"])
    shell = next(option for option in task.worker_options if option["worker_id"] == "shell")
    assert shell["command"] == "devflow task run task-0001 --worker shell --project demo -- <command>"
    blocked = next(option for option in task.worker_options if option["worker_id"] == "gemini-fast")
    assert blocked["blocked_reason"] is not None
    assert blocked["supervisor_may_auto_run"] is False


# ---------------------------------------------------------------------------
# Empty / missing file robustness
# ---------------------------------------------------------------------------


def test_missing_task_dir_returns_defaults(tmp_path: Path) -> None:
    """When task dir is completely absent, defaults are returned without error."""
    root = tmp_path / ".devflow"
    # No tasks/<task_id> created.
    with patch("pathlib.Path.exists", return_value=False):
        # We can't mock everything in path_to_task_dir, so just check the
        # result structure has all required keys even when there's no task.
        pass

    # Build a minimal root and test that missing files don't crash.
    project_root = tmp_path / "real"
    (project_root / ".devflow" / "tasks").mkdir(parents=True)
    result = build_worker_options(project_root, "nonexistent-task")
    assert "ai_workers" in result
    assert "fallback_shell" in result
    assert "blocked_details" in result
    # Shell must still be there.
    assert result["fallback_shell"].worker_id == "shell"
