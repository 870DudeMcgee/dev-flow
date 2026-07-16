# Implementation Plan — M4: Control Plane + Ready Queue + Human Gates

**Status:** Planning only. No code, tests, or config changed.
**Date:** 2026-07-15
**Baseline:** M0 + M1 + M2 + M3 complete (1,092 tests green, spine-fixture green)
**Authority:** Subordinate to blueprint §4.1 (control plane), §5.2 (blockers/decisions/handoffs),
§9.1–9.4 (verification/repair/promotion), then live source/tests.

**Goal:** Build the control plane that owns ticket/project/milestone lifecycle, formalize
the task analyzer that drives workflow-family selection, introduce the multi-workflow
Ready Queue, add independent review + bounded repair, make Blocker/Decision/Handoff
first-class objects, and separate merge/full-verify/ship into distinct human-gated stages.

---

## What we're building on (verified live shapes)

### Pipeline run (`pipeline_run.py`)
- `create_pipeline_run(root, source)`, `load_pipeline_run(root, run_id)`, `update_pipeline_run_record()`
- Runs under `.devflow/pipeline-runs/<run_id>/`

### Ledger (`workflow_ledger.py`)
- `DecisionReceipt` (frozen) — decision_id, run_id, integration_id, decision_type, promotion_eligible
- `record_decision()` — persists immutable decision receipts
- `NodeReceipt` (frozen) — receipt_id, node_id, outcome, evidence

### Supervisor (`run_supervisor.py`)
- Hard `human_decision` boundary — stops at `phase6_reached_human_decision`
- Repeat-only: never invents commands, never self-accepts

### Result branch (`result_branch.py`)
- `create_result_ref()` — create-only `refs/heads/devflow/results/<run_id>`
- `PromotionCommand` / `PromotionReceipt` (frozen)
- Push/deploy `enabled=False` by default

### Scout discovery (`scout_discovery.py`)
- `discover_agent_scout_context()` → `AgentScoutDiscovery` (files, tests, risks, lane, verification)
- `recommended_lane` field exists but is not a typed family/approvals object

### Integration candidates (M3-S4)
- `collect_integration_candidates()` → `CandidateSummary` (dependency-ordered, verified)

---

## M4-S1 — Control plane aggregate (C1)

**Outcome:** A first-class control plane owning ticket/project/milestone/dependency state.
No autonomous promotion; reuses `result_branch.py` boundary.

### Files
- **NEW** `src/devflow/control_plane/__init__.py`
- **NEW** `src/devflow/control_plane/aggregate.py`

### Types

```python
class TicketStatus(str, Enum):
    open = "open"
    in_progress = "in_progress"
    in_review = "in_review"
    blocked = "blocked"
    merged = "merged"
    closed = "closed"

class Ticket(BaseModel):  # frozen, extra="forbid"
    ticket_id: str = Field(pattern=r"^[A-Za-z0-9][A-Za-z0-9._-]*$")
    title: str = Field(min_length=1)
    description: str = ""
    status: TicketStatus = TicketStatus.open
    project_id: str = ""
    milestone_id: str | None = None
    run_id: str | None = None  # linked pipeline run
    created_at: str  # ISO UTC
    updated_at: str  # ISO UTC

class Project(BaseModel):  # frozen, extra="forbid"
    project_id: str = Field(pattern=r"^[A-Za-z0-9][A-Za-z0-9._-]*$")
    name: str = Field(min_length=1)
    description: str = ""

class Milestone(BaseModel):  # frozen, extra="forbid"
    milestone_id: str = Field(pattern=r"^[A-Za-z0-9][A-Za-z0-9._-]*$")
    project_id: str = Field(min_length=1)
    name: str = Field(min_length=1)
    ticket_ids: tuple[str, ...] = ()

class DependencyState(BaseModel):  # frozen, extra="forbid"
    """Tracks cross-ticket dependencies."""
    ticket_id: str
    depends_on: tuple[str, ...] = ()
    blocked_by: tuple[str, ...] = ()
```

