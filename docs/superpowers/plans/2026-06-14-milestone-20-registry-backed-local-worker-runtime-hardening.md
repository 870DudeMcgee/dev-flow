# Milestone 20 Registry-Backed Local Worker Runtime Hardening Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a read-only local worker lane projection and surface it consistently across CLI, supervisor, operating-layer, and dogfood without enabling provider-backed execution or autonomous routing.

**Architecture:** Add one derived read model for local worker evidence, then route all user-facing surfaces through that vocabulary. Keep mutation in existing explicit commands: local worker run, patch review, patch dry-run, patch apply, task verify, promote-preview, and human promotion.

**Tech Stack:** Python, Typer CLI, Pydantic operating-layer models, filesystem JSON/Markdown evidence, pytest, existing Dev-Flow dogfood harness.

---

## File Structure

- Create `src/devflow/control_room/local_worker_lane.py`: read-only projection over local worker evidence.
- Modify `src/devflow/cli.py`: print local worker lane fields in `task show`, `task review-ready`, and `agent evidence` output where appropriate.
- Modify `src/devflow/control_room/review_readiness.py`: include local worker lane fields and evidence paths.
- Modify `src/devflow/control_room/supervisor_surface.py`: include `local_worker_lane` in task records and supervisor packets.
- Modify `src/devflow/control_room/operating_layer.py`: add local worker lane model to snapshots and task detail summaries.
- Modify `src/devflow/control_room/operating_layer_script.py`: render compact local worker lane block in the selected task panel.
- Modify `src/devflow/control_room/operating_layer_styles.py`: style the local worker lane block.
- Modify `src/devflow/control_room/dogfood.py`: add deterministic production-readiness dogfood case.
- Test with `tests/test_local_worker_lane.py`, `tests/test_supervisor_operating_surface.py`, `tests/test_operating_layer.py`, `tests/test_dogfood_harness.py`, and existing local worker tests.
- Update active docs and add final handoff after implementation.

## Task 1: Add Local Worker Lane Read Model

**Files:**
- Create: `src/devflow/control_room/local_worker_lane.py`
- Create: `tests/test_local_worker_lane.py`

- [ ] **Step 1: Write failing tests for read-only patch-worker summary**

Add `tests/test_local_worker_lane.py`:

```python
from __future__ import annotations

import json
from pathlib import Path

from devflow.control_room.local_worker_lane import local_worker_lane_summary
from devflow.control_room.persistence import TaskRecord


def _task(task_id: str = "task-0001") -> TaskRecord:
    return TaskRecord(
        id=task_id,
        title="local worker lane",
        status="new",
        worker="shell",
        workspace=f".devflow/workspaces/{task_id}",
        workspace_path=f".devflow/workspaces/{task_id}",
    )


def _write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def test_local_worker_lane_summary_reports_patch_worker_next_action(tmp_path: Path) -> None:
    task = _task()
    agent_dir = tmp_path / ".devflow/tasks/task-0001/agents/qwopus-implementer"
    _write_json(
        agent_dir / "run.json",
        {
            "schema_version": 1,
            "task_id": "task-0001",
            "agent_id": "qwopus-implementer",
            "status": "complete",
            "model": "qwopus:latest",
            "adapter": "ollama_chat",
            "proposal_patch_found": True,
            "proposal_patch_path": ".devflow/tasks/task-0001/agents/qwopus-implementer/proposal.patch",
            "proposal_patch_byte_length": 42,
            "proposed_file_count": 1,
            "proposed_file_paths": ["hello.txt"],
        },
    )
    (agent_dir / "proposal.patch").write_text("diff --git a/hello.txt b/hello.txt\n", encoding="utf-8")
    (agent_dir / "result.md").write_text("Patch proposed\n", encoding="utf-8")
    (agent_dir / "logs").mkdir(parents=True, exist_ok=True)
    (agent_dir / "logs/worker.log").write_text("ok\n", encoding="utf-8")

    summary = local_worker_lane_summary(tmp_path, task)

    assert summary is not None
    assert summary["lane_type"] == "local-patch-worker"
    assert summary["worker_id"] == "qwopus-implementer"
    assert summary["latest_status"] == "complete"
    assert summary["patch_candidate"] is True
    assert summary["readiness_status"] == "needs_review"
    assert summary["next_safe_action"] == "devflow task review-patch task-0001 --agent qwopus-implementer"
    assert ".devflow/tasks/task-0001/agents/qwopus-implementer/run.json" in summary["evidence_paths"]
```

- [ ] **Step 2: Run test to verify it fails**

Run:

```bash
PYTHONPATH=src:. .venv/bin/python -m pytest tests/test_local_worker_lane.py::test_local_worker_lane_summary_reports_patch_worker_next_action -q
```

