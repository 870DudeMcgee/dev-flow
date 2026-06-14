# Milestone 16 Agent Registry Runtime Hardening Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make existing shell, manual, local patch, and read-only local model worker paths resolve through one permissioned registry runtime contract with role-scoped context-pack evidence.

**Architecture:** Add derived runtime, context-pack, and evidence-summary modules under `src/devflow/control_room/`. Wire existing CLI/worker paths to those projections for consistent eligibility, refusal, and evidence visibility while keeping verification and promotion in existing Dev-Flow commands.

**Tech Stack:** Python 3, Typer CLI, Pydantic/dataclasses, pytest, Markdown docs.

---

### Task 1: Runtime Projection Module

**Files:**
- Create: `src/devflow/control_room/agent_runtime.py`
- Create: `tests/test_agent_runtime.py`
- Modify: `src/devflow/control_room/worker_adapter.py`

- [ ] **Step 1: Write runtime projection tests**

Create `tests/test_agent_runtime.py` with tests for stable shell/manual, local patch, read-only local worker-pool, and remote experimental profiles:

```python
from pathlib import Path

from devflow.control_room.agent_registry import AgentDefinition, ProviderDefinition, load_agent_registry
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
        "    role: implementation_worker\n"
        "    tier: frontier\n"
        "    default_mode: workspace_write\n"
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
```

- [ ] **Step 2: Run red tests**

Run:

```bash
PYTHONPATH=src:. .venv/bin/python -m pytest tests/test_agent_runtime.py -q
```

Expected: fail with `ModuleNotFoundError: No module named 'devflow.control_room.agent_runtime'`.

- [ ] **Step 3: Implement `agent_runtime.py`**

Create `src/devflow/control_room/agent_runtime.py` with this initial shape:

```python
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from devflow.control_room.agent_registry import (
    AgentDefinition,
    ProviderDefinition,
    adapter_execution_refusal,
    is_executable_agent_runtime,
    is_local_model_worker_pool_agent,
    is_local_patch_runtime_agent,
    load_agent_registry,
    load_provider_registry,
)


@dataclass(frozen=True)
class EvidenceContract:
    required_outputs: list[str] = field(default_factory=list)
    optional_outputs: list[str] = field(default_factory=list)
    forbidden_outputs: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class ResolvedAgentRuntime:
    agent_id: str
    provider_id: str
    provider: str
    adapter: str
    adapter_maturity: str
    permission_mode: str
    execution_surface: str
    task_run_allowed: bool
    agent_run_allowed: bool
    packet_allowed: bool
    remote_provider: bool
    network_allowed: bool
    can_promote: bool
    refusal_reason: str | None
    next_command: str | None
    evidence_contract: EvidenceContract


LOCAL_PROVIDERS = {"shell", "manual", "ollama"}


def resolve_agent_runtime(root: Path, agent_id: str) -> ResolvedAgentRuntime:
    agent = load_agent_registry(root).require_agent(agent_id)
    provider = _provider_for(root, agent)
    return resolve_agent_runtime_definition(agent, provider)


def resolve_agent_runtime_definition(
    agent: AgentDefinition,
    provider: ProviderDefinition | None = None,
) -> ResolvedAgentRuntime:
    remote_provider = agent.provider not in LOCAL_PROVIDERS
    if is_local_model_worker_pool_agent(agent, provider=provider):
        surface = "agent_run"
        task_run_allowed = False
        agent_run_allowed = True
        refusal = (
            f"Agent '{agent.id}' is a read-only local model worker-pool profile. "
            "Run it with 'devflow agent run --task <task-id> --profile <profile-id>', not task worker adapter execution."
        )
        next_command = f"devflow agent run --task <task-id> --profile {agent.id} --json"
    elif is_executable_agent_runtime(agent, provider=provider):
        surface = "task_run"
        task_run_allowed = True
        agent_run_allowed = False
        refusal = None
        next_command = f"devflow task run <task-id> --worker {agent.id}"
    else:
        surface = "blocked"
        task_run_allowed = False
        agent_run_allowed = False
        refusal = adapter_execution_refusal(agent.adapter, agent_id=agent.id)
        next_command = None

    return ResolvedAgentRuntime(
        agent_id=agent.id,
        provider_id=agent.provider,
        provider=provider.provider if provider else agent.provider,
        adapter=agent.adapter,
        adapter_maturity=agent.adapter_maturity or "planned_not_executable",
        permission_mode=agent.default_mode,
        execution_surface=surface,
        task_run_allowed=task_run_allowed,
        agent_run_allowed=agent_run_allowed,
        packet_allowed=agent.default_mode in {"manual_packet_only", "read_only", "docs_only"} or task_run_allowed,
        remote_provider=remote_provider,
        network_allowed=agent.can_use_network,
        can_promote=agent.can_promote,
        refusal_reason=refusal,
        next_command=next_command,
        evidence_contract=EvidenceContract(
            required_outputs=list(agent.required_outputs),
            optional_outputs=list(agent.allowed_writes),
            forbidden_outputs=list(agent.forbidden_writes or agent.cannot_touch),
        ),
    )


def _provider_for(root: Path, agent: AgentDefinition) -> ProviderDefinition | None:
    try:
        return load_provider_registry(root).providers.get(agent.provider)
    except Exception:
        return None
```

