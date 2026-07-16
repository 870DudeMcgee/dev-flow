# Implementation Plan — M0 + M1: Read Model + Obsidian Command Center Projection

**Status:** Planning only. No code, tests, or config changed.
**Date:** 2026-07-15
**Baseline SHA:** `99d27a5` (re-verify before starting)
**Authority:** Subordinate to blueprint, then live source/tests, then DEVFLOW_SOURCE_OF_TRUTH.md.

**Goal:** Make the proven `canonical_product_build@1` runtime observable through one honest
read model and an Obsidian Command Center projection — all additive, zero canonical-state
mutation, zero new workflow capability.

---

## What we're building on (verified live shapes)

### WorkflowSnapshot (the ledger read surface)
`workflow_ledger.py:69` — frozen pydantic:
- `workflow_id: "canonical_product_build@1"`
- `current_node_id: str`
- `stage: LoopStage` (one of 11 enum values)
- `completed_node_ids: tuple[str, ...]`

### Key functions
- `rebuild_workflow_snapshot(root, run_id) -> WorkflowSnapshot` (`:334`) — deterministic replay
- `replay_workflow_run(root, run_id) -> WorkflowSnapshot` (`:316`) — same, without write
- `is_canonical_workflow_run(root, run_id) -> bool` (`:344`) — checks workflow-definition.json exists
- `record_node_outcome(root, run_id, *, receipt, event) -> WorkflowSnapshot` (`:386`)
- `record_decision(root, receipt, *, repo, event_id) -> DecisionReceipt` (`:448`)

### NodeReceipt (frozen, `:47`)
- `receipt_id`, `node_id`, `outcome: "success"|"failure"`, `evidence: tuple[EvidenceReference,...]`

### DecisionReceipt (frozen, `:93`)
- `decision_id`, `run_id`, `integration_id`, `integration_head`, `integration_tree`,
  `integration_fingerprint`, `verification_receipt_id`, `verification_receipt_hash`,
  `actor`, `decision_type: accept|reject|request_changes`, `promotion_eligible`, `created_at`

### The 11-node success chain (`workflow_definition.py`)
```
idea → definition → spec → planning → planning_judge → assignment → build_judge → verification → human_decision → complete
                                  ↓ (any failure) → blocked
```
9 productive nodes + `complete` + `blocked` = 11 total.

### Pipeline run builder (test pattern)
```python
run_id = create_pipeline_run(tmp_path, {"repo": "test/repo"})
initialize_workflow_run(tmp_path, run_id)  # creates canonical marker
record_node_outcome(tmp_path, run_id, receipt=..., event=...)
```

### Atomic write pattern (`model_catalog_markdown.py:145`)
temp → write → replace; or START_MARKER/END_MARKER block replacement.

---

## M0-S1 — Canonical run read-model adapter (additive)

**Outcome:** One importable helper that derives a public run model from the ledger.
Existing writers untouched. `LoopStage` kept for compat.

### Files
- **NEW** `src/devflow/loop/read_model.py`
- **EDIT** `src/devflow/loop/models.py:18` — add docstring noting `LoopStage` is a compat/UI projection

### `CanonicalRunModel` schema (frozen dataclass/pydantic)
```python
class NodeStatus(str, Enum):
    completed = "completed"
    current = "current"
    pending = "pending"

class NodeInfo(BaseModel):       # frozen, extra="forbid"
    node_id: str
    stage: LoopStage
    status: NodeStatus

class CanonicalRunModel(BaseModel):  # frozen, extra="forbid"
    run_id: str
    workflow_id: Literal["canonical_product_build@1"]
    current_node_id: str
    current_stage: LoopStage
    completed_node_ids: tuple[str, ...]
    pending_node_ids: tuple[str, ...]   # remaining nodes in the success chain
    nodes: tuple[NodeInfo, ...]         # all nodes with their status
    progress: float                     # 0.0–1.0: completed / 9 (non-terminal chain length)
    is_terminal: bool                   # complete or blocked
    is_blocked: bool
    snapshot_stage: LoopStage           # raw snapshot stage (compat passthrough)
```

