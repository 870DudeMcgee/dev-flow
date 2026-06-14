from __future__ import annotations

import json
from pathlib import Path
import pytest
from typer.testing import CliRunner

from devflow.control_room.persistence import save_task, get_task
from devflow.control_room.service import create_task
from devflow.control_room.router import route_task, save_routing_decision
from devflow.control_room.agent_registry import AgentDefinition, AgentRegistry
from devflow.cli import app


def test_router_heuristics_and_saving(tmp_path: Path) -> None:
    # 1. Initialize structures
    (tmp_path / ".devflow/tasks").mkdir(parents=True)
    (tmp_path / ".devflow/workspaces").mkdir(parents=True)
    (tmp_path / ".devflow/agents").mkdir(parents=True)

    # 2. Write mock agents registry.yaml
    registry_file = tmp_path / ".devflow/agents/registry.yaml"
    registry_file.write_text("""version: 1
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
    enabled: true
  qwen-senior:
    provider: local
    model: qwen2.5-coder:14b
    adapter: ollama_chat
    role: senior_developer_worker
    tier: strong_local
    default_mode: workspace_write
    workspace: isolated_task_workspace
    enabled: true
  openai-architect:
    provider: openai
    model: gpt-4o
    adapter: openai_chat
    role: frontier_planner_architect_reviewer
    tier: frontier
    default_mode: read_only
    workspace: isolated_task_workspace
    enabled: true
""", encoding="utf-8")

    # Create dummy task
    task = create_task(tmp_path, "Refactor core model selection algorithms")
    task_dir_path = tmp_path / ".devflow/tasks" / task.id
    save_task(task_dir_path, task)

    # Run router
    routing_res = route_task(tmp_path, task.id)
    rd = routing_res["routing_decision"]

    # Verify evidence-only routing records candidates without running or auto-selecting workers.
    assert rd["task_id"] == task.id
    assert rd["policy_version"] == 2
    assert rd["decision_mode"] == "evidence_only"
    assert rd["requires_escalation"] is True
    selected = rd["selected"]
    assert selected["verifier"] == "deterministic-shell"
    assert "worker" not in selected
    assert any(item["status"] == "human_escalation_required" for item in rd["unresolved"])

    # Test saving
    save_routing_decision(tmp_path, task.id, routing_res)
    yaml_file = task_dir_path / "routing-decision.yaml"
    assert yaml_file.exists()
    
    yaml_content = yaml_file.read_text(encoding="utf-8")
    assert "routing_decision:" in yaml_content
    assert "decision_mode: evidence_only" in yaml_content
    assert "requires_escalation: true" in yaml_content
    assert "selected:" in yaml_content
    assert "verifier: deterministic-shell" in yaml_content
    assert "blocked:" in yaml_content
    assert "unresolved:" in yaml_content
    assert "recommended_next_commands:" in yaml_content


