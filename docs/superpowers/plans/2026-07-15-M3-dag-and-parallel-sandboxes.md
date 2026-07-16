# Implementation Plan — M3: Per-Run DAG + Conflict-Aware Parallel Sandboxes

**Status:** Planning only. No code, tests, or config changed.
**Date:** 2026-07-15
**Baseline:** M0 + M1 + M2 complete (1,011 tests green, spine-fixture green)
**Authority:** Subordinate to blueprint §6.5 (runtime primitives), §7.5 (conflict-aware
parallelism), §8.5 (orchestration patterns), then live source/tests.

**Goal:** Enable independent workflow slices to run concurrently in isolated sandboxes,
respecting dependency, file, resource, and semantic conflicts — and produce verified,
dependency-ordered integration candidates. **No multi-workflow Ready Queue here** (deferred
to M4-S3 per D.14).

---

## What we're building on (verified live shapes)

### Packet DAG (`packet_dag.py` — 81 lines)
- `PacketState`: pending / succeeded / failed
- `validate_packet_dag(packets)` — checks unique IDs, known dependencies, no cycles
- `ready_packet_ids(packets, states)` — returns pending packets whose dependencies all succeeded

### ExecutionPacket (`execution_plan.py:53`)
- `id: str`, `target_files: list[str]`, `depends_on: list[str]`
- Frozen, validated (no self-dependency, unique target_files, unique deps)

### Node lifecycle (M2-S2, `node_lifecycle.py`)
- `NodeState`: planned / ready / running / verified / retrying / blocked / awaiting_gate / failed / cancelled
- `record_lifecycle_event()`, `load_lifecycle_events()`, `get_current_node_state()`

### Workflow schema (M2-S1, `workflow_schema.py`)
- `WorkflowStrategy`: sequence / parallel / dag / loop / conditional
- `BudgetPolicy.heavy_model_slots` (default 1)
- `NodeKind`: gate / human_gate / artifact_emit (new kinds)

### Integration (`run_integration.py`)
- `IntegrationSnapshot` — integration_id, sandbox_id, base_commit, integration_order, applied_packet_ids, head, tree, fingerprint, conflict_id
- `IntegrationVerificationReceipt` — model-family non-overlap enforcement
- `conflicting_paths` field on integration events

---

## M3-S1 — Per-run phase DAG scheduler

**Outcome:** A run's nodes release per dependency edges + per-node lifecycle states,
within one run. This is the **generalized** scheduler — it works on any DAG of
nodes with dependency edges, not just the existing fixed packet DAG.

### Design distinction from packet_dag.py
`packet_dag.py` operates on `ExecutionPacket` objects (file-producing build slices).
The new `dag_scheduler.py` operates on **workflow nodes** — any node in a
`WorkflowSchemaV2` graph. It uses `NodeState` from M2-S2 instead of `PacketState`.

The two coexist: `packet_dag` remains the packet-level ready-set authority;
`dag_scheduler` is the workflow-node-level scheduler.

### Files
- **NEW** `src/devflow/loop/dag_scheduler.py`

### Types

```python
class SchedulerNode(BaseModel):  # frozen, extra="forbid"
    """One node in the scheduler's view of a workflow DAG."""
    node_id: str
    depends_on: tuple[str, ...] = ()
    target_files: tuple[str, ...] = ()  # for file-conflict detection (M3-S2)

class SchedulerState(BaseModel):  # frozen, extra="forbid"
    """Immutable snapshot of all node states at one point in time."""
    node_states: dict[str, NodeState]  # node_id → current lifecycle state
```

### Functions

```python
def compute_ready_set(
    nodes: Sequence[SchedulerNode],
    states: Mapping[str, NodeState],
) -> tuple[str, ...]:
    """Return node_ids that are planned/ready and whose dependencies are all verified."""

def validate_dag(nodes: Sequence[SchedulerNode]) -> tuple[SchedulerNode, ...]:
    """Validate unique IDs, known deps, no cycles. Return stable order."""

def can_advance(
    node_id: str,
    nodes: Sequence[SchedulerNode],
    states: Mapping[str, NodeState],
) -> bool:
    """True if a single node's dependencies are satisfied and it's not terminal."""
```