Expected: fail with `ModuleNotFoundError` or missing `local_worker_lane_summary`.

- [ ] **Step 3: Implement minimal read model**

Create `src/devflow/control_room/local_worker_lane.py`:

```python
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from devflow.control_room.models import TaskRecord
from devflow.control_room.paths import relative_path, task_dir


PATCH_WORKER_NEXT_ACTIONS = {
    "needs_review": "devflow task review-patch {task_id} --agent {worker_id}",
    "needs_dry_run": "devflow task patch-dry-run {task_id} --agent {worker_id}",
    "needs_apply": "devflow task apply-patch {task_id} --agent {worker_id}",
    "needs_verification": 'devflow task verify {task_id} --shell "<command>"',
    "needs_promotion_preview": "devflow task promote-preview {task_id}",
    "ready": "devflow task promote {task_id}",
    "failed": "devflow task escalation-packet {task_id} --agent {worker_id}",
}


def local_worker_lane_summary(root: Path, task: TaskRecord, worker_id: str | None = None) -> dict[str, Any] | None:
    base = task_dir(root, task.id)
    patch_summary = _latest_patch_worker_summary(root, base, task, worker_id)
    pool_summary = _latest_worker_pool_summary(root, base, task, worker_id)
    if patch_summary and pool_summary:
        return patch_summary if patch_summary["generated_at_sort"] >= pool_summary["generated_at_sort"] else pool_summary
    return patch_summary or pool_summary


def _latest_patch_worker_summary(root: Path, base: Path, task: TaskRecord, worker_id: str | None) -> dict[str, Any] | None:
    agents_dir = base / "agents"
    if not agents_dir.is_dir():
        return None
    candidates = [agents_dir / worker_id] if worker_id else sorted(path for path in agents_dir.iterdir() if path.is_dir())
    runs: list[tuple[str, Path, dict[str, Any]]] = []
    for run_dir in candidates:
        run_json = _read_json_object(run_dir / "run.json")
        if run_json:
            runs.append((_sort_value(run_json), run_dir, run_json))
    if not runs:
        return None
    _, run_dir, run_json = sorted(runs, key=lambda item: item[0])[-1]
    resolved_worker = str(run_json.get("agent_id") or run_json.get("worker_id") or run_dir.name)
    readiness = _patch_readiness(base, task, run_dir, run_json)
    evidence_paths = _existing_paths(
        root,
        [
            run_dir / "run.json",
            run_dir / "proposal.patch",
            run_dir / "result.md",
            run_dir / "logs" / "worker.log",
            base / "local-model-runs",
            base / "patch-application.json",
            base / "verification.json",
            run_dir / "escalation-packet.md",
        ],
    )
    return {
        "schema": 1,
        "task_id": task.id,
        "lane_type": "local-patch-worker",
        "profile_id": resolved_worker,
        "worker_id": resolved_worker,
        "model": run_json.get("model"),
        "adapter": run_json.get("adapter"),
        "permission_mode": "workspace_write",
        "latest_run_id": run_dir.name,
        "latest_status": str(run_json.get("status") or "unknown"),
        "patch_candidate": bool(run_json.get("proposal_patch_found") and (run_dir / "proposal.patch").exists()),
        "patch_review_status": readiness.get("patch_review_status"),
        "patch_dry_run_status": readiness.get("patch_dry_run_status"),
        "patch_application_status": readiness.get("patch_application_status"),
        "verification_status": task.verification_status,
        "promotion_readiness": readiness.get("promotion_readiness"),
        "readiness_status": readiness["status"],
        "readiness_errors": readiness["errors"],
        "readiness_warnings": readiness["warnings"],
        "evidence_paths": evidence_paths,
        "next_safe_action": _next_action(task.id, resolved_worker, readiness["status"]),
        "generated_at_sort": _sort_value(run_json),
    }


def _latest_worker_pool_summary(root: Path, base: Path, task: TaskRecord, worker_id: str | None) -> dict[str, Any] | None:
    runs_dir = base / "local-model-runs"
    if not runs_dir.is_dir():
        return None
    candidates = sorted(path for path in runs_dir.iterdir() if path.is_dir())
    runs: list[tuple[str, Path, dict[str, Any]]] = []
    for run_dir in candidates:
        run_json = _read_json_object(run_dir / "run.json")
        if run_json and (worker_id is None or run_json.get("worker_id") == worker_id or run_json.get("profile_id") == worker_id):
            runs.append((_sort_value(run_json), run_dir, run_json))
    if not runs:
        return None
    _, run_dir, run_json = sorted(runs, key=lambda item: item[0])[-1]
    status = str(run_json.get("status") or "unknown")
    readiness = "failed" if status == "failed" else "low_quality" if status == "low_quality" else "needs_review"
    resolved_worker = str(run_json.get("worker_id") or run_json.get("profile_id") or run_dir.name)
    return {
        "schema": 1,
        "task_id": task.id,
        "lane_type": "local-model-worker-pool",
        "profile_id": run_json.get("profile_id"),
        "worker_id": resolved_worker,
        "model": run_json.get("model"),
        "adapter": run_json.get("adapter"),
        "permission_mode": run_json.get("permission_mode") or "read_only",
        "latest_run_id": run_dir.name,
        "latest_status": status,
        "patch_candidate": False,
        "patch_review_status": None,
        "patch_dry_run_status": None,
        "patch_application_status": None,
        "verification_status": task.verification_status,
        "promotion_readiness": None,
        "readiness_status": readiness,
        "readiness_errors": [str(run_json.get("error_message") or "local worker failed")] if status == "failed" else [],
        "readiness_warnings": [str(run_json.get("quality_notes") or "local worker output is low quality")] if status == "low_quality" else [],
        "evidence_paths": _existing_paths(
            root,
            [
                run_dir / "run.json",
                run_dir / "packet.md",
                run_dir / "response.md",
                run_dir / "raw_output.txt",
                run_dir / "error.txt",
            ],
        ),
        "next_safe_action": "devflow agent evidence {task_id} --json".format(task_id=task.id),
        "generated_at_sort": _sort_value(run_json),
    }


def _patch_readiness(base: Path, task: TaskRecord, run_dir: Path, run_json: dict[str, Any]) -> dict[str, Any]:
    errors: list[str] = []
    warnings: list[str] = []
    if run_json.get("status") in {"failed", "error"}:
        return {"status": "failed", "errors": [str(run_json.get("summary") or "local patch worker failed")], "warnings": warnings}
    if not (run_json.get("proposal_patch_found") and (run_dir / "proposal.patch").exists()):
        return {"status": "failed", "errors": ["proposal.patch is missing"], "warnings": warnings}
    review = _latest_json(base / "local-model-runs", "patch-review.json")
    if not review:
        return {"status": "needs_review", "errors": errors, "warnings": warnings}
    dry_run = _latest_json(base / "local-model-runs", "patch-dry-run.json")
    if not dry_run:
        return {"status": "needs_dry_run", "errors": errors, "warnings": warnings, "patch_review_status": review.get("review_status")}
    application = _read_json_object(base / "patch-application.json")
    if not application:
        return {
            "status": "needs_apply",
            "errors": errors,
            "warnings": warnings,
            "patch_review_status": review.get("review_status"),
            "patch_dry_run_status": dry_run.get("dry_run_status"),
        }
    if task.verification_status != "passed":
        return {
            "status": "needs_verification",
            "errors": errors,
            "warnings": warnings,
            "patch_review_status": review.get("review_status"),
            "patch_dry_run_status": dry_run.get("dry_run_status"),
            "patch_application_status": application.get("status") or application.get("application_status"),
        }
    promotion = _read_json_object(base / "promotion-preview.json")
    promotion_readiness = promotion.get("promotion_readiness") if promotion else None
    status = "ready" if promotion_readiness == "ready" else "needs_promotion_preview"
    return {
        "status": status,
        "errors": errors,
        "warnings": warnings,
        "patch_review_status": review.get("review_status"),
        "patch_dry_run_status": dry_run.get("dry_run_status"),
        "patch_application_status": application.get("status") or application.get("application_status"),
        "promotion_readiness": promotion_readiness,
    }


def _next_action(task_id: str, worker_id: str, status: str) -> str:
    return PATCH_WORKER_NEXT_ACTIONS.get(status, "devflow task show {task_id}").format(task_id=task_id, worker_id=worker_id)


def _read_json_object(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return payload if isinstance(payload, dict) else {}


def _latest_json(parent: Path, name: str) -> dict[str, Any]:
    if not parent.is_dir():
        return {}
    matches = sorted(path for path in parent.glob(f"*/{name}") if path.is_file())
    return _read_json_object(matches[-1]) if matches else {}


def _existing_paths(root: Path, paths: list[Path]) -> list[str]:
    found: list[str] = []
    for path in paths:
        if path.is_file():
            found.append(relative_path(root, path))
        elif path.is_dir():
            found.extend(relative_path(root, child) for child in sorted(path.rglob("*")) if child.is_file())
    return sorted(dict.fromkeys(found))


def _sort_value(payload: dict[str, Any]) -> str:
    return str(payload.get("finished_at") or payload.get("updated_at") or payload.get("started_at") or payload.get("run_id") or "")
```

