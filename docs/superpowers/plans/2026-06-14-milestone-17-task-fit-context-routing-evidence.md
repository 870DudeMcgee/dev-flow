# Milestone 17 Task-Fit Context Routing Evidence Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Promote deterministic task-fit, scout, route, and routing-quality commands into stable evidence-only control-room surfaces.

**Architecture:** Keep routing logic inside `src/devflow/control_room/` and expose it through thin Typer command wiring in `src/devflow/cli.py`. The implementation writes derived task-local artifacts only; routing decisions can recommend commands but must not run workers, call providers, verify, promote, commit, push, or publish.

**Tech Stack:** Python 3, Typer, pytest, existing Dev-Flow task artifacts, YAML/text evidence files, JSON CLI output.

---

## File Structure

- Modify `src/devflow/control_room/estimator.py`: deterministic task-fit profile, bounded context estimates, explicit evidence inputs, missing input notes, role tier recommendations, JSON-safe payload.
- Modify `src/devflow/control_room/scout.py`: deterministic scout report generation for one role or all roles, concrete stale-context signals, JSON-safe payload, explicit artifact paths.
- Modify `src/devflow/control_room/router.py`: evidence-only routing decision engine using registry/runtime/local-selection evidence, selected/rejected/blocked/unresolved candidates, next commands, and policy version.
- Modify `src/devflow/control_room/scorecard.py`: routing-quality scorecard over existing routing, worker, verification, review, and promotion evidence without changing task state.
- Modify `src/devflow/cli.py`: make `task fit`, `task scout`, `task route`, and `task scorecard` stable commands with `--json`; keep legacy `task pack` hidden unless it remains needed for compatibility.
- Modify `tests/test_estimator.py`: task-fit artifact and stable CLI coverage.
- Modify `tests/test_scout.py`: scout role and stable CLI coverage.
- Modify `tests/test_router.py`: evidence-only route decisions, local-selection evidence, blocked providers, useful-context rejection, and critical-risk escalation.
- Modify `tests/test_scorecard.py`: scorecard evidence-only behavior and JSON/text CLI coverage.
- Modify `docs/architecture/agent-selection-and-context-routing.md`: update status to implemented evidence-only slice.
- Modify `docs/architecture/agent-registry-and-adapter-runtime.md`: reference Milestone 17 task-fit evidence boundary.
- Modify `docs/control-room-mvp.md`: add stable evidence commands and keep autonomous routing excluded.
- Modify `docs/mvp-contract.md`: add artifact/command contract and keep execution gates unchanged.
- Modify `docs/roadmap.md`: mark Milestone 17 implemented after verification.
- Modify `CODE_MAP.md`: adjust routing boundary wording if command status changes.

## Task 1: Stabilize Task-Fit Evidence

**Files:**
- Modify: `src/devflow/control_room/estimator.py`
- Modify: `tests/test_estimator.py`

- [ ] **Step 1: Write failing tests for enriched task-fit evidence**

Append these tests to `tests/test_estimator.py`:

```python
def test_estimator_records_policy_fields_and_evidence_inputs(tmp_path: Path) -> None:
    (tmp_path / ".devflow/tasks").mkdir(parents=True)
    (tmp_path / ".devflow/workspaces").mkdir(parents=True)
    (tmp_path / "CODE_MAP.md").write_text("# Code Map\n\n## Layout\n- `src/devflow/control_room/` active core\n", encoding="utf-8")

    task = create_task(tmp_path, "Design model routing selector")
    task_dir_path = tmp_path / ".devflow/tasks" / task.id
    save_task(task_dir_path, task)

    fit_data = estimate_task_fit(tmp_path, task.id)
    task_fit = fit_data["task_fit"]
    repo_scan = fit_data["repo_scan"]

    assert task_fit["task_type"] == "model_routing_change"
    assert task_fit["architectural_risk"] == "critical"
    assert task_fit["recommended_planner_tier"] == "frontier"
    assert task_fit["recommended_worker_tier"] == "frontier"
    assert task_fit["recommended_reviewer_tier"] == "frontier"
    assert task_fit["recommended_verifier_tier"] == "deterministic"
    assert task_fit["recommended_summarizer_tier"] in {"local", "strong_local"}
    assert task_fit["recommended_scout_tier"] in {"local", "strong_local"}
    assert "task.yaml" in repo_scan["evidence_inputs"]
    assert "CODE_MAP.md" in repo_scan["evidence_inputs"]
    assert isinstance(repo_scan["missing_inputs"], list)
```

Add this CLI test to `tests/test_estimator.py`:

```python
def test_estimator_cli_json_is_stable_without_experimental_env(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    (tmp_path / ".devflow/tasks").mkdir(parents=True)
    (tmp_path / ".devflow/workspaces").mkdir(parents=True)
    task = create_task(tmp_path, "Clean up documentation in PRODUCT_NORTH_STAR.md")
    save_task(tmp_path / ".devflow/tasks" / task.id, task)

    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("DEVFLOW_EXPERIMENTAL", raising=False)

    result = CliRunner().invoke(app, ["task", "fit", task.id, "--json"])

    assert result.exit_code == 0
    payload = json.loads(result.output)
    assert payload["task_id"] == task.id
    assert payload["task_fit"]["task_type"] == "documentation_cleanup"
    assert payload["artifact_path"] == f".devflow/tasks/{task.id}/task-fit.yaml"
```