Keep the public names in this snippet unless an existing imported symbol has a different name in `agent_registry.py`; if a name differs, use the existing symbol and update the tests in this task to match that existing API.

- [ ] **Step 4: Wire `worker_adapter.py` to projection**

In `get_worker_adapter`, replace duplicated local-model/eligibility checks with `resolve_agent_runtime_definition(agent, provider)`. Keep the public behavior identical except for more consistent refusal messages.

- [ ] **Step 5: Run green tests**

Run:

```bash
PYTHONPATH=src:. .venv/bin/python -m pytest tests/test_agent_runtime.py tests/test_worker_adapter_safety.py -q
```

Expected: pass.

- [ ] **Step 6: Commit**

Use Dev-Flow checkpoint after focused tests pass:

```bash
PYTHONPATH=src:. .venv/bin/devflow git checkpoint --message "feat: add agent runtime projection" --yes
```

### Task 2: Context Pack Evidence

**Files:**
- Create: `src/devflow/control_room/context_pack.py`
- Create: `tests/test_context_pack.py`
- Modify: `src/devflow/cli.py`
- Modify: `tests/test_agent_registry.py`

- [ ] **Step 1: Write context-pack tests**

Create `tests/test_context_pack.py`:

```python
import json
from pathlib import Path

from typer.testing import CliRunner

from devflow.cli import app
from devflow.control_room.context_pack import build_context_pack, write_context_pack
from devflow.control_room.service import create_task


runner = CliRunner()


def test_build_context_pack_is_role_scoped_and_derived(tmp_path: Path) -> None:
    task = create_task(tmp_path, "Implement context pack")

    pack = build_context_pack(
        tmp_path,
        task.id,
        agent_id="qwopus-implementer",
        role="implementation_worker",
    )

    assert pack.task_id == task.id
    assert pack.agent_id == "qwopus-implementer"
    assert pack.role == "implementation_worker"
    assert pack.source_packet_path == f".devflow/tasks/{task.id}/context-packs/implementation_worker-qwopus-implementer.packet.json"
    assert "<task>/task.yaml" in pack.included_sources
    assert ".env" in "\n".join(pack.excluded_sources)
    assert pack.estimated_chars > 0
    assert pack.estimated_tokens >= 1


def test_write_context_pack_writes_json_and_markdown_without_mutating_task(tmp_path: Path) -> None:
    task = create_task(tmp_path, "Write context pack")
    before = (tmp_path / ".devflow" / "tasks" / task.id / "task.yaml").read_text(encoding="utf-8")

    result = write_context_pack(
        tmp_path,
        task.id,
        agent_id="qwopus-implementer",
        role="reviewer",
    )

    assert result.json_path.is_file()
    assert result.markdown_path.is_file()
    payload = json.loads(result.json_path.read_text(encoding="utf-8"))
    assert payload["role"] == "reviewer"
    assert payload["agent_id"] == "qwopus-implementer"
    assert (tmp_path / ".devflow" / "tasks" / task.id / "task.yaml").read_text(encoding="utf-8") == before


def test_agent_context_pack_cli_writes_paths(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    assert runner.invoke(app, ["task", "create", "Context CLI"]).exit_code == 0

    result = runner.invoke(
        app,
        ["agent", "context-pack", "task-0001", "qwopus-implementer", "--role", "implementation_worker", "--json"],
    )

    assert result.exit_code == 0, result.output
    payload = json.loads(result.output)
    assert payload["task_id"] == "task-0001"
    assert payload["agent_id"] == "qwopus-implementer"
    assert payload["json_path"].endswith("implementation_worker-qwopus-implementer.json")
```

