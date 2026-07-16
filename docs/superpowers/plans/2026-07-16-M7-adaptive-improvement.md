# Implementation Plan — M7: Adaptive Improvement (Final Milestone)

**Status:** Planning only. No code, tests, or config changed.
**Date:** 2026-07-16
**Baseline:** M0–M6 complete (1,303 tests green, spine-fixture green)
**Authority:** Subordinate to blueprint §12.5 (adaptive improvement under human
control), §13 (reusability), then live source/tests.

**Goal:** Close the loop. The system learns from evidence (replay benchmarks,
route-quality history) and proposes template refinements — but humans approve
every change to control logic. No self-modifying policies.

---

## What we're building on (verified live shapes)

### Workflow ledger replay (existing, `workflow_ledger.py`)
- `replay_workflow_run(root, run_id) -> WorkflowSnapshot` — deterministic replay
- `WorkflowSnapshot(workflow_id, current_node_id, stage, completed_node_ids)` — frozen
- `_replay_unlocked(run_dir)` — internal replay from events + receipts

### Existing replay tests (`test_workflow_ledger.py`)
- `test_replaying_same_ledger_is_deterministic` — replay produces identical snapshots
- `test_failure_route_replays_to_blocked` — failure paths replay correctly

### Node lifecycle (M2-S2, `node_lifecycle.py`)
- `legacy_success_replays_unchanged` / `legacy_failure_replays_unchanged` — byte-identical legacy

### Workflow library (M5-S1, `workflow_library.py`)
- `WORKFLOW_LIBRARY` — 4 family templates + Fixed member
- `get_template(id)`, `list_templates()`, `select_template(family)`

### Human decision (existing, `human_decision.py`)
- `record_operator_decision(root, receipt, repo=repo)` — Phase 6A authority

### Metrics aggregator (M5-S3, `metrics_aggregator.py`)
- `aggregate_metrics(root, run_id) -> WorkflowMetrics`

### Gates (M4-S6, `control_plane/gates.py`)
- `GateDecision`, `GateConfig`, `can_merge()`, `can_ship()`

---

## M7-S1 — Benchmark + replay suite

**Outcome:** A replay benchmark tool that runs over completed runs, replays their
ledgers, and records route-quality history. Proves that all existing runs replay
byte/semantically identically. No production writer changes — test/bench only.

### Design
A lightweight benchmark harness that:
1. Discovers all canonical pipeline runs under `.devflow/pipeline-runs/`
2. Replays each run's ledger using `replay_workflow_run()`
3. Compares the replayed snapshot against the stored snapshot (byte/semantic identity)
4. Collects route-quality metrics (duration, tokens, retries, repair rounds)
5. Produces a `ReplayBenchmarkResult` summary

### Files
- **NEW** `src/devflow/loop/replay_bench.py`
- **NEW** `tests/test_replay_benchmark.py`

### Types

```python
class RunReplayResult(BaseModel):  # frozen, extra="forbid"
    """Result of replaying one run."""
    run_id: str = Field(min_length=1)
    replay_succeeded: bool
    snapshot_matches: bool  # replayed == stored
    duration_seconds: float = 0.0
    error_message: str = ""

class ReplayBenchmarkResult(BaseModel):  # frozen, extra="forbid"
    """Aggregate result of replaying all runs."""
    total_runs: int = Field(ge=0)
    successful_replays: int = Field(ge=0)
    failed_replays: int = Field(ge=0)
    mismatched_snapshots: int = Field(ge=0)
    results: tuple[RunReplayResult, ...] = ()
    benchmark_id: str = Field(min_length=1)
    benchmarked_at: str = Field(min_length=1)
```

### Function
```python
def run_replay_benchmark(
    root: Path | str,
) -> ReplayBenchmarkResult:
    """Replay all canonical pipeline runs and verify snapshot identity.

    Returns an aggregate result. Never mutates canonical state.
    """

def discover_canonical_runs(
    root: Path | str,
) -> tuple[str, ...]:
    """Find all run IDs that have workflow snapshots."""
```

### Tests: `tests/test_replay_benchmark.py`
```
test_frozen_corpus_replays              # spine-fixture run replays identically
test_discover_canonical_runs            # finds runs with snapshots
test_replay_benchmark_empty             # no runs → zero results
test_replay_benchmark_succeeds          # successful replays counted
test_replay_snapshot_matches            # snapshot_matches True for valid runs
test_run_replay_result_records_duration # duration recorded
test_benchmark_result_frozen            # immutable
test_replay_benchmark_read_only         # run dir unchanged after benchmark
```

### Verification
```bash
.venv/bin/python -m pytest tests/test_replay_benchmark.py -q
```

---

## M7-S2 — Human-approved template refinements

**Outcome:** Proposed workflow template refinements surface for explicit human
approval. No refinement can apply without a recorded human decision. No
self-modifying policies.

### Design
A refinement is a proposed change to a workflow template (budget adjustment,
node addition/removal, phase reordering). The system proposes; humans dispose.

Three steps:
1. **Propose** — analyze run metrics and suggest refinements
2. **Present** — human-readable summary of proposed changes
3. **Apply** — only with an explicit human approval receipt

### Files
- **NEW** `src/devflow/control_plane/template_refinement.py`
- **NEW** `tests/test_template_improvement.py`

### Types

