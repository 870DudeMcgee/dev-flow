# Milestone 15 Multi-Project Control Room Hardening Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make stale or missing registered project paths visible, recoverable, and consistently guided across multi-project control-room surfaces.

**Architecture:** Keep the global project registry as an index and project-local `.devflow/` as authority. Read-only surfaces continue to report missing paths without mutation, while next-action text consistently routes humans to `project doctor` before explicit archive, repair, or registry-only removal.

**Tech Stack:** Python 3, Typer CLI, Pydantic models, pytest, Markdown docs.

---

### Task 1: Missing-Project Next Actions

**Files:**
- Modify: `tests/test_freshness_loop.py`
- Modify: `tests/test_operating_layer.py`
- Modify: `src/devflow/control_room/multi_project_freshness.py`
- Modify: `src/devflow/control_room/operating_layer.py`

- [ ] **Step 1: Write failing tests**

Add assertions that all-project freshness and operating-layer project summaries point missing active projects to `devflow project doctor <project_id>`.

- [ ] **Step 2: Run focused red tests**

Run:

```bash
PYTHONPATH=src:. .venv/bin/python -m pytest tests/test_freshness_loop.py::test_multi_project_freshness_scans_registered_projects_in_parallel tests/test_operating_layer.py::test_operating_layer_includes_multi_project_overview -q
```

Expected: fail because the operating-layer missing-project next action still points to `devflow project show <project_id>`.

- [ ] **Step 3: Implement minimal projection change**

Update the missing-project next action in `operating_layer.py` to use `devflow project doctor <project_id>`. Keep `multi_project_freshness.py` aligned with the same diagnostic-first language.

- [ ] **Step 4: Run focused green tests**

Run the same focused pytest command. Expected: pass.

### Task 2: Archive And Removal Policy Coverage

**Files:**
- Modify: `tests/test_project_registry.py`

- [ ] **Step 1: Write focused tests**

Add coverage proving `project archive` hides records from default `project list`, keeps them visible with `--include-archived`, and `project remove <project_id> --registry-only` removes only the registry record without deleting a present project directory.

- [ ] **Step 2: Run focused tests**

Run:

```bash
PYTHONPATH=src:. .venv/bin/python -m pytest tests/test_project_registry.py -q
```

Expected: pass if existing archive/remove primitives already match policy; otherwise implement the minimal correction inside `src/devflow/control_room/project_registry.py` or CLI command output.

### Task 3: Active Docs Alignment

**Files:**
- Modify: `docs/architecture/multi-project-registry.md`
- Modify: `docs/control-room-mvp.md`
- Modify: `docs/mvp-contract.md`

- [ ] **Step 1: Add missing-project policy wording**

Document the diagnostic-first sequence: `project doctor`, then explicit repair/import, archive, or `remove --registry-only`.

- [ ] **Step 2: Keep boundaries explicit**

Confirm docs say read-only all-project surfaces do not auto-recreate, auto-archive, auto-remove, publish, push, or call providers.

### Task 4: Verification

**Files:**
- Read: touched files and test output only

- [ ] **Step 1: Run focused test suite**

```bash
PYTHONPATH=src:. .venv/bin/python -m pytest tests/test_project_registry.py tests/test_freshness_loop.py::test_multi_project_freshness_scans_registered_projects_in_parallel tests/test_operating_layer.py::test_operating_layer_includes_multi_project_overview -q
```

- [ ] **Step 2: Run docs/check status**

```bash
git diff --check
PYTHONPATH=src:. .venv/bin/devflow git status
```

- [ ] **Step 3: Report final handoff**

Use the repository handoff headings and include the exact verification commands and outputs.