- [ ] **Step 4: Run the first test**

Run:

```bash
PYTHONPATH=src:. .venv/bin/python -m pytest tests/test_local_worker_lane.py -q
```

Expected: pass for the first test. If `TaskRecord` import differs, use the same import pattern as nearby tests that construct task records.

- [ ] **Step 5: Add read-only WorkerEvidence tests**

Append:

```python
from devflow.control_room.worker_evidence import write_worker_evidence


def test_local_worker_lane_summary_reports_read_only_worker_pool_run(tmp_path: Path) -> None:
    task = _task()
    write_worker_evidence(
        root=tmp_path,
        worker_type="local_model_worker_pool",
        profile_id="local-qwopus-inspector",
        worker_id="local-qwopus-inspector",
        task_id="task-0001",
        run_id="run-1",
        packet_text="packet",
        raw_output="raw",
        response_text="response",
        model="qwopus:latest",
        adapter="ollama_chat",
        adapter_maturity="local_patch_runtime",
        permission_mode="read_only",
        hermes_delegable=True,
        runtime="local_model_client",
        status="success",
        started_at="2026-06-14T00:00:00+00:00",
        quality_notes="useful",
        quality_score=0.85,
    )

    summary = local_worker_lane_summary(tmp_path, task)

    assert summary is not None
    assert summary["lane_type"] == "local-model-worker-pool"
    assert summary["worker_id"] == "local-qwopus-inspector"
    assert summary["permission_mode"] == "read_only"
    assert summary["patch_candidate"] is False
    assert summary["readiness_status"] == "needs_review"
    assert summary["next_safe_action"] == "devflow agent evidence task-0001 --json"
    assert ".devflow/tasks/task-0001/local-model-runs/run-1/run.json" in summary["evidence_paths"]
```