### Ready-set rules
A node is ready when:
1. Its state is `planned` or `ready` (not running/terminal)
2. All nodes in `depends_on` are in `verified` state
3. (M3-S2 adds: no resource or semantic conflict blocks it)

### Tests: `tests/test_dag_scheduler.py`
```
test_ready_set_respects_edges           # A→B→C: only A ready initially
test_ready_set_after_a_verified         # A verified → B ready
test_ready_set_parallel_branches        # A→{B,C}: B and C both ready after A
test_ready_set_empty_when_all_terminal  # all verified → empty ready set
test_validate_dag_rejects_cycle         # cycle → ValueError
test_validate_dag_rejects_unknown_dep   # unknown dependency → ValueError
test_validate_dag_rejects_duplicate_ids # duplicate node IDs → ValueError
test_can_advance_single_node            # can_advance true when deps met
test_can_advance_false_when_dep_pending # can_advance false when dep not verified
test_can_advance_false_when_terminal    # terminal node → false
test_diamond_dependency                 # A→B,C→D: D ready only after B AND C verified
test_ready_set_excludes_blocked         # blocked node not in ready set
test_ready_set_stable_order             # deterministic ordering
```

### Verification
```bash
.venv/bin/python -m pytest tests/test_dag_scheduler.py -q
PYTHONPATH=src .venv/bin/python -m devflow.cli loop spine-fixture --json
```

---

## M3-S2 — Resource + semantic conflict scheduling (§7.5)

**Outcome:** The scheduler honors `heavy_model_slots` (resource conflicts) and
semantic conflicts (shared design decisions) in addition to dependency + file conflicts.

### Conflict types (blueprint §7.5)

| Type | Rule |
|------|------|
| Dependency | Node can't start until dependencies are verified (M3-S1) |
| File | Nodes with overlapping `target_files` serialize or use separate worktrees |
| Resource | Scheduler respects `heavy_model_slots` — at most N heavy models resident |
| Semantic | Nodes sharing an unfrozen design decision/schema/API wait |

### Files
- **NEW** `src/devflow/loop/conflict_rules.py`

### Types

```python
class ConflictType(str, Enum):
    dependency = "dependency"
    file = "file"
    resource = "resource"
    semantic = "semantic"

class ConflictResult(BaseModel):  # frozen, extra="forbid"
    """Result of checking conflicts for a candidate ready node."""
    node_id: str
    has_conflict: bool
    conflict_type: ConflictType | None = None
    conflicting_with: tuple[str, ...] = ()  # node_ids causing the conflict
    reason: str = ""

class ResourceBudget(BaseModel):  # frozen, extra="forbid"
    """Available resources for scheduling decisions."""
    heavy_model_slots: int = Field(default=1, ge=0, le=4)
    heavy_model_in_use: int = Field(default=0, ge=0, le=4)
```

### Functions

```python
def check_file_conflicts(
    candidate: SchedulerNode,
    running_nodes: Sequence[SchedulerNode],
) -> ConflictResult:
    """Check if candidate's target_files overlap with any running node's."""

def check_resource_conflict(
    candidate_route: str,  # capability route (heavy or light)
    budget: ResourceBudget,
) -> ConflictResult:
    """Check if a heavy candidate exceeds available heavy_model_slots."""

def check_semantic_conflicts(
    candidate: SchedulerNode,
    running_nodes: Sequence[SchedulerNode],
    semantic_groups: Mapping[str, set[str]],  # group_name → node_ids sharing a decision
) -> ConflictResult:
    """Check if candidate shares an unfrozen semantic group with running nodes."""

def apply_conflict_filters(
    ready_nodes: Sequence[str],
    all_nodes: Mapping[str, SchedulerNode],
    running_nodes: Sequence[SchedulerNode],
    budget: ResourceBudget,
    node_routes: Mapping[str, str],  # node_id → capability route
    semantic_groups: Mapping[str, set[str]],
) -> tuple[str, ...]:
    """Filter a ready set through all conflict rules. Return schedulable nodes."""
```