### Functions
```python
def create_ticket(root, project_id, title, description="") -> Ticket
def update_ticket_status(root, ticket_id, status) -> Ticket
def link_run_to_ticket(root, ticket_id, run_id) -> Ticket
def get_ticket(root, ticket_id) -> Ticket | None
def list_tickets(root, project_id=None) -> tuple[Ticket, ...]
```

### Storage
Tickets are persisted as JSON in `.devflow/control-plane/tickets/<ticket_id>.json`.
Projects in `.devflow/control-plane/projects/<project_id>.json`.
Atomic writes (temp + replace). No mutation of pipeline-run or ledger state.

### Tests: `tests/test_control_plane.py`
```
test_ticket_lifecycle                 # open → in_progress → in_review → merged
test_ticket_creation                  # create returns frozen Ticket
test_ticket_status_update             # update returns new Ticket with new status
test_ticket_link_run                  # link_run_to_ticket sets run_id
test_ticket_frozen                    # Ticket is immutable
test_project_creation                 # create project persists
test_milestone_creation               # milestone with ticket_ids
test_dependency_state                 # depends_on and blocked_by
test_list_tickets_by_project          # filter by project_id
test_list_tickets_all                 # all tickets
test_get_ticket_not_found             # returns None
test_no_promotion_side_effects        # no branch creation or merge
test_control_plane_separate_from_runs # tickets stored separately from pipeline-runs
```

### Verification
```bash
.venv/bin/python -m pytest tests/test_control_plane.py -q
PYTHONPATH=src .venv/bin/python -m devflow.cli loop spine-fixture --json
```

---

## M4-S2 — Task Analyzer (C3) + typed objects

**Outcome:** `discover_agent_scout_context` output formalized into a typed
`TaskAnalysis(family, risk, required_approvals)` object consumed by the compiler (M5)
and control-plane ticket contract.

### Files
- **NEW** `src/devflow/control_plane/task_analyzer.py`
- **EDIT** `src/devflow/loop/scout_discovery.py` — add a function that emits `TaskAnalysis` from scout output (additive, existing `AgentScoutDiscovery` unchanged)

### Types

```python
class WorkflowFamily(str, Enum):
    """Blueprint §8 workflow families."""
    hotfix = "hotfix"
    feature = "feature"
    bug = "bug"
    chore = "chore"
    unknown = "unknown"

class RiskLevel(str, Enum):
    low = "low"
    medium = "medium"
    high = "high"

class TaskAnalysis(BaseModel):  # frozen, extra="forbid"
    """Typed analyzer output consumed by the compiler and control plane."""
    task_id: str = Field(min_length=1)
    family: WorkflowFamily = WorkflowFamily.unknown
    risk: RiskLevel = RiskLevel.medium
    required_approvals: tuple[str, ...] = ()
    affected_areas: tuple[str, ...] = ()
    recommended_scope: str = ""
    confidence: str = "low"  # low/medium/high
```

### `analyze_task(scout_discovery, ticket) -> TaskAnalysis`
Derives family from the scout's `recommended_lane` + file patterns:
- 1-2 files, fix-oriented → hotfix
- new files, multi-module → feature
- test files, repro-oriented → bug
- lint/format/config → chore
- uncertain → unknown

Derives risk from file count + test coverage + known-risky paths.

### Tests: `tests/test_task_analyzer.py`
```
test_emits_family_and_approvals       # returns WorkflowFamily + required_approvals
test_hotfix_classification            # small fix → hotfix
test_feature_classification           # new files → feature
test_bug_classification               # test-heavy → bug
test_chore_classification             # config/lint → chore
test_unknown_when_uncertain           # ambiguous → unknown
test_risk_level_low                   # 1 file, has tests → low
test_risk_level_high                  # many files, no tests → high
test_required_approvals               # high risk → human approval required
test_task_analysis_frozen             # immutable
test_legacy_scout_output_preserved    # AgentScoutDiscovery unchanged
```

### Verification
```bash
.venv/bin/python -m pytest tests/test_task_analyzer.py -q
```

---

## M4-S3 — Ready Queue (multi-workflow)

**Outcome:** A multi-workflow Ready Queue that admits workflows only when required
gates pass and dependencies are satisfied. Distinct from `packet_dag.py` per-run
ready set (M3-S1).

