# Implementation Plan — M5: Workflow Families + Factory Router + Metrics

**Status:** Planning only. No code, tests, or config changed.
**Date:** 2026-07-16
**Baseline:** M0–M4 complete (1,210 tests green, spine-fixture green)
**Authority:** Subordinate to blueprint §6.4 (workflow classes), §8.1–8.4 (workflow families),
§4.5 (Factory Router), §10.2 (metrics), then live source/tests.

**Goal:** Build four parameterized workflow-family templates (hotfix/feature/bug/chore),
a dedicated Factory Router that binds lane/sandbox/resources/concurrency, and wire per-run
metrics into the promotion packet. After M5, the system has a workflow library, routing
to execution lanes, and evidence-backed metrics for workflow evaluation.

---

## What we're building on (verified live shapes)

### Workflow schema (M2-S1, `workflow_schema.py`)
- `WorkflowSchemaV2` with `WorkflowStrategy`, `NodeKind` (human/agent/code/gate/human_gate/artifact_emit)
- `LoopPolicy`, `BudgetPolicy`, `PromotionPolicy`, `PhaseDefinition`
- `validate_workflow()` dispatches v1 and v2

### Workflow definition (M2-S1, `workflow_definition.py`)
- `canonical_product_build_v1()` — the Fixed "verified-change" member
- `WorkflowNode(id, kind, stage, required_evidence)`, `WorkflowEdge(source, target, outcome)`

### Task analyzer (M4-S2, `task_analyzer.py`)
- `TaskAnalysis(family, risk, required_approvals)` — `WorkflowFamily` enum: hotfix/feature/bug/chore/unknown

### Routing (M2-S4 + existing, `routing.py`)
- `ResolvedSlot(role, model_name, provider, endpoint, transport, cost_class, resolved_via, capability_route)`
- `resolve_role()`, `resolve_role_compatible()`

### Capability routes (M2-S4, `capability_routes.py`)
- `CapabilityRoute` enum: repository_analysis, deep_planning, bounded_coding, independent_review, frontier_judgment, cheap_summary
- `route_for_role()` maps each role to a route

### Sandbox (existing, `git_sandbox.py`)
- `SandboxRequest(repo, root, run_id, sandbox_id, kind, authorization_id, packet_id, max_sandboxes)`
- `create_sandbox(request) -> SandboxReceipt`

### Promotion packet (M1-S5, `obsidian/promotion_packet.py`)
- `build_promotion_packet(root, run_id) -> str | None` — reads intent, spec, verification, reliability
- Independent review section honestly says "not yet produced" (now upgradeable with M4-S4)

### Reliability metrics (existing, `reliability.py`)
- `ReliabilityReport(run_id, safe, action, breaches, metrics, thresholds, recovery_actions)`
- `metrics` dict contains: concurrent_role_starts, routing_drifts, replay_completions, etc.

### Conflict rules (M3-S2, `conflict_rules.py`)
- `ResourceBudget(heavy_model_slots, heavy_model_in_use)`
- `BudgetPolicy.heavy_model_slots` from M2-S1

---

## M5-S1 — Parameterized + family templates (R2/F1)

**Outcome:** Four family templates (hotfix/feature/bug/chore) with blueprint phase shapes.
`canonical_product_build@1` remains the Fixed "verified-change" member. Family selection
uses the M4-S2 task analyzer + ticket contract.

### Files
- **NEW** `src/devflow/loop/workflow_library.py`
- **EDIT** `src/devflow/loop/workflow_definition.py` — add a registry function (additive)

### Family templates (blueprint §8.1–8.4)

Each template is a `WorkflowSchemaV2` definition with the blueprint's phase shape:

#### Hotfix (§8.1): Parallel Grounding → Proposal → Approval Gate → Bounded Patch → Targeted Verification → Independent Review
```python
def hotfix_template() -> WorkflowSchemaV2
```
- Optimized for speed, containment, explicit risk control
- Strategy: sequence (linear, fast)
- Budget: max_repair_rounds=2, max_runtime_minutes=60

#### Feature (§8.2): Parallel Grounding → Spec Synthesis ↔ Spec Judge → Implementation DAG → Parallel Build → Per-Slice Verify → Integration → Review
```python
def feature_template() -> WorkflowSchemaV2
```
- Optimized for spec quality, decomposable work, integration confidence
- Strategy: dag (phases with parallel branches)
- Budget: max_repair_rounds=4, max_runtime_minutes=180

#### Bug (§8.3): Reproduction → Parallel Diagnosis → Root-Cause Judge → Minimal Repair → Regression Verify → Adversarial Review
```python
def bug_template() -> WorkflowSchemaV2
```
- Optimized for reproduction and causal evidence
- Strategy: sequence with convergence loop for diagnosis
- Budget: max_repair_rounds=3, max_runtime_minutes=120

#### Chore (§8.4): Scope Check → Bounded Change → Lint/Format → CI/CD → Focused Review
```python
def chore_template() -> WorkflowSchemaV2
```
- Optimized for low overhead
- Strategy: sequence (minimal)
- Budget: max_repair_rounds=1, max_runtime_minutes=30