### Tests: `tests/test_conflict_scheduling.py`
```
test_file_conflict_detected            # overlapping target_files → conflict
test_no_file_conflict_disjoint_paths   # disjoint paths → no conflict
test_resource_slot_respected           # two heavy nodes, 1 slot → serialize
test_resource_slot_available           # 1 heavy running, 2 slots → second allowed
test_semantic_conflict_detected        # shared semantic group → wait
test_semantic_conflict_none_when_group_empty  # no groups → no conflict
test_apply_filters_all_clear           # no conflicts → all pass
test_apply_filters_file_conflict       # file conflict removes node from schedulable set
test_apply_filters_resource_conflict   # resource conflict removes node
test_apply_filters_semantic_conflict   # semantic conflict removes node
test_dependency_conflict_implicit      # dependency conflicts handled by M3-S1, not here
```

### Verification
```bash
.venv/bin/python -m pytest tests/test_conflict_scheduling.py -q
```

---

## M3-S3 — Reusable orchestration patterns (§8.5)

**Outcome:** Five composable pattern builders that produce valid workflow subgraphs
following blueprint §8.5. These are **schema-level builders** — they compose nodes
and edges into reusable shapes, no new runtime.

### The five patterns (blueprint §8.5)

| Pattern | Shape |
|---------|-------|
| Scatter–gather | N independent readers → 1 synthesizer |
| Competing proposals | M planners propose → 1 judge selects/merges |
| Adversarial verification | 1 builder → 1 reviewer tries to disprove |
| Map–verify–reduce | Fan-out over items, each verified, then reduced |
| Convergence loop | Check → repair → recheck until pass or bound |

### Files
- **NEW** `src/devflow/loop/patterns.py`

### Types

```python
class PatternSpec(BaseModel):  # frozen, extra="forbid"
    """Specification for one pattern instance."""
    pattern_id: str
    kind: str  # "scatter_gather" | "competing" | "adversarial" | "map_verify_reduce" | "convergence"
    node_prefix: str  # prefix for generated node IDs
    participant_roles: tuple[str, ...] = ()  # functional role names only
    config: dict = {}  # pattern-specific config

class PatternResult(BaseModel):  # frozen, extra="forbid"
    """Result of building a pattern — nodes and edges to insert."""
    nodes: tuple[WorkflowNode, ...]
    edges: tuple[WorkflowEdge, ...]
    entry_node_id: str  # first node to execute
    exit_node_id: str   # last node (or gather/reduce/judge)
```

### Builders

```python
def build_scatter_gather(spec: PatternSpec) -> PatternResult:
    """N independent investigators → 1 synthesizer."""

def build_competing(spec: PatternSpec) -> PatternResult:
    """M planners propose → 1 judge selects."""

def build_adversarial(spec: PatternSpec) -> PatternResult:
    """Builder → adversarial reviewer."""

def build_map_verify_reduce(spec: PatternSpec) -> PatternResult:
    """Fan-out over items, each verified, then reduced."""

def build_convergence(spec: PatternSpec) -> PatternResult:
    """Check → repair → recheck loop with bounds."""

def build_pattern(spec: PatternSpec) -> PatternResult:
    """Dispatch to the correct builder by spec.kind."""
```

### Tests: `tests/test_orchestration_patterns.py`
```
test_scatter_gather_composes           # N readers → synthesizer, valid edges
test_scatter_gather_entry_exit         # entry = first reader, exit = synthesizer
test_competing_composes                # M planners → judge, valid edges
test_competing_judge_is_exit           # judge is the exit node
test_adversarial_composes              # builder → reviewer, valid edges
test_adversarial_reviewer_after_builder  # reviewer depends on builder
test_map_verify_reduce_composes        # fan-out → verify → reduce
test_convergence_composes              # check → repair → recheck
test_convergence_has_loop_bounds       # convergence includes max_rounds
test_build_pattern_dispatches          # build_pattern routes by kind
test_unknown_pattern_raises            # unknown kind → ValueError
test_pattern_nodes_use_functional_roles  # no model names in generated nodes
test_pattern_result_validates_as_workflow  # output nodes/edges pass validate_references
```