### `derive_canonical_run_model(snapshot, run_id) -> CanonicalRunModel`
Pure function. No I/O. Derives:
- Walks the `_SUCCESS_CHAIN` from `workflow_definition.py` to compute pending nodes
- `progress = len(completed_node_ids) / 9`
- `is_terminal` = stage in {complete, blocked}
- `nodes` = all 11 nodes labeled completed/current/pending

### Wrapper: `load_canonical_run_model(root, run_id) -> CanonicalRunModel`
1. Check `is_canonical_workflow_run(root, run_id)` → raise `NotCanonicalRunError` if False
2. `snapshot = rebuild_workflow_snapshot(root, run_id)`
3. Return `derive_canonical_run_model(snapshot, run_id)`

### Tests: `tests/test_loop_read_model.py`
```
test_derive_from_fresh_snapshot          # just initialized → stage=idea, progress=0.0, 0 completed
test_derive_after_one_node               # idea success → stage=definition, progress=1/9
test_derive_mid_chain                    # spec success → progress=3/9, 3 completed
test_derive_complete                     # all 9 → stage=complete, progress=1.0, is_terminal=True
test_derive_blocked                      → stage=blocked, is_blocked=True, is_terminal=True
test_pending_nodes_excludes_completed    # pending = full chain - completed - current
test_load_rejects_noncanonical_run       # no workflow-definition.json → NotCanonicalRunError
test_loopstage_still_importable          # import check — LoopStage NOT deleted
test_existing_writers_unchanged          # record_node_outcome still works after read_model import
```

### Verification
```bash
.venv/bin/python -m pytest tests/test_loop_read_model.py -q
PYTHONPATH=src .venv/bin/python -m devflow.cli loop spine-fixture --json  # regression gate
```

---

## M0-S2 — Reconcile linear-chain doc drift + stale Phase 6 sentence

**Outcome:** Docs truthfully state Phase 6 is complete; linear chain is noted as
fixed target, not the blueprint's branching phase graph.

### Files
- **EDIT** `docs/DEVFLOW_SOURCE_OF_TRUTH.md` near `:344–347` — annotate `LoopStage` as
  compat/UI projection; note noncanonical runs retain saved-state without migration.

### Tests
- Targeted stale-context scan: `grep -n "remain Phase 6 work"` → no match
- `git diff --check` clean

### Verification
```bash
grep -n "remain Phase 6 work" docs/DEVFLOW_SOURCE_OF_TRUTH.md   # → no output
git diff --check
```

---

## M1-S1 — Projection data contract + extraction

**Outcome:** A deterministic, fail-closed extractor that turns a canonical run into a
typed `ProjectionState` matching blueprint Appendix C.

### Files
- **NEW** `src/devflow/obsidian/__init__.py`
- **NEW** `src/devflow/obsidian/projection.py`

### `ProjectionState` schema (frozen)
```python
class RunHealth(str, Enum):
    healthy = "Healthy"
    running = "Running"
    repairing = "Repairing"
    awaiting_decision = "Awaiting Decision"
    blocked = "Blocked"
    verification_failed = "Verification Failed"
    completed = "Completed"

class ProjectionState(BaseModel):     # frozen, extra="forbid"
    run_id: str
    workflow_id: str
    health: RunHealth
    current_phase: str                # human-readable: "Specification", "Planning", etc.
    stage: LoopStage                  # raw stage for machine consumers
    progress: float                   # 0.0–1.0
    progress_percent: int             # 0–100
    completed_node_ids: tuple[str, ...]
    current_node_id: str | None
    blocker_count: int
    decision_count: int
    handoff_count: int
    open_decisions: tuple[dict, ...]  # DecisionReceipt summary dicts
    result_branch: str | None         # refs/heads/devflow/results/<run_id> if exists
    canonical_run_dir: str            # absolute path to the run directory
    updated_at: str                   # ISO timestamp
    extraction_note: str | None       # "not_canonical" or None
```

### `extract_projection(root, run_id) -> ProjectionState`
1. `is_canonical_workflow_run` → if False, return `ProjectionState` with
   `health=Healthy`, `extraction_note="not_canonical"`, all fields empty
2. `model = load_canonical_run_model(root, run_id)` (from M0-S1)
3. Derive health from model:
   - `blocked` → `Blocked`
   - `complete` + has accept decision → `Completed`
   - `complete` + has reject/request_changes → `Needs Rework` (map to `Blocked`)
   - `human_decision` stage → `Awaiting Decision`
   - any failure edge in receipts → `Repairing` (or `Verification Failed` if terminal)
   - otherwise → `Running`