- [ ] **Step 2: Run tests to verify they fail**

Run:

```bash
PYTHONPATH=src:. .venv/bin/python -m pytest tests/test_estimator.py -q
```

Expected: fail because the current payload lacks `recommended_verifier_tier`, `recommended_summarizer_tier`, `recommended_scout_tier`, `evidence_inputs`, `missing_inputs`, `artifact_path`, and stable `--json` support.

- [ ] **Step 3: Implement enriched estimator fields**

In `src/devflow/control_room/estimator.py`, add these helpers near the top of the file after imports:

```python
def _relative(root: Path, path: Path) -> str:
    try:
        return str(path.resolve().relative_to(root.resolve()))
    except ValueError:
        return str(path)


def _line_and_token_estimate(path: Path) -> tuple[int, int]:
    try:
        text = path.read_text(encoding="utf-8", errors="ignore")
    except OSError:
        return (0, 0)
    return (len(text.splitlines()), max(1, len(text) // 4))


def _tier_for_summarizer(context_requirement: str) -> str:
    if context_requirement in {"high", "critical"}:
        return "strong_local"
    return "local"


def _tier_for_scout(repo_scope: str) -> str:
    if repo_scope == "large":
        return "strong_local"
    return "local"
```

Inside `estimate_task_fit()`, after `docs_list` is built, add explicit evidence input tracking:

```python
    evidence_inputs = ["task.yaml"]
    missing_inputs: list[str] = []
    code_map_path = root / "CODE_MAP.md"
    if code_map_path.exists():
        evidence_inputs.append("CODE_MAP.md")
    else:
        missing_inputs.append("CODE_MAP.md")

    if not referenced_files:
        missing_inputs.append("explicit referenced files")
    if not test_files_list:
        missing_inputs.append("matched test files")
```

Replace the current relevant file line/token loop with:

```python
    relevant_lines = 0
    relevant_tokens = 0
    for path in all_relevant_files:
        line_count, token_count = _line_and_token_estimate(path)
        relevant_lines += line_count
        relevant_tokens += token_count
```

After `recommended_reviewer_tier` is calculated, add:

```python
    recommended_verifier_tier = "deterministic"
    recommended_summarizer_tier = _tier_for_summarizer(context_requirement)
    recommended_scout_tier = _tier_for_scout(repo_scope)
```

Add these keys to `task_fit`:

```python
        "recommended_verifier_tier": recommended_verifier_tier,
        "recommended_summarizer_tier": recommended_summarizer_tier,
        "recommended_scout_tier": recommended_scout_tier,
```

Add these keys to `repo_scan`:

```python
        "evidence_inputs": evidence_inputs,
        "missing_inputs": missing_inputs,
```

Update `save_task_fit()` so list values are written as YAML lists:

```python
        if isinstance(val, list):
            lines.append(f"  {key}:")
            if val:
                for item in val:
                    lines.append(f"    - {item}")
            else:
                lines.append("    - none")
            continue
```

Apply that list handling in both the `task_fit` and `repo_scan` loops.

- [ ] **Step 4: Run estimator tests to verify data behavior passes**

Run:

```bash
PYTHONPATH=src:. .venv/bin/python -m pytest tests/test_estimator.py::test_estimator_records_policy_fields_and_evidence_inputs -q
```

Expected: pass.

- [ ] **Step 5: Commit Task 1**

Run:

```bash
PYTHONPATH=src:. .venv/bin/devflow git checkpoint --message "feat: enrich task fit evidence" --yes
```

Expected: commit created, tree clean or only later-task files absent.

## Task 2: Stabilize Scout Evidence

**Files:**
- Modify: `src/devflow/control_room/scout.py`
- Create: `tests/test_scout.py` if it does not exist
- Modify: `tests/test_scout.py` if it exists

- [ ] **Step 1: Write failing scout tests**

Create or append `tests/test_scout.py`:

```python
from __future__ import annotations

import json
from pathlib import Path

import pytest
from typer.testing import CliRunner

from devflow.cli import app
from devflow.control_room.persistence import save_task
from devflow.control_room.scout import run_scout_report, run_scout_reports, save_scout_report
from devflow.control_room.service import create_task


def test_run_scout_reports_returns_all_roles_without_provider_calls(tmp_path: Path) -> None:
    (tmp_path / ".devflow/tasks").mkdir(parents=True)
    (tmp_path / ".devflow/workspaces").mkdir(parents=True)
    task = create_task(tmp_path, "Route implementation worker safely")
    save_task(tmp_path / ".devflow/tasks" / task.id, task)

    reports = run_scout_reports(tmp_path, task.id, role="all")

    assert sorted(reports) == ["context", "repo_scope", "risk", "stale_context", "test"]
    assert reports["risk"]["scout_report"]["role"] == "risk_scout"
    assert reports["stale_context"]["scout_report"]["poison_context_risk"] in {"low", "high"}


def test_save_scout_report_returns_artifact_path(tmp_path: Path) -> None:
    (tmp_path / ".devflow/tasks").mkdir(parents=True)
    (tmp_path / ".devflow/workspaces").mkdir(parents=True)
    task = create_task(tmp_path, "Find likely tests")
    save_task(tmp_path / ".devflow/tasks" / task.id, task)

    report = run_scout_report(tmp_path, task.id, "test")
    path = save_scout_report(tmp_path, task.id, "test", report)

    assert path == tmp_path / ".devflow/tasks" / task.id / "scout-test.yaml"
    assert "scout_report:" in path.read_text(encoding="utf-8")


def test_scout_cli_json_is_stable_without_experimental_env(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    (tmp_path / ".devflow/tasks").mkdir(parents=True)
    (tmp_path / ".devflow/workspaces").mkdir(parents=True)
    task = create_task(tmp_path, "Assess routing risks")
    save_task(tmp_path / ".devflow/tasks" / task.id, task)

    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("DEVFLOW_EXPERIMENTAL", raising=False)

    result = CliRunner().invoke(app, ["task", "scout", task.id, "--role", "risk", "--json"])

    assert result.exit_code == 0
    payload = json.loads(result.output)
    assert payload["task_id"] == task.id
    assert payload["reports"]["risk"]["scout_report"]["role"] == "risk_scout"
    assert payload["artifact_paths"]["risk"] == f".devflow/tasks/{task.id}/scout-risk.yaml"
```

- [ ] **Step 2: Run tests to verify they fail**

Run:

```bash
PYTHONPATH=src:. .venv/bin/python -m pytest tests/test_scout.py -q
```

Expected: fail because `run_scout_reports()` and stable `task scout --role --json` do not exist, and `save_scout_report()` does not return a path.

- [ ] **Step 3: Add multi-role scout helper and path return**

In `src/devflow/control_room/scout.py`, add this constant above `run_scout_report()`:

```python
SCOUT_ROLES = ("repo_scope", "risk", "context", "test", "stale_context")
```

Add this function above `run_scout_report()`:

```python
def run_scout_reports(root: Path, task_id: str, role: str = "all") -> dict[str, dict[str, Any]]:
    roles = SCOUT_ROLES if role == "all" else (role,)
    return {item: run_scout_report(root, task_id, item) for item in roles}
```

Replace the local `allowed_roles` tuple inside `run_scout_report()` with `SCOUT_ROLES`:

```python
    if role not in SCOUT_ROLES:
        raise ValueError(f"Invalid scout role: '{role}'. Must be one of: {', '.join(SCOUT_ROLES)}")
```

Change the signature of `save_scout_report()`:

```python
def save_scout_report(root: Path, task_id: str, role: str, report_data: dict[str, Any]) -> Path:
```

Add this return at the end of `save_scout_report()`:

```python
    return yaml_file
```

- [ ] **Step 4: Run focused scout helper tests**

Run:

```bash
PYTHONPATH=src:. .venv/bin/python -m pytest tests/test_scout.py::test_run_scout_reports_returns_all_roles_without_provider_calls tests/test_scout.py::test_save_scout_report_returns_artifact_path -q
```

Expected: pass.

- [ ] **Step 5: Commit Task 2**

Run:

```bash
PYTHONPATH=src:. .venv/bin/devflow git checkpoint --message "feat: stabilize scout evidence helpers" --yes
```

Expected: commit created.

## Task 3: Rewrite Routing As Evidence-Only Selection

**Files:**
- Modify: `src/devflow/control_room/router.py`
- Modify: `tests/test_router.py`

- [ ] **Step 1: Write failing router tests**

Append these tests to `tests/test_router.py`:

```python
def test_router_requires_explicit_local_selection_for_local_model_worker(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
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


def test_router_uses_matching_selected_agent_evidence(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
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


def test_router_blocks_remote_provider_candidates(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
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
```

- [ ] **Step 2: Run router tests to verify they fail**

Run:

```bash
PYTHONPATH=src:. .venv/bin/python -m pytest tests/test_router.py -q
```

Expected: fail because the current router falls back to agents too broadly, lacks `decision_mode`, `unresolved`, `requires_escalation`, `recommended_next_commands`, and selected-agent evidence checks.

- [ ] **Step 3: Add selected-agent evidence reader and candidate rejection helpers**

In `src/devflow/control_room/router.py`, add imports:

```python
import json
from devflow.control_room.agent_runtime import resolve_agent_runtime_definition
```

Add these helpers after imports:

```python
POLICY_VERSION = 2
LOCAL_MODEL_PROVIDERS = {"ollama", "local"}


def _read_selected_agent_evidence(root: Path, task_id: str) -> dict[str, Any] | None:
    path = task_dir(root, task_id) / "agent-selection.json"
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return None


def _tier_cost(tier: str) -> int:
    return {
        "tiny_local": 0,
        "fast_local": 1,
        "local": 1,
        "strong_local": 2,
        "premium_local": 3,
        "frontier": 4,
        "manual": 5,
    }.get(tier.lower(), 4)


def _role_matches(agent: AgentDefinition, role_name: str) -> bool:
    role_text = " ".join([agent.id, agent.role, *agent.secondary_roles]).lower()
    if role_name == "planner":
        return any(word in role_text for word in ("planner", "architect", "lead", "reviewer"))
    if role_name == "worker":
        return any(word in role_text for word in ("worker", "implementer", "developer", "coder"))
    if role_name == "reviewer":
        return any(word in role_text for word in ("reviewer", "audit", "architect"))
    return False


def _selected_local_agent_id(selection: dict[str, Any] | None, role_name: str) -> str | None:
    if role_name != "worker" or selection is None:
        return None
    if selection.get("role") != "implementation_worker" or selection.get("status") != "selected":
        return None
    selected = selection.get("selected_agent_id")
    return selected if isinstance(selected, str) and selected else None
```

- [ ] **Step 4: Replace route selection with evidence-only candidate resolution**

Replace the body of `route_task()` with this structure:

```python
def route_task(root: Path, task_id: str) -> dict[str, Any]:
    task_fit_file = task_dir(root, task_id) / "task-fit.yaml"
    fit_data = estimate_task_fit(root, task_id)
    if not task_fit_file.exists():
        save_task_fit(root, task_id, fit_data)

    tf = fit_data.get("task_fit", {})
    rs = fit_data.get("repo_scan", {})
    registry = load_agent_registry(root)
    selection = _read_selected_agent_evidence(root, task_id)

    selected: dict[str, str] = {}
    rejected: list[dict[str, str]] = []
    blocked: list[dict[str, str]] = []
    unresolved: list[dict[str, str]] = []
    recommended_next_commands: dict[str, str] = {}
    reasons = [
        f"context estimate ({rs.get('total_context_estimate', 0)} tokens) is {tf.get('context_requirement', 'medium')}",
        f"architectural risk is {tf.get('architectural_risk', 'medium')}",
        f"code edit risk is {tf.get('code_edit_risk', 'medium')}",
    ]

    requires_escalation = (
        tf.get("task_type") == "model_routing_change"
        or tf.get("architectural_risk") == "critical"
        or tf.get("code_edit_risk") == "critical"
    )
    if requires_escalation:
        reasons.append("critical routing or architectural risk requires human-visible escalation")

    selected_local_worker = _selected_local_agent_id(selection, "worker")
    total_context = int(rs.get("total_context_estimate", 0) or 0)

    def choose(role_name: str, required_tier: str) -> None:
        role_candidates = [agent for agent in registry.enabled_agents() if _role_matches(agent, role_name)]
        if role_name == "worker" and requires_escalation:
            unresolved.append(
                {
                    "role": role_name,
                    "status": "human_escalation_required",
                    "next_action": "Review task-fit.yaml and choose a worker manually after planning approval.",
                }
            )
            return

        eligible: list[AgentDefinition] = []
        for agent in role_candidates:
            runtime = resolve_agent_runtime_definition(agent, None)
            if runtime.remote_provider or runtime.execution_surface == "blocked":
                reason = "provider is experimental-readonly or planned and cannot be selected by evidence-only routing"
                rejected.append({"agent": agent.id, "role": role_name, "reason": reason})
                blocked.append({"agent": agent.id, "role": role_name, "reason": runtime.refusal_reason or reason})
                continue
            if role_name == "worker" and not runtime.task_run_allowed:
                rejected.append({"agent": agent.id, "role": role_name, "reason": "candidate is read-only and cannot serve as implementation worker"})
                continue
            if role_name == "worker" and agent.provider in LOCAL_MODEL_PROVIDERS and selected_local_worker != agent.id:
                rejected.append({"agent": agent.id, "role": role_name, "reason": "no selected-agent evidence for local model worker"})
                continue
            if _tier_cost(agent.tier) < _tier_cost(required_tier):
                rejected.append({"agent": agent.id, "role": role_name, "reason": f"tier mismatch: {agent.tier} below {required_tier}"})
                continue
            useful_context = 32768 if agent.tier in {"local", "strong_local", "premium_local"} else 128000
            if total_context > useful_context:
                rejected.append({"agent": agent.id, "role": role_name, "reason": f"useful context below pack estimate: {useful_context} < {total_context}"})
                continue
            eligible.append(agent)

        if not eligible:
            unresolved.append(
                {
                    "role": role_name,
                    "status": "needs_human_agent_selection" if role_name == "worker" else "no_eligible_agent",
                    "next_action": f"Inspect .devflow/tasks/{task_id}/task-fit.yaml and choose a registered {role_name} explicitly.",
                }
            )
            return

        eligible.sort(key=lambda agent: (_tier_cost(agent.tier), agent.id))
        chosen = eligible[0]
        selected[role_name] = chosen.id
        if role_name == "worker":
            recommended_next_commands[role_name] = f"devflow task run {task_id} --worker {chosen.id}"
        else:
            recommended_next_commands[role_name] = f"devflow agent context-pack {task_id} {chosen.id} --role {role_name} --json"

    choose("planner", tf.get("recommended_planner_tier", "frontier"))
    choose("worker", tf.get("recommended_worker_tier", "strong_local"))
    choose("reviewer", tf.get("recommended_reviewer_tier", "frontier"))
    selected["verifier"] = "deterministic-shell"
    recommended_next_commands["verifier"] = f"devflow task verify {task_id} --shell '<verification-command>'"

    return {
        "routing_decision": {
            "task_id": task_id,
            "policy_version": POLICY_VERSION,
            "decision_mode": "evidence_only",
            "task_fit_profile_path": f".devflow/tasks/{task_id}/task-fit.yaml",
            "requires_escalation": requires_escalation,
            "selected": selected,
            "reason": reasons,
            "rejected": rejected,
            "blocked": blocked,
            "unresolved": unresolved,
            "recommended_next_commands": recommended_next_commands,
            "execution_boundary": "Routing evidence recommends commands only; it does not run workers, call providers, verify, promote, commit, push, or publish.",
        }
    }
```

