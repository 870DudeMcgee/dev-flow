# Implementation Plan — M2: Generalized Workflow VM Contracts (Schema-First)

**Status:** Planning only. No code, tests, or config changed.
**Date:** 2026-07-15
**Baseline:** M0 + M1 complete (912 tests green, spine-fixture green)
**Authority:** Subordinate to blueprint §6.4–6.6, §7.1–7.5, then live source/tests, then DEVFLOW_SOURCE_OF_TRUTH.md.

**Goal:** Transform the workflow runtime from a single fixed linear chain into a
real VM with versioned schema, full primitive set, per-node lifecycle, enforced
agent contracts, and typed capability routes. Executable executors land *after*
the schema/validator. All existing primitives are preserved and generalized —
nothing is rewritten.

---

## What we're building on (verified live shapes)

### Current workflow definition (`workflow_definition.py`)
- `NodeKind` = {human, agent, code} — executable node kinds only
- `WorkflowNode` — id, kind, stage, required_evidence (frozen, extra="forbid")
- `WorkflowEdge` — id, source, target, outcome: "success"|"failure" (frozen)
- `WorkflowDefinition` — workflow_id (literal "canonical_product_build@1"), nodes, edges
- `validate_references()` — checks: unique IDs, known nodes, duplicate routes, cycles, terminal completeness, evidence uniqueness
- `canonical_product_build_v1()` — the one fixed 11-node linear chain

### Current roles (`roles.py`)
- `RoleDefinition` (frozen dataclass) — name, description, required_capabilities, preferred_cost_classes, preferred_transports, output_size, reasoning, fallbacks
- 7 roles: brainstorm, planner, planning_judge, builder, build_judge, verifier, final_judge
- **Missing from blueprint §7.1:** allowed/forbidden actions, evidence rules, completion/failure conditions, handoff contract, resource profile

### Current routing (`routing.py`)
- `ResolvedSlot` with `resolved_via` provenance ("audition_override" | "override" | "profile" | "auto")
- `resolve_role()` / `resolve_role_compatible()`
- **Missing from blueprint §7.4:** the 6 named capability routes

### Current ledger (`workflow_ledger.py`)
- `NodeReceipt` — receipt_id, node_id, outcome: "success"|"failure", evidence (frozen)
- `WorkflowSnapshot` — workflow_id, current_node_id, stage, completed_node_ids (frozen)
- `record_node_outcome()`, `replay_workflow_run()`, `rebuild_workflow_snapshot()`

### Naming rule (user directive)
Workers identified by functional role ONLY (Orchestrator, Planner, Builder, Verifier,
Judge, Reviewer, Research Agent, Human Operator). Model names NEVER appear in primary
UI, contracts, or handoffs. Model details live behind technical inspection controls.

---

## M2-S1 — Versioned workflow schema + validator

**Outcome:** A versioned workflow schema with `WorkflowStrategy` (composition) separated
from `NodeKind` (execution), plus extended validation for budgets, gates, loops, and
promotion policy. The legacy `canonical_product_build@1` still validates unchanged.

### Design decision (D.13): composition vs execution
Separate two concerns:
- **Composition strategy** (`WorkflowStrategy`): how nodes are organized — sequence, parallel, dag, loop, conditional. This is a property of the workflow or phase, not the node.
- **Executable node kind** (`NodeKind`): what a node does — human, agent, code, gate, human_gate, artifact_emit. Extended from the current {human, agent, code}.

### Files
- **NEW** `src/devflow/loop/workflow_schema.py` — versioned schema (v1 → v2 additive)
- **EDIT** `src/devflow/loop/workflow_definition.py` — add `WorkflowStrategy` enum, extend `NodeKind` with gate/human_gate/artifact_emit (additive), add optional `strategy` field to `WorkflowDefinition`

### New types in `workflow_schema.py`