### Files
- **NEW** `src/devflow/control_plane/ready_queue.py`

### Types

```python
class QueueEntry(BaseModel):  # frozen, extra="forbid"
    run_id: str = Field(min_length=1)
    ticket_id: str = Field(min_length=1)
    admitted: bool = False
    gates_passed: tuple[str, ...] = ()  # e.g. ("verification", "integration")
    dependencies_satisfied: bool = False
    admitted_at: str | None = None

class ReadyQueue(BaseModel):  # frozen, extra="forbid"
    entries: tuple[QueueEntry, ...] = ()
```

### Functions
```python
def evaluate_admission(
    root,
    run_id,
    ticket_id,
    candidate_summary: CandidateSummary,
    dependency_state: DependencyState,
) -> QueueEntry:
    """Check if a run qualifies for the ready queue."""

def admit_to_queue(queue: ReadyQueue, entry: QueueEntry) -> ReadyQueue:
    """Return a new queue with the entry admitted (if eligible)."""

def queue_order(queue: ReadyQueue) -> tuple[str, ...]:
    """Return run_ids in admission order (dependency-respecting)."""
```

### Admission rules
1. `candidate_summary.all_verified` must be True
2. `candidate_summary.ready_for_integration` must be True
3. All ticket dependencies must be satisfied (dep tickets closed/merged)
4. If any gate fails, `admitted=False` with the reason recorded

### Tests: `tests/test_ready_queue.py`
```
test_admits_only_gate_passed         # verified + deps → admitted
test_rejects_unverified              # unverified → not admitted
test_rejects_unsatisfied_deps        # open dependency → not admitted
test_queue_order_respects_deps       # dependency order preserved
test_admit_returns_new_queue         # immutable — new queue returned
test_queue_entry_frozen              # immutable
test_queue_empty                     # empty queue → empty order
test_multiple_entries                # multiple runs queued correctly
test_gates_passed_recorded           # which gates passed is recorded
```

### Verification
```bash
.venv/bin/python -m pytest tests/test_ready_queue.py -q
```

---

## M4-S4 — Independent reviewer + bounded repair loop (V1)

**Outcome:** A distinct independent reviewer (different model family) + workflow-level
repair loop with no-progress/retry bounds. This is the slice that later upgrades M1-S5's
`not_run` review fields.

### Files
- **NEW** `src/devflow/loop/independent_review.py`
- **NEW** `src/devflow/loop/repair_loop.py`

### `independent_review.py`

```python
class ReviewResult(BaseModel):  # frozen, extra="forbid"
    reviewer_id: str
    verdict: Literal["pass", "fail", "revise"]
    findings: tuple[str, ...] = ()
    reviewer_family: str = ""  # model family of the reviewer
    builder_family: str = ""   # model family of the builder
    families_independent: bool = True  # True if reviewer ≠ builder family

def select_independent_reviewer(
    builder_families: tuple[str, ...],
    available_reviewers: tuple[str, ...],  # reviewer family candidates
) -> str | None:
    """Select a reviewer whose family differs from all builder families."""

def record_review(root, run_id, result: ReviewResult) -> ReviewResult:
    """Persist review result to the run directory."""
```

### `repair_loop.py`

```python
class RepairRound(BaseModel):  # frozen, extra="forbid"
    round_number: int = Field(ge=1)
    triggered_by: str = ""  # what failed
    progress_detected: bool = False
    completed: bool = False

class RepairState(BaseModel):  # frozen, extra="forbid"
    run_id: str
    rounds: tuple[RepairRound, ...] = ()
    max_rounds: int = Field(default=4, ge=1, le=10)
    stop_if_no_progress: int = Field(default=2, ge=1, le=5)
    exhausted: bool = False

def should_continue_repair(state: RepairState) -> bool:
    """True if repair can continue (not exhausted, making progress)."""

def record_repair_round(root, run_id, round_data: RepairRound) -> RepairState:
    """Append a repair round and return updated state."""
```