def test_router_cli_command(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    # 1. Initialize structures
    (tmp_path / ".devflow/tasks").mkdir(parents=True)
    (tmp_path / ".devflow/workspaces").mkdir(parents=True)

    # 2. Create task
    task = create_task(tmp_path, "Clean up documentation in PRODUCT_NORTH_STAR.md")
    task_dir_path = tmp_path / ".devflow/tasks" / task.id
    save_task(task_dir_path, task)

    # Monkeypatch Cwd to point to our tmp_path
    monkeypatch.chdir(tmp_path)

    runner = CliRunner()
    result = runner.invoke(app, ["task", "route", task.id])

    assert result.exit_code == 0
    assert "Executed routing mapping for task" in result.output
    assert "Wrote routing-decision.yaml" in result.output

    # Check files exist
    yaml_file = task_dir_path / "routing-decision.yaml"
    assert yaml_file.exists()


def test_route_cli_json_is_stable_without_experimental_env(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    (tmp_path / ".devflow/tasks").mkdir(parents=True)
    (tmp_path / ".devflow/workspaces").mkdir(parents=True)
    task = create_task(tmp_path, "Clean up documentation")
    save_task(tmp_path / ".devflow/tasks" / task.id, task)

    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("DEVFLOW_EXPERIMENTAL", raising=False)

    result = CliRunner().invoke(app, ["task", "route", task.id, "--json"])

    assert result.exit_code == 0
    payload = json.loads(result.output)
    assert payload["task_id"] == task.id
    assert payload["routing_decision"]["decision_mode"] == "evidence_only"
    assert payload["artifact_path"] == f".devflow/tasks/{task.id}/routing-decision.yaml"


def test_router_marks_planner_and_reviewer_unresolved_when_not_selected(tmp_path: Path) -> None:
    (tmp_path / ".devflow/tasks").mkdir(parents=True)
    (tmp_path / ".devflow/workspaces").mkdir(parents=True)
    task = create_task(tmp_path, "Clean up documentation")
    save_task(tmp_path / ".devflow/tasks" / task.id, task)

    routing_res = route_task(tmp_path, task.id)
    rd = routing_res["routing_decision"]

    unresolved_by_role = {item["role"]: item for item in rd["unresolved"]}
    assert unresolved_by_role["planner"]["status"] == "not_selected_evidence_only"
    assert unresolved_by_role["reviewer"]["status"] == "not_selected_evidence_only"
    assert unresolved_by_role["planner"]["next_command"] == (
        f"devflow agent context-pack {task.id} <agent-id> --role planner --json"
    )
    assert unresolved_by_role["reviewer"]["next_command"] == (
        f"devflow agent context-pack {task.id} <agent-id> --role reviewer --json"
    )
    assert rd["recommended_next_commands"]["planner"] == unresolved_by_role["planner"]["next_command"]
    assert rd["recommended_next_commands"]["reviewer"] == unresolved_by_role["reviewer"]["next_command"]


def test_router_project_scopes_recommended_commands(tmp_path: Path) -> None:
    (tmp_path / ".devflow/tasks").mkdir(parents=True)
    (tmp_path / ".devflow/workspaces").mkdir(parents=True)
    task = create_task(tmp_path, "Clean up documentation")
    task.verification_command = "pytest tests/test_docs.py"
    save_task(tmp_path / ".devflow/tasks" / task.id, task)

    routing_res = route_task(tmp_path, task.id, project_id="alpha-app")
    rd = routing_res["routing_decision"]

    assert rd["recommended_next_commands"]["verifier"] == (
        f'devflow task verify {task.id} --project alpha-app --shell "pytest tests/test_docs.py"'
    )
    assert rd["recommended_next_commands"]["planner"] == (
        f"devflow agent context-pack {task.id} <agent-id> --project alpha-app --role planner --json"
    )
    assert rd["recommended_next_commands"]["reviewer"] == (
        f"devflow agent context-pack {task.id} <agent-id> --project alpha-app --role reviewer --json"
    )


def test_high_risk_tasks_require_human_escalation_without_worker_selection(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    # 1. Initialize structures
    (tmp_path / ".devflow/tasks").mkdir(parents=True)
    (tmp_path / ".devflow/workspaces").mkdir(parents=True)
    (tmp_path / ".devflow/agents").mkdir(parents=True)

    # 2. Write mock agents registry.yaml
    registry_file = tmp_path / ".devflow/agents/registry.yaml"
    registry_file.write_text("""version: 1
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
    enabled: true
  qwen-local:
    provider: ollama
    model: qwen-local
    adapter: ollama_chat
    role: local_senior_worker
    tier: local
    default_mode: workspace_write
    workspace: isolated_task_workspace
    enabled: true
  qwen-senior:
    provider: local
    model: qwen2.5-coder:14b
    adapter: ollama_chat
    role: senior_developer_worker
    tier: strong_local
    default_mode: workspace_write
    workspace: isolated_task_workspace
    enabled: true
  openai-architect:
    provider: openai
    model: gpt-4o
    adapter: openai_chat
    role: frontier_planner_architect_reviewer
    tier: frontier
    default_mode: read_only
    workspace: isolated_task_workspace
    enabled: true
""", encoding="utf-8")

    # Create dummy task
    task = create_task(tmp_path, "Refactor core model selection algorithms")
    task_dir_path = tmp_path / ".devflow/tasks" / task.id
    
    # 3. Simulate high risk in task-fit file using monkeypatch mock
    from devflow.control_room.estimator import estimate_task_fit, save_task_fit
    original_estimate = estimate_task_fit
    
    def mock_estimate(root, task_id):
        data = original_estimate(root, task_id)
        data["task_fit"]["code_edit_risk"] = "high"
        data["task_fit"]["recommended_worker_tier"] = "strong_local"
        return data

    monkeypatch.setattr("devflow.control_room.router.estimate_task_fit", mock_estimate)
    fit_data = mock_estimate(tmp_path, task.id)
    save_task_fit(tmp_path, task.id, fit_data)

    save_task(task_dir_path, task)

    # Run router
    routing_res = route_task(tmp_path, task.id)
    rd = routing_res["routing_decision"]

    # Verify high-risk routing remains evidence-only and does not auto-select a worker.
    selected = rd["selected"]
    assert selected["verifier"] == "deterministic-shell"
    assert "worker" not in selected
    assert rd["requires_escalation"] is True
    assert any(item["status"] == "human_escalation_required" for item in rd["unresolved"])
    
    rejected = rd["rejected"]
    # Check that qwen-local is in rejected list due to risk mismatch
    local_rejections = [r for r in rejected if r["agent"] == "qwen-local"]
    assert len(local_rejections) >= 1
    assert any("risk mismatch" in r["reason"] for r in local_rejections)


def test_router_does_not_fallback_to_read_only_worker_pool_profiles(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    (tmp_path / ".devflow/tasks").mkdir(parents=True)
    (tmp_path / ".devflow/workspaces").mkdir(parents=True)
    agent = AgentDefinition(
        id="local-qwopus-inspector",
        provider="ollama",
        model="qwopus:latest",
        adapter="ollama_chat",
        role="implementation_worker",
        tier="strong_local",
        default_mode="read_only",
        execution_mode="automated",
        workspace="isolated_task_workspace",
        allowed_writes=["<task>/local-model-runs/**"],
        forbidden_writes=["<workspace>/**", "<task>/agents/**/proposal.patch"],
        enabled=True,
    )
    registry = AgentRegistry(
        version=1,
        default_agent_id=agent.id,
        agents={agent.id: agent},
    )
    monkeypatch.setattr("devflow.control_room.router.load_agent_registry", lambda root: registry)

    task = create_task(tmp_path, "Route read-only worker pool safely")
    routing_res = route_task(tmp_path, task.id)
    rd = routing_res["routing_decision"]

    assert "worker" not in rd["selected"]
    assert any(
        item["agent"] == "local-qwopus-inspector" and "read-only profile" in item["reason"]
        for item in rd["rejected"]
    )


def test_router_requires_explicit_local_selection_for_local_model_worker(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    (tmp_path / ".devflow/tasks").mkdir(parents=True)
    (tmp_path / ".devflow/workspaces").mkdir(parents=True)
    agent = AgentDefinition(
        id="qwopus-implementer",
        provider="ollama",
        model="qwopus:latest",
        adapter="ollama_chat",
        role="implementation_worker",
        tier="strong_local",
        default_mode="workspace_write",
        execution_mode="automated",
        workspace="isolated_task_workspace",
        allowed_writes=["<task>/agents/qwopus-implementer/proposal.patch"],
        enabled=True,
    )
    registry = AgentRegistry(version=1, default_agent_id=agent.id, agents={agent.id: agent})
    monkeypatch.setattr("devflow.control_room.router.load_agent_registry", lambda root: registry)

    task = create_task(tmp_path, "Implement a small worker feature")
    routing_res = route_task(tmp_path, task.id)
    rd = routing_res["routing_decision"]

    assert "worker" not in rd["selected"]
    assert any(item["role"] == "worker" and item["status"] == "needs_human_agent_selection" for item in rd["unresolved"])
    assert any(item["agent"] == "qwopus-implementer" and "no selected-agent evidence" in item["reason"] for item in rd["rejected"])


def test_router_uses_matching_selected_agent_evidence(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    (tmp_path / ".devflow/tasks").mkdir(parents=True)
    (tmp_path / ".devflow/workspaces").mkdir(parents=True)
    agent = AgentDefinition(
        id="qwopus-implementer",
        provider="ollama",
        model="qwopus:latest",
        adapter="ollama_chat",
        role="implementation_worker",
        tier="strong_local",
        default_mode="workspace_write",
        execution_mode="automated",
        workspace="isolated_task_workspace",
        allowed_writes=["<task>/agents/qwopus-implementer/proposal.patch"],
        enabled=True,
    )
    registry = AgentRegistry(version=1, default_agent_id=agent.id, agents={agent.id: agent})
    monkeypatch.setattr("devflow.control_room.router.load_agent_registry", lambda root: registry)

    task = create_task(tmp_path, "Implement a small worker feature")
    selection_path = tmp_path / ".devflow/tasks" / task.id / "agent-selection.json"
    selection_path.write_text(
        json.dumps(
            {
                "task_id": task.id,
                "role": "implementation_worker",
                "status": "selected",
                "selected_agent_id": "qwopus-implementer",
                "selected_model": "qwopus:latest",
            }
        ),
        encoding="utf-8",
    )

    routing_res = route_task(tmp_path, task.id)
    rd = routing_res["routing_decision"]

    assert rd["decision_mode"] == "evidence_only"
    assert rd["selected"]["worker"] == "qwopus-implementer"
    assert rd["recommended_next_commands"]["worker"] == f"devflow task run {task.id} --worker qwopus-implementer"


def test_router_blocks_selected_local_patch_worker_when_provider_base_url_is_remote(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    (tmp_path / ".devflow/tasks").mkdir(parents=True)
    (tmp_path / ".devflow/workspaces").mkdir(parents=True)
    providers_dir = tmp_path / ".devflow/providers"
    providers_dir.mkdir(parents=True)
    (providers_dir / "ollama.yaml").write_text(
        """provider: ollama
adapter: ollama_chat
base_url: https://ollama.example.invalid
default_timeout_seconds: 300
enabled: true
""",
        encoding="utf-8",
    )
    agent = AgentDefinition(
        id="qwopus-implementer",
        provider="ollama",
        model="qwopus:latest",
        adapter="ollama_chat",
        role="implementation_worker",
        tier="strong_local",
        default_mode="workspace_write",
        execution_mode="automated",
        workspace="isolated_task_workspace",
        allowed_writes=["<task>/agents/qwopus-implementer/proposal.patch"],
        enabled=True,
    )
    registry = AgentRegistry(version=1, default_agent_id=agent.id, agents={agent.id: agent})
    monkeypatch.setattr("devflow.control_room.router.load_agent_registry", lambda root: registry)

    task = create_task(tmp_path, "Implement a small worker feature")
    selection_path = tmp_path / ".devflow/tasks" / task.id / "agent-selection.json"
    selection_path.write_text(
        json.dumps(
            {
                "task_id": task.id,
                "role": "implementation_worker",
                "status": "selected",
                "selected_agent_id": "qwopus-implementer",
                "selected_model": "qwopus:latest",
            }
        ),
        encoding="utf-8",
    )

    routing_res = route_task(tmp_path, task.id)
    rd = routing_res["routing_decision"]

    assert "worker" not in rd["selected"]
    assert any(
        item["agent"] == "qwopus-implementer" and "non-local" in item["reason"]
        for item in rd["rejected"]
    )
    assert any(
        item["agent"] == "qwopus-implementer" and item["status"] == "blocked_runtime"
        for item in rd["blocked"]
    )


def test_router_rejects_unknown_tier_for_strong_worker_requirement(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    (tmp_path / ".devflow/tasks").mkdir(parents=True)
    (tmp_path / ".devflow/workspaces").mkdir(parents=True)
    agent = AgentDefinition(
        id="unknown-tier-implementer",
        provider="ollama",
        model="unknown-tier:latest",
        adapter="ollama_chat",
        role="implementation_worker",
        tier="mystery_tier",
        default_mode="workspace_write",
        execution_mode="automated",
        workspace="isolated_task_workspace",
        allowed_writes=["<task>/agents/unknown-tier-implementer/proposal.patch"],
        enabled=True,
    )
    registry = AgentRegistry(version=1, default_agent_id=agent.id, agents={agent.id: agent})
    monkeypatch.setattr("devflow.control_room.router.load_agent_registry", lambda root: registry)

    task = create_task(tmp_path, "Implement a small worker feature")
    selection_path = tmp_path / ".devflow/tasks" / task.id / "agent-selection.json"
    selection_path.write_text(
        json.dumps(
            {
                "task_id": task.id,
                "role": "implementation_worker",
                "status": "selected",
                "selected_agent_id": "unknown-tier-implementer",
                "selected_model": "unknown-tier:latest",
            }
        ),
        encoding="utf-8",
    )

    routing_res = route_task(tmp_path, task.id)
    rd = routing_res["routing_decision"]

    assert "worker" not in rd["selected"]
    assert any(
        item["agent"] == "unknown-tier-implementer" and "tier mismatch" in item["reason"]
        for item in rd["rejected"]
    )


def test_router_blocks_remote_provider_candidates(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    (tmp_path / ".devflow/tasks").mkdir(parents=True)
    (tmp_path / ".devflow/workspaces").mkdir(parents=True)
    remote = AgentDefinition(
        id="openai-architect",
        provider="openai",
        model="gpt-5",
        adapter="openai_chat",
        role="frontier_planner_architect_reviewer",
        tier="frontier",
        default_mode="frontier_read_only",
        execution_mode="automated",
        workspace="isolated_task_workspace",
        can_use_network=True,
        enabled=True,
    )
    registry = AgentRegistry(version=1, default_agent_id=remote.id, agents={remote.id: remote})
    monkeypatch.setattr("devflow.control_room.router.load_agent_registry", lambda root: registry)

    task = create_task(tmp_path, "Design model routing selector")
    routing_res = route_task(tmp_path, task.id)
    rd = routing_res["routing_decision"]

    assert rd["requires_escalation"] is True
    assert any(item["agent"] == "openai-architect" and "provider is experimental-readonly" in item["reason"] for item in rd["rejected"])
    assert any(item["status"] == "human_escalation_required" for item in rd["unresolved"])


def test_router_blocks_local_provider_candidates_with_non_executable_runtime(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    (tmp_path / ".devflow/tasks").mkdir(parents=True)
    (tmp_path / ".devflow/workspaces").mkdir(parents=True)
    agent = AgentDefinition(
        id="legacy-local-implementer",
        provider="local",
        model="legacy-local",
        adapter="ollama_chat",
        role="implementation_worker",
        tier="strong_local",
        default_mode="workspace_write",
        execution_mode="automated",
        workspace="isolated_task_workspace",
        enabled=True,
    )
    registry = AgentRegistry(version=1, default_agent_id=agent.id, agents={agent.id: agent})
    monkeypatch.setattr("devflow.control_room.router.load_agent_registry", lambda root: registry)

    task = create_task(tmp_path, "Implement a small worker feature")
    routing_res = route_task(tmp_path, task.id)
    rd = routing_res["routing_decision"]

    assert "worker" not in rd["selected"]
    assert any(
        item["agent"] == "legacy-local-implementer" and "cannot execute" in item["reason"]
        for item in rd["rejected"]
    )
    assert any(
        item["agent"] == "legacy-local-implementer" and item["status"] == "blocked_runtime"
        for item in rd["blocked"]
    )
