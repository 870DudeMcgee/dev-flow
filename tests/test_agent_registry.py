from __future__ import annotations

from pathlib import Path

import pytest

import json
from devflow.control_room.agent_registry import (
    AgentRegistryError,
    load_agent_registry,
    load_provider_registry,
    load_role_registry,
    AgentDefinition,
)
from devflow.control_room.seed import initialize_seed
from devflow.control_room.service import create_task
from devflow.control_room.task_packet import build_agent_packet


STARTER_LOCAL_PROFILES = [
    "local-qwopus-inspector",
    "local-qwen36-inspector",
    "local-qwen25-coder-32b-code-reviewer",
    "local-qwen25-coder-32b-patch-proposer",
    "local-qwen25-coder-14b-test-planner",
    "local-qwen25-coder-7b-code-reviewer",
    "local-qwen25-coder-15b-classifier",
    "local-gemma4-summarizer",
    "local-gemma4-doc-reviewer",
    "local-gemma4-31b-dense-judge",
]


def test_valid_agent_registry_loads_enabled_default_agent(tmp_path: Path) -> None:
    registry_path = tmp_path / ".devflow/agents/registry.yaml"
    registry_path.parent.mkdir(parents=True)
    registry_path.write_text(
        """version: 1
default_agent: local-shell
agents:
  local-shell:
    provider: shell
    model: local-shell
    adapter: shell
    role: test_runner
    tier: local
    default_mode: verify_only
    workspace: isolated_task_workspace
    can_see:
      - task_packet
      - assigned_workspace
    can_touch:
      - "<workspace>/**"
    cannot_touch:
      - "<main_checkout>/**"
      - ".git/**"
    can_run_shell: true
    can_use_network: false
    can_promote: false
    enabled: true
""",
        encoding="utf-8",
    )

    registry = load_agent_registry(tmp_path)

    assert registry.version == 1
    assert registry.default_agent_id == "local-shell"
    assert registry.default_agent().id == "local-shell"
    assert sorted(registry.enabled_agent_ids()) == sorted([
        "local-shell",
        "qwopus-implementer",
        "devflow-manual-codex-worker",
        *STARTER_LOCAL_PROFILES,
    ])
    agent = registry.require_agent("local-shell")
    assert agent.adapter == "shell"
    assert agent.default_mode == "verify_only"
    assert agent.can_touch == ["<workspace>/**"]
    assert agent.adapter_maturity == "stable_runtime"


def test_agent_registry_uses_real_yaml_parser_for_inline_collections(tmp_path: Path) -> None:
    registry_path = tmp_path / ".devflow/agents/registry.yaml"
    registry_path.parent.mkdir(parents=True)
    registry_path.write_text(
        """version: 1
default_agent: local-shell
agents:
  local-shell:
    provider: shell
    model: local-shell
    adapter: shell
    adapter_maturity: stable_runtime
    role: test_runner
    tier: local
    default_mode: verify_only
    workspace: isolated_task_workspace
    can_see: ["task_packet", "assigned_workspace"]
    can_touch: ["<workspace>/**"]
    cannot_touch: ["<main_checkout>/**", ".git/**"]
    can_run_shell: true
    can_use_network: false
    can_promote: false
    enabled: true
""",
        encoding="utf-8",
    )

    registry = load_agent_registry(tmp_path)

    agent = registry.require_agent("local-shell")
    assert agent.can_see == ["task_packet", "assigned_workspace"]
    assert agent.can_touch == ["<workspace>/**"]
    assert agent.cannot_touch == ["<main_checkout>/**", ".git/**"]