### Tests: `tests/test_repair_loop.py`
```
test_no_progress_stops               # N rounds with no progress → stop
test_max_rounds_stops                # max_rounds reached → exhausted
test_progress_allows_continue        # progress detected → continue
test_select_independent_reviewer     # different family selected
test_same_family_rejected            # reviewer = builder family → None
test_review_result_frozen            # immutable
test_repair_state_frozen             # immutable
test_repair_round_appended           # round persisted
test_exhausted_when_max_reached      # exhausted=True at max_rounds
test_exhausted_when_no_progress      # exhausted=True after no_progress bound
test_record_review_persists          # review saved to run dir
```

### Verification
```bash
.venv/bin/python -m pytest tests/test_repair_loop.py -q
```

---

## M4-S5 — First-class Blocker / Decision / Handoff (V2)

**Outcome:** `Blocker` and `Handoff` become persisted first-class objects with
cause/owner/resolution + counts. `Decision` is already first-class via `DecisionReceipt`.

### Files
- **NEW** `src/devflow/loop/blocker_handoff.py`
- **EDIT** `src/devflow/loop/workflow_ledger.py` — add recorder functions for blocker/handoff (additive, never mutate `DecisionReceipt`)

### Types

```python
class BlockerReceipt(BaseModel):  # frozen, extra="forbid", schema_version=1
    blocker_id: str = Field(pattern=_ID_PATTERN)
    run_id: str = Field(pattern=_ID_PATTERN)
    node_id: str = Field(pattern=_ID_PATTERN)
    cause: str = Field(min_length=1)
    owner: str = "system"  # who must resolve
    resolution: str = ""   # empty until resolved
    resolved: bool = False
    created_at: str
    resolved_at: str | None = None
    schema_version: Literal[1] = 1

class HandoffReceipt(BaseModel):  # frozen, extra="forbid", schema_version=1
    handoff_id: str = Field(pattern=_ID_PATTERN)
    run_id: str = Field(pattern=_ID_PATTERN)
    from_node: str = Field(pattern=_ID_PATTERN)
    to_node: str = Field(pattern=_ID_PATTERN)
    artifact_refs: tuple[str, ...] = ()
    acceptance_status: str = "pending"  # pending/accepted/rejected
    created_at: str
    schema_version: Literal[1] = 1
```

### Functions
```python
def record_blocker(root, run_id, receipt: BlockerReceipt) -> BlockerReceipt
def resolve_blocker(root, run_id, blocker_id, resolution) -> BlockerReceipt
def record_handoff(root, run_id, receipt: HandoffReceipt) -> HandoffReceipt
def load_blockers(root, run_id) -> tuple[BlockerReceipt, ...]
def load_handoffs(root, run_id) -> tuple[HandoffReceipt, ...]
def blocker_count(root, run_id) -> int  # unresolved blockers
def handoff_count(root, run_id) -> int  # pending handoffs
```

### Storage
Persisted in separate files: `blocker-events.jsonl` and `handoff-events.jsonl`
in the run directory. Never touches `decision-events.jsonl` or `workflow-events.jsonl`.

### Tests: `tests/test_blocker_decision_handoff.py`
```
test_blocker_persisted_with_cause     # blocker has cause/owner/resolution
test_blocker_resolved                 # resolve_blocker sets resolved=True
test_blocker_count_unresolved         # count only unresolved blockers
test_handoff_persisted                # handoff has from/to/artifact_refs
test_handoff_acceptance               # pending → accepted
test_handoff_count_pending            # count only pending handoffs
test_blocker_frozen                   # immutable
test_handoff_frozen                   # immutable
test_decision_untouched               # DecisionReceipt unchanged
test_ledger_events_untouched          # workflow-events.jsonl unchanged
test_blocker_separate_file            # blocker-events.jsonl, not decision-events
test_blocker_count_zero_when_none     # no blockers → 0
```

### Verification
```bash
.venv/bin/python -m pytest tests/test_blocker_decision_handoff.py -q
.venv/bin/python -m pytest tests/test_workflow_ledger_decision.py -q  # legacy decision green
```

---

## M4-S6 — Distinct merge / full-verification / ship gates

**Outcome:** Merge, full-verification acceptance, and ship/deploy are three distinct
human-gated stages. Ship remains `enabled=False` by default. No autonomous promotion.

### Files
- **NEW** `src/devflow/control_plane/gates.py`

### Types