```python
class WorkflowVersion(str, Enum):
    v1 = "v1"  # canonical_product_build@1 (legacy, no strategy field)
    v2 = "v2"  # generalized (strategy + budgets + gates + loops)

class WorkflowStrategy(str, Enum):
    """How nodes within a phase or workflow are composed."""
    sequence = "sequence"
    parallel = "parallel"
    dag = "dag"
    loop = "loop"
    conditional = "conditional"

class LoopPolicy(BaseModel):  # frozen, extra="forbid"
    """Bounds for a loop strategy — required when strategy=loop."""
    max_rounds: int = Field(ge=1, le=20)
    stop_if_no_progress: int = Field(ge=1, le=10)  # stop after N rounds with no progress

class BudgetPolicy(BaseModel):  # frozen, extra="forbid"
    """Resource budgets for a workflow."""
    max_runtime_minutes: int = Field(default=180, ge=1, le=1440)
    max_agent_runs: int = Field(default=30, ge=1, le=200)
    max_repair_rounds: int = Field(default=4, ge=0, le=10)
    heavy_model_slots: int = Field(default=1, ge=0, le=4)

class PromotionPolicy(BaseModel):  # frozen, extra="forbid"
    """Human authority over promotion."""
    human_required: bool = True
    auto_promote: bool = False  # ALWAYS False for now

class WorkflowSchemaV2(BaseModel):  # frozen, extra="forbid"
    """Versioned generalized workflow schema."""
    version: Literal["v2"]
    workflow_id: str = Field(min_length=1)
    strategy: WorkflowStrategy = WorkflowStrategy.sequence
    loop_policy: LoopPolicy | None = None  # required if strategy=loop
    budget: BudgetPolicy = Field(default_factory=BudgetPolicy)
    promotion: PromotionPolicy = Field(default_factory=PromotionPolicy)
    nodes: tuple[WorkflowNode, ...] = Field(min_length=1)
    edges: tuple[WorkflowEdge, ...]
    phases: tuple[PhaseDefinition, ...] = ()  # optional phase grouping

class PhaseDefinition(BaseModel):  # frozen, extra="forbid"
    """A named group of nodes with its own composition strategy."""
    id: str = Field(min_length=1)
    strategy: WorkflowStrategy = WorkflowStrategy.sequence
    node_ids: tuple[str, ...] = Field(min_length=1)
    loop_policy: LoopPolicy | None = None
```

### Extended `NodeKind` (additive, in `workflow_definition.py`)
```python
class NodeKind(str, Enum):
    # Existing (preserved)
    human = "human"
    agent = "agent"
    code = "code"
    # New (additive)
    gate = "gate"              # deterministic pass/fail/revise/escalate
    human_gate = "human_gate"  # pause for operator approval
    artifact_emit = "artifact_emit"  # persist typed artifact
```

### Validator: `validate_workflow_schema(definition, version) -> None`
Extended checks beyond `validate_references`:
1. If strategy=loop, `loop_policy` must be present with valid bounds
2. Budget fields within allowed ranges
3. Promotion policy: `auto_promote` must be False (no autonomous promotion)
4. If phases defined: every node must belong to exactly one phase; phase node_ids must reference real nodes
5. `gate` and `human_gate` nodes must have defined gate outcome types
6. All existing `validate_references` checks still pass

### Tests: `tests/test_workflow_schema.py`
```
test_v1_legacy_validates_unchanged       # canonical_product_build@1 passes v1 validator
test_v2_sequence_validates               # simple v2 sequence graph validates
test_v2_rejects_unbounded_loop           # strategy=loop without loop_policy → ValueError
test_v2_loop_with_policy_validates       # strategy=loop + loop_policy → valid
test_v2_rejects_auto_promote             # auto_promote=True → ValueError
test_v2_budget_range_enforced            # max_runtime_minutes=0 or 9999 → ValueError
test_v2_phase_node_coverage              # phase missing a node → ValueError
test_v2_phase_unknown_node               # phase references nonexistent node → ValueError
test_v2_new_node_kinds_valid             # gate/human_gate/artifact_emit accepted
test_v2_gate_node_validates              # gate node with outcomes validates
test_v1_and_v2_coexist                   # both versions importable, no conflict
test_strategy_enum_values                # sequence/parallel/dag/loop/conditional
```

### Verification
```bash
.venv/bin/python -m pytest tests/test_workflow_schema.py -q
PYTHONPATH=src .venv/bin/python -m devflow.cli loop spine-fixture --json  # v1 still works
.venv/bin/python -m pytest tests/test_workflow_ledger.py -q  # legacy ledger unaffected
```

---

## M2-S2 — Node lifecycle state machine (additive, never replaces NodeReceipt)