- [ ] **Step 5: Update routing persistence**

In `save_routing_decision()`, write the new fields under `routing_decision`:

```python
    lines.append(f"  decision_mode: {rd.get('decision_mode', 'evidence_only')}")
    lines.append(f"  requires_escalation: {'true' if rd.get('requires_escalation') else 'false'}")
```

After `selected`, write `recommended_next_commands`, `blocked`, and `unresolved`:

```python
    lines.append("  recommended_next_commands:")
    for key, value in rd.get("recommended_next_commands", {}).items():
        lines.append(f"    {key}: {value}")

    for section in ("blocked", "unresolved"):
        lines.append(f"  {section}:")
        items = rd.get(section, [])
        if not items:
            lines.append("    - none")
        else:
            for item in items:
                lines.append(f"    - role: {item.get('role', '')}")
                if item.get("agent"):
                    lines.append(f"      agent: {item.get('agent', '')}")
                if item.get("status"):
                    lines.append(f"      status: {item.get('status', '')}")
                if item.get("reason"):
                    lines.append(f"      reason: {item.get('reason', '')}")
                if item.get("next_action"):
                    lines.append(f"      next_action: {item.get('next_action', '')}")
```

- [ ] **Step 6: Run router tests**

Run:

```bash
PYTHONPATH=src:. .venv/bin/python -m pytest tests/test_router.py -q
```

Expected: pass after updating old assertions that expected automatic fallback to remote or shell workers. Preserve the existing read-only worker-pool refusal expectation by changing its assertion from `selected["worker"] == "deterministic-shell"` to an unresolved worker role with a rejection reason.

- [ ] **Step 7: Commit Task 3**

Run:

```bash
PYTHONPATH=src:. .venv/bin/devflow git checkpoint --message "feat: add evidence only routing decisions" --yes
```

Expected: commit created.

## Task 4: Promote Stable CLI Evidence Commands

**Files:**
- Modify: `src/devflow/cli.py`
- Modify: `tests/test_estimator.py`
- Modify: `tests/test_scout.py`
- Modify: `tests/test_router.py`

- [ ] **Step 1: Write failing CLI tests for route JSON**

Append this test to `tests/test_router.py`:

```python
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
```

- [ ] **Step 2: Run CLI tests to verify they fail**

Run:

```bash
PYTHONPATH=src:. .venv/bin/python -m pytest tests/test_estimator.py::test_estimator_cli_json_is_stable_without_experimental_env tests/test_scout.py::test_scout_cli_json_is_stable_without_experimental_env tests/test_router.py::test_route_cli_json_is_stable_without_experimental_env -q
```

Expected: fail until command decorators and parameters are updated.

- [ ] **Step 3: Remove experimental gate from stable evidence commands**

In `src/devflow/cli.py`, change the decorators for `task_fit_command`, `task_scout_command`, `task_route_command`, and `task_scorecard_command` to plain command decorators:

```python
@task_app.command("fit")
```

```python
@task_app.command("scout")
```

```python
@task_app.command("route")
```

```python
@task_app.command("scorecard")
```

Remove these calls from those four command bodies:

```python
    _enforce_experimental("task fit")
    _enforce_experimental("task scout")
    _enforce_experimental("task route")
    _enforce_experimental("task scorecard")
```

Keep `task pack` hidden and experimental.

- [ ] **Step 4: Add JSON output to `task fit`**

Change `task_fit_command` signature:

```python
def task_fit_command(
    task_id: str,
    json_output: bool = typer.Option(False, "--json", help="Emit machine-readable JSON."),
) -> None:
```

After saving `fit_data`, add:

```python
    artifact_path = f".devflow/tasks/{task_id}/task-fit.yaml"
    if json_output:
        payload = {"task_id": task_id, "artifact_path": artifact_path, **fit_data}
        typer.echo(json.dumps(payload, indent=2, sort_keys=True))
        return
```

- [ ] **Step 5: Add role option and JSON output to `task scout`**

Change `task_scout_command` signature:

```python
def task_scout_command(
    task_id: str,
    role: str = typer.Option("all", "--role", help="Scout role to run, or 'all'."),
    json_output: bool = typer.Option(False, "--json", help="Emit machine-readable JSON."),
) -> None:
```

Replace the current role loop with:

```python
    try:
        from devflow.control_room.scout import run_scout_reports, save_scout_report

        reports = run_scout_reports(root, task_id, role=role)
        artifact_paths = {}
        for scout_role, data in reports.items():
            path = save_scout_report(root, task_id, scout_role, data)
            artifact_paths[scout_role] = _relative(root, path)
    except Exception as exc:
        typer.echo(str(exc), err=True)
        raise typer.Exit(code=1) from exc

    if json_output:
        typer.echo(
            json.dumps(
                {"task_id": task_id, "reports": reports, "artifact_paths": artifact_paths},
                indent=2,
                sort_keys=True,
            )
        )
        return
```

- [ ] **Step 6: Add JSON output to `task route`**

Change `task_route_command` signature:

```python
def task_route_command(
    task_id: str,
    json_output: bool = typer.Option(False, "--json", help="Emit machine-readable JSON."),
) -> None:
```

After saving `decision_data`, add:

```python
    artifact_path = f".devflow/tasks/{task_id}/routing-decision.yaml"
    if json_output:
        payload = {"task_id": task_id, "artifact_path": artifact_path, **decision_data}
        typer.echo(json.dumps(payload, indent=2, sort_keys=True))
        return
```

Update text output to print `unresolved`, `blocked`, and `recommended_next_commands` when present.

- [ ] **Step 7: Run stable CLI tests**

Run:

```bash
PYTHONPATH=src:. .venv/bin/python -m pytest tests/test_estimator.py::test_estimator_cli_json_is_stable_without_experimental_env tests/test_scout.py::test_scout_cli_json_is_stable_without_experimental_env tests/test_router.py::test_route_cli_json_is_stable_without_experimental_env -q
```

Expected: pass.

- [ ] **Step 8: Commit Task 4**

Run:

```bash
PYTHONPATH=src:. .venv/bin/devflow git checkpoint --message "feat: expose routing evidence commands" --yes
```

Expected: commit created.

## Task 5: Align Routing Quality Scorecards

**Files:**
- Modify: `src/devflow/control_room/scorecard.py`
- Create: `tests/test_scorecard.py` if it does not exist
- Modify: `tests/test_scorecard.py` if it exists
- Modify: `src/devflow/cli.py`

- [ ] **Step 1: Write failing scorecard tests**

Create or append `tests/test_scorecard.py`:

```python
from __future__ import annotations

import json
from pathlib import Path

import pytest
from typer.testing import CliRunner

from devflow.cli import app
from devflow.control_room.persistence import save_task
from devflow.control_room.router import route_task, save_routing_decision
from devflow.control_room.scorecard import generate_scorecard, save_scorecard
from devflow.control_room.service import create_task


def test_scorecard_reports_measurement_only_without_verification(tmp_path: Path) -> None:
    (tmp_path / ".devflow/tasks").mkdir(parents=True)
    (tmp_path / ".devflow/workspaces").mkdir(parents=True)
    task = create_task(tmp_path, "Clean up docs")
    save_task(tmp_path / ".devflow/tasks" / task.id, task)
    save_routing_decision(tmp_path, task.id, route_task(tmp_path, task.id))

    scorecard = generate_scorecard(tmp_path, task.id)["scorecard"]

    assert scorecard["task_id"] == task.id
    assert scorecard["decision_mode"] == "evidence_only"
    assert scorecard["verification_passed"] == "unknown"
    assert scorecard["promotion_ready"] == "unknown"
    assert scorecard["state_mutation"] == "none"


def test_scorecard_cli_json_is_stable_without_experimental_env(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    (tmp_path / ".devflow/tasks").mkdir(parents=True)
    (tmp_path / ".devflow/workspaces").mkdir(parents=True)
    task = create_task(tmp_path, "Clean up docs")
    save_task(tmp_path / ".devflow/tasks" / task.id, task)

    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("DEVFLOW_EXPERIMENTAL", raising=False)

    result = CliRunner().invoke(app, ["task", "scorecard", task.id, "--json"])

    assert result.exit_code == 0
    payload = json.loads(result.output)
    assert payload["task_id"] == task.id
    assert payload["artifact_path"] == f".devflow/tasks/{task.id}/routing-quality-scorecard.yaml"
    assert payload["scorecard"]["state_mutation"] == "none"
```

- [ ] **Step 2: Run scorecard tests to verify they fail**

Run:

```bash
PYTHONPATH=src:. .venv/bin/python -m pytest tests/test_scorecard.py -q
```