```python
class GateType(str, Enum):
    merge = "merge"
    full_verification = "full_verification"
    ship = "ship"

class GateStatus(str, Enum):
    pending = "pending"
    approved = "approved"
    rejected = "rejected"
    skipped = "skipped"

class GateDecision(BaseModel):  # frozen, extra="forbid"
    gate_type: GateType
    run_id: str
    ticket_id: str
    status: GateStatus
    actor: str  # human operator
    decided_at: str  # ISO UTC
    reason: str = ""

class GateConfig(BaseModel):  # frozen, extra="forbid"
    """Configuration for each gate type."""
    merge_enabled: bool = True
    full_verification_enabled: bool = True
    ship_enabled: bool = False  # ALWAYS False by default
```

### Functions
```python
def record_gate_decision(root, run_id, decision: GateDecision) -> GateDecision
def can_merge(gate_config: GateConfig, decisions: tuple[GateDecision, ...]) -> bool
def can_ship(gate_config: GateConfig, decisions: tuple[GateDecision, ...]) -> bool
def gate_status(decisions: tuple[GateDecision, ...], gate_type: GateType) -> GateStatus | None
```

### Rules
- `ship_enabled` defaults to `False` — the validator rejects `True` unless explicitly set
- Merge requires full-verification approved first
- Ship requires merge approved first AND ship explicitly enabled
- Each gate decision is human-authored (actor field is required, never "system")
- No gate auto-approves

### Tests: `tests/test_ship_gates.py`
```
test_ship_disabled_by_default         # ship_enabled=False in default config
test_merge_requires_full_verification # can_merge False without full_verify approved
test_ship_requires_merge              # can_ship False without merge approved
test_ship_requires_enabled            # can_ship False when ship_enabled=False
test_gate_decision_persisted          # decision saved to run dir
test_gate_decision_human_actor        # actor is required, not "system"
test_gate_decision_frozen             # immutable
test_gate_status_pending              # gate with no decision → None
test_gate_status_approved             # approved decision → approved
test_full_verification_independent    # full_verify gate is separate from merge
test_gate_config_frozen               # immutable
test_gate_config_rejects_ship_true    # ship_enabled=True in default → rejected
```

### Verification
```bash
.venv/bin/python -m pytest tests/test_ship_gates.py -q
```

---

## Dependency order

```
M4-S1 (control plane aggregate)
  │
  ├── M4-S2 (task analyzer — needs ticket contract)
  │
  ├── M4-S5 (blocker/handoff — needs run_id linkage)
  │
  └── M4-S3 (ready queue — needs control plane + candidates)
        │
        └── M4-S6 (gates — needs ready queue)

M4-S4 (repair loop + independent review — independent of S1-S3, needs M3-S2)
```

Recommended build order: **S1 → S2 → S5 → S4 → S3 → S6**

## Full regression gate (after each slice)

```bash
PYTHONPATH=src .venv/bin/python -m devflow.cli loop spine-fixture --json
.venv/bin/python -m pytest tests/test_workflow_ledger.py tests/test_workflow_ledger_decision.py -q
.venv/bin/python -m pytest tests/test_loop_read_model.py tests/test_obsidian_projection.py -q
.venv/bin/python -m pytest tests/test_dag_scheduler.py tests/test_conflict_scheduling.py -q
.venv/bin/python -m pytest  # full suite
```

## What this delivers (acceptance criteria)

After all 6 slices:
- [ ] First-class control plane: Ticket/Project/Milestone/DependencyState
- [ ] Task Analyzer emitting typed WorkflowFamily + RiskLevel + required_approvals
- [ ] Multi-workflow Ready Queue with gate-pass + dependency-satisfied admission
- [ ] Independent reviewer (different model family) + bounded repair loop
- [ ] First-class Blocker/Decision/Handoff with counts
- [ ] Distinct merge/full-verification/ship gates; ship disabled by default
- [ ] `canonical_product_build@1` still runs unchanged
- [ ] `DecisionReceipt` and `NodeReceipt` never mutated
- [ ] No autonomous promotion/push/merge/ship
- [ ] All 1,092+ existing tests green + all new tests green
- [ ] All types use functional role names only