**Outcome:** A per-node lifecycle with defined states and transitions, recorded
*alongside* the existing `NodeReceipt` (which is never mutated). Legacy
success/failure receipts replay byte-identically.

### Design principle: additive, versioned, backward-compatible
- `NodeReceipt` stays frozen and immutable — never replaced
- New `NodeLifecycleReceipt` is recorded *alongside* NodeReceipt
- Legacy receipts replay byte/semantically identical
- New lifecycle is additive: old runs without lifecycle events still work

### Files
- **NEW** `src/devflow/loop/node_lifecycle.py` — `NodeState` enum, `NodeLifecycleReceipt`, lifecycle recorder
- **NEW** `tests/fixtures/legacy_receipts/` — replay fixtures for legacy success/failure receipts
- **EDIT** `src/devflow/loop/workflow_ledger.py` — add lifecycle recorder alongside `record_node_outcome` (never mutate NodeReceipt path)

### New types in `node_lifecycle.py`

```python
class NodeState(str, Enum):
    """Per-node lifecycle states (blueprint §5.1)."""
    planned = "planned"
    ready = "ready"
    running = "running"
    verified = "verified"
    retrying = "retrying"
    blocked = "blocked"
    awaiting_gate = "awaiting_gate"
    failed = "failed"
    cancelled = "cancelled"

class WorkflowTerminalState(str, Enum):
    """Workflow-level terminal states."""
    completed = "completed"
    awaiting_promotion = "awaiting_promotion"
    needs_rework = "needs_rework"
    failed = "failed"
    cancelled = "cancelled"
    shipped = "shipped"

class NodeLifecycleReceipt(BaseModel):  # frozen, extra="forbid"
    """Versioned, additive lifecycle event — never replaces NodeReceipt."""
    lifecycle_id: str = Field(pattern=r"^[A-Za-z0-9][A-Za-z0-9._:-]*$")
    node_id: str = Field(pattern=r"^[A-Za-z0-9][A-Za-z0-9._:-]*$")
    run_id: str = Field(pattern=r"^[A-Za-z0-9][A-Za-z0-9._:-]*$")
    from_state: NodeState
    to_state: NodeState
    timestamp: str  # ISO UTC
    evidence_ref: str | None = None  # optional link to NodeReceipt
    schema_version: Literal[1] = 1
```

### Lifecycle transitions (validated)
```
planned → ready                    (dependencies satisfied)
ready → running                    (worker claimed)
running → verified                 (success)
running → retrying                 (failure, within bounds)
running → failed                   (failure, bounds exhausted)
running → blocked                  (dependency/resource/policy issue)
running → awaiting_gate            (needs human approval)
awaiting_gate → running            (approved)
awaiting_gate → failed             (rejected/cancelled)
retrying → running                 (retry dispatched)
retrying → failed                  (bounds exhausted)
blocked → ready                    (blocker resolved)
verified → (terminal for this node)
failed → (terminal for this node)
cancelled → (terminal for this node)
```

### `record_lifecycle_event(root, run_id, receipt)` — in node_lifecycle.py
1. Validate transition is legal per the transition map
2. Append to `node-lifecycle-events.jsonl` in the run directory
3. Never touches `NodeReceipt`, `WorkflowEvent`, or the existing ledger

### Legacy replay compatibility
The recorder detects whether a run has lifecycle events. If not (legacy run),
the existing `NodeReceipt` success/failure maps cleanly:
- `success` → `verified`
- `failure` → `failed` (or `retrying` if within bounds)

This mapping is read-only — it never mutates the legacy receipt.

### Tests: `tests/test_node_lifecycle.py`
```
test_legacy_success_replays_unchanged    # NodeReceipt bytes identical after lifecycle module
test_legacy_failure_replays_unchanged    # same for failure receipts
test_lifecycle_planned_to_ready          # legal transition
test_lifecycle_running_to_verified       # legal transition
test_lifecycle_illegal_transition        # planned → verified → ValueError
test_lifecycle_receipt_appended          # lifecycle event in jsonl, NodeReceipt untouched
test_lifecycle_receipt_frozen            # immutable
test_legacy_success_maps_to_verified     # read-only mapping: success→verified
test_legacy_failure_maps_to_failed       # read-only mapping: failure→failed
test_workflow_terminal_states            # completed/awaiting_promotion/etc are valid enums
test_lifecycle_does_not_mutate_ledger    # workflow-events.jsonl unchanged
```