- [ ] **Step 6: Run read model tests**

Run:

```bash
PYTHONPATH=src:. .venv/bin/python -m pytest tests/test_local_worker_lane.py -q
```

Expected: all tests in `tests/test_local_worker_lane.py` pass.

- [ ] **Step 7: Commit**

Use Dev-Flow checkpoint:

```bash
PYTHONPATH=src:. .venv/bin/devflow git checkpoint -m "feat(devflow): add local worker lane summary" --yes
```

Expected: checkpoint commit created on the task branch used by the implementing agent.

## Task 2: Surface Local Worker Lane In CLI And Review Readiness

**Files:**
- Modify: `src/devflow/cli.py`
- Modify: `src/devflow/control_room/review_readiness.py`
- Test: `tests/test_local_worker_lane.py`

- [ ] **Step 1: Add failing CLI assertions**

Append to `tests/test_local_worker_lane.py`:

```python
from typer.testing import CliRunner
from devflow.cli import app

runner = CliRunner()


def test_task_show_includes_local_worker_lane_summary(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    result = runner.invoke(app, ["task", "create", "local lane"])
    assert result.exit_code == 0, result.output
    agent_dir = tmp_path / ".devflow/tasks/task-0001/agents/qwopus-implementer"
    _write_json(
        agent_dir / "run.json",
        {
            "schema_version": 1,
            "task_id": "task-0001",
            "agent_id": "qwopus-implementer",
            "status": "complete",
            "model": "qwopus:latest",
            "adapter": "ollama_chat",
            "proposal_patch_found": True,
            "proposal_patch_path": ".devflow/tasks/task-0001/agents/qwopus-implementer/proposal.patch",
        },
    )
    (agent_dir / "proposal.patch").write_text("diff --git a/hello.txt b/hello.txt\n", encoding="utf-8")

    show = runner.invoke(app, ["task", "show", "task-0001"])

    assert show.exit_code == 0, show.output
    assert "local_worker_lane: local-patch-worker" in show.output
    assert "local_worker: qwopus-implementer" in show.output
    assert "local_worker_readiness: needs_review" in show.output
    assert "local_worker_next_action: devflow task review-patch task-0001 --agent qwopus-implementer" in show.output
```

- [ ] **Step 2: Run failing CLI test**

Run:

```bash
PYTHONPATH=src:. .venv/bin/python -m pytest tests/test_local_worker_lane.py::test_task_show_includes_local_worker_lane_summary -q
```

Expected: fail because `task show` does not print local worker lane fields.

- [ ] **Step 3: Print lane fields in `task show`**

In `src/devflow/cli.py`, import the helper:

```python
from devflow.control_room.local_worker_lane import local_worker_lane_summary
```

In the `task_show` command after existing worker lane output, add:

```python
    local_lane = local_worker_lane_summary(root, task)
    if local_lane:
        typer.echo(f"local_worker_lane: {local_lane['lane_type']}")
        typer.echo(f"local_worker: {local_lane['worker_id']}")
        typer.echo(f"local_worker_readiness: {local_lane['readiness_status']}")
        typer.echo(f"local_worker_next_action: {local_lane['next_safe_action']}")
```