### Verification
```bash
.venv/bin/python -m pytest tests/test_orchestration_patterns.py -q
```

---

## M3-S4 — Verified integration candidates (Q1 partial; no ready queue)

**Outcome:** Verified slices are prepared as integration candidates in dependency
order. This is a **read-only summary** — no new queue state, no multi-workflow
queue (that's M4-S3).

### Files
- **NEW** `src/devflow/loop/integration_candidates.py` (separate from the complex `run_integration.py`)

### Types

```python
class IntegrationCandidate(BaseModel):  # frozen, extra="forbid"
    """One verified slice ready for integration, in dependency order."""
    packet_id: str
    target_files: tuple[str, ...]
    depends_on: tuple[str, ...]
    verified: bool
    integration_order_index: int  # position in dependency-ordered sequence

class CandidateSummary(BaseModel):  # frozen, extra="forbid"
    """Read-only summary of all integration candidates for a run."""
    run_id: str
    candidates: tuple[IntegrationCandidate, ...]
    all_verified: bool  # True when every candidate is verified
    ready_for_integration: bool  # True when all deps satisfied + all verified
```

### Function

```python
def collect_integration_candidates(
    root: Path | str,
    run_id: str,
) -> CandidateSummary:
    """Collect verified slices as dependency-ordered integration candidates.

    Reads execution plan + packet states + verification receipts.
    Returns a read-only summary — no mutation, no queue state.
    Ship/merge remain gated (enabled=False).
    """
```

### Implementation approach
1. Load `execution-plan.json` from the run directory
2. Get packets from the plan
3. For each packet: check if it has a verification receipt (verified)
4. Sort by dependency order (topological sort using `validate_packet_dag`)
5. Build `CandidateSummary` with `all_verified` and `ready_for_integration`
6. Return summary — never mutate, never queue

### Tests: `tests/test_integration_candidates.py`
```
test_candidates_dependency_ordered      # candidates returned in dep order
test_candidates_all_verified           # all packets verified → all_verified=True
test_candidates_partial_verified       # some unverified → all_verified=False
test_candidates_empty_plan             # no packets → empty candidates
test_candidates_single_packet          # one packet → one candidate, order 0
test_ready_for_integration_true        # all verified + deps satisfied → True
test_ready_for_integration_false       # unverified packet → False
test_read_only_no_mutation             # run dir unchanged after collect
test_candidates_include_target_files   # each candidate has its target_files
```

### Verification
```bash
.venv/bin/python -m pytest tests/test_integration_candidates.py -q
```

---

## Dependency order

```
M3-S1 (DAG scheduler) → {M3-S2 (conflict rules), M3-S3 (patterns)}
M3-S2 → M3-S4 (integration candidates)
```

- M3-S2 and M3-S3 depend on M3-S1 but are independent of each other
- M3-S4 depends on M3-S2 (needs conflict-aware ordering)

## Full regression gate (after each slice)

```bash
PYTHONPATH=src .venv/bin/python -m devflow.cli loop spine-fixture --json
.venv/bin/python -m pytest tests/test_workflow_ledger.py tests/test_node_lifecycle.py -q
.venv/bin/python -m pytest tests/test_loop_read_model.py tests/test_obsidian_projection.py -q
.venv/bin/python -m pytest  # full suite
```

## What this delivers (acceptance criteria)

After all 4 slices:
- [ ] Per-run DAG scheduler computing ready sets from node dependencies + lifecycle
- [ ] File / resource / semantic conflict detection with configurable budgets
- [ ] Five composable orchestration patterns as schema-level builders
- [ ] Verified integration candidates collected in dependency order (read-only)
- [ ] `canonical_product_build@1` still runs unchanged
- [ ] No multi-workflow Ready Queue (deferred to M4-S3)
- [ ] No autonomous promotion
- [ ] All 1,011+ existing tests green + all new tests green
- [ ] All types use functional role names only (naming rule)