def test_disabled_agents_are_loaded_but_not_available_and_seed_is_empty(tmp_path: Path) -> None:
    initialize_seed(tmp_path)
    seeded_registry = load_agent_registry(tmp_path)
    assert seeded_registry.default_agent().id == "devflow-manual-codex-worker"
    assert sorted(seeded_registry.enabled_agent_ids()) == sorted([
        "qwopus-implementer",
        "devflow-manual-codex-worker",
        *STARTER_LOCAL_PROFILES,
    ])

    registry_path = tmp_path / ".devflow/agents/registry.yaml"
    registry_path.parent.mkdir(parents=True, exist_ok=True)
    registry_path.write_text(
        """version: 1
default_agent: local-shell
agents:
  disabled-local:
    provider: ollama
    model: qwen3:36b
    adapter: ollama_chat
    role: local_senior_worker
    tier: local
    default_mode: workspace_write
    workspace: isolated_task_workspace
    can_see:
      - task_packet
    can_touch:
      - "<workspace>/**"
    cannot_touch:
      - "<main_checkout>/**"
    can_run_shell: false
    can_use_network: false
    can_promote: false
    enabled: false
  local-shell:
    provider: shell
    model: local-shell
    adapter: shell
    role: test_runner
    tier: local
    default_mode: verify_only
    workspace: isolated_task_workspace
    can_see:
      - task_packet
    can_touch:
      - "<workspace>/**"
    cannot_touch:
      - "<main_checkout>/**"
    can_run_shell: true
    can_use_network: false
    can_promote: false
    enabled: true
""",
        encoding="utf-8",
    )

    registry = load_agent_registry(tmp_path)

    expected_agents = [
        "devflow-manual-codex-worker",
        "qwopus-implementer",
        "devflow-ollama-worker",
        "devflow-openai-worker",
        "devflow-anthropic-worker",
        "devflow-gemini-worker",
        "devflow-openai-compatible-worker",
        "devflow-openai-planner",
        "devflow-openai-reviewer",
        "disabled-local",
        "local-shell",
        *STARTER_LOCAL_PROFILES,
    ]
    assert sorted(registry.agents) == sorted(expected_agents)
    assert sorted(registry.enabled_agent_ids()) == sorted([
        "qwopus-implementer",
        "local-shell",
        "devflow-manual-codex-worker",
        *STARTER_LOCAL_PROFILES,
    ])
    assert registry.default_agent().id == "local-shell"
    assert registry.require_agent("disabled-local").enabled is False


def test_agent_registry_validation_errors_report_bad_policy(tmp_path: Path) -> None:
    registry_path = tmp_path / ".devflow/agents/registry.yaml"
    registry_path.parent.mkdir(parents=True)
    registry_path.write_text(
        """version: 1
default_agent: missing-agent
agents:
  bad:
    provider: openai
    model: gpt-5
    adapter: openai_responses
    role: frontier_code_reviewer
    tier: frontier
    default_mode: workspace_write
    workspace: isolated_task_workspace
    can_see:
      - task_packet
    can_touch:
      - "<workspace>/**"
    cannot_touch:
      - "<main_checkout>/**"
    can_run_shell: true
    can_use_network: true
    can_promote: true
    enabled: true
""",
        encoding="utf-8",
    )

    with pytest.raises(AgentRegistryError) as exc_info:
        load_agent_registry(tmp_path)

    message = str(exc_info.value)
    assert ".devflow/agents/registry.yaml" in message
    assert "default_agent 'missing-agent' is not defined" in message
    assert "agents.bad.can_promote must be false" in message
    assert "agents.bad.frontier agents cannot use workspace_write" in message
    assert "agents.bad.frontier agents cannot run shell commands" in message


def test_valid_provider_registry_loads_and_enabled_providers(tmp_path: Path) -> None:
    providers_dir = tmp_path / ".devflow/providers"
    providers_dir.mkdir(parents=True)
    
    (providers_dir / "openai.yaml").write_text(
        """provider: openai
adapter: openai_responses
base_url: https://api.openai.com/v1
api_key_env: OPENAI_API_KEY
default_timeout_seconds: 120
enabled: true
""",
        encoding="utf-8",
    )
    (providers_dir / "ollama.yaml").write_text(
        """provider: ollama
adapter: ollama_chat
base_url: http://127.0.0.1:11434
default_timeout_seconds: 300
enabled: false
""",
        encoding="utf-8",
    )

    registry = load_provider_registry(tmp_path)

    assert sorted(registry.providers.keys()) == ["ollama", "openai"]
    assert registry.enabled_provider_ids() == ["openai"]
    assert registry.require_provider("openai").adapter == "openai_responses"
    assert registry.require_provider("openai").base_url == "https://api.openai.com/v1"
    assert registry.require_provider("openai").api_key_env == "OPENAI_API_KEY"
    assert registry.require_provider("openai").default_timeout_seconds == 120
    assert registry.require_provider("ollama").enabled is False