### Verification
```bash
.venv/bin/python -m pytest tests/test_node_lifecycle.py -q
.venv/bin/python -m pytest tests/test_workflow_ledger.py tests/test_workflow_ledger_decision.py -q  # legacy ledger green
PYTHONPATH=src .venv/bin/python -m devflow.cli loop spine-fixture --json
```

---

## M2-S3 — Agent contract schema + enforcement (§7.1–7.2)

**Outcome:** `RoleDefinition` carries the full blueprint §7.1 contract fields
(allowed/forbidden/inputs/outputs/evidence_rules/completion/failure/handoff/resource),
enforced per node at authorization time. Existing roles remain backward compatible.

### Files
- **EDIT** `src/devflow/loop/roles.py` — add contract fields to `RoleDefinition` (additive, all optional with defaults)
- **EDIT** `src/devflow/loop/execution_authorization.py` — enforce allowed/forbidden + evidence rules
- **NEW** `tests/test_agent_contracts.py`

### Extended `RoleDefinition` (additive fields, all optional)

```python
@dataclass(frozen=True)
class AgentContract(BaseModel):  # frozen, extra="forbid"
    """Blueprint §7.1 typed agent contract."""
    allowed_actions: tuple[str, ...] = ()      # e.g., ("read", "write:workspace", "search")
    forbidden_actions: tuple[str, ...] = ()    # e.g., ("modify:main_branch", "network")
    required_inputs: tuple[str, ...] = ()      # artifact keys that must exist before execution
    required_outputs: tuple[str, ...] = ()     # schema/file keys the node must emit
    evidence_rules: tuple[str, ...] = ()       # e.g., ("cite_file_paths", "mark_uncertainty")
    completion_conditions: tuple[str, ...] = () # observable conditions meaning done
    failure_conditions: tuple[str, ...] = ()   # known reasons to stop/escalate
    handoff_contract: str | None = None        # which downstream consumer gets what artifact
    resource_profile: ResourceProfile | None = None

class ResourceProfile(BaseModel):  # frozen, extra="forbid"
    """Blueprint §7.1 resource profile."""
    context_size: str = "medium"  # small/medium/large
    expected_duration_minutes: int = Field(default=5, ge=1, le=120)
    model_class: str = "any"      # any/local/cloud/frontier
    memory_needs: str = "normal"  # normal/heavy
    retry_policy: str = "bounded" # bounded/none
```

### `RoleDefinition` gains an optional `contract: AgentContract | None = None`
Existing roles get `contract=None` → fully backward compatible. New roles or
updated roles populate the contract.

### Enforcement in `execution_authorization.py`
Add a check in `authorize_execution()`:
1. If the node's role has a contract with `forbidden_actions`, reject any requested action that matches
2. If the contract has `required_inputs`, verify those artifact keys exist in the run directory
3. If the contract has `evidence_rules`, they become advisory metadata on the receipt (not a hard block in M2 — enforcement hardens in M4)

### Tests: `tests/test_agent_contracts.py`
```
test_role_without_contract_loads          # existing roles still work (contract=None)
test_role_with_contract_loads             # new role with full contract loads
test_forbidden_action_blocked             # authorization rejects forbidden action
test_allowed_action_passes                # authorization allows explicitly allowed action
test_missing_required_input_blocked       # required_inputs absent → reject
test_required_input_present_passes        # required_inputs present → allow
test_contract_frozen                      # AgentContract is immutable
test_resource_profile_defaults            # ResourceProfile has correct defaults
test_evidence_rules_advisory              # evidence_rules attached to receipt metadata
test_handoff_contract_stored              # handoff_contract accessible
test_legacy_roles_backward_compatible     # all 7 existing roles load without contract
```

### Verification
```bash
.venv/bin/python -m pytest tests/test_agent_contracts.py -q
.venv/bin/python -m pytest tests/test_capability_routing.py -q  # existing routing tests green
```

---

## M2-S4 — Six capability routes (§7.4)

**Outcome:** The 6 blueprint capability routes are typed as an enum.
`resolve_role` records which route was used as provenance. Existing resolution
machinery unchanged for current callers.

### Files
- **NEW** `src/devflow/loop/capability_routes.py` — `CapabilityRoute` enum + role→route mapping
- **EDIT** `src/devflow/loop/routing.py` — add route provenance to `ResolvedSlot` (additive field)
- **NEW** `tests/test_capability_routes.py`