- [ ] **Step 4: Extend review readiness projection**

In `src/devflow/control_room/review_readiness.py`, add optional fields to the projection dataclass or model used there:

```python
local_worker_lane: str | None = None
local_worker: str | None = None
local_worker_readiness: str | None = None
local_worker_next_action: str | None = None
```

When building each task projection:

```python
lane = local_worker_lane_summary(root, task)
if lane:
    local_worker_lane = lane["lane_type"]
    local_worker = lane["worker_id"]
    local_worker_readiness = lane["readiness_status"]
    local_worker_next_action = lane["next_safe_action"]
    evidence_paths.extend(lane.get("evidence_paths") or [])
```

Render these fields in the single-task text output using the same style as existing lane fields.

- [ ] **Step 5: Run CLI/review tests**

Run:

```bash
PYTHONPATH=src:. .venv/bin/python -m pytest tests/test_local_worker_lane.py tests/test_review_readiness.py -q
```

Expected: new local worker lane tests pass; existing review readiness tests stay green.

- [ ] **Step 6: Commit**

```bash
PYTHONPATH=src:. .venv/bin/devflow git checkpoint -m "feat(devflow): surface local worker lane in CLI" --yes
```

## Task 3: Add Supervisor And Operating-Layer Projection

**Files:**
- Modify: `src/devflow/control_room/supervisor_surface.py`
- Modify: `src/devflow/control_room/operating_layer.py`
- Modify: `src/devflow/control_room/operating_layer_script.py`
- Modify: `src/devflow/control_room/operating_layer_styles.py`
- Test: `tests/test_supervisor_operating_surface.py`
- Test: `tests/test_operating_layer.py`

- [ ] **Step 1: Add supervisor failing assertions**

In `tests/test_supervisor_operating_surface.py`, add a task with local patch worker evidence and assert:

```python
status = _read_json(_invoke_read_only(tmp_path, ["supervisor", "status", "--json"]))
task_record = status["tasks"][0]
assert task_record["local_worker_lane"]["lane_type"] == "local-patch-worker"
assert task_record["local_worker_lane"]["worker_id"] == "qwopus-implementer"
assert task_record["local_worker_lane"]["readiness_status"] == "needs_review"
assert task_record["local_worker_lane"]["next_safe_action"] == "devflow task review-patch task-0001 --agent qwopus-implementer"

packet = _read_json(_invoke_read_only(tmp_path, ["supervisor", "packet", "--json"]))
packet_task = packet["tasks"][0]
assert packet_task["local_worker_lane"]["lane_type"] == "local-patch-worker"
assert ".devflow/tasks/task-0001/agents/qwopus-implementer/run.json" in packet_task["evidence_paths"]
```

- [ ] **Step 2: Add operating-layer failing assertions**

In `tests/test_operating_layer.py`, add a snapshot test that asserts:

```python
payload = build_operating_layer_snapshot(tmp_path).model_dump(mode="json")
lane = payload["tasks"][0]["local_worker_lane"]
assert lane["lane_type"] == "local-patch-worker"
assert lane["worker_id"] == "qwopus-implementer"
assert lane["readiness_status"] == "needs_review"
assert lane["next_safe_action"] == "devflow task review-patch task-0001 --agent qwopus-implementer"

review = {item["label"]: item["value"] for item in payload["tasks"][0]["detail"]["review_summary"]}
assert review["Local worker"] == "qwopus-implementer"
assert review["Local worker readiness"] == "needs_review"
```

Update the asset contract test:

```python
assert ".local-worker-lane-block" in APP_CSS
assert "renderLocalWorkerLaneBlock" in APP_JS
```

- [ ] **Step 3: Run failing surface tests**

```bash
PYTHONPATH=src:. .venv/bin/python -m pytest tests/test_supervisor_operating_surface.py tests/test_operating_layer.py -q
```

Expected: fail because the projections do not include `local_worker_lane`.

- [ ] **Step 4: Implement supervisor projection**

In `src/devflow/control_room/supervisor_surface.py`, call `local_worker_lane_summary(root, task)` wherever compact task records are built. Add:

```python
if local_lane:
    record["local_worker_lane"] = {
        "lane_type": local_lane["lane_type"],
        "worker_id": local_lane["worker_id"],
        "readiness_status": local_lane["readiness_status"],
        "next_safe_action": local_lane["next_safe_action"],
        "evidence_paths": local_lane.get("evidence_paths") or [],
    }
    record.setdefault("evidence_paths", []).extend(local_lane.get("evidence_paths") or [])
```

- [ ] **Step 5: Implement operating-layer projection**

In `src/devflow/control_room/operating_layer.py`, add a Pydantic model:

```python
class OperatingLayerLocalWorkerLane(BaseModel):
    lane_type: str
    worker_id: str
    profile_id: str | None = None
    model: str | None = None
    adapter: str | None = None
    permission_mode: str | None = None
    latest_run_id: str | None = None
    latest_status: str | None = None
    patch_candidate: bool = False
    readiness_status: str
    next_safe_action: str
    evidence_paths: list[str] = Field(default_factory=list)
```

Add `local_worker_lane: OperatingLayerLocalWorkerLane | None = None` to the task model. Populate it from `local_worker_lane_summary(root, task)`. Add review summary rows:

```python
if local_lane:
    review_summary.append({"label": "Local worker", "value": local_lane["worker_id"]})
    review_summary.append({"label": "Local worker readiness", "value": local_lane["readiness_status"]})
```

- [ ] **Step 6: Render local worker lane block**

In `src/devflow/control_room/operating_layer_script.py`, add:

```javascript
function renderLocalWorkerLaneBlock(lane) {
  if (!lane) return "";
  const rows = [
    ["Worker", lane.worker_id],
    ["Type", lane.lane_type],
    ["Status", lane.latest_status],
    ["Readiness", lane.readiness_status],
    ["Next", lane.next_safe_action],
  ].filter(([, value]) => Boolean(value));
  return `<section class="local-worker-lane-block">${rows.map(([label, value]) => (
    `<div><span>${escapeHtml(label)}</span><strong>${escapeHtml(String(value))}</strong></div>`
  )).join("")}</section>`;
}
```

Call it in the selected task review panel near the existing worker lane block.

In `src/devflow/control_room/operating_layer_styles.py`, add:

```css
.local-worker-lane-block {
  display: grid;
  gap: 8px;
  padding: 10px;
  border: 1px solid var(--border-muted);
  border-radius: 8px;
  background: var(--surface-subtle);
}

.local-worker-lane-block div {
  display: flex;
  justify-content: space-between;
  gap: 12px;
}
```

Use existing CSS variables; adjust names if the current stylesheet uses different tokens.

- [ ] **Step 7: Run surface tests**

```bash
PYTHONPATH=src:. .venv/bin/python -m pytest tests/test_supervisor_operating_surface.py tests/test_operating_layer.py -q
```

Expected: pass.

- [ ] **Step 8: Commit**

```bash
PYTHONPATH=src:. .venv/bin/devflow git checkpoint -m "feat(devflow): project local worker lanes to surfaces" --yes
```

## Task 4: Harden Recovery States And Next Safe Actions

**Files:**
- Modify: `src/devflow/control_room/local_worker_lane.py`
- Test: `tests/test_local_worker_lane.py`
- Test: existing patch review/apply tests if assertions need updating

- [ ] **Step 1: Add recovery tests**

Add tests for:

```python
def test_local_worker_lane_summary_reports_failed_worker_recovery(tmp_path: Path) -> None:
    task = _task()
    agent_dir = tmp_path / ".devflow/tasks/task-0001/agents/qwopus-implementer"
    _write_json(
        agent_dir / "run.json",
        {
            "schema_version": 1,
            "task_id": "task-0001",
            "agent_id": "qwopus-implementer",
            "status": "failed",
            "summary": "model missing",
            "proposal_patch_found": False,
        },
    )

    summary = local_worker_lane_summary(tmp_path, task)

    assert summary is not None
    assert summary["readiness_status"] == "failed"
    assert "model missing" in summary["readiness_errors"]
    assert summary["next_safe_action"] == "devflow task escalation-packet task-0001 --agent qwopus-implementer"
```

```python
def test_local_worker_lane_summary_reports_patch_ladder_states(tmp_path: Path) -> None:
    task = _task()
    agent_dir = tmp_path / ".devflow/tasks/task-0001/agents/qwopus-implementer"
    _write_json(agent_dir / "run.json", {"agent_id": "qwopus-implementer", "status": "complete", "proposal_patch_found": True})
    (agent_dir / "proposal.patch").write_text("diff --git a/a.txt b/a.txt\n", encoding="utf-8")
    _write_json(tmp_path / ".devflow/tasks/task-0001/local-model-runs/run-1/patch-review.json", {"review_status": "low_risk_candidate"})
    summary = local_worker_lane_summary(tmp_path, task)
    assert summary["readiness_status"] == "needs_dry_run"
    assert summary["next_safe_action"] == "devflow task patch-dry-run task-0001 --agent qwopus-implementer"
```

- [ ] **Step 2: Run failing recovery tests**

```bash
PYTHONPATH=src:. .venv/bin/python -m pytest tests/test_local_worker_lane.py -q
```

Expected: fail until readiness edge cases are implemented.

- [ ] **Step 3: Implement exact edge states**