4. Read decision receipts from `DECISION_RECEIPTS_DIR` for `open_decisions`
5. Read result branch existence via `git show-ref`
6. Build `ProjectionState`

### Health derivation rules (deterministic)
```
stage=blocked                                 → Blocked
stage=complete + accept receipt present       → Completed
stage=complete + reject/request_changes       → Blocked (needs rework)
stage=human_decision                          → Awaiting Decision
stage=verification + any failure receipt      → Verification Failed
stage in [idea..verification] + failure edge  → Repairing
otherwise                                     → Running
```

### Phase name map (LoopStage → human-readable)
```
idea            → "Idea & Brainstorm"
definition      → "Definition"
spec            → "Specification"
planning        → "Planning"
planning_judge  → "Planning Review"
assignment      → "Assignment"
build_judge     → "Build & Judge"
verification    → "Verification"
human_decision  → "Human Decision"
complete        → "Complete"
blocked         → "Blocked"
```

### Tests: `tests/test_obsidian_projection.py`
```
test_extract_fresh_run                    # idea stage → health=Running, progress=0
test_extract_after_spec                   # 3 nodes done → progress=33, phase="Specification"
test_extract_awaiting_decision            # human_decision stage → Awaiting Decision
test_extract_blocked                      # blocked → Blocked
test_extract_complete_with_accept         # complete + accept → Completed
test_extract_derives_decision_count       # decision receipts present → count matches
test_extract_noncanonical_run_returns_note # no marker → extraction_note="not_canonical"
test_extract_no_canonical_state_mutation   # run dir files unchanged after extract
test_extract_fail_closed_on_missing_ledger # corrupt/missing ledger → clear error, not crash
```

### Verification
```bash
.venv/bin/python -m pytest tests/test_obsidian_projection.py -q
```

---

## M1-S2 — Markdown renderers (Overview / Workflow / Evidence / Decisions / History)

**Outcome:** Human-readable Command Center notes rendered from `ProjectionState`.
Pure functions, no I/O to canonical state.

### Files
- **NEW** `src/devflow/obsidian/render.py`

### Renderers (each takes `ProjectionState` → `str`)
```python
def render_overview(state: ProjectionState) -> str:
    """Front matter (Appendix C) + health hero + phase + progress bar + attention summary + next action."""

def render_workflow(state: ProjectionState) -> str:
    """Node-by-node status table: node | stage | status. Wikilinks to evidence."""

def render_evidence(state: ProjectionState) -> str:
    """Available receipts, verification results, changed-path checks. Links to run dir."""

def render_decisions(state: ProjectionState) -> str:
    """Open + historical decisions. Decision type, actor, timestamp, promotion status."""

def render_history(state: ProjectionState) -> str:
    """Chronological event list from the workflow ledger events."""
```

### Front matter (Appendix C style)
```yaml
---
type: devflow-run
project: DevFlow
run_id: <run_id>
workflow: canonical_product_build@1
status: running
health: Running
phase: Specification
progress: 33
blockers: 0
decisions: 0
handoffs: 0
updated: 2026-07-15T10:00:00Z
canonical_state: /absolute/path/to/run-dir
---
```

### Overview structure
```markdown
# DevFlow — Current Focus

> [!info] Health: Running · Phase: Specification · 33% complete

## Attention
- No blockers · No pending decisions · No handoffs

## Next Action
> Continue with the planning stage.

[[Workflow]] · [[Evidence]] · [[Decisions]] · [[History]]
```

### Atomic-safe markers
Each generated file gets:
```html
<!-- DEVFLOW-GENERATED:START -->
...content...
<!-- DEVFLOW-GENERATED:END -->
```

### Tests: `tests/test_obsidian_render.py`
```
test_render_overview_contains_wikilinks        # [[Workflow]], [[Evidence]], etc.
test_render_overview_front_matter_valid        # YAML parses, has all required keys
test_render_overview_progress_matches_state    # 33% when 3/9 nodes done
test_render_workflow_shows_node_status_table   # all 11 nodes present
test_render_workflow_marks_current_node        # current node has "→ current" marker
test_render_evidence_links_to_run_dir          # canonical_run_dir in link
test_render_decisions_shows_open_decisions     # decision_count > 0 renders table
test_render_decisions_empty_when_none          # "No decisions" when count=0
test_render_history_chronological              # events in order
test_all_renderers_pure_functions              # no file I/O, no side effects
```