### `CapabilityRoute` enum (blueprint §7.4)

```python
class CapabilityRoute(str, Enum):
    """Provider-independent capability routes (blueprint §7.4)."""
    repository_analysis = "repository_analysis"
    deep_planning = "deep_planning"
    bounded_coding = "bounded_coding"
    independent_review = "independent_review"
    frontier_judgment = "frontier_judgment"
    cheap_summary = "cheap_summary"

# Maps each DevFlow role to its primary capability route.
ROLE_ROUTE_MAP: dict[str, CapabilityRoute] = {
    "brainstorm": CapabilityRoute.deep_planning,
    "planner": CapabilityRoute.deep_planning,
    "planning_judge": CapabilityRoute.independent_review,
    "builder": CapabilityRoute.bounded_coding,
    "build_judge": CapabilityRoute.independent_review,
    "verifier": CapabilityRoute.independent_review,
    "final_judge": CapabilityRoute.frontier_judgment,
}

def route_for_role(role_name: str) -> CapabilityRoute:
    """Return the capability route for a role."""
    ...

def describe_route(route: CapabilityRoute) -> str:
    """Human-readable description of a capability route."""
    ...
```

### `ResolvedSlot` gains `capability_route: CapabilityRoute | None = None`
Additive field. Existing callers that don't set it get `None`. The field
records which blueprint route was used for this resolution.

### Tests: `tests/test_capability_routes.py`
```
test_six_routes_typed                     # all 6 enum values exist
test_route_for_each_role                  # every role maps to a route
test_route_for_unknown_role_raises        # unknown role → ValueError
test_repository_analysis_route            # route description correct
test_deep_planning_route
test_bounded_coding_route
test_independent_review_route
test_frontier_judgment_route
test_cheap_summary_route
test_route_in_resolved_slot              # resolve_role records capability_route
test_legacy_callers_unaffected           # callers not setting route get None
```

### Verification
```bash
.venv/bin/python -m pytest tests/test_capability_routes.py -q
.venv/bin/python -m pytest tests/test_capability_routing.py -q  # existing routing green
```

---

## Dependency order

```
M2-S1 (schema + validator)
  │
  ├── M2-S2 (node lifecycle — depends on schema for node identity)
  │
  ├── M2-S3 (agent contracts — depends on schema for node context)
  │
  └── M2-S4 (capability routes — independent of S2/S3, depends on schema)
```

M2-S2, M2-S3, and M2-S4 all depend on M2-S1 but are independent of each other.
They can be built in any order after M2-S1.

## Full regression gate (after each slice)

```bash
PYTHONPATH=src .venv/bin/python -m devflow.cli loop spine-fixture --json
.venv/bin/python -m pytest tests/test_workflow_ledger.py tests/test_workflow_ledger_decision.py -q
.venv/bin/python -m pytest tests/test_loop_read_model.py tests/test_obsidian_projection.py -q
.venv/bin/python -m pytest  # full suite
```

## Naming rule compliance

All new types use functional role names only:
- `CapabilityRoute.bounded_coding` — not "qwen_coder"
- `RoleDefinition.builder` — not "qwen_builder"
- Agent contracts reference capabilities, not model names
- Lifecycle receipts record node_id and state, never model identity
- Model identity stays in `ResolvedSlot` (existing technical layer), behind inspection controls

## What this delivers (acceptance criteria)

After all 4 slices:
- [ ] Versioned workflow schema (v1 legacy + v2 generalized) with strategies, budgets, gates, loops
- [ ] Extended NodeKind: gate, human_gate, artifact_emit alongside human/agent/code
- [ ] Per-node lifecycle state machine (planned→ready→running→verified...) coexisting with legacy NodeReceipt
- [ ] Legacy receipts replay byte-identically
- [ ] Agent contracts with allowed/forbidden/inputs/outputs/evidence/completion/failure/handoff/resource
- [ ] 6 typed capability routes with role mapping and resolution provenance
- [ ] `canonical_product_build@1` still validates and runs unchanged
- [ ] All 912+ existing tests green + all new tests green
- [ ] Zero changes to NodeReceipt immutability
- [ ] Zero autonomous promotion (auto_promote always False)