Expected: fail because scorecard output lacks `decision_mode`, `verification_passed`, `promotion_ready`, `state_mutation`, stable CLI JSON, and the expected artifact path.

- [ ] **Step 3: Add measurement-only scorecard fields**

In `src/devflow/control_room/scorecard.py`, after `rd = decision_data.get("routing_decision", {})`, add:

```python
    verification_passed: bool | str = "unknown"
    verification_json = task_dir(root, task_id) / "verification.json"
    if verification_json.exists():
        try:
            verification_payload = json.loads(verification_json.read_text(encoding="utf-8"))
            verification_passed = bool(verification_payload.get("passed", False))
        except json.JSONDecodeError:
            verification_passed = "unknown"

    promotion_ready: bool | str = "unknown"
    merge_readiness_json = task_dir(root, task_id) / "merge-readiness.json"
    if merge_readiness_json.exists():
        try:
            readiness_payload = json.loads(merge_readiness_json.read_text(encoding="utf-8"))
            promotion_ready = bool(readiness_payload.get("ready", False))
        except json.JSONDecodeError:
            promotion_ready = "unknown"
```

Add these keys to the returned `scorecard` dict:

```python
            "decision_mode": rd.get("decision_mode", "evidence_only"),
            "verification_passed": verification_passed,
            "promotion_ready": promotion_ready,
            "selected_roles": sorted(rd.get("selected", {}).keys()),
            "unresolved_roles": [item.get("role", "") for item in rd.get("unresolved", [])],
            "state_mutation": "none",
```

- [ ] **Step 4: Save scorecard to the spec artifact path**

In `save_scorecard()`, ensure the artifact path is:

```python
    yaml_file = task_directory / "routing-quality-scorecard.yaml"
```

If the current function writes another filename, update tests and callers to use `routing-quality-scorecard.yaml`.

- [ ] **Step 5: Add JSON output to `task scorecard`**

In `src/devflow/cli.py`, change `task_scorecard_command` signature:

```python
def task_scorecard_command(
    task_id: str,
    json_output: bool = typer.Option(False, "--json", help="Emit machine-readable JSON."),
) -> None:
```

After saving the scorecard, add:

```python
    artifact_path = f".devflow/tasks/{task_id}/routing-quality-scorecard.yaml"
    if json_output:
        payload = {"task_id": task_id, "artifact_path": artifact_path, **scorecard_data}
        typer.echo(json.dumps(payload, indent=2, sort_keys=True))
        return
```

- [ ] **Step 6: Run scorecard tests**

Run:

```bash
PYTHONPATH=src:. .venv/bin/python -m pytest tests/test_scorecard.py -q
```

Expected: pass.

- [ ] **Step 7: Commit Task 5**

Run:

```bash
PYTHONPATH=src:. .venv/bin/devflow git checkpoint --message "feat: add routing quality scorecards" --yes
```

Expected: commit created.

## Task 6: Align Active Docs And Stale Context

**Files:**
- Modify: `docs/architecture/agent-selection-and-context-routing.md`
- Modify: `docs/architecture/agent-registry-and-adapter-runtime.md`
- Modify: `docs/control-room-mvp.md`
- Modify: `docs/mvp-contract.md`
- Modify: `docs/roadmap.md`
- Modify: `CODE_MAP.md`

- [ ] **Step 1: Update architecture status**

In `docs/architecture/agent-selection-and-context-routing.md`, replace the current status line with:

```markdown
Status: active architecture with Milestone 17 evidence-only routing implementation. This document does not enable autonomous routing, provider-backed worker execution, worker-owned verification, or promotion.
```

Add this paragraph after the opening section:

```markdown
Milestone 17 promotes deterministic task-fit, scout, route, and routing-quality artifacts as derived evidence. The stable commands write evidence and recommend next commands only; humans or explicit dogfood lanes still invoke worker execution, verification, promotion, commit, push, and publication.
```

- [ ] **Step 2: Update registry architecture boundary**

In `docs/architecture/agent-registry-and-adapter-runtime.md`, add this sentence to the "Task Fit And Context Routing Boundary" section:

```markdown
Milestone 17 implements the first evidence-only task-fit/context-routing slice: task-fit, scout, routing-decision, and routing-quality artifacts are stable derived evidence, while autonomous worker assignment and provider-backed execution remain excluded.
```

- [ ] **Step 3: Update MVP command contract docs**

In `docs/control-room-mvp.md` and `docs/mvp-contract.md`, add these stable commands to the command lists:

```bash
devflow task fit <task_id>
devflow task fit <task_id> --json
devflow task scout <task_id> --role all
devflow task scout <task_id> --role risk --json
devflow task route <task_id>
devflow task route <task_id> --json
devflow task scorecard <task_id>
devflow task scorecard <task_id> --json
```

Add this boundary paragraph near the agent selection section:

```markdown
The task-fit/context-routing evidence form writes derived artifacts only. It classifies task fit, context size, scout signals, candidate eligibility, rejected candidates, unresolved roles, and post-run quality signals. It does not run workers, call remote providers, silently substitute models, verify, promote, commit, push, or create pull requests.
```

