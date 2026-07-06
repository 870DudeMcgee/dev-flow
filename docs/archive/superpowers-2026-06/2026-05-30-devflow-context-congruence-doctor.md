# DevFlow Context Congruence Doctor Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make `devflow doctor` detect stale or contradictory seeded `.devflow/` context, starting with implementation-layer `known-gaps.md` and `current-slice.md` drift.

**Architecture:** Keep the runtime authority inside `src/devflow/control_room/`. Extend the existing seed contract validator with a small declarative context-congruence rule set for active seeded Markdown files. `devflow init` continues to create or repair missing files without overwriting user edits; `devflow doctor` becomes the detector for existing stale seeded context.

**Tech Stack:** Python, Typer CLI, pytest, existing filesystem-backed `.devflow/` seed contract.

---

## Spec

### Problem

`.devflow/` now exists as a durable context layer, but some checked-in context can drift away from runtime reality. The concrete failure is `.devflow/layers/implementation/known-gaps.md` claiming there is no schema validation and no deterministic init/repair command even though `src/devflow/control_room/seed.py`, `devflow init`, and the current tests prove otherwise.

### Product Rule

Active `.devflow/` context must be treated as live product memory. When a seeded active context file contradicts the current shell-worker MVP or seed runtime, `devflow doctor` must fail with a precise reason.

### In Scope

- Detect stale/contradictory claims in `.devflow/layers/implementation/known-gaps.md`.
- Detect stale/contradictory current-slice framing in `.devflow/layers/implementation/current-slice.md`.
- Keep seed validation and congruence checks in `src/devflow/control_room/seed.py`.
- Update checked-in seeded Markdown so the repository passes its own doctor contract.
- Add focused pytest coverage for the new drift detection.

### Out Of Scope

- No enabled non-shell adapters.
- No autonomous routing.
- No web dashboard.
- No database.
- No broad Markdown knowledge graph.
- No automatic rewrite of user-edited existing context files during `devflow init`.
- No legacy `_legacy/` or top-level feature implementation changes.

### Acceptance

- A fresh `devflow init` tree passes `validate_seed_contract(root)`.
- The checked-in repository passes `validate_seed_contract(repo_root)`.
- If `known-gaps.md` contains `No schema validation exists yet`, `validate_seed_contract` reports that exact file as stale.
- If `known-gaps.md` contains `No command creates or repairs this structure deterministically`, `validate_seed_contract` reports that exact file as stale.
- `devflow doctor` exits `1` and prints `missing: seed contract` when those stale claims exist.
- Existing test that verifies `devflow init` does not overwrite user-edited files still passes.

## File Structure

- Modify: `src/devflow/control_room/seed.py`
  - Add a narrow context-congruence rules table near `SEED_FILES`.
  - Add `_validate_context_congruence(root, errors)` and call it from `validate_seed_contract`.
  - Keep all active implementation inside the control-room boundary.
- Modify: `tests/test_devflow_init_structure.py`
  - Add focused validation and doctor tests for stale implementation-layer context.
- Modify: `.devflow/layers/implementation/known-gaps.md`
  - Remove stale claims about missing schema validation and init/repair.
  - Keep true gaps: human-controlled merge readiness, no enabled non-shell adapters, no scheduling, legacy surfaces outside MVP path.
- Modify: `.devflow/layers/implementation/current-slice.md`
  - Reframe the current slice as context congruence plus shell-worker MVP stability.

## Task 1: Failing Tests For Stale Context Detection

**Files:**
- Modify: `tests/test_devflow_init_structure.py`

- [ ] **Step 1: Add validation test for stale `known-gaps.md` claims**

Append this test after `test_seed_schema_validation_reports_contract_drift`:

```python
def test_seed_context_congruence_reports_stale_known_gaps_claims() -> None:
    old_cwd = Path.cwd()
    with tempfile.TemporaryDirectory() as tmp:
        try:
            os.chdir(tmp)
            result = runner.invoke(app, ["init"])
            assert result.exit_code == 0, result.output

            Path(".devflow/layers/implementation/known-gaps.md").write_text(
                "# Known Gaps\n\n"
                "- No schema validation exists yet for the seeded `.devflow/` YAML, JSON, and JSONL files.\n"
                "- No command creates or repairs this structure deterministically.\n",
                encoding="utf-8",
            )

            errors = validate_seed_contract(Path.cwd())
            assert (
                ".devflow/layers/implementation/known-gaps.md: stale context contradicts runtime: "
                "No schema validation exists yet"
            ) in errors
            assert (
                ".devflow/layers/implementation/known-gaps.md: stale context contradicts runtime: "
                "No command creates or repairs this structure deterministically"
            ) in errors
        finally:
            os.chdir(old_cwd)
```

- [ ] **Step 2: Add doctor test for stale context output**

Append this test after `test_devflow_doctor_reports_seed_schema_drift`:

```python
def test_devflow_doctor_reports_stale_seeded_context() -> None:
    old_cwd = Path.cwd()
    with tempfile.TemporaryDirectory() as tmp:
        try:
            os.chdir(tmp)
            result = runner.invoke(app, ["init"])
            assert result.exit_code == 0, result.output

            Path(".devflow/layers/implementation/known-gaps.md").write_text(
                "# Known Gaps\n\n"
                "- No schema validation exists yet for the seeded `.devflow/` YAML, JSON, and JSONL files.\n",
                encoding="utf-8",
            )

            doctor = runner.invoke(app, ["doctor"])
            assert doctor.exit_code == 1
            assert "missing: seed contract" in doctor.output
            assert ".devflow/layers/implementation/known-gaps.md: stale context contradicts runtime" in doctor.output
        finally:
            os.chdir(old_cwd)
```

- [ ] **Step 3: Run focused tests to verify failure**

Run:

```bash
.venv/bin/python -m pytest tests/test_devflow_init_structure.py -q
```

Expected: FAIL because `validate_seed_contract` does not yet check Markdown congruence.

## Task 2: Implement Context Congruence Rules

**Files:**
- Modify: `src/devflow/control_room/seed.py`

- [ ] **Step 1: Add rule table after `SEED_FILES`**

Insert this immediately after the `SEED_FILES` dictionary:

```python
CONTEXT_CONGRUENCE_RULES = [
    {
        "path": ".devflow/layers/implementation/known-gaps.md",
        "required": [
            "Merge readiness is still human-controlled.",
            "Provider-backed adapters and scheduling remain out of scope.",
        ],
        "forbidden": [
            "No schema validation exists yet",
            "No command creates or repairs this structure deterministically",
        ],
    },
    {
        "path": ".devflow/layers/implementation/current-slice.md",
        "required": [
            "Keep the shell-worker MVP stable",
            "seeded filesystem context current",
        ],
        "forbidden": [
            "Current implementation slice: seed the `.devflow/` filesystem/context structure",
            "No runtime automation is part of this slice.",
        ],
    },
]
```

- [ ] **Step 2: Call congruence validation from `validate_seed_contract`**

Change the end of `validate_seed_contract` from:

```python
    _validate_empty_registry(root / ".devflow/workers/registry.yaml", "workers", errors)
    _validate_empty_registry(root / ".devflow/models/registry.yaml", "models", errors)
    _validate_reports_readme(root / ".devflow/reports/README.md", errors)
    return errors
```

to:

```python
    _validate_empty_registry(root / ".devflow/workers/registry.yaml", "workers", errors)
    _validate_empty_registry(root / ".devflow/models/registry.yaml", "models", errors)
    _validate_reports_readme(root / ".devflow/reports/README.md", errors)
    _validate_context_congruence(root, errors)
    return errors
```

- [ ] **Step 3: Add `_validate_context_congruence`**

Insert this helper after `_validate_reports_readme`:

```python
def _validate_context_congruence(root: Path, errors: list[str]) -> None:
    for rule in CONTEXT_CONGRUENCE_RULES:
        display_path = str(rule["path"])
        path = root / display_path
        if not path.exists():
            continue
        content = path.read_text(encoding="utf-8")
        for required in rule["required"]:
            if required not in content:
                errors.append(f"{display_path}: missing current context: {required}")
        for forbidden in rule["forbidden"]:
            if forbidden in content:
                errors.append(f"{display_path}: stale context contradicts runtime: {forbidden}")
```

- [ ] **Step 4: Run focused tests**

Run:

```bash
.venv/bin/python -m pytest tests/test_devflow_init_structure.py -q
```

Expected: FAIL until the checked-in seeded Markdown and `SEED_FILES` contents are updated to satisfy the new required phrases.

## Task 3: Update Seeded Implementation Context

**Files:**
- Modify: `src/devflow/control_room/seed.py`
- Modify: `.devflow/layers/implementation/known-gaps.md`
- Modify: `.devflow/layers/implementation/current-slice.md`

- [ ] **Step 1: Update `SEED_FILES` values**

In `src/devflow/control_room/seed.py`, replace the two implementation-layer entries with:

```python
    ".devflow/layers/implementation/current-slice.md": "# Current Slice\n\nKeep the shell-worker MVP stable while making seeded filesystem context current, detectable, and congruent with runtime seed validation.\n",
    ".devflow/layers/implementation/known-gaps.md": "# Known Gaps\n\nMerge readiness is still human-controlled. Provider-backed adapters and scheduling remain out of scope.\n\nLegacy surfaces still exist outside the frozen MVP path and must not be treated as active product authority.\n",
```

- [ ] **Step 2: Update checked-in `known-gaps.md`**

Replace `.devflow/layers/implementation/known-gaps.md` with:

```markdown
# Known Gaps

Merge readiness is still human-controlled. Provider-backed adapters and scheduling remain out of scope.

Legacy surfaces still exist outside the frozen MVP path and must not be treated as active product authority.
```

- [ ] **Step 3: Update checked-in `current-slice.md`**

Replace `.devflow/layers/implementation/current-slice.md` with:

```markdown
# Current Slice

Keep the shell-worker MVP stable while making seeded filesystem context current, detectable, and congruent with runtime seed validation.
```

- [ ] **Step 4: Run focused tests**

Run:

```bash
.venv/bin/python -m pytest tests/test_devflow_init_structure.py -q
```

Expected: PASS.

## Task 4: Verify Doctor Behavior End To End

**Files:**
- No source changes expected.

- [ ] **Step 1: Run the checked-in seed validation directly**

Run:

```bash
.venv/bin/python -m pytest tests/test_devflow_init_structure.py::test_checked_in_devflow_seed_contract_is_machine_readable -q
```

Expected: PASS.

- [ ] **Step 2: Run the doctor drift test directly**

Run:

```bash
.venv/bin/python -m pytest tests/test_devflow_init_structure.py::test_devflow_doctor_reports_stale_seeded_context -q
```

Expected: PASS.

- [ ] **Step 3: Run the focused control-room suite**

Run:

```bash
.venv/bin/python -m pytest tests/test_devflow_init_structure.py tests/test_control_room_shell.py tests/test_task_packet.py -q
```

Expected: PASS.

- [ ] **Step 4: Run `devflow doctor` on the repository**

Run:

```bash
.venv/bin/devflow doctor
```

Expected: exit code `0`; output includes `ok: seed contract (.devflow seed contract)`.

## Self-Review

- Spec coverage: The plan covers stale `known-gaps.md`, stale `current-slice.md`, checked-in seed validity, fresh init validity, doctor failure behavior, and init non-overwrite behavior.
- Placeholder scan: No placeholder tasks are present.
- Type consistency: New functions stay in `seed.py`, use `Path`, and append string errors to the existing `list[str]` contract consumed by `service.doctor`.