Update `_patch_readiness()` so:

- failed run status returns `failed`;
- missing proposal patch returns `failed`;
- proposal without review returns `needs_review`;
- review without dry-run returns `needs_dry_run`;
- dry-run without patch application returns `needs_apply`;
- applied patch without passed verification returns `needs_verification`;
- passed verification without ready promotion preview returns `needs_promotion_preview`;
- ready promotion preview returns `ready`.

Use `readiness_errors` only for states that block interpretation. Use `readiness_warnings` for low-quality or stale advisory evidence.

- [ ] **Step 4: Run recovery tests**

```bash
PYTHONPATH=src:. .venv/bin/python -m pytest tests/test_local_worker_lane.py -q
```

Expected: pass.

- [ ] **Step 5: Commit**

```bash
PYTHONPATH=src:. .venv/bin/devflow git checkpoint -m "feat(devflow): harden local worker recovery states" --yes
```

## Task 5: Add Production-Readiness Dogfood Case

**Files:**
- Modify: `src/devflow/control_room/dogfood.py`
- Modify: `tests/test_dogfood_harness.py`

- [ ] **Step 1: Add failing dogfood test**

In `tests/test_dogfood_harness.py`, add:

```python
def test_local_worker_lane_dogfood_case_exercises_evidence_ladder(tmp_path: Path) -> None:
    _init_dogfood_repo(tmp_path)

    result = run_dogfood_suite(tmp_path, case_ids=["local-worker-lane-hardening"])
    case_result = result["results"][0]

    assert case_result["status"] == "passed"
    assert case_result["score"] == case_result["max_score"]
    assert any("read-only local worker evidence was summarized" in lesson for lesson in case_result["lessons"])
    assert any("local patch worker evidence reached apply/verify gates" in lesson for lesson in case_result["lessons"])
    assert any("no provider API calls or autonomous routing were introduced" in lesson for lesson in case_result["lessons"])
```

Increase the expected production-readiness case count by one.

- [ ] **Step 2: Run failing dogfood test**

```bash
PYTHONPATH=src:. .venv/bin/python -m pytest tests/test_dogfood_harness.py::test_local_worker_lane_dogfood_case_exercises_evidence_ladder -q
```

Expected: fail because the case id is unknown.

- [ ] **Step 3: Implement dogfood case**

In `src/devflow/control_room/dogfood.py`, add a case id `local-worker-lane-hardening`. Build it in a scratch Git repo under the case artifact directory. The case should:

1. Create a task.
2. Run `devflow agent run --task <task_id> --profile local-qwopus-inspector --dry-run --json`.
3. Write deterministic read-only WorkerEvidence using `write_worker_evidence()` inside the scratch repo.
4. Write deterministic local patch worker evidence with a small `proposal.patch`.
5. Assert `devflow task show <task_id>` and `devflow supervisor status --json` include local worker lane fields.
6. Run `devflow task review-patch`, `devflow task patch-dry-run`, `devflow task apply-patch`, `devflow task verify`, and `devflow task promote-preview` only after each prior evidence gate exists.
7. Assert source changes do not exist before apply and do exist after apply.
8. Assert no commands include remote provider names, `push-main`, autonomous route execution, or promotion.

Write `local-worker-lane-summary.json` with the case evidence and lessons.

- [ ] **Step 4: Run dogfood tests**

```bash
PYTHONPATH=src:. .venv/bin/python -m pytest tests/test_dogfood_harness.py -q
```

Expected: pass.

- [ ] **Step 5: Run production-readiness suite**

```bash
PYTHONPATH=src:. .venv/bin/devflow dogfood run --suite production-readiness
```

Expected: silver threshold still met; no provider API calls, autonomous routing, auto-promotion, auto-commit, auto-push, database, or hidden memory.

- [ ] **Step 6: Commit**

```bash
PYTHONPATH=src:. .venv/bin/devflow git checkpoint -m "test(devflow): dogfood local worker lane hardening" --yes
```

## Task 6: Align Active Docs And Write Handoff

**Files:**
- Modify: `docs/control-room-mvp.md`
- Modify: `docs/agent-handoff.md`
- Create: `docs/handoffs/2026-06-14-milestone-20-registry-backed-local-worker-runtime-hardening-implementation.md`

- [ ] **Step 1: Update active docs**

In `docs/control-room-mvp.md`, update the Current Priority paragraph so it says Milestone 20 is implemented in the active branch after implementation. Keep explicit exclusions for remote provider execution, autonomous routing, auto-promotion, auto-commit, auto-push, PRs, databases, and worker-owned verification.

In `docs/agent-handoff.md`, add Milestone 20 implementation status and links to the spec/plan/handoff. Remove any stale instruction saying future agents should continue from `task-0037` if Milestone 19 has already been promoted.