- [ ] **Step 4: Update roadmap status and code map**

In `docs/roadmap.md`, change Milestone 17 status to:

```markdown
Status: implemented. Design and implementation plan live in [docs/superpowers/specs/2026-06-14-milestone-17-task-fit-context-routing-design.md](superpowers/specs/2026-06-14-milestone-17-task-fit-context-routing-design.md) and [docs/superpowers/plans/2026-06-14-milestone-17-task-fit-context-routing-evidence.md](superpowers/plans/2026-06-14-milestone-17-task-fit-context-routing-evidence.md).
```

In `CODE_MAP.md`, update the routing boundary bullet to say:

```markdown
- Task-fit/context routing commands are evidence-only. They write derived fit, scout, route, and scorecard artifacts; autonomous route selection and provider-backed execution remain excluded.
```

- [ ] **Step 5: Run stale-context scan**

Run:

```bash
rg -n "task-fit/context routing runtime \\(Design documented only|fully automatic best-model-for-any-task routing remains future|future task-fit/context-routing work" docs CODE_MAP.md README.md PRODUCT_NORTH_STAR.md
```

Expected: no matches. If matches remain in superseded handoff files, update the search to exclude `docs/handoffs/` and confirm active docs are clean:

```bash
rg -n "task-fit/context routing runtime \\(Design documented only|fully automatic best-model-for-any-task routing remains future|future task-fit/context-routing work" docs CODE_MAP.md README.md PRODUCT_NORTH_STAR.md -g '!docs/handoffs/**'
```

Expected: no matches.

- [ ] **Step 6: Commit Task 6**

Run:

```bash
PYTHONPATH=src:. .venv/bin/devflow git checkpoint --message "docs: align routing evidence contract" --yes
```

Expected: commit created.

## Task 7: Final Verification And Handoff

**Files:**
- Verify all files changed in Tasks 1-6
- Create handoff only if this milestone is being closed in this implementation run

- [ ] **Step 1: Run focused routing tests**

Run:

```bash
PYTHONPATH=src:. .venv/bin/python -m pytest tests/test_estimator.py tests/test_scout.py tests/test_router.py tests/test_scorecard.py tests/test_agent_runtime.py tests/test_local_agent_discovery.py -q
```

Expected: all selected tests pass.

- [ ] **Step 2: Run CLI smoke checks**

Create a disposable task and run stable evidence commands:

```bash
TASK_ID="$(PYTHONPATH=src:. .venv/bin/devflow task create "Milestone 17 routing evidence smoke" | awk '/task_id:/ {print $2}')"
PYTHONPATH=src:. .venv/bin/devflow task fit "$TASK_ID" --json
PYTHONPATH=src:. .venv/bin/devflow task scout "$TASK_ID" --role risk --json
PYTHONPATH=src:. .venv/bin/devflow task route "$TASK_ID" --json
PYTHONPATH=src:. .venv/bin/devflow task scorecard "$TASK_ID" --json
```

Expected: each command exits `0`, writes the documented artifact under `.devflow/tasks/<task_id>/`, and does not run a worker or verification command.

- [ ] **Step 3: Run diff and stale-context checks**

Run:

```bash
git diff --check
rg -n "task-fit/context routing runtime \\(Design documented only|fully automatic best-model-for-any-task routing remains future|future task-fit/context-routing work" docs CODE_MAP.md README.md PRODUCT_NORTH_STAR.md -g '!docs/handoffs/**'
```

Expected: `git diff --check` exits `0` with no output. The stale-context scan exits `1` with no matches.

- [ ] **Step 4: Run broader verification**

Run:

```bash
PYTHONPATH=src:. .venv/bin/python -m pytest tests -q
```

Expected: full test suite passes. If failures are unrelated to this milestone, capture the failing test names and stop for review before checkpointing.

- [ ] **Step 5: Checkpoint implementation**

Run:

```bash
PYTHONPATH=src:. .venv/bin/devflow git checkpoint --message "feat: implement routing evidence commands" --yes
```

Expected: commit created with only Milestone 17 implementation/docs changes.

- [ ] **Step 6: Confirm final Git state**

Run:

```bash
PYTHONPATH=src:. .venv/bin/devflow git status
```

Expected: clean `main`. If ahead of `origin/main`, do not push unless the human explicitly approves `devflow push-main`.

## Self-Review

- Spec coverage: Tasks 1-5 implement task-fit, scouts, route decisions, CLI stability, and scorecards. Task 6 implements active doc alignment. Task 7 verifies and checkpoints.
- Forbidden-marker scan: clear.
- Type consistency: command names, artifact paths, `decision_mode`, `recommended_next_commands`, `unresolved`, `blocked`, and `routing-quality-scorecard.yaml` are used consistently across tasks.
- Scope check: the plan is evidence-only. It does not add provider execution, autonomous worker dispatch, verification ownership, promotion, commits outside explicit checkpoints, pushes, pull requests, memory, RAG, embeddings, or training.