- [ ] **Step 2: Run red tests**

Run:

```bash
PYTHONPATH=src:. .venv/bin/python -m pytest tests/test_context_pack.py -q
```

Expected: fail because `context_pack.py` and `agent context-pack` do not exist.

- [ ] **Step 3: Implement context-pack builder**

Create `src/devflow/control_room/context_pack.py` with a dataclass or Pydantic model that:

- calls `build_agent_packet(task_id, agent, root=root)`
- derives included sources from `allowed_artifacts`, logs, verification, and task fields
- excludes `.env*`, `.git/**`, main checkout globs, and forbidden writes
- estimates tokens as `max(1, estimated_chars // 4)`
- writes JSON and markdown with atomic writes

Use existing `persistence.atomic_write_text` for writes.

Minimum implementation shape:

```python
from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from pathlib import Path

from devflow.control_room.agent_registry import load_agent_registry
from devflow.control_room.persistence import atomic_write_text, utc_now
from devflow.control_room.task_packet import build_agent_packet, render_task_packet_text


@dataclass(frozen=True)
class ContextPack:
    schema_version: int
    task_id: str
    agent_id: str
    role: str
    permission_mode: str
    source_packet_path: str
    included_sources: list[str]
    excluded_sources: list[str]
    estimated_chars: int
    estimated_tokens: int
    truncation_notes: list[str] = field(default_factory=list)
    created_at: str = ""


@dataclass(frozen=True)
class WrittenContextPack:
    pack: ContextPack
    json_path: Path
    markdown_path: Path


def build_context_pack(root: Path, task_id: str, *, agent_id: str, role: str) -> ContextPack:
    agent = load_agent_registry(root).require_agent(agent_id)
    packet = build_agent_packet(task_id, agent, root=root)
    text = render_task_packet_text(packet)
    source_packet_path = f".devflow/tasks/{task_id}/context-packs/{role}-{agent_id}.packet.json"
    included_sources = sorted(set(packet.allowed_artifacts + [packet.logs["worker"].path, packet.logs["verify"].path]))
    excluded_sources = sorted(set(agent.forbidden_writes + [".env*", ".git/**", "<main_checkout>/**"]))
    estimated_chars = len(text)
    return ContextPack(
        schema_version=1,
        task_id=task_id,
        agent_id=agent_id,
        role=role,
        permission_mode=agent.default_mode,
        source_packet_path=source_packet_path,
        included_sources=included_sources,
        excluded_sources=excluded_sources,
        estimated_chars=estimated_chars,
        estimated_tokens=max(1, estimated_chars // 4),
        truncation_notes=list(packet.truncation_notes),
        created_at=utc_now().isoformat(),
    )


def write_context_pack(root: Path, task_id: str, *, agent_id: str, role: str) -> WrittenContextPack:
    pack = build_context_pack(root, task_id, agent_id=agent_id, role=role)
    base = root / ".devflow" / "tasks" / task_id / "context-packs"
    base.mkdir(parents=True, exist_ok=True)
    json_path = base / f"{role}-{agent_id}.json"
    markdown_path = base / f"{role}-{agent_id}.md"
    atomic_write_text(json_path, json.dumps(asdict(pack), indent=2, sort_keys=True) + "\n")
    atomic_write_text(markdown_path, _render_markdown(pack))
    return WrittenContextPack(pack=pack, json_path=json_path, markdown_path=markdown_path)


def _render_markdown(pack: ContextPack) -> str:
    return (
        f"# Context Pack: {pack.task_id} / {pack.agent_id}\n\n"
        f"Role: {pack.role}\n"
        f"Permission mode: {pack.permission_mode}\n"
        f"Estimated tokens: {pack.estimated_tokens}\n\n"
        "## Included Sources\n"
        + "\n".join(f"- {source}" for source in pack.included_sources)
        + "\n\n## Excluded Sources\n"
        + "\n".join(f"- {source}" for source in pack.excluded_sources)
        + "\n"
    )
```

- [ ] **Step 4: Add CLI command**

Add an `agent context-pack <task_id> <agent_id> --role <role> --json` command in `src/devflow/cli.py`. The command should:

- load the repository root from `Path.cwd()`
- call `write_context_pack`
- print either JSON with paths and metadata or a concise text summary
- not call providers, run workers, verify, promote, or mutate canonical task state

- [ ] **Step 5: Run green tests**

Run:

```bash
PYTHONPATH=src:. .venv/bin/python -m pytest tests/test_context_pack.py tests/test_task_packet.py tests/test_agent_registry.py -q
```

Expected: pass.

- [ ] **Step 6: Commit**

```bash
PYTHONPATH=src:. .venv/bin/devflow git checkpoint --message "feat: add role context pack evidence" --yes
```

### Task 3: Agent Evidence Summary

**Files:**
- Create: `src/devflow/control_room/agent_evidence.py`
- Create: `tests/test_agent_evidence.py`
- Modify: `src/devflow/cli.py`
- Modify: `src/devflow/control_room/operating_layer.py`

- [ ] **Step 1: Write evidence-summary tests**

Create `tests/test_agent_evidence.py`:

```python
import json
from pathlib import Path

from typer.testing import CliRunner

from devflow.cli import app
from devflow.control_room.agent_evidence import summarize_agent_evidence
from devflow.control_room.service import create_task
from devflow.control_room.worker_evidence import write_worker_evidence


runner = CliRunner()


def test_summarize_agent_evidence_reports_local_model_runs(tmp_path: Path) -> None:
    task = create_task(tmp_path, "Evidence summary")
    write_worker_evidence(
        root=tmp_path,
        worker_type="local_model",
        profile_id="local-qwopus-inspector",
        worker_id="local-qwopus-inspector",
        task_id=task.id,
        run_id="run-1",
        packet_text="packet",
        raw_output="raw",
        response_text="response",
        model="qwopus",
        adapter="ollama_chat",
        adapter_maturity="local_patch_runtime",
        permission_mode="read_only",
        hermes_delegable=False,
        runtime="ollama",
        status="succeeded",
        started_at="2026-06-13T00:00:00Z",
    )

    summary = summarize_agent_evidence(tmp_path, task.id)

    assert summary.task_id == task.id
    assert summary.has_worker_evidence is True
    assert summary.local_model_runs[0].worker_id == "local-qwopus-inspector"
    assert summary.next_safe_action == "review worker evidence before verification or promotion"


def test_agent_evidence_cli_is_read_only_json(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    assert runner.invoke(app, ["task", "create", "Evidence CLI"]).exit_code == 0
    task_yaml = Path(".devflow/tasks/task-0001/task.yaml").read_text(encoding="utf-8")

    result = runner.invoke(app, ["agent", "evidence", "task-0001", "--json"])

    assert result.exit_code == 0, result.output
    payload = json.loads(result.output)
    assert payload["task_id"] == "task-0001"
    assert Path(".devflow/tasks/task-0001/task.yaml").read_text(encoding="utf-8") == task_yaml
```

- [ ] **Step 2: Run red tests**

```bash
PYTHONPATH=src:. .venv/bin/python -m pytest tests/test_agent_evidence.py -q
```

Expected: fail because `agent_evidence.py` and `agent evidence` do not exist.

- [ ] **Step 3: Implement evidence projection**

Create `src/devflow/control_room/agent_evidence.py` with derived models for:

- local model WorkerEvidence runs under `.devflow/tasks/<task_id>/local-model-runs/*/run.json`
- local patch agent evidence under `.devflow/tasks/<task_id>/agents/<agent_id>/proposal.patch`, `raw_output.md`, `run.json`, and `result.md`
- manual proof-agent evidence under `.devflow/tasks/<task_id>/agents/devflow-manual-codex-worker/`
- shell log/result evidence under existing task fields

Keep it read-only. It should never write task state.

- [ ] **Step 4: Add CLI command and operating-layer field**

Add `devflow agent evidence <task_id> --json` to `src/devflow/cli.py`. In `src/devflow/control_room/operating_layer.py`, add the derived `agent_evidence_summary` dictionary to each task payload produced for the operating-layer snapshot. Keep it compact:

```python
{
    "has_worker_evidence": summary.has_worker_evidence,
    "local_model_run_count": len(summary.local_model_runs),
    "local_patch_agent_count": len(summary.local_patch_agents),
    "manual_result_present": summary.manual_result_present,
    "next_safe_action": summary.next_safe_action,
}
```

Do not expand the browser UI in this task.

- [ ] **Step 5: Run green tests**