- [ ] **Step 2: Add implementation handoff**

Create `docs/handoffs/2026-06-14-milestone-20-registry-backed-local-worker-runtime-hardening-implementation.md` using:

```markdown
## Status

needs-review

## Files Changed

- `src/devflow/control_room/local_worker_lane.py` (read-only local worker lane projection)
- `src/devflow/cli.py` (local worker lane fields in task surfaces)
- `src/devflow/control_room/review_readiness.py` (local worker evidence and readiness projection)
- `src/devflow/control_room/supervisor_surface.py` (supervisor local worker lane task records)
- `src/devflow/control_room/operating_layer.py` / `operating_layer_script.py` / `operating_layer_styles.py` (operating-layer local worker lane block)
- `src/devflow/control_room/dogfood.py` (production-readiness local worker lane dogfood case)
- `tests/` (focused coverage)
- `docs/` (active milestone docs)

## Verification

- `<focused pytest command>`: pass, `<actual output>`
- `PYTHONPATH=src:. .venv/bin/devflow dogfood run --suite production-readiness`: pass, `<actual output>`
- `PATH=/Users/josh/Desktop/Dev-Flow/.venv/bin:$PATH ./scripts/release-check.sh`: pass, `<actual output>`
- `PYTHONPATH=src:. .venv/bin/devflow git status`: pass, clean branch state

## Risks

- `<specific remaining risk or None>`

## Next Safe Action

- Promote the implementation task after review: `PYTHONPATH=src:. .venv/bin/devflow task promote <task_id>`
```

Replace placeholder angle-bracket text with real command output before finalizing. Do not leave placeholder text in the committed handoff.

- [ ] **Step 3: Run stale-context scan**

```bash
rg -n "Milestone 19.*next planned|task-0037.*continue|provider-backed execution is active|autonomous routing is active|local worker owns verification|local worker owns promotion" docs README.md AGENTS.md -S
```

Expected: no misleading active-doc matches.

- [ ] **Step 4: Commit**

```bash
PYTHONPATH=src:. .venv/bin/devflow git checkpoint -m "docs(devflow): align milestone 20 handoff" --yes
```

## Task 7: Final Verification And Promotion Preparation

**Files:**
- No new files unless verification uncovers a bug.

- [ ] **Step 1: Run focused suites**

```bash
PYTHONPATH=src:. .venv/bin/python -m pytest tests/test_local_worker_lane.py tests/test_ollama_worker.py tests/test_local_packet_worker.py tests/test_worker_evidence.py tests/test_supervisor_operating_surface.py tests/test_operating_layer.py tests/test_dogfood_harness.py -q
```

Expected: all selected tests pass.

- [ ] **Step 2: Run whitespace check**

```bash
git diff --check
```

Expected: no output.

- [ ] **Step 3: Verify through Dev-Flow task verifier**

From the main checkout, after the implementation is in a Dev-Flow task lane:

```bash
PYTHONPATH=src:. .venv/bin/devflow task verify <task_id> --shell "PYTHONPATH=src:. /Users/josh/Desktop/Dev-Flow/.venv/bin/python -m pytest tests/test_local_worker_lane.py tests/test_ollama_worker.py tests/test_local_packet_worker.py tests/test_worker_evidence.py tests/test_supervisor_operating_surface.py tests/test_operating_layer.py tests/test_dogfood_harness.py -q"
```

Expected: task verification passes.

- [ ] **Step 4: Finalize the worker branch**

```bash
PYTHONPATH=src:. .venv/bin/devflow task finalize <task_id> --commit
```

Expected: finalized commit on the worker branch, `main_changed: no`.

- [ ] **Step 5: Run promotion preview**

```bash
PYTHONPATH=src:. .venv/bin/devflow task promote-preview <task_id>
```

Expected: `promotion_readiness: ready`, `lane_readiness: ready`.

- [ ] **Step 6: Run full release check in the finalized worker worktree**

```bash
PATH=/Users/josh/Desktop/Dev-Flow/.venv/bin:$PATH ./scripts/release-check.sh
```

Expected: full pytest, CLI smoke, distribution build, twine check, and wheel smoke install pass.

- [ ] **Step 7: Final handoff**

Update the implementation handoff with the final command outputs, then re-run task verification/finalization if the handoff file changed. Leave exactly one next safe action: promote the implementation task.

## Self-Review Checklist

- The plan keeps provider-backed execution deferred.
- The plan does not add autonomous routing.
- The plan does not let local workers verify, promote, commit, push, or create PRs.
- The plan keeps the local worker lane projection read-only.
- Every mutation still flows through existing explicit Dev-Flow commands.
- Dogfood proves the control-room evidence ladder without requiring paid frontier credits.