### Workflow class registry
```python
class WorkflowClass(str, Enum):
    fixed = "fixed"             # canonical_product_build@1
    parameterized = "parameterized"  # family templates with runtime params
    generated = "generated"     # M6 (not yet built)

WORKFLOW_LIBRARY: dict[str, WorkflowSchemaV2] = {
    "canonical_product_build@1": ...,
    "hotfix@1": hotfix_template(),
    "feature@1": feature_template(),
    "bug@1": bug_template(),
    "chore@1": chore_template(),
}

def get_template(workflow_id: str) -> WorkflowSchemaV2 | None
def select_template(analysis: TaskAnalysis) -> str  # returns workflow_id
def list_templates() -> tuple[str, ...]
```

### `select_template(analysis)` maps `WorkflowFamily` → template ID
- `hotfix` → `hotfix@1`
- `feature` → `feature@1`
- `bug` → `bug@1`
- `chore` → `chore@1`
- `unknown` → `canonical_product_build@1` (fallback to Fixed)

### Tests: `tests/test_workflow_families.py`
```
test_four_family_templates            # hotfix/feature/bug/chore all validate
test_hotfix_template_shape            # grounding→proposal→patch→verify→review
test_feature_template_shape           # grounding→spec↔judge→DAG→build→verify→integrate→review
test_bug_template_shape               # reproduction→diagnosis→judge→repair→regression→adversarial
test_chore_template_shape             # scope→change→lint→ci→review
test_canonical_product_build_still_fixed  # v1 unchanged
test_select_template_from_analysis    # TaskAnalysis.family → correct template_id
test_unknown_family_falls_back        # unknown → canonical_product_build@1
test_all_templates_validate_v2        # every template passes validate_workflow
test_template_budgets_differ          # hotfix < feature budgets
test_no_auto_promote_in_any_template  # all templates have auto_promote=False
test_list_templates_returns_all       # 5 templates (1 fixed + 4 families)
test_templates_use_functional_roles   # no model names
```

### Verification
```bash
.venv/bin/python -m pytest tests/test_workflow_families.py -q
PYTHONPATH=src .venv/bin/python -m devflow.cli loop spine-fixture --json
```

---

## M5-S2 — Factory Router (W3)

**Outcome:** A dedicated component that binds lane, sandbox profile, model routes,
resource limits, and concurrency policy for a given ticket + workflow template.

### Design
The Factory Router is a **composition layer** — it doesn't implement new model resolution.
It takes the existing `resolve_role()` outputs and `BudgetPolicy` / `ResourceBudget` and
produces a single `BoundExecutionPlan` that the runtime can consume.

### Files
- **NEW** `src/devflow/control_plane/factory_router.py`

### Types

```python
class LaneProfile(BaseModel):  # frozen, extra="forbid"
    """One execution lane's resource and concurrency profile."""
    lane_id: str = Field(min_length=1)
    heavy_model_slots: int = Field(default=1, ge=0, le=4)
    max_concurrent_sandboxes: int = Field(default=1, ge=1, le=8)
    network_default: Literal["denied", "allowed"] = "denied"

class RoleBinding(BaseModel):  # frozen, extra="forbid"
    """One role's resolved model + capability route binding."""
    role: str = Field(min_length=1)
    capability_route: str = Field(min_length=1)
    resolved_model: str = ""        # behind inspection control
    cost_class: str = ""
    resolved_via: str = ""

class BoundExecutionPlan(BaseModel):  # frozen, extra="forbid"
    """Complete binding of a workflow to execution resources."""
    ticket_id: str = Field(min_length=1)
    workflow_id: str = Field(min_length=1)
    lane: LaneProfile
    role_bindings: tuple[RoleBinding, ...] = ()
    budget: BudgetPolicy = Field(default_factory=BudgetPolicy)
    promotion: PromotionPolicy = Field(default_factory=PromotionPolicy)
    sandbox_profile: str = "workspace_write"
    capability_routes: tuple[str, ...] = ()
```

### Function
```python
def bind_execution_plan(
    ticket_id: str,
    workflow: WorkflowSchemaV2,
    role_slots: Mapping[str, ResolvedSlot],  # role → resolved model
) -> BoundExecutionPlan:
    """Bind a workflow template to execution resources.

    Composes:
    - Lane profile from workflow.budget.heavy_model_slots
    - Role bindings from resolved slots (functional role names only)
    - Capability routes from role→route mapping
    - Budget and promotion policy from the workflow schema
    """
```

### Tests: `tests/test_factory_router.py`
```
test_binds_lane_and_sandbox           # BoundExecutionPlan has lane + sandbox_profile
test_role_bindings_functional_names   # RoleBinding uses role names, not model names
test_heavy_slots_from_budget          # lane.heavy_model_slots matches workflow budget
test_capability_routes_recorded       # routes in the plan
test_budget_inherited_from_workflow   # plan.budget == workflow.budget
test_no_auto_promote                  # plan.promotion.auto_promote is False
test_bind_execution_plan_frozen       # BoundExecutionPlan is immutable
test_lane_profile_defaults            # default lane has 1 slot, denied network
test_network_denied_by_default        # sandbox_profile = workspace_write
test_model_details_behind_binding     # resolved_model present but not in primary fields
```

