# Implementation Plan — M6: Validated Generated Workflow Proposals

**Status:** Planning only. No code, tests, or config changed.
**Date:** 2026-07-16
**Baseline:** M0–M5 complete (1,264 tests green, spine-fixture green)
**Authority:** Subordinate to blueprint §6.4 (workflow classes), §12.5 (generated
workflows), §6.3 (authority boundaries), then live source/tests.

**Goal:** Allow a model to propose a purpose-built workflow graph for novel tasks.
DevFlow validates the graph against the M2 schema, estimates resource cost and
risk, presents it for human inspection, freezes it, and requires explicit human
approval before execution. No generated workflow can grant itself more authority
than policy allows.

---

## What we're building on (verified live shapes)

### Workflow schema (M2-S1, `workflow_schema.py`)
- `WorkflowSchemaV2` — the typed graph definition with strategy, nodes, edges, budget, promotion
- `validate_workflow(schema)` — dispatches v1 and v2, checks cycles/references/terminals/budgets/promotion
- `BudgetPolicy`, `PromotionPolicy` (always `auto_promote=False`)
- `WorkflowClass` enum: fixed / parameterized / generated (M5-S1)

### Workflow library (M5-S1, `workflow_library.py`)
- 4 family templates + Fixed member
- `select_template(family)` for family selection

### Human decision (existing, `human_decision.py`)
- `record_operator_decision(root, receipt, repo=repo)` — Phase 6A authority boundary
- `DecisionReceipt` — typed immutable decision with accept/reject/request_changes

### Gates (M4-S6, `control_plane/gates.py`)
- `GateDecision(actor, gate_type, status)` — three distinct human gates
- `GateConfig(ship_enabled=False)` — ship disabled by default

### Routing + Factory Router (M5-S2, `control_plane/factory_router.py`)
- `bind_execution_plan(ticket_id, workflow, role_slots)` → `BoundExecutionPlan`
- `LaneProfile(heavy_model_slots, max_concurrent_sandboxes)`

---

## M6-S1 — Workflow generator + schema validation

**Outcome:** A generator proposes a candidate `WorkflowSchemaV2` graph for a novel
task. The graph is validated against the M2 schema (or rejected with reasons).
No execution — validation only.

### Design
The generator is a **pure function** that takes a task description + capability
requirements and produces a candidate graph. It does not call any model — it's
a deterministic graph composer that uses the M3-S3 pattern builders and M2 node/edge
primitives. A model *could* call this API to construct a graph, but the generator
itself is deterministic.

This keeps authority boundaries clean: the model *proposes*, the schema *validates*,
the human *approves*.

### Files
- **NEW** `src/devflow/loop/workflow_generator.py`

### Types

```python
class GenerationRequest(BaseModel):  # frozen, extra="forbid"
    """Request for a generated workflow graph."""
    task_description: str = Field(min_length=1)
    ticket_id: str = Field(pattern=ID_PATTERN)
    required_capabilities: tuple[str, ...] = ()  # capability route names
    max_nodes: int = Field(default=15, ge=3, le=30)  # bounded graph size
    strategy_hint: WorkflowStrategy = WorkflowStrategy.sequence

class GenerationResult(BaseModel):  # frozen, extra="forbid"
    """Result of a generation attempt."""
    request: GenerationRequest
    workflow: WorkflowSchemaV2 | None = None  # None if rejected
    validation_errors: tuple[str, ...] = ()
    generation_id: str = Field(pattern=ID_PATTERN)
    generated_at: str = Field(min_length=1)
```

### Function
```python
def generate_workflow(request: GenerationRequest) -> GenerationResult:
    """Generate a candidate workflow graph from a task description.

    1. Compose nodes/edges from the request's required capabilities
    2. Assign budget based on node count and capabilities
    3. Validate against the M2 schema
    4. Return result with workflow (if valid) or validation_errors
    """
```

### Composition logic
The generator composes a graph from the task's required capabilities:

1. **Entry:** `grounding` (repository_analysis) — always present
2. **Body:** one node per required capability (in order)
3. **Gate:** `human_gate` before terminal
4. **Terminals:** `complete` + `blocked`

Budget is derived from node count:
- `max_runtime_minutes = min(30 * node_count, 480)` (cap at 8 hours)
- `max_agent_runs = min(3 * node_count, 60)`
- `max_repair_rounds = min(node_count, 5)`
- `heavy_model_slots = 1` (default safe)

The `workflow_id` is `generated:<generation_id>` and `WorkflowClass.generated`.

### Validation rules enforced (non-negotiable)
- `auto_promote=False` (always)
- `human_required=True` (always)
- No node kind of `human` in the body except explicit `human_gate`
- Graph is acyclic (validated by `validate_workflow`)
- All nodes have required outcomes (validated by `validate_workflow`)
- Node count within `max_nodes` bound

### Tests: `tests/test_workflow_generator.py`
```
test_generated_graph_validates              # valid request → valid workflow
test_generated_graph_rejected_invalid       # invalid graph → validation_errors
test_generation_request_frozen              # immutable
test_generation_result_frozen               # immutable
test_generated_workflow_id_prefix           # workflow_id starts with "generated:"
test_generated_has_grounding_entry          # first body node is grounding
test_generated_has_human_gate               # includes a human_gate before terminal
test_generated_budget_proportional          # more nodes → higher budget
test_generated_max_nodes_enforced           # max_nodes bound respected
test_generated_auto_promote_false           # generated workflow never auto-promotes
test_generated_uses_functional_roles        # no model names in nodes
test_generated_strategy_from_hint           # strategy from request hint
test_generate_with_empty_capabilities       # minimal graph still valid
test_validation_errors_populated            # rejected graph has error messages
```

### Verification
```bash
.venv/bin/python -m pytest tests/test_workflow_generator.py -q
```

---

## M6-S2 — Resource estimation + visible approval gate

**Outcome:** A generated workflow gets a resource/cost estimate, is presented for
human inspection, and requires explicit human approval before execution. A generated
workflow cannot grant itself more authority than policy allows.

### Design
Three separate steps:
1. **Estimate** — deterministic cost/risk assessment of the generated graph
2. **Present** — human-readable summary for inspection
3. **Approve** — explicit human decision required; no self-escalation

The approval uses the existing `record_operator_decision` boundary — generated
workflows cannot bypass Phase 6A authority.

### Files
- **NEW** `src/devflow/control_plane/generated_approval.py`

### Types

```python
class ResourceEstimate(BaseModel):  # frozen, extra="forbid"
    """Deterministic cost/risk estimate for a generated workflow."""
    generation_id: str = Field(pattern=ID_PATTERN)
    estimated_duration_minutes: int = Field(ge=1)
    estimated_agent_runs: int = Field(ge=1)
    estimated_heavy_model_hours: float = Field(ge=0.0)
    risk_level: Literal["low", "medium", "high"]
    risk_factors: tuple[str, ...] = ()
    authority_capped: bool = True  # always True — cannot self-escalate

class GeneratedApproval(BaseModel):  # frozen, extra="forbid"
    """Human approval state for a generated workflow."""
    generation_id: str = Field(pattern=ID_PATTERN)
    ticket_id: str = Field(pattern=ID_PATTERN)
    workflow_id: str = Field(min_length=1)
    status: Literal["pending", "approved", "rejected"]
    actor: str = Field(min_length=1)  # human operator, never "system"
    decided_at: str | None = None
    reason: str = ""
    schema_version: Literal[1] = 1
```

### Functions

```python
def estimate_resources(
    workflow: WorkflowSchemaV2,
    generation_id: str,
) -> ResourceEstimate:
    """Estimate duration, agent runs, heavy-model hours, and risk.

    Deterministic — reads node count, kinds, budget, and strategy.
    """

def approval_required(
    workflow: WorkflowSchemaV2,
) -> bool:
    """True for any generated workflow. Fixed/parameterized templates don't
    need generated-workflow approval (they're pre-approved by being in the
    library)."""

def can_execute(
    approval: GeneratedApproval,
    estimate: ResourceEstimate,
) -> bool:
    """True only when approval.status == 'approved' AND estimate.authority_capped."""

def record_approval(
    root: Path | str,
    approval: GeneratedApproval,
) -> GeneratedApproval:
    """Persist approval to generated-approval-events.jsonl in the ticket dir."""
```