def test_provider_registry_validation_errors(tmp_path: Path) -> None:
    providers_dir = tmp_path / ".devflow/providers"
    providers_dir.mkdir(parents=True)
    
    (providers_dir / "bad-provider.yaml").write_text(
        """provider: 123
adapter: []
default_timeout_seconds: "not-an-int"
""",
        encoding="utf-8",
    )

    with pytest.raises(AgentRegistryError) as exc_info:
        load_provider_registry(tmp_path)

    message = str(exc_info.value)
    assert ".devflow/providers" in message
    assert "providers.bad-provider.provider: Input should be a valid string" in message
    assert "providers.bad-provider.adapter: Input should be a valid string" in message
    assert "providers.bad-provider.default_timeout_seconds: Input should be a valid integer" in message


def test_provider_registry_disabled_default_seed_behavior(tmp_path: Path) -> None:
    initialize_seed(tmp_path)
    seeded_registry = load_provider_registry(tmp_path)
    assert sorted(seeded_registry.enabled_provider_ids()) == sorted([
        "ollama",
        "openai",
        "anthropic",
        "gemini",
        "openai_compatible",
        "xai",
        "grok",
    ])


def test_valid_role_registry_loads_and_enabled_roles(tmp_path: Path) -> None:
    roles_path = tmp_path / ".devflow/agents/roles.yaml"
    roles_path.parent.mkdir(parents=True)
    roles_path.write_text(
        """version: 1
roles:
  local_senior_worker:
    description: "Local senior worker for implementation tasks"
    enabled: true
  disabled_role:
    description: "A role that is disabled"
    enabled: false
""",
        encoding="utf-8",
    )

    registry = load_role_registry(tmp_path)

    assert sorted(registry.roles.keys()) == ["disabled_role", "local_senior_worker"]
    assert registry.enabled_role_ids() == ["local_senior_worker"]
    assert registry.require_role("local_senior_worker").description == "Local senior worker for implementation tasks"
    assert registry.require_role("disabled_role").enabled is False


def test_role_registry_validation_errors(tmp_path: Path) -> None:
    roles_path = tmp_path / ".devflow/agents/roles.yaml"
    roles_path.parent.mkdir(parents=True)
    roles_path.write_text(
        """version: 2
roles:
  bad_role:
    description: []
    enabled: "not-a-bool"
""",
        encoding="utf-8",
    )

    with pytest.raises(AgentRegistryError) as exc_info:
        load_role_registry(tmp_path)

    message = str(exc_info.value)
    assert ".devflow/agents/roles.yaml" in message
    assert "version must be 1" in message
    assert "roles.bad_role.description: Input should be a valid string" in message
    assert "roles.bad_role.enabled: Input should be a valid boolean" in message


def test_role_registry_disabled_default_seed_behavior(tmp_path: Path) -> None:
    initialize_seed(tmp_path)
    seeded_registry = load_role_registry(tmp_path)
    assert sorted(seeded_registry.enabled_role_ids()) == sorted([
        "implementation_worker",
        "local_senior_worker",
        "test_runner",
        "frontier_code_reviewer",
        "tester",
        "senior",
        "frontier_planner_architect_reviewer",
    ])


def test_build_agent_packet_redacts_by_permissions(tmp_path: Path) -> None:
    task = create_task(tmp_path, "Security bounded task")
    task_id = task.id

    agent = AgentDefinition(
        id="limited-agent",
        provider="shell",
        model="limited",
        adapter="shell",
        role="tester",
        tier="local",
        default_mode="verify_only",
        workspace="isolated_task_workspace",
        can_see=["verification_plan"],
        can_touch=[],
        cannot_touch=[],
        enabled=True,
    )

    packet = build_agent_packet(task_id, agent, root=tmp_path)

    assert packet.workspace_path == "[REDACTED]"
    assert packet.task == {}
    assert packet.recent_events == []
    assert packet.verification != {}

    senior_agent = AgentDefinition(
        id="senior-agent",
        provider="ollama",
        model="qwen",
        adapter="ollama_chat",
        role="senior",
        tier="local",
        default_mode="workspace_write",
        workspace="isolated_task_workspace",
        can_see=["task_packet", "assigned_workspace", "recent_events", "verification_summary"],
        can_touch=[],
        cannot_touch=[],
        enabled=True,
    )

    full_packet = build_agent_packet(task_id, senior_agent, root=tmp_path)
    assert full_packet.workspace_path != "[REDACTED]"
    assert full_packet.task != {}
    assert full_packet.recent_events != []