### Verification
```bash
.venv/bin/python -m pytest tests/test_factory_router.py -q
```

---

## M5-S3 — Metrics aggregation into promotion packet (M1)

**Outcome:** Per-workflow cost/route/retries/history aggregated into the M1-S5
promotion packet. The packet now includes a metrics section; review fields are
upgraded when M4-S4 reviews exist.

### Files
- **NEW** `src/devflow/loop/metrics_aggregator.py`
- **EDIT** `src/devflow/obsidian/promotion_packet.py` — add metrics section to `build_promotion_packet()`

### `metrics_aggregator.py`

```python
class WorkflowMetrics(BaseModel):  # frozen, extra="forbid"
    """Aggregated per-run workflow metrics."""
    run_id: str = Field(min_length=1)
    total_duration_seconds: float = 0.0
    total_tokens: int = 0
    role_routes: tuple[str, ...] = ()  # capability routes used
    retry_count: int = 0
    repair_rounds: int = 0
    human_interventions: int = 0
    reliability_safe: bool | None = None
    reliability_breaches: tuple[str, ...] = ()
    workflow_version: str = ""

def aggregate_metrics(
    root: Path | str,
    run_id: str,
) -> WorkflowMetrics:
    """Aggregate per-run metrics from reliability report, lifecycle events,
    and repair events. Read-only — never mutates canonical state."""
```

### Implementation approach
1. Read `reliability-report.json` for `reliability_safe`, `breaches`, duration/tokens
2. Read `repair-events.jsonl` (M4-S4) for `repair_rounds`
3. Read `node-lifecycle-events.jsonl` (M2-S2) for `retry_count`
4. Read `review-events.jsonl` (M4-S4) for `human_interventions` count
5. Read `workflow-definition.json` for `workflow_version`
6. Build and return `WorkflowMetrics`

### Promotion packet edit
Add a new section to `build_promotion_packet()`:
```markdown
## Workflow Metrics
- Total duration: 92 minutes
- Total tokens: 15,420
- Capability routes: bounded_coding, independent_review
- Retries: 2
- Repair rounds: 1
- Human interventions: 0
- Reliability: safe
```

If M4-S4 reviews exist, upgrade the Independent Review section from "not yet produced"
to the actual review findings.

### Tests: `tests/test_promotion_metrics.py`
```
test_packet_contains_workflow_metrics     # metrics section present
test_aggregate_metrics_from_reliability   # reads reliability-report.json
test_aggregate_metrics_repair_rounds      # counts repair events
test_aggregate_metrics_retry_count        # counts lifecycle retries
test_aggregate_metrics_no_data            # missing files → zeros
test_metrics_read_only                    # run dir unchanged after aggregate
test_workflow_metrics_frozen              # immutable
test_packet_upgrades_review_when_present  # review-events.jsonl → real findings
test_packet_metrics_section_format        # human-readable format
test_aggregate_includes_routes            # capability routes recorded
```

### Verification
```bash
.venv/bin/python -m pytest tests/test_promotion_metrics.py -q
.venv/bin/python -m pytest tests/test_obsidian_promotion_packet.py -q  # existing packet tests green
```

---

## Dependency order

```
M5-S1 (family templates — needs M4-S2 analyzer)
  │
  ├── M5-S2 (Factory Router — needs templates + routing + budget)
  │
  └── M5-S3 (metrics — independent of S1/S2, needs M1-S5 + M4 receipts)
```

All three can proceed after M4. S1 should come first (templates needed for S2).

## Full regression gate (after each slice)

```bash
PYTHONPATH=src .venv/bin/python -m devflow.cli loop spine-fixture --json
.venv/bin/python -m pytest tests/test_workflow_schema.py tests/test_workflow_ledger.py -q
.venv/bin/python -m pytest tests/test_obsidian_promotion_packet.py -q
.venv/bin/python -m pytest  # full suite
```

## What this delivers (acceptance criteria)

After all 3 slices:
- [ ] Four family templates (hotfix/feature/bug/chore) validating against M2 schema
- [ ] `canonical_product_build@1` remains the Fixed member, unchanged
- [ ] `select_template(TaskAnalysis)` maps family → template
- [ ] Factory Router binding lane/sandbox/model/resource/concurrency
- [ ] Per-run metrics aggregated from reliability + repair + lifecycle events
- [ ] Promotion packet includes metrics section
- [ ] Promotion packet upgrades review section when M4-S4 reviews exist
- [ ] `canonical_product_build@1` still runs unchanged
- [ ] No autonomous promotion (all templates `auto_promote=False`)
- [ ] All 1,210+ existing tests green + all new tests green
- [ ] All types use functional role names only