```bash
PYTHONPATH=src:. .venv/bin/python -m pytest tests/test_agent_evidence.py tests/test_operating_layer.py -q
```

Expected: pass.

- [ ] **Step 6: Commit**

```bash
PYTHONPATH=src:. .venv/bin/devflow git checkpoint --message "feat: summarize agent evidence" --yes
```

### Task 4: Wire Runtime Projection Into Existing Refusals

**Files:**
- Modify: `src/devflow/control_room/local_model_worker_pool.py`
- Modify: `src/devflow/control_room/service.py`
- Modify: `tests/test_agent_local_worker_pool_cli.py`
- Modify: `tests/test_ollama_worker.py`
- Modify: `tests/test_worker_adapter_safety.py`

- [ ] **Step 1: Add focused refusal tests**

Add or update tests with this concrete coverage:

```python
def test_task_run_read_only_local_profile_reports_agent_run_next_action(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    assert runner.invoke(app, ["task", "create", "Read-only profile misuse"]).exit_code == 0

    result = runner.invoke(app, ["task", "run", "task-0001", "--worker", "local-qwopus-inspector"])

    assert result.exit_code != 0
    assert "read-only local model worker-pool profile" in result.output
    assert "devflow agent run --task <task-id> --profile local-qwopus-inspector" in result.output


def test_task_run_remote_provider_agent_still_fails_closed(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    assert runner.invoke(app, ["task", "create", "Remote refusal"]).exit_code == 0

    result = runner.invoke(app, ["task", "run", "task-0001", "--worker", "devflow-openai-worker"])

    assert result.exit_code != 0
    assert "cannot execute" in result.output
    assert "experimental_readonly" in result.output
```

Keep or add existing assertions that:

- `task run --worker local-qwopus-inspector` refuses with the `agent run` next command
- remote provider-backed agents still refuse task-run execution
- `qwopus-implementer` remains allowed as local patch runtime
- local worker-pool profiles still write WorkerEvidence through `agent run`

- [ ] **Step 2: Run red or characterization tests**

```bash
PYTHONPATH=src:. .venv/bin/python -m pytest tests/test_worker_adapter_safety.py tests/test_agent_local_worker_pool_cli.py tests/test_ollama_worker.py -q
```

Expected: current behavior may pass partially, but at least one assertion should fail if refusal text is not yet centralized.

- [ ] **Step 3: Use runtime projection in worker paths**

In `service.py`, `worker_adapter.py`, and `local_model_worker_pool.py`, use `resolve_agent_runtime` or `resolve_agent_runtime_definition` for:

- task-run eligibility
- agent-run eligibility
- refusal text
- next command text
- evidence contract metadata where available

Do not change provider execution maturity.

- [ ] **Step 4: Run green tests**

```bash
PYTHONPATH=src:. .venv/bin/python -m pytest tests/test_worker_adapter_safety.py tests/test_agent_local_worker_pool_cli.py tests/test_ollama_worker.py -q
```

Expected: pass.

- [ ] **Step 5: Commit**

```bash
PYTHONPATH=src:. .venv/bin/devflow git checkpoint --message "refactor: centralize agent runtime refusals" --yes
```

### Task 5: Paused Local Patch Runtime Dogfood

**Status:** Paused after dogfood exposed that the configured local patch worker can point at a model that is not installed on the current machine.

Do not continue the local patch runtime ladder by hard-coding `qwopus:latest`, `gemma4:12b-it-qat`, or any other single model as the universal default. Dev-Flow must support replaceable local agents. The next implementation slice is local agent discovery and deterministic classification, then dogfood can run against an explicitly selected eligible local patch agent.

**Observed evidence from the paused run:**
- `task-0033` was created for "Milestone 16 local patch runtime dogfood".
- `devflow task run task-0033 --worker qwopus-implementer` failed because `qwopus:latest` was not installed locally.
- `ollama list` showed `gemma4:12b-it-qat` installed on this machine.
- The dogfood task was closed `evidence-only` because no proposal patch was produced.

### Task 5A: Local Agent Discovery And Classification Design Slice

**Files:**
- Create: `src/devflow/control_room/local_agent_discovery.py`
- Create: `tests/test_local_agent_discovery.py`
- Modify: `src/devflow/cli.py`
- Modify: `docs/architecture/local-model-worker-pool.md`
- Modify: `docs/architecture/agent-selection-and-context-routing.md`
- Modify: `docs/control-room-mvp.md`