```python
class RefinementKind(str, Enum):
    """Type of proposed refinement."""
    budget_adjustment = "budget_adjustment"
    node_addition = "node_addition"
    node_removal = "node_removal"
    phase_reorder = "phase_reorder"

class TemplateRefinement(BaseModel):  # frozen, extra="forbid"
    """A proposed refinement to a workflow template."""
    refinement_id: str = Field(pattern=ID_PATTERN)
    template_id: str = Field(min_length=1)
    kind: RefinementKind
    description: str = Field(min_length=1)
    rationale: str = ""  # evidence-based rationale
    proposed_change: str = ""  # JSON-serialized delta
    confidence: float = Field(ge=0.0, le=1.0)
    schema_version: Literal[1] = 1

class RefinementApproval(BaseModel):  # frozen, extra="forbid"
    """Human approval for a proposed refinement."""
    refinement_id: str = Field(pattern=ID_PATTERN)
    template_id: str = Field(min_length=1)
    status: Literal["pending", "approved", "rejected"]
    actor: str = Field(min_length=1)  # human, never "system"
    decided_at: str | None = None
    reason: str = ""
    schema_version: Literal[1] = 1
```

### Functions

```python
def propose_refinements(
    template_id: str,
    metrics_history: tuple[WorkflowMetrics, ...],
) -> tuple[TemplateRefinement, ...]:
    """Analyze metrics and propose refinements.

    Heuristics:
    - High retry count → suggest max_repair_rounds increase
    - Long duration with low retries → suggest node parallelization
    - Frequent human interventions → suggest adding a review node
    """

def can_apply_refinement(
    approval: RefinementApproval,
) -> bool:
    """True only when status == 'approved'."""

def record_refinement_approval(
    root: Path | str,
    approval: RefinementApproval,
) -> RefinementApproval:
    """Persist approval to refinement-approvals.jsonl."""

def load_refinement_approvals(
    root: Path | str,
) -> tuple[RefinementApproval, ...]:
    """Load all approvals in append order."""
```

### Authority rules (non-negotiable)
1. `can_apply_refinement()` returns `False` unless `status == "approved"`
2. `actor` can never be `"system"` — validated by model_validator
3. Refinements are **proposals only** — they don't modify the library until approved
4. Even approved refinements produce a new template version, they never overwrite existing ones
5. No self-modifying policy — the system cannot approve its own refinements

### Refinement heuristics
- **Retry-heavy** (avg retries > 3): propose `budget_adjustment` to increase `max_repair_rounds`
- **Slow with few retries** (avg duration > 120min, avg retries < 2): propose `phase_reorder` for parallelization
- **Frequent interventions** (avg human_interventions > 1): propose `node_addition` of a review gate
- **All within norms**: no refinements proposed (empty tuple)

### Persistence
Approval events stored in `.devflow/control-plane/refinement-approvals.jsonl`.

### Tests: `tests/test_template_improvement.py`
```
test_refinement_requires_human          # can_apply False without approval
test_refinement_approved                 # approved → can_apply True
test_refinement_rejected                 # rejected → can_apply False
test_actor_cannot_be_system              # model_validator rejects "system"
test_propose_retry_heavy                 # high retries → budget_adjustment
test_propose_slow_low_retries            # slow → phase_reorder
test_propose_frequent_interventions      # interventions → node_addition
test_propose_no_refinements_normal       # normal metrics → empty
test_record_approval_persists            # saved to control-plane
test_record_approval_idempotent          # replay → idempotent
test_refinement_frozen                   # immutable
test_refinement_approval_frozen          # immutable
test_proposal_does_not_modify_library    # proposing doesn't change WORKFLOW_LIBRARY
```

### Verification
```bash
.venv/bin/python -m pytest tests/test_template_improvement.py -q
```

---

## Dependency order

```
M7-S1 (benchmark) — independent
M7-S2 (refinements) — independent (needs M5-S1 library + M5-S3 metrics)
```

Both slices can proceed in parallel, but S1 first is cleaner.

## Full regression gate (after each slice)

```bash
PYTHONPATH=src .venv/bin/python -m devflow.cli loop spine-fixture --json
.venv/bin/python -m pytest tests/test_workflow_ledger.py tests/test_node_lifecycle.py -q
.venv/bin/python -m pytest  # full suite
```

## What this delivers (acceptance criteria)

After both slices:
- [ ] Replay benchmark proves all runs replay identically
- [ ] Route-quality metrics recorded per run
- [ ] Template refinements proposed from evidence-based heuristics
- [ ] No refinement applies without explicit human approval
- [ ] `actor` can never be `"system"`
- [ ] Proposing refinements does not modify the library
- [ ] `canonical_product_build@1` still runs unchanged
- [ ] All 1,303+ existing tests green + all new tests green
- [ ] No self-modifying policies

## What this is NOT
- No automatic template updates (all human-approved)
- No self-modifying control logic (explicitly forbidden, §12.5)
- No retiring of legacy writers (migration gates F.21 must hold)
- No model-driven refinement generation (heuristics are deterministic)

## After M7 — the full DevFlow Software Factory

M7 closes the gap-closure roadmap. The system then has:
- Honest read model + Obsidian Command Center (M0/M1)
- Generalized workflow VM with schema, lifecycle, contracts, routes (M2)
- DAG scheduling + conflict-aware parallel sandboxes + patterns (M3)
- Control plane with tickets, ready queue, human gates (M4)
- Workflow families + Factory Router + metrics (M5)
- Generated workflow proposals with human approval (M6)
- Adaptive replay benchmarks + human-approved template refinements (M7)

The only explicitly postponed items (§12.5): visual workflow editor, raw-log vault
duplication, self-modifying policies, OS-level network isolation, generated-workflow
authority escalation.