### Verification
```bash
.venv/bin/python -m pytest tests/test_obsidian_render.py -q
```

---

## M1-S3 — Atomic vault writer (read-only-first, §10.8)

**Outcome:** Generated notes land atomically under `.generated/` without overwriting
human notes or touching canonical state.

### Files
- **NEW** `src/devflow/obsidian/vault.py`

### `write_vault_projection(vault_path, run_id, views: dict[str, str]) -> VaultWriteResult`
1. Target: `vault_path/Command Center/Projects/DevFlow/.generated/`
2. For each `(filename, markdown)` in `views`:
   - Write to `.filename.tmp`
   - `os.replace(tmp, target)` — atomic
3. Return `VaultWriteResult(files_written, bytes_written, vault_dir)`

### Guards (fail-closed)
- Only writes under `.generated/` — `Path.resolve()` check rejects anything outside
- Never calls `save_loop_state` / `advance_run` / `create_result_ref` / `record_decision`
- Idempotent: same input → identical output bytes
- Never overwrites files outside `.generated/`

### `VaultWriteResult` (frozen)
```python
class VaultWriteResult(BaseModel):  # frozen
    files_written: tuple[str, ...]
    bytes_written: int
    vault_dir: str
```

### Tests: `tests/test_obsidian_vault.py`
```
test_write_atomic_no_human_note_overwrite    # human .md in parent dir untouched
test_write_creates_generated_dir             # .generated/ created if missing
test_write_idempotent                        # re-run → identical bytes
test_write_only_in_generated                 # no files outside .generated/
test_write_preserves_existing_generated      # re-run doesn't delete other generated files
test_write_result_reports_files              # VaultWriteResult correct
test_write_rejects_traversal                  # ../../etc/passwd rejected
```

### Verification
```bash
.venv/bin/python -m pytest tests/test_obsidian_vault.py -q
```

---

## M1-S4 — CLI surface

**Outcome:** Operator can run `obsidian run <run_id> --vault <path>` to project any
canonical run into the vault.

### Files
- **NEW** `obsidian_app` Typer subcommand added to `src/devflow/cli.py`

### CLI commands
```
devflow obsidian run <run_id> [--root PATH] [--vault PATH]
    Extract + render + write the Command Center projection for one run.

devflow obsidian list [--root PATH]
    List canonical run IDs available for projection.
```

### `obsidian run` flow
1. Validate `run_id` is canonical
2. `extract_projection(root, run_id)` → `ProjectionState`
3. `render_*` for each view → `views` dict
4. `write_vault_projection(vault, run_id, views)`
5. Print summary: files written, vault path

### Tests: `tests/test_v2_cli.py` (append to existing)
```
test_obsidian_run_emits_generated          # .generated/current-focus.md exists after run
test_obsidian_run_requires_canonical_run   # non-canonical → error exit
test_obsidian_list_shows_canonical_runs    # list outputs run IDs
```

### Verification
```bash
PYTHONPATH=src .venv/bin/python -m devflow.cli obsidian --help
PYTHONPATH=src .venv/bin/python -m devflow.cli obsidian run --help
.venv/bin/python -m pytest tests/test_v2_cli.py -q
PYTHONPATH=src .venv/bin/python -m devflow.cli loop spine-fixture --json  # regression
```

---

## M1-S5 — Promotion packet materialization (honest, no invention)

**Outcome:** An inspectable `promotion-packet.md` after `accept`, derived and
non-authoritative. Never fabricates review evidence.

### Files
- **NEW** `src/devflow/obsidian/promotion_packet.py`

### `build_promotion_packet(root, run_id, decision_receipt) -> str`
Reads from the run directory:
- `fixture-spec.md` / `intent.md` → objective section
- Changed-path summary from integration receipts
- `verification-receipt-*` → deterministic verification section
- `reliability-report.json` → reliability summary
- `decision-receipts/` → decision summary