**Goal:** Add a small, deterministic local-agent discovery and selection-evidence slice before running provider-backed local patch workers. This slice must inventory local Ollama models, classify capability from local manifests and conservative built-in heuristics, rank eligible local agents for a requested role, and write explicit selected-agent evidence before `task run` uses any local model.

**Non-goals:**
- No autonomous routing.
- No hidden model fallback inside `task run`.
- No remote provider calls.
- No benchmark harness or heavy profiling.
- No automatic source edits, verification, promotion, merge, or push.
- No claim that a discovered model is safe for a role without manifest evidence and policy classification.

- [ ] **Step 1: Write discovery tests**

Create `tests/test_local_agent_discovery.py` with focused tests for:

- parsing `ollama list` output into installed local model records
- parsing `ollama show <model>` manifest facts into a capability profile
- classifying `gemma4:12b-it-qat` as an installed local Gemma 4 12B QAT model with conservative roles such as `summarizer`, `reviewer`, `bounded_worker`, and `patch_proposer_candidate`
- ranking eligible local agents for `implementation_worker` without selecting missing models
- writing selected-agent evidence under `.devflow/tasks/<task_id>/agent-selection.json`
- refusing to auto-select when no installed candidate satisfies the requested role

- [ ] **Step 2: Run red tests**

Run:

```bash
PYTHONPATH=src:. .venv/bin/python -m pytest tests/test_local_agent_discovery.py -q
```

Expected: fail because `devflow.control_room.local_agent_discovery` does not exist yet.

- [ ] **Step 3: Implement deterministic discovery module**

Create `src/devflow/control_room/local_agent_discovery.py` with:

- `parse_ollama_list(text: str) -> list[InstalledLocalModel]`
- `parse_ollama_show(model: str, text: str) -> LocalModelManifest`
- `classify_local_model(manifest: LocalModelManifest) -> ModelCapabilityProfile`
- `rank_local_agent_candidates(registry, installed_models, role: str) -> LocalAgentSelection`
- `write_selected_agent_evidence(root, task_id, selection) -> Path`

Keep classification deterministic and conservative. Prefer actual `ollama show` facts over public model-name assumptions. Treat unknown or partial manifests as lower trust. Missing models must not rank as eligible for execution.

- [ ] **Step 4: Add explicit CLI surface**

Add read-mostly commands:

```bash
PYTHONPATH=src:. .venv/bin/devflow agent discover-local --json
PYTHONPATH=src:. .venv/bin/devflow agent select-local <task_id> --role implementation_worker --json
```

`discover-local` may call local Ollama only. `select-local` writes selection evidence only; it must not run a worker. The output must include installed models, missing registry models, classification, ranked candidates, selected agent if exactly one is policy-eligible, and refusal reasons for rejected candidates.

- [ ] **Step 5: Wire dogfood to explicit selection evidence**

Update the local patch dogfood instructions to run:

```bash
PYTHONPATH=src:. .venv/bin/devflow agent discover-local --json
PYTHONPATH=src:. .venv/bin/devflow agent select-local <task_id> --role implementation_worker --json
```

Then run `devflow task run` only with the selected local patch agent from `.devflow/tasks/<task_id>/agent-selection.json`. Do not let `task run` silently choose a different model if the selected model is unavailable.

- [ ] **Step 6: Run focused verification**

Run:

```bash
PYTHONPATH=src:. .venv/bin/python -m pytest tests/test_local_agent_discovery.py tests/test_agent_registry.py tests/test_agent_runtime.py tests/test_ollama_worker.py -q
```

Expected: pass.

- [ ] **Step 7: Checkpoint**

Use Dev-Flow checkpoint after focused tests pass:

```bash
PYTHONPATH=src:. .venv/bin/devflow git checkpoint --message "feat: add local agent discovery selection" --yes
```

### Task 5B: Dogfood Local Patch Runtime Ladder

**Files:**
- Modify: docs only if dogfood exposes stale wording
- Evidence: `.devflow/tasks/<task_id>/...`

- [ ] **Step 1: Create a small docs-only task**

```bash
PYTHONPATH=src:. .venv/bin/devflow task create "Milestone 16 local patch runtime dogfood"
```

Expected: creates the next local task id.

- [ ] **Step 2: Run local patch proposal only if local Ollama is available**

First discover and select an eligible local implementation worker:

```bash
PYTHONPATH=src:. .venv/bin/devflow agent discover-local --json
PYTHONPATH=src:. .venv/bin/devflow agent select-local <task_id> --role implementation_worker --json
```

Continue only if selection evidence identifies an installed eligible local patch agent. Then run the selected worker explicitly:

```bash
PYTHONPATH=src:. .venv/bin/devflow task run <task_id> --worker <selected-agent-id>
```

Expected when a selected local patch agent is available: writes `.devflow/tasks/<task_id>/agents/<selected-agent-id>/proposal.patch`, `raw_output.md`, `result.md`, `run.json`, and `logs/worker.log`.

Expected when no eligible installed local patch agent is available: selection records a clear refusal. In that case, do not fake model evidence; stop and document the blocker.

- [ ] **Step 3: Review, dry-run, apply, verify**

Run these only if Step 2 produced a proposal patch:

```bash
PYTHONPATH=src:. .venv/bin/devflow task review-patch <task_id> --agent <selected-agent-id>
PYTHONPATH=src:. .venv/bin/devflow task patch-dry-run <task_id> --agent <selected-agent-id>
PYTHONPATH=src:. .venv/bin/devflow task apply-patch <task_id> --agent <selected-agent-id>
PYTHONPATH=src:. .venv/bin/devflow task verify <task_id> --shell "<focused verification command>"
PYTHONPATH=src:. .venv/bin/devflow task review-ready <task_id> --json
```

Expected: each command preserves explicit evidence and does not promote automatically.

- [ ] **Step 4: Capture dogfood result**

Record the dogfood command outputs in the final handoff. If the dogfood task is evidence-only or rejected, close it explicitly with an outcome and reason.

**Task 5B update, 2026-06-14:** `task-0035` selected `gemma4-12b-qat-implementer` after the explicit registry entry was added, but the existing generic Ollama patch worker emitted only `{"` and stopped with `done_reason: length`, `prompt_eval_count: 4095`, and `eval_count: 1`. Direct probes proved `gemma4:12b-it-qat` returns valid JSON when `num_ctx` and `num_predict` are explicit. Resume Task 5B only after completing `docs/superpowers/plans/2026-06-14-gemma-native-patch-output-reliability.md`.

### Task 6: Docs And Final Verification

**Files:**
- Modify: `docs/roadmap.md`
- Modify: `docs/control-room-mvp.md`
- Modify: `docs/mvp-contract.md`
- Modify: `docs/architecture/agent-registry-and-adapter-runtime.md`
- Create or modify: `docs/handoffs/<date>-milestone-16-agent-registry-runtime-complete.md`

- [x] **Step 1: Align docs with implemented behavior**

Update active docs to say exactly which Milestone 16 surfaces are now current behavior and which remain deferred. Keep remote providers, autonomous routing, provider-backed worktrees, PR automation, databases, and memory out of stable runtime.

- [x] **Step 2: Run focused tests**

```bash
PYTHONPATH=src:. .venv/bin/python -m pytest tests/test_agent_runtime.py tests/test_context_pack.py tests/test_agent_evidence.py tests/test_worker_adapter_safety.py tests/test_agent_local_worker_pool_cli.py tests/test_local_agent_discovery.py tests/test_ollama_worker.py tests/test_task_packet.py -q
```

Expected: pass.

- [x] **Step 3: Run broader release check**

```bash
./scripts/release-check.sh
```

Expected: pass on a clean tree after checkpointing any dirty work.

- [x] **Step 4: Stale-context scan**

```bash
rg -n "Milestone 15.*next planned|multi-project control room hardening.*next planned|agent registry.*future-only|remote provider.*stable runtime|autonomous routing.*current" README.md PRODUCT_NORTH_STAR.md CODE_MAP.md docs/control-room-mvp.md docs/mvp-contract.md docs/roadmap.md docs/architecture docs/handoffs
```

Expected: no active-doc matches claiming Milestone 15 is still the next planned slice or remote/autonomous provider behavior is stable. Historical specs/plans may match only when clearly historical.

- [x] **Step 5: Final status and push**

```bash
PYTHONPATH=src:. .venv/bin/devflow git status
PYTHONPATH=src:. .venv/bin/devflow git checkpoint --message "feat: harden agent registry runtime" --yes
PYTHONPATH=src:. .venv/bin/devflow push-main
```

Expected: clean synced `main` after explicit human approval for push.
