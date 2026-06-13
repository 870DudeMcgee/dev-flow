from __future__ import annotations

from pathlib import Path

from devflow.control_room.agent_runtime import resolve_agent_runtime


def test_resolve_builtin_manual_agent_is_task_run_runtime(tmp_path: Path) -> None:
    runtime = resolve_agent_runtime(tmp_path, "devflow-manual-codex-worker")

    assert runtime.agent_id == "devflow-manual-codex-worker"
    assert runtime.adapter == "manual"
    assert runtime.adapter_maturity == "stable_runtime"
    assert runtime.execution_surface == "task_run"
    assert runtime.task_run_allowed is True
    assert runtime.agent_run_allowed is False
    assert runtime.packet_allowed is True
    assert runtime.remote_provider is False
    assert runtime.refusal_reason is None
    assert runtime.next_command == "devflow task run <task-id> --worker devflow-manual-codex-worker"


def test_resolve_qwopus_implementer_is_local_patch_runtime(tmp_path: Path) -> None:
    runtime = resolve_agent_runtime(tmp_path, "qwopus-implementer")

    assert runtime.adapter == "ollama_chat"
    assert runtime.adapter_maturity == "local_patch_runtime"
    assert runtime.execution_surface == "task_run"
    assert runtime.task_run_allowed is True
    assert runtime.agent_run_allowed is False
    assert runtime.remote_provider is False
    assert runtime.next_command == "devflow task run <task-id> --worker qwopus-implementer"
    assert "<task>/agents/qwopus-implementer/proposal.patch" in runtime.evidence_contract.required_outputs


def test_resolve_read_only_local_profile_uses_agent_run(tmp_path: Path) -> None:
    runtime = resolve_agent_runtime(tmp_path, "local-qwopus-inspector")

    assert runtime.execution_surface == "agent_run"
    assert runtime.task_run_allowed is False
    assert runtime.agent_run_allowed is True
    assert runtime.packet_allowed is True
    assert runtime.next_command == "devflow agent run --task <task-id> --profile local-qwopus-inspector --json"
    assert "read-only local model worker-pool profile" in runtime.refusal_reason


def test_resolve_remote_profile_is_blocked(tmp_path: Path) -> None:
    agents_dir = tmp_path / ".devflow" / "agents"
    agents_dir.mkdir(parents=True)
    (agents_dir / "registry.yaml").write_text(
        "version: 1\n"
        "agents:\n"
        "  remote-worker:\n"
        "    provider: openai\n"
        "    model: gpt-5\n"
        "    adapter: openai_chat\n"
        "    role: frontier_planner_architect_reviewer\n"
        "    tier: frontier\n"
        "    default_mode: frontier_read_only\n"
        "    execution_mode: automated\n"
        "    workspace: isolated_task_workspace\n"
        "    can_use_network: true\n"
        "    can_promote: false\n"
        "    enabled: true\n",
        encoding="utf-8",
    )

    runtime = resolve_agent_runtime(tmp_path, "remote-worker")

    assert runtime.execution_surface == "blocked"
    assert runtime.task_run_allowed is False
    assert runtime.agent_run_allowed is False
    assert runtime.remote_provider is True
    assert "experimental_readonly" in runtime.refusal_reason