### Authority rules (non-negotiable)
1. `authority_capped` is always `True` — the estimate can never report uncapped authority
2. `can_execute()` returns `False` unless `status == "approved"` AND `authority_capped`
3. `actor` can never be `"system"` — validated by model_validator
4. `approval_required()` returns `True` for any `WorkflowClass.generated` workflow
5. A generated workflow's `PromotionPolicy.auto_promote` is always `False` (enforced by M2 validator)
6. A generated workflow's budget cannot exceed policy maximums (enforced by M2 validator bounds)

### Risk estimation heuristics
- **Low:** ≤ 5 nodes, all `agent`/`code` kind, ≤ 60 min budget
- **Medium:** 6–12 nodes, or includes `gate`/`human_gate`, or 61–180 min
- **High:** > 12 nodes, or includes `human_gate` with `dag` strategy, or > 180 min

### Persistence
Approval events stored in `.devflow/control-plane/generated-approvals/` (separate
from pipeline runs and from gate-events.jsonl). Idempotent replay supported.

### Tests: `tests/test_generated_approval.py`
```
test_estimate_resources_basic              # estimate from node count
test_estimate_risk_low                     # few nodes → low risk
test_estimate_risk_medium                  # gates or moderate size → medium
test_estimate_risk_high                    # large/dag → high risk
test_authority_always_capped               # authority_capped is always True
test_approval_required_for_generated       # generated class → True
test_approval_not_required_for_fixed       # fixed/parameterized → False
test_can_execute_requires_approved         # pending → False
test_can_execute_approved                  # approved + capped → True
test_cannot_execute_rejected               # rejected → False
test_actor_cannot_be_system                # model_validator rejects "system"
test_record_approval_persists              # saved to control-plane dir
test_record_approval_idempotent            # replay → idempotent
test_generated_cannot_self_promote         # auto_promote=False enforced
test_generated_budget_within_policy        # budget ≤ policy maximums
test_resource_estimate_frozen              # immutable
test_generated_approval_frozen             # immutable
```

### Verification
```bash
.venv/bin/python -m pytest tests/test_generated_approval.py -q
.venv/bin/python -m pytest tests/test_workflow_generator.py tests/test_workflow_schema.py -q
```

---

## Dependency order

```
M6-S1 (generator) → M6-S2 (estimation + approval)
```

Sequential only. S2 needs S1's generated workflow to estimate.

## Full regression gate (after each slice)

```bash
PYTHONPATH=src .venv/bin/python -m devflow.cli loop spine-fixture --json
.venv/bin/python -m pytest tests/test_workflow_schema.py tests/test_workflow_families.py -q
.venv/bin/python -m pytest  # full suite
```

## What this delivers (acceptance criteria)

After both slices:
- [ ] A generated workflow graph validates against the M2 schema or is rejected with reasons
- [ ] Generated workflows always have `auto_promote=False` and `human_required=True`
- [ ] Resource estimates are deterministic and include risk level
- [ ] `authority_capped` is always `True` — no self-escalation
- [ ] `approval_required()` returns `True` for generated workflows, `False` for Fixed/Parameterized
- [ ] `can_execute()` returns `False` unless explicitly approved by a human
- [ ] `actor` can never be `"system"`
- [ ] `canonical_product_build@1` still runs unchanged
- [ ] All 1,264+ existing tests green + all new tests green
- [ ] All types use functional role names only

## What this is NOT
- No model execution of the generated workflow (that's runtime, not M6)
- No self-modifying workflow templates (M7)
- No visual workflow editor (explicitly out of scope, §12.5)
- No generated-workflow authority escalation (explicitly forbidden, §6.3)