Sections:
```markdown
# Promotion Packet — <run_id>

## Objective
<from intent.md / spec>

## Changed Files
<from integration receipts — paths only>

## Deterministic Verification
<verification receipt summary: command, exit code, pass/fail>

## Independent Review
> **Not yet produced.** Independent review is part of the M4 control-plane
> milestone (see gap assessment V1). This section will be populated when the
> adversarial reviewer is implemented.

## Open Risks
<from reliability-report or "none recorded">

## Recommended Action
<accept / approve with note / return for rework — from decision_receipt.decision_type>
```

### `emit_promotion_packet(root, run_id) -> Path | None`
1. Check for accept-type `DecisionReceipt` in `decision-receipts/`
2. If found, build packet, write to run dir as `promotion-packet.md`
3. Return path or None (no accept decision yet)
4. Never overwrites an existing packet (idempotent)

### Honesty rules
- If `verification-receipt-*` is missing → section says "not available" with source ref
- If `reliability-report.json` is missing → section says "not available"
- Independent review section ALWAYS says "not yet produced" until M4 lands
- No section is ever populated with fabricated content

### Tests: `tests/test_obsidian_promotion_packet.py`
```
test_packet_declares_not_run_review           # independent review section says "not yet produced"
test_packet_includes_objective                # objective from intent.md
test_packet_includes_changed_files            # paths from integration receipts
test_packet_includes_verification_summary     # from verification receipts
test_packet_recommended_action_matches_decision  # accept → "approve"
test_packet_emitted_only_after_accept         # no accept decision → None
test_packet_idempotent                        # re-emit → same content
test_packet_does_not_invent_missing_evidence  # missing verification → "not available", not fake
test_packet_read_only                         # canonical state unchanged after emit
```

### Verification
```bash
.venv/bin/python -m pytest tests/test_obsidian_promotion_packet.py -q
```

---

## Dependency order and execution sequence

```
M0-S1 (read_model.py)
  │
  ├── M0-S2 (doc reconciliation — parallel, no code dep)
  │
  └── M1-S1 (projection.py — depends on read_model)
        │
        └── M1-S2 (render.py — depends on ProjectionState)
              │
              └── M1-S3 (vault.py — depends on renderers for content)
                    │
                    └── M1-S4 (CLI — depends on projection + render + vault)
                          │
                          └── M1-S5 (promotion_packet.py — depends on decision receipts)
```

M0-S2 can run in parallel with M1-S1 since it's a doc edit.

## Full regression gate (run after each slice)

```bash
# 1. Spine fixture (must exit 0, final_stage=complete)
PYTHONPATH=src .venv/bin/python -m devflow.cli loop spine-fixture --json

# 2. Focused new tests
.venv/bin/python -m pytest tests/test_loop_read_model.py -q         # after M0-S1
.venv/bin/python -m pytest tests/test_obsidian_projection.py -q      # after M1-S1
.venv/bin/python -m pytest tests/test_obsidian_render.py -q          # after M1-S2
.venv/bin/python -m pytest tests/test_obsidian_vault.py -q           # after M1-S3
.venv/bin/python -m pytest tests/test_v2_cli.py -q                   # after M1-S4
.venv/bin/python -m pytest tests/test_obsidian_promotion_packet.py -q # after M1-S5

# 3. Existing ledger tests (must stay green — we didn't touch the ledger)
.venv/bin/python -m pytest tests/test_workflow_ledger.py tests/test_workflow_ledger_decision.py -q

# 4. Full suite (final gate)
make verify  # or .venv/bin/python -m pytest
```

## What this delivers (acceptance criteria)

After all 7 slices:
- [ ] `src/devflow/loop/read_model.py` — one honest `CanonicalRunModel`
- [ ] `src/devflow/obsidian/` — new package with projection, render, vault, promotion_packet
- [ ] `devflow obsidian run <run_id> --vault <path>` — CLI works against any canonical run
- [ ] Generated views land in `vault/Command Center/Projects/DevFlow/.generated/`
- [ ] Promotion packet emitted after accept, honestly declares missing evidence
- [ ] Zero changes to canonical state writers
- [ ] Zero changes to existing workflow definition or ledger
- [ ] All existing tests green + all new tests green
- [ ] spine-fixture regression gate passes