def test_builtin_manual_codex_worker_contract_is_available(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.chdir(tmp_path)
    initialize_seed(tmp_path)

    registry = load_agent_registry(tmp_path)
    agent = registry.require_agent("devflow-manual-codex-worker")

    assert agent.role == "implementation_worker"
    assert agent.adapter == "manual"
    assert agent.execution_mode == "human_launched_agent"
    assert agent.allowed_reads == [
        "<task>/packet.json",
        "<task>/events.jsonl",
        "<task>/questions.jsonl",
        "<task>/agents/devflow-manual-codex-worker/handoff.md",
        "<workspace>/**",
    ]
    assert agent.allowed_writes == [
        "<workspace>/**",
        "<task>/agents/devflow-manual-codex-worker/result.md",
        "<task>/agents/devflow-manual-codex-worker/questions.jsonl",
        "<task>/agents/devflow-manual-codex-worker/worker_failed.json",
    ]
    assert "<main_checkout>/**" in agent.forbidden_writes
    assert "<task>/task.yaml" in agent.forbidden_writes
    assert "result.md" in ", ".join(agent.required_outputs)
    assert "Stop after writing exactly one terminal evidence artifact." in agent.completion_rules

    from devflow.cli import app
    from typer.testing import CliRunner

    runner = CliRunner()
    show_result = runner.invoke(app, ["agent", "show", "devflow-manual-codex-worker"])
    assert show_result.exit_code == 0, show_result.output
    assert "agent: devflow-manual-codex-worker" in show_result.output
    assert "role: implementation_worker" in show_result.output
    assert "adapter: manual" in show_result.output
    assert "execution_mode: human_launched_agent" in show_result.output
    assert "allowed_writes:" in show_result.output
    assert "<workspace>/**" in show_result.output
    assert "forbidden_writes:" in show_result.output
    assert "<main_checkout>/**" in show_result.output


def test_agent_packet_includes_manual_proof_contract_fields(tmp_path: Path) -> None:
    initialize_seed(tmp_path)
    task = create_task(tmp_path, "Manual proof packet task")
    registry = load_agent_registry(tmp_path)
    agent = registry.require_agent("devflow-manual-codex-worker")

    packet = build_agent_packet(task.id, agent, root=tmp_path)

    assert packet.agent_id == "devflow-manual-codex-worker"
    assert packet.role == "implementation_worker"
    assert packet.execution_mode == "human_launched_agent"
    assert packet.allowed_reads == agent.allowed_reads
    assert packet.allowed_writes == agent.allowed_writes
    assert packet.forbidden_writes == agent.forbidden_writes
    assert packet.required_outputs == agent.required_outputs
    assert packet.completion_rules == agent.completion_rules
    assert "You are devflow-manual-codex-worker." in packet.manual_instructions
    assert "Edit only files under <workspace>." in packet.manual_instructions
    assert "Do not edit <task>/task.yaml." in packet.manual_instructions


def test_agent_cli_commands(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.chdir(tmp_path)
    initialize_seed(tmp_path)

    from devflow.cli import app
    from typer.testing import CliRunner
    runner = CliRunner()

    result = runner.invoke(app, ["agent", "list"])
    assert result.exit_code == 0
    assert "devflow-manual-codex-worker" in result.output

    registry_path = tmp_path / ".devflow/agents/registry.yaml"
    registry_path.parent.mkdir(parents=True, exist_ok=True)
    registry_path.write_text(
        """version: 1
default_agent: qwen-agent
agents:
  qwen-agent:
    provider: ollama
    model: qwen3:36b
    adapter: ollama_chat
    role: local_senior_worker
    tier: local
    default_mode: workspace_write
    workspace: isolated_task_workspace
    can_see:
      - task_packet
    can_touch:
      - "<workspace>/**"
    cannot_touch:
      - "<main_checkout>/**"
    can_run_shell: false
    can_use_network: false
    can_promote: false
    enabled: true
""",
        encoding="utf-8",
    )

    list_result = runner.invoke(app, ["agent", "list"])
    assert list_result.exit_code == 0
    assert "qwen-agent" in list_result.output
    assert "ollama" in list_result.output
    assert "local_senior_worker" in list_result.output

    show_result = runner.invoke(app, ["agent", "show", "qwen-agent"])
    assert show_result.exit_code == 0
    assert "agent: qwen-agent" in show_result.output
    assert "provider: ollama" in show_result.output
    assert "model: qwen3:36b" in show_result.output
    assert "role: local_senior_worker" in show_result.output

    task = create_task(tmp_path, "Agent CLI packet task")
    packet_result = runner.invoke(app, ["agent", "packet", task.id, "qwen-agent"])
    assert packet_result.exit_code == 0
    packet_json = json.loads(packet_result.output)
    assert packet_json["task_id"] == task.id
    assert packet_json["task"] != {}
    assert packet_json["workspace_path"] == "[REDACTED]"


def test_shell_alignment_resolves_and_logs_under_agent_dir(tmp_path: Path) -> None:
    initialize_seed(tmp_path)
    task = create_task(tmp_path, "Shell alignment test")

    registry_path = tmp_path / ".devflow/agents/registry.yaml"
    registry_path.parent.mkdir(parents=True, exist_ok=True)
    registry_path.write_text(
        """version: 1
default_agent: qwen-agent
agents:
  qwen-agent:
    provider: shell
    model: qwen-coder
    adapter: shell
    role: local_senior_worker
    tier: local
    default_mode: workspace_write
    workspace: isolated_task_workspace
    can_see:
      - task_packet
      - assigned_workspace
    can_touch:
      - "<workspace>/**"
    cannot_touch:
      - "<main_checkout>/**"
    can_run_shell: true
    can_use_network: false
    can_promote: false
    enabled: true
""",
        encoding="utf-8",
    )

    from devflow.control_room.service import run_shell_task
    task_res = run_shell_task(
        tmp_path,
        task.id,
        ["echo", "aligned"],
        worker_adapter="qwen-agent"
    )

    assert task_res.status == "complete"
    assert task_res.worker == "qwen-agent"

    agent_dir = tmp_path / ".devflow/tasks" / task.id / "agents" / "qwen-agent"
    assert agent_dir.exists()
    assert (agent_dir / "logs" / "worker.log").exists()
    assert (agent_dir / "result.md").exists()
    assert (agent_dir / "packet.json").exists()

    packet_json = json.loads((agent_dir / "packet.json").read_text(encoding="utf-8"))
    assert packet_json["task_id"] == task.id
    assert packet_json["task"] != {}
    assert packet_json["workspace_path"] != "[REDACTED]"


def test_preseeded_agent_presets_load_and_validate(tmp_path: Path) -> None:
    initialize_seed(tmp_path)
    
    # Verify agent registry loads all automated agents plus manual worker
    registry = load_agent_registry(tmp_path)
    assert len(registry.agents) >= 9
    
    expected_agents = [
        "devflow-manual-codex-worker",
        "qwopus-implementer",
        "devflow-ollama-worker",
        "devflow-openai-worker",
        "devflow-anthropic-worker",
        "devflow-gemini-worker",
        "devflow-openai-compatible-worker",
        "devflow-openai-planner",
        "devflow-openai-reviewer",
        *STARTER_LOCAL_PROFILES,
    ]
    
    for agent_id in expected_agents:
        assert agent_id in registry.agents
        agent = registry.require_agent(agent_id)
        assert agent.enabled is (agent_id in {"devflow-manual-codex-worker", "qwopus-implementer", *STARTER_LOCAL_PROFILES})
        assert agent.workspace == "isolated_task_workspace"
        
        # Verify specific fields
        if agent_id == "devflow-manual-codex-worker":
            assert agent.tier == "manual"
            assert agent.can_use_network is False
            assert agent.role == "implementation_worker"
        elif agent_id == "qwopus-implementer":
            assert agent.tier == "strong_local"
            assert agent.execution_mode == "automated"
            assert agent.role == "implementation_worker"
            assert agent.provider == "ollama"
            assert agent.model == "qwopus:latest"
            assert agent.adapter == "ollama_chat"
            assert agent.adapter_maturity == "local_patch_runtime"
            assert agent.can_use_network is False
            assert "<task>/agents/qwopus-implementer/proposal.patch" in agent.allowed_writes
        elif agent_id in STARTER_LOCAL_PROFILES:
            assert agent.provider == "ollama"
            assert agent.adapter == "ollama_chat"
            assert agent.adapter_maturity == "local_patch_runtime"
            assert agent.default_mode == "read_only"
            assert agent.can_use_network is False
            assert agent.can_promote is False
            assert agent.can_run_shell is False
            assert "<task>/local-model-runs/**" in agent.allowed_writes
            assert not any("<workspace>" in path or "proposal.patch" in path for path in agent.allowed_writes)
            assert agent.machine_class in {"mac_mini", "mac_studio", "either"}
            assert agent.weight_class in {"tiny", "small", "medium", "heavy"}
            assert agent.model_role_name
            assert agent.required_verification_command.startswith("ollama show ")
        elif agent_id in ("devflow-openai-planner", "devflow-openai-reviewer"):
            assert agent.tier == "frontier"
            assert agent.execution_mode == "automated"
            assert agent.role == "frontier_planner_architect_reviewer"
            assert agent.can_use_network is True
        else:
            assert agent.tier == "strong_local"
            assert agent.execution_mode == "automated"
            assert agent.role == "implementation_worker"
            if agent_id == "devflow-ollama-worker":
                assert agent.can_use_network is False
            else:
                assert agent.can_use_network is True


def test_preseeded_providers_load_and_validate(tmp_path: Path) -> None:
    initialize_seed(tmp_path)
    
    provider_registry = load_provider_registry(tmp_path)
    expected_providers = ["ollama", "openai", "anthropic", "gemini", "openai_compatible", "xai", "grok"]
    
    for prov_id in expected_providers:
        assert prov_id in provider_registry.providers
        prov = provider_registry.require_provider(prov_id)
        assert prov.enabled is True
        
        if prov_id == "ollama":
            assert prov.adapter == "ollama_chat"
            assert prov.base_url == "http://127.0.0.1:11434"
            assert prov.api_key_env is None
            assert prov.default_timeout_seconds == 600
        elif prov_id == "openai":
            assert prov.adapter == "openai_chat"
            assert prov.base_url == "https://api.openai.com/v1"
            assert prov.default_timeout_seconds == 300
        elif prov_id == "anthropic":
            assert prov.adapter == "anthropic_messages"
            assert prov.base_url == "https://api.anthropic.com/v1"
            assert prov.default_timeout_seconds == 300
        elif prov_id == "gemini":
            assert prov.adapter == "gemini"
            assert prov.base_url == "https://generativelanguage.googleapis.com"
            assert prov.default_timeout_seconds == 300
        elif prov_id == "openai_compatible":
            assert prov.adapter == "openai_compatible"
            assert prov.base_url == "http://127.0.0.1:8000/v1"
            assert prov.default_timeout_seconds == 300
        elif prov_id == "xai":
            assert prov.adapter == "openai_compatible"
            assert prov.base_url == "https://api.x.ai/v1"
            assert prov.api_key_env == "XAI_API_KEY"
            assert prov.default_timeout_seconds == 300
        elif prov_id == "grok":
            assert prov.adapter == "openai_compatible"
            assert prov.base_url == "https://api.x.ai/v1"
            assert prov.api_key_env == "GROK_API_KEY"
            assert prov.default_timeout_seconds == 300


def test_hermes_delegable_defaults_false_and_starter_profiles_opt_in_safely(tmp_path: Path) -> None:
    initialize_seed(tmp_path)

    registry = load_agent_registry(tmp_path)
    manual = registry.require_agent("devflow-manual-codex-worker")
    qwopus_patch_worker = registry.require_agent("qwopus-implementer")
    inspector = registry.require_agent("local-qwopus-inspector")
    patch_proposer = registry.require_agent("local-qwen25-coder-32b-patch-proposer")
    qwen_fast = registry.require_agent("local-qwen25-coder-7b-code-reviewer")
    qwen_medium = registry.require_agent("local-qwen25-coder-14b-test-planner")
    gemma_fast = registry.require_agent("local-gemma4-summarizer")
    gemma_dense = registry.require_agent("local-gemma4-31b-dense-judge")

    assert manual.hermes_delegable is False
    assert qwopus_patch_worker.hermes_delegable is False
    assert inspector.hermes_delegable is True
    assert inspector.machine_class == "mac_studio"
    assert inspector.weight_class == "heavy"
    assert inspector.model_alias_group == "qwopus-qwen36-07d35212591f"
    assert inspector.default_mode == "read_only"
    assert not any("<workspace>" in path or "proposal.patch" in path for path in inspector.allowed_writes)
    assert patch_proposer.hermes_delegable is False
    assert qwen_fast.machine_class == "mac_mini"
    assert qwen_fast.model_role_name == "qwen-coder-fast"
    assert qwen_medium.machine_class == "either"
    assert gemma_fast.model == "gemma4:latest"
    assert gemma_fast.weight_class == "small"
    assert "8.0B" in " ".join(gemma_fast.manifest_notes)
    assert gemma_dense.model == "gemma4:31b"
    assert gemma_dense.machine_class == "mac_studio"
    assert gemma_dense.model_role_name == "gemma-dense-judge"


def test_agent_registry_rejects_unsafe_hermes_delegation(tmp_path: Path) -> None:
    registry_path = tmp_path / ".devflow/agents/registry.yaml"
    registry_path.parent.mkdir(parents=True)
    registry_path.write_text(
        """version: 1
agents:
  future-worker:
    provider: openai
    model: future
    adapter: openai_responses
    role: frontier_code_reviewer
    tier: frontier
    default_mode: read_only
    workspace: isolated_task_workspace
    can_run_shell: false
    can_use_network: false
    can_promote: false
    hermes_delegable: true
    enabled: true
  risky-writer:
    provider: ollama
    model: qwen2.5-coder:32b-instruct
    adapter: ollama_chat
    role: implementation_worker
    tier: strong_local
    default_mode: workspace_write
    workspace: isolated_task_workspace
    allowed_writes:
      - "<workspace>/**"
      - "<task>/agents/risky-writer/proposal.patch"
    can_run_shell: false
    can_use_network: false
    can_promote: false
    hermes_delegable: true
    enabled: true
""",
        encoding="utf-8",
    )

    with pytest.raises(AgentRegistryError) as exc_info:
        load_agent_registry(tmp_path)

    message = str(exc_info.value)
    assert "future-worker.hermes_delegable must be false for planned_not_executable adapters" in message
    assert "risky-writer.hermes_delegable requires a read-only or proposal-only permission mode" in message
    assert "risky-writer.hermes_delegable cannot write workspace files or proposal.patch" in message


def test_registry_json_includes_hermes_delegable_and_no_profile_points_to_quarantined_checkout(tmp_path: Path) -> None:
    from devflow.control_room.local_model_worker_pool import registry_json_payload

    initialize_seed(tmp_path)
    payload = registry_json_payload(tmp_path)

    assert any(agent["id"] == "local-qwopus-inspector" for agent in payload["agents"])
    for agent in payload["agents"]:
        assert "hermes_delegable" in agent
        encoded = json.dumps(agent, sort_keys=True)
        assert "/Users/jewelbait/Desktop/DevFlow" not in encoded


def test_provider_registry_rejects_literal_secrets_as_api_key_env(tmp_path: Path) -> None:
    providers_dir = tmp_path / ".devflow/providers"
    providers_dir.mkdir(parents=True)

    (providers_dir / "bad-secret.yaml").write_text(
        """provider: openai
adapter: openai_chat
api_key_env: sk-proj-someSecretValueHere
enabled: true
""",
        encoding="utf-8"
    )

    with pytest.raises(AgentRegistryError) as exc_info:
        load_provider_registry(tmp_path)

    assert "must be an uppercase environment variable name, not a literal secret value" in str(exc_info.value)
