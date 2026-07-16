> For Hermes: Use subagent-driven-development skill to implement task-by-task.

# Implementation Plan — DevFlow Software-Factory Blueprint Gap Closure

**Planning-only.** No implementation was performed. This plan is a dependency-sliced, replay-safe, fresh-checkout-executable closure map from the verified Phase 6 baseline (`6122fb5`, 150 passing Phase tests) to the full blueprint (`docs/DevFlow_Software_Factory_Vision_Architecture_Blueprint.docx`). It preserves and generalizes the existing Phase 1–6 primitives; it does not rewrite them. It is deliberately conservative: primitive/data presence is separated from end-to-end product behavior, the canonical ledger is treated as canonical **only for canonical-marked runs**, and no writer change or state collapse ships before legacy receipts are proven to replay byte/semantically unchanged.

- **Goal:** Carry DevFlow from its fixed `canonical_product_build@1` verified-change workflow to the full six-stage software-factory blueprint: control plane, generalized workflow VM, DAG/parallel execution, human merge/full-verify/ship gates, parameterized/generated workflow library, adaptive improvement — all projected observability-first into an Obsidian Command Center.
- **Architecture:** Three planes (control, workflow, worker) + evidence/projection layer, exactly as blueprint §4. Canonical state stays in the append-only `workflow_ledger` **for canonical-marked runs**; Obsidian holds generated, read-only-first projections. Human authority is never bypassed: no autonomous promotion/push/deploy.
- **Tech stack:** Python 3.11, Pydantic v2 (frozen models), Typer CLI (`src/devflow/cli.py`), Git worktree sandboxes, existing `routing.py`/`roles.py`/ledger/integration modules reused verbatim. No new heavy dependencies.

**Authority (for current facts — the operative hierarchy this plan follows):**
1. **Blueprint** (`docs/...Blueprint.docx`) — highest *target direction* (north star). It describes the goal, not today's code.
2. **Live source/tests** (`src/devflow/...`, `tests/`) — the *operative current-implementation facts*. Any `file:line` here was read directly from live source; where prose docs and live code disagree on what exists today, live code wins.
3. **`DEVFLOW_SOURCE_OF_TRUTH.md`** — a *subordinate current-runtime orientation*; it may lag live code (it even admits stale sentences) and is re-pointed by this packet, so it is below live source/tests for "what is implemented now."
4. **This plan and the gap assessment** (`docs/DEVFLOW_BLUEPRINT_GAP_ASSESSMENT.md`) — *dated derived docs*; they are planning artifacts, never authoritative over the three tiers above.

Gap detail lives in `docs/DEVFLOW_BLUEPRINT_GAP_ASSESSMENT.md`. All status claims there are conservative: IMPLEMENTED is reserved for end-to-end product behavior, not mere data/primitive presence.

---

## Canonical-state / replay-safety principles (apply to every milestone)

- **No destructive collapse.** The ledger is canonical **only for canonical-marked runs** (`is_canonical_workflow_run`, `workflow_ledger.py:344`). `LoopStage` (`models.py:18`) and loop-state persistence (`adapter.py:74/148`) are retained for noncanonical/historical compatibility; we do **not** erase that state.
- **Strangler, not rewrite.** Add a canonical read model derived from `WorkflowSnapshot` (`workflow_ledger.py:69/334`); migrate canonical consumers incrementally; prove old receipts replay byte/semantically unchanged before retiring any writer.
- **Immutable schemas are never replaced in place.** `NodeReceipt` (`workflow_ledger.py:47`) is frozen and kept. New lifecycle is added as *versioned, additive* events/receipts with backward-compatible replay of legacy `success`/`failure` receipts. Every schema change ships with replay fixtures/tests asserting byte/semantic preservation.
- **No live run IDs.** Tests build disposable runs under `tmp_path` via `devflow.loop.pipeline_run.create_pipeline_run(root, {...})` (the pattern already used across `tests/`). No slice depends on a gitignored `.devflow/pipeline-runs/<timestamp>` path.
- **Live repo commands only.** CLI via `PYTHONPATH=src .venv/bin/python -m devflow.cli ...`; tests via `.venv/bin/python -m pytest ...`. Bare `devflow` console commands appear only where an editable install is an explicit tested prerequisite (not assumed here). Regressions gate on `make verify` (the named release gate, `./scripts/release-check.sh`) plus `PYTHONPATH=src .venv/bin/python -m devflow.cli loop spine-fixture --json` exiting 0 with `final_stage=complete`.
- **No autonomous promotion.** Every promotion/push/PR/deploy stays behind explicit human authority and `enabled=False` defaults (`result_branch.py`). Obsidian projections are read-only-first (§10.8); editing a note never mutates canonical state.

---

## Dependency graph (high level)

```text
M0 (read-model convergence: #26/#27 strangler, stale-doc repair)
   │
   ├──► M1 (Obsidian Command Center projection + promotion packet)  [observability-first; existing workflow]
   │
   └──► M2 (generalized workflow VM: schema/validators R1, primitives R3, node lifecycle R4, contracts W1, capability routes W2)
            │
            └──► M3 (per-run DAG + conflict-aware parallel sandboxes + integration candidates Q1, patterns R6, R5)
                     │
                     └──► M4 (control plane C1/C3 + ready queue + independent review/repair V1 + Blocker/Decision/Handoff V2 + merge/full-verify/ship gates)
                              │
                              └──► M5 (parameterized + family templates R2/F1 + Factory Router W3 + metrics aggregation M1)
                                       │
                                       └──► M6 (validated generated workflow proposals, explicit approval)
                                                │
                                                └──► M7 (adaptive evaluation/replay/template improvement under human control M2)
```

Dependency notes (D.13/D.14/D.15):
- **Schema/validator before executors.** Versioned workflow schema + validator (`workflow_definition.py:56` `validate_references`, extended) can precede the typed task analyzer; but **family/template selection uses the typed analyzer (M4-S2) and the control-plane ticket contract** — it is not wired in M2.
- **Structural composition vs executable nodes (D.13).** Separate composition strategy (`sequence`/`parallel`/`dag`/`loop`/`conditional`) from executable node kinds (`agent`/`command`/`gate`/`human_gate`/`artifact_emit`). `NodeKind` (`workflow_definition.py:16`) is extended for *executable* nodes only; composition is a `WorkflowStrategy`/edge attribute. Schema + validator land before executors.
- **Ready Queue belongs after M4 control-plane ownership (D.14).** M3 provides only *per-run* DAG ready sets and verified integration candidates. The multi-workflow Ready Queue is introduced in M4-S3 after the control-plane aggregate exists.

Every blueprint domain is covered: control plane (M4), compiler/runtime (M2/M3/M5), worker contracts/routing/scheduling (M2/M3/M5), verification/human authority (M2/M4), evidence/artifacts (M1/M4), workflow families (M5), ready queue/integration/ship (M3/M4), Obsidian projection/UX (M1), metrics/durability/adaptive improvement (M5/M7). M1 is intentionally decoupled from M2 so the operator gains observability on the *existing* verified workflow before the VM generalizes.

---

## Milestone M0 — Read-model convergence (strangler, not collapse) and promotion-packet truth

**Outcome:** a canonical read model is *derived* from the ledger for canonical-marked runs; `LoopStage` and loop-state persistence remain for noncanonical/historical compatibility; stale Phase 6 docs repaired; public read model honest. **No writer changed, no state erased.**

- **M0-S1 — Add a canonical run read-model adapter (additive).** *(Replaces the old "collapse dual state model" slice — see replay-safety principles.)*
  - Operator-visible outcome: a single importable helper that derives a public run read model from `WorkflowSnapshot`; `LoopStage` stays as-is for compatibility.
  - Prereq: none.
  - Reuse (live symbols): `workflow_ledger.py:334` `rebuild_workflow_snapshot`, `:344` `is_canonical_workflow_run`, `:69` `WorkflowSnapshot`; `models.py:18` `LoopStage`; `adapter.py:74` `load_loop_state`.
  - New/Edit (labeled): NEW `src/devflow/loop/read_model.py` with `derive_canonical_run_model(snapshot) -> CanonicalRunModel` (frozen dataclass; for canonical-marked runs only). EDIT `src/devflow/loop/models.py:19` docstring to state `LoopStage` is a compatibility/UI projection, **not** deleted.
  - RED: `tests/test_loop_read_model.py::test_derive_from_snapshot` fails (helper absent).
  - GREEN (minimal): helper returns a model built purely from `rebuild_workflow_snapshot`; no persistence added; `LoopStage` still importable and unchanged.
  - Verify: `.venv/bin/python -m pytest tests/test_loop_read_model.py -q`.
  - Accept: single derived read model exists; existing writers (`record_node_outcome`, `record_decision`) untouched.
  - Rollback/authority: revert only `read_model.py` + the docstring edit; no migration of stored state. Authority: do not delete `LoopStage`; keep compat (blueprint §10.1).
- **M0-S2 — Reconcile linear-chain doc drift (#27) + repair stale Phase 6 sentence.**
  - Operator-visible outcome: `DEVFLOW_SOURCE_OF_TRUTH.md` truthfully states Phase 6 is complete and points at the gap assessment; notes the live graph is a fixed `canonical_product_build@1` chain while the blueprint phase graph is the target.
  - Prereq: M0-S1.
  - Reuse (live symbols): `DEVFLOW_SOURCE_OF_TRUTH.md:401–403` (already repaired in this packet to state Phase 6 complete + pointer to gap assessment).
  - New/Edit (labeled): EDIT `docs/DEVFLOW_SOURCE_OF_TRUTH.md` near `:344–347` to annotate `LoopStage` as compatibility/UI projection and note noncanonical runs retain saved-state without migration.
  - RED: targeted stale scan for "remain Phase 6 work" near line 403 returns a hit. GREEN: scan clean.
  - Verify: `grep -n "remain Phase 6 work" docs/DEVFLOW_SOURCE_OF_TRUTH.md` → no match; `git diff --check` clean.
  - Accept: docs truthful; rollback = revert the doc edit.

---

## Milestone M1 — Obsidian read-only Command Center projection for the existing verified-change workflow

**Outcome:** from a CLI command, a live canonical run renders into a vault `.generated/` tree the operator can read without logs or touching canonical state. The promotion packet is emitted **derived, non-authoritative**, and never invents missing independent-review/adversarial evidence.

> All run fixtures are built under `tmp_path` via `devflow.loop.pipeline_run.create_pipeline_run` — no slice references a gitignored `.devflow/pipeline-runs/<timestamp>` ID.

- **M1-S1 — Projection data contract + extraction (root).**
  - Operator-visible outcome: a deterministic, fail-closed extractor that turns a canonical run into a typed `ProjectionState`.
  - Prereq: M0.
  - Reuse (live symbols): `workflow_ledger.py:334` `rebuild_workflow_snapshot`, `:344` `is_canonical_workflow_run`, `:93` `DecisionReceipt`; `adapter.py:74` `load_loop_state`; `pipeline_run.py:71` `pipeline_runs_dir`, `:162` `load_pipeline_run`; `pipeline_run.create_pipeline_run` (disposable-run builder used by `tests/`).
  - New/Edit (labeled): NEW `src/devflow/obsidian/projection.py` with frozen `ProjectionState` (health ∈ {Healthy, Running, Repairing, Awaiting Decision, Blocked, Verification Failed}, phase, progress, blocker_count, decision_count, handoff_count, open_decisions, result_branch ref, canonical links) and `extract_projection(root, run_id)` that builds a **disposable** run via `create_pipeline_run` in the test and reads ledger state.
  - RED: `tests/test_obsidian_projection.py::test_extract_derives_decision_count` fails (helper absent).
  - GREEN (minimal): decision count derived from `rebuild_workflow_snapshot` + decision receipts; noncanonical runs skipped with a clear `not_canonical` result.
  - Verify: `.venv/bin/python -m pytest tests/test_obsidian_projection.py -q`.
  - Accept: deterministic derive; fail-closed on missing receipts; **no stored-state mutation**.
  - Rollback/authority: new module only; no edits to ledger/adapter.
- **M1-S2 — Markdown renderers (Overview/Workflow/Evidence/Decisions/History).**
  - Operator-visible outcome: human-readable Command Center notes rendered from `ProjectionState`.
  - Prereq: M1-S1.
  - Reuse (live symbols): `model_catalog_markdown.py:9/145` `START_MARKER`/`END_MARKER` + `update_model_dashboard` pattern; `brief_intelligence/formatter.py:7` `format_obsidian` front-matter style.
  - New/Edit (labeled): NEW `src/devflow/obsidian/render.py` (`render_overview/render_workflow/render_evidence/render_decisions/render_history`) with `[[Wikilinks]]` and Appendix C front-matter.
  - RED: `tests/test_obsidian_render.py::test_render_overview_contains_wikilinks` fails.
  - GREEN (minimal): implement renderers; pure functions, no I/O to canonical state.
  - Verify: `.venv/bin/python -m pytest tests/test_obsidian_render.py -q`.
  - Accept: views render from the derived model only.
  - Rollback/authority: new module; no canonical writes.
- **M1-S3 — Atomic vault writer (read-only-first, §10.8).**
  - Operator-visible outcome: generated notes land atomically under `.generated/` without overwriting human notes.
  - Prereq: M1-S2.
  - Reuse (live symbols): `model_catalog_markdown.py:150` atomic `START_MARKER`/`END_MARKER` replace pattern.
  - New/Edit (labeled): NEW `src/devflow/obsidian/vault.py` `write_vault_projection(vault, run_id, views)` → temp+replace into `vault/Command Center/Projects/DevFlow/.generated/`. Never writes outside `.generated/`; never calls `save_loop_state`/`advance_run`/`create_result_ref`.
  - RED: `tests/test_obsidian_vault.py::test_write_atomic_no_human_note_overwrite` fails.
  - GREEN (minimal): canonical files untouched + idempotent replay (re-run yields identical bytes).
  - Verify: `.venv/bin/python -m pytest tests/test_obsidian_vault.py -q`.
  - Accept: atomic; human-authored notes preserved.
  - Rollback/authority: new module; no canonical writes.
- **M1-S4 — CLI surface (module form, disposable run).**
  - Operator-visible outcome: operator can run `obsidian run <run_id>` against any run built by the test harness.
  - Prereq: M1-S3.
  - Reuse (live symbols): `cli.py:28` `loop_app`, `:93` `spine-fixture` precedent; `pipeline_run.create_pipeline_run` for the test's run_id.
  - New/Edit (labeled): NEW `obsidian_app` Typer subcommand `obsidian run <run_id>` and `obsidian project --vault <path>` added to `cli.py`.
  - RED: `tests/test_v2_cli.py::test_obsidian_run_emits_generated` fails (command absent).
  - GREEN (minimal): `PYTHONPATH=src .venv/bin/python -m devflow.cli obsidian run <tmp_run_id> --vault /tmp/vault` emits `.generated/current-focus.md`; uses a run created by `create_pipeline_run` inside the test.
  - Verify: `.venv/bin/python -m pytest tests/test_v2_cli.py -q`.
  - Accept: no bare `devflow`; run_id supplied by fixture, not a gitignored timestamp.
  - Rollback/authority: additive CLI; no existing command changed.
- **M1-S5 — Promotion packet materialization (§9.4, Appendix C) — honest, no invention.**
  - Operator-visible outcome: an inspectable `promotion-packet.md` after `accept`, derived and non-authoritative.
  - Prereq: M1-S1 + Phase 6 (done).
  - Reuse (live symbols): `result_branch.py:126` `PromotionReceipt`, `:382` `create_result_ref`; run dir `reliability-report.json`, `verification-receipt-*`, `fixture-spec.md`, `fixture-plan.md` (produced by the spine fixture / disposable run).
  - New/Edit (labeled): NEW `src/devflow/obsidian/promotion_packet.py` `build_promotion_packet(root, run_id, receipt)`. Sections: objective, diff/changed-path summary, deterministic verification, **independent-review/adversarial findings (typed `not_available`/`not_run` with source reference when not yet produced),** open risks, recommended action. Derived, non-authoritative (SOURCE_OF_TRUTH §10.3 link-only).
  - RED: `tests/test_obsidian_promotion_packet.py::test_packet_declares_not_run_review` fails (packet absent / invents review).
  - GREEN (minimal): packet written alongside branch; review/adversarial fields emitted as `not_available`/`not_run` with a source reference (e.g. "independent review not yet produced — see M4-S4"); **never fabricated**. Push/PR/deploy remain `enabled=False` (`result_branch.py`).
  - Verify: `.venv/bin/python -m pytest tests/test_obsidian_promotion_packet.py -q`.
  - Accept: packet present after `accept`; no invented evidence; later M4 review work upgrades these fields.
  - Rollback/authority: new module; read-only/derived; separate from the `accept` result-ref authority until its own gate (M4-S4) is proven.
- **M1-S6 — Optional browser surfacing (defer/low prio).**
  - Reuse `control_room/server.py:1356` `run_server`. Postpone unless operator wants it now.

---

## Milestone M2 — Complete generalized workflow VM contracts (schema-first)

**Outcome:** the workflow runtime is a real VM: versioned schema + validator, full primitive set, per-node lifecycle, enforced agent contracts, typed capability routes. Executable executors land after the schema/validator.

- **M2-S1 — Versioned workflow schema + validator (precedes executors).**
  - Operator-visible outcome: a versioned workflow definition schema with a deterministic validator that checks cycles, references, terminal states, budgets, and promotion policy — extended from today's `validate_references`.
  - Prereq: M0.
  - Reuse (live symbols): `workflow_definition.py:56` `validate_references` (cycle/ref/terminal), `:23` `canonical_product_build_v1`, `:16` `NodeKind`.
  - New/Edit (labeled): EDIT `workflow_definition.py` to add `WorkflowStrategy` (sequence/parallel/dag/loop/conditional) and extend `validate_references` with budget/gate/promotion-policy checks. NEW `src/devflow/loop/workflow_schema.py` versioned schema (v1 → v2 additive). Keep `NodeKind` for *executable* nodes; composition is a strategy/edge attribute (D.13).
  - RED: `tests/test_workflow_schema.py::test_validator_rejects_unbounded_loop` fails.
  - GREEN (minimal): validator rejects a loop without `max_rounds`/`stop_if_no_progress`; legacy `canonical_product_build@1` still validates.
  - Verify: `.venv/bin/python -m pytest tests/test_workflow_schema.py -q`.
  - Accept: schema additive/versioned; legacy graph still valid.
  - Rollback/authority: additive schema; no executor change yet.
- **M2-S2 — Node lifecycle state machine (additive, never replaces `NodeReceipt`).**
  - Operator-visible outcome: a per-node lifecycle (planned→ready→running→verified/retrying/blocked/awaiting_gate/failed/cancelled) plus workflow terminal states (completed/awaiting_promotion/needs_rework/failed/cancelled/shipped), with **backward-compatible replay** of legacy `success`/`failure` receipts.
  - Prereq: M2-S1.
  - Reuse (live symbols): `workflow_ledger.py:47` `NodeReceipt` (kept immutable), `:386` `record_node_outcome`, `:316` `replay_workflow_run`.
  - New/Edit (labeled): NEW `src/devflow/loop/node_lifecycle.py` with `NodeState` enum + `NodeLifecycleReceipt` (versioned, additive) recorded *alongside* `NodeReceipt`. NEW replay fixtures in `tests/fixtures/legacy_receipts/` covering legacy `success`/`failure` receipts. EDIT `workflow_ledger.py` only to *add* a recorder for the new lifecycle event (never mutate `NodeReceipt`).
  - RED: `tests/test_node_lifecycle.py::test_legacy_success_replays_unchanged` and `::test_lifecycle_transitions` fail.
  - GREEN (minimal): legacy `success`/`failure` receipts replay byte/semantically identical; new lifecycle events append without breaking old replay.
  - Verify: `.venv/bin/python -m pytest tests/test_node_lifecycle.py -q` (includes the legacy replay fixture assertions).
  - Accept: legacy receipts unchanged; new lifecycle coexists. **No `NodeReceipt` replacement.**
  - Rollback/authority: additive records only; rollback removes the new recorder + fixtures; `NodeReceipt` untouched.
- **M2-S3 — Agent contract schema + enforcement (§7.1–7.2).**
  - Operator-visible outcome: `RoleDefinition` carries allowed/forbidden/inputs/outputs/evidence_rules/completion/failure/handoff/resource, enforced per node.
  - Prereq: M2-S1.
  - Reuse (live symbols): `roles.py:28` `RoleDefinition` (capabilities + `preferred_cost_classes`); `execution_authorization.py:133` `authorize_execution`; `validator_service` (allowlisted argv, `shell=False`).
  - New/Edit (labeled): EDIT `roles.py:28` `RoleDefinition` to add the contract fields (frozen, additive). EDIT `execution_authorization.py:133` to enforce allowed/forbidden + evidence rules.
  - RED: `tests/test_agent_contracts.py::test_forbidden_action_blocked` fails.
  - GREEN (minimal): a node requesting a forbidden action fails closed at authorization; legacy roles still load.
  - Verify: `.venv/bin/python -m pytest tests/test_agent_contracts.py -q`.
  - Accept: enforcement fields present; existing roles backward compatible.
  - Rollback/authority: additive fields + guard; no runtime behavior change for existing roles.
- **M2-S4 — Six capability routes (§7.4).**
  - Operator-visible outcome: the 6 blueprint routes are typed and `resolve_role` records `resolved_via` provenance.
  - Prereq: M2-S1.
  - Reuse (live symbols): `routing.py:195` `resolve_role`, `:378` `resolve_role_compatible`; `model_router.py:449` `resolve_role_slot`.
  - New/Edit (labeled): NEW `src/devflow/loop/capability_routes.py` with `CapabilityRoute` enum (repository_analysis/deep_planning/bounded_coding/independent_review/frontier_judgment/cheap_summary). EDIT `routing.py:195` to map resolution to the enum + provenance.
  - RED: `tests/test_capability_routes.py::test_six_routes_typed` fails.
  - GREEN (minimal): all 6 routes resolve to a model/tool with provenance; unknown route rejected.
  - Verify: `.venv/bin/python -m pytest tests/test_capability_routes.py -q`.
  - Accept: named routes typed; resolution machinery unchanged for existing callers.
  - Rollback/authority: additive enum + mapping; no caller break.

---

## Milestone M3 — Per-run DAG + conflict-aware parallel sandboxes and integration candidates

**Outcome:** independent slices run concurrently in isolated worktrees, integrate without unsafe shared writes; reusable orchestration patterns. **No multi-workflow Ready Queue here (moved to M4-S3).**

- **M3-S1 — Per-run phase DAG scheduler.**
  - Operator-visible outcome: a run's nodes release per dependency edges + per-node states (M2-S2), within one run.
  - Prereq: M2-S2.
  - Reuse (live symbols): `packet_dag.py:19` `validate_packet_dag`, `:54` `ready_packet_ids`; `run_advancement.py:484` `save_advancement_command`, `:972` `advance_run`.
  - New/Edit (labeled): NEW `src/devflow/loop/dag_scheduler.py` computing per-run ready sets from dependency edges + `NodeState`.
  - RED: `tests/test_dag_scheduler.py::test_ready_set_respects_edges` fails.
  - GREEN (minimal): scheduler returns correct ready set for a small DAG; single-run scope only.
  - Verify: `.venv/bin/python -m pytest tests/test_dag_scheduler.py -q`.
  - Accept: per-run DAG ready sets; no cross-run queue.
  - Rollback/authority: new module; reuses `advance_run`.
- **M3-S2 — Resource + semantic conflict scheduling (§7.5).**
  - Operator-visible outcome: scheduler honors `heavy_model_slots`/resource and semantic-conflict rules in addition to dependency + file conflicts.
  - Prereq: M3-S1.
  - Reuse (live symbols): `run_integration.py:140` `conflicting_paths`; `result_branch.py:455` conflict handling.
  - New/Edit (labeled): EDIT `run_integration.py:140` `conflicting_paths` to also evaluate resource + semantic conflict rules. NEW `src/devflow/loop/conflict_rules.py`.
  - RED: `tests/test_conflict_scheduling.py::test_resource_slot_respected` fails.
  - GREEN (minimal): two nodes needing the same `heavy_model_slot` serialize; semantic-conflict pairs wait.
  - Verify: `.venv/bin/python -m pytest tests/test_conflict_scheduling.py -q`.
  - Accept: dependency + file conflict retained; resource/semantic added.
  - Rollback/authority: additive rules; existing conflict behavior preserved.
- **M3-S3 — Reusable patterns (§8.5).**
  - Operator-visible outcome: scatter-gather / competing / adversarial / map-verify-reduce / convergence as composable primitives.
  - Prereq: M3-S1.
  - Reuse (live symbols): `workflow_definition.py` node/edge model; `packet_dag.py` ready-set.
  - New/Edit (labeled): NEW `src/devflow/loop/patterns.py` implementing the 5 patterns as composable builders over the schema.
  - RED: `tests/test_orchestration_patterns.py::test_scatter_gather_composes` fails.
  - GREEN (minimal): one pattern composes a valid subgraph; others follow.
  - Verify: `.venv/bin/python -m pytest tests/test_orchestration_patterns.py -q`.
  - Accept: patterns are schema-level builders, no new runtime.
  - Rollback/authority: new module; additive.
- **M3-S4 — Verified integration candidates (Q1 partial; no ready queue).**
  - Operator-visible outcome: verified slices are prepared as integration candidates in dependency order; the multi-workflow Ready Queue is **deferred to M4-S3**.
  - Prereq: M3-S2.
  - Reuse (live symbols): `run_integration.py` integration manager + merge into worktree; `verification` stage as full verification; `result_branch.py` ship/merge `enabled=False`.
  - New/Edit (labeled): EDIT `run_integration.py` to expose a `collect_integration_candidates(run)` returning verified, dependency-ordered slices (read-only summary; no new queue state).
  - RED: `tests/test_integration_candidates.py::test_candidates_dependency_ordered` fails.
  - GREEN (minimal): candidates returned in dependency order for a single run; ship/merge still gated.
  - Verify: `.venv/bin/python -m pytest tests/test_integration_candidates.py -q`.
  - Accept: per-run candidates only; no multi-workflow queue.
  - Rollback/authority: additive reader; no queue state introduced.

---

## Milestone M4 — Control plane + ticket/task analyzer + ready queue + distinct human merge/full-verification/ship gates

**Outcome:** a named control plane owns tickets/projects/milestones; the Task Analyzer drives family selection; the Ready Queue is introduced here (after control-plane ownership); merge/full-verify/ship are distinct human-gated stages. **Order (D.14): control-plane aggregate → task analyzer/typed objects → ready queue → distinct human merge/full-verify/ship gates.**

- **M4-S1 — Control plane aggregate (C1).**
  - Operator-visible outcome: a `control_plane` module owning ticket/project/milestone/dependency state + ready-queue *tracking* (queue population in M4-S3).
  - Prereq: M3.
  - Reuse (live symbols): lifecycle ownership currently ad-hoc in `human_decision.py:262`, `result_branch.py:382`, `run_integration.py`; `pipeline_run.py` run records.
  - New/Edit (labeled): NEW `src/devflow/control_plane/aggregate.py` with `Ticket`/`Project`/`Milestone`/`DependencyState` (frozen, additive). No autonomous promotion (reuse `result_branch.py` boundary).
  - RED: `tests/test_control_plane.py::test_ticket_lifecycle` fails.
  - GREEN (minimal): a ticket can be created, scoped, and linked to a run; no promotion side effects.
  - Verify: `.venv/bin/python -m pytest tests/test_control_plane.py -q`.
  - Accept: first-class control-plane aggregate exists; legacy modules untouched.
  - Rollback/authority: new module; additive.
- **M4-S2 — Task Analyzer (C3) + typed objects (drives family selection).**
  - Operator-visible outcome: `discover_agent_scout_context` output formalized into a typed analyzer object (family + risk + required approvals) consumed by the compiler (R1) and control-plane ticket contract.
  - Prereq: M4-S1 + M2-S1 (schema).
  - Reuse (live symbols): `scout_discovery.py:408` `discover_agent_scout_context`; `brief_intelligence` module.
  - New/Edit (labeled): NEW `src/devflow/control_plane/task_analyzer.py` with `TaskAnalysis(family, risk, required_approvals, ...)`. EDIT `scout_discovery.py:408` to emit the typed object (additive).
  - RED: `tests/test_task_analyzer.py::test_emits_family_and_approvals` fails.
  - GREEN (minimal): analyzer returns a typed object the compiler (M5) and control plane can consume; **family selection requires this typed object + the M4-S1 ticket contract** (D.15).
  - Verify: `.venv/bin/python -m pytest tests/test_task_analyzer.py -q`.
  - Accept: typed analyzer exists; no template selection yet (M5).
  - Rollback/authority: additive; legacy scout output preserved.
- **M4-S3 — Ready Queue (moved here from M3 per D.14).**
  - Operator-visible outcome: a multi-workflow Ready Queue that admits workflows only when required gates pass and declared dependencies are satisfied.
  - Prereq: M4-S1, M4-S2.
  - Reuse (live symbols): `run_integration.py` integration manager (verified slices); `control_plane/aggregate.py` dependency state.
  - New/Edit (labeled): NEW `src/devflow/control_plane/ready_queue.py` with admission rules (gate-pass + dependency-satisfied). Distinct from `packet_dag.py:54` per-run ready set.
  - RED: `tests/test_ready_queue.py::test_admits_only_gate_passed` fails.
  - GREEN (minimal): a verified, dependency-satisfied workflow enters the queue; an unverified one does not.
  - Verify: `.venv/bin/python -m pytest tests/test_ready_queue.py -q`.
  - Accept: ready queue exists post control-plane ownership; per-run ready set (M3-S1) unchanged.
  - Rollback/authority: new module; additive.
- **M4-S4 — Independent reviewer + bounded repair loop (V1).**
  - Operator-visible outcome: a distinct independent reviewer (different model family per `run_integration.py:234` non-overlap rule) + a workflow-level repair loop with no-progress/retry bounds.
  - Prereq: M4-S1, M3-S2.
  - Reuse (live symbols): `run_integration.py:234` `IntegrationVerificationReceipt` (non-overlap), 3-attempt integration repair; `verification.py:35` `VerificationReceipt`; `builder_judge.py`/`planning_judge.py`.
  - New/Edit (labeled): EDIT `run_integration.py` to expose a workflow-level repair loop with `max_rounds` + `stop_if_no_progress`; NEW `src/devflow/loop/independent_review.py` selecting a different-family reviewer.
  - RED: `tests/test_repair_loop.py::test_no_progress_stops` fails.
  - GREEN (minimal): repair stops at no-progress bound; reviewer family differs from builder family.
  - Verify: `.venv/bin/python -m pytest tests/test_repair_loop.py -q`.
  - Accept: independent reviewer distinct; bounds enforced. (This slice is what later upgrades M1-S5's `not_run` review fields.)
  - Rollback/authority: additive loop + reviewer selection; no promotion change.
- **M4-S5 — First-class Blocker/Decision/Handoff (V2).**
  - Operator-visible outcome: `Blocker`/`Handoff` become persisted first-class objects with cause/owner/resolution + counts; `Decision` already first-class via `DecisionReceipt`.
  - Prereq: M4-S1.
  - Reuse (live symbols): `workflow_ledger.py:93` `DecisionReceipt`; `control_room/server.py` ad-hoc strings (to be replaced by derived views).
  - New/Edit (labeled): NEW `src/devflow/loop/blocker_handoff.py` with `BlockerReceipt`/`HandoffReceipt` (additive, versioned). EDIT `workflow_ledger.py` to add recorders (never mutate `DecisionReceipt`).
  - RED: `tests/test_blocker_decision_handoff.py::test_blocker_persisted_with_cause` fails.
  - GREEN (minimal): a blocker/handoff persists with cause/owner/resolution; counts derive from ledger.
  - Verify: `.venv/bin/python -m pytest tests/test_blocker_decision_handoff.py -q`.
  - Accept: three first-class objects; counts queryable.
  - Rollback/authority: additive receipts; `DecisionReceipt` untouched.
- **M4-S6 — Distinct merge / full-verification / ship gates (last).**
  - Operator-visible outcome: merge, full-verification acceptance, and ship/deploy are three distinct human-gated stages; ship remains `enabled=False` by default.
  - Prereq: M4-S3, M4-S4.
  - Reuse (live symbols): `result_branch.py` create-only result ref + `enabled=False` push/deploy; `run_supervisor.py` hard `human_decision` boundary; `run_integration.py` merge into worktree.
  - New/Edit (labeled): NEW `src/devflow/control_plane/gates.py` with distinct `MergeGate`/`FullVerifyGate`/`ShipGate` (all human-gated; ship `enabled=False`).
  - RED: `tests/test_ship_gates.py::test_ship_disabled_by_default` fails.
  - GREEN (minimal): each gate is a separate human decision; ship cannot run unless explicitly enabled by a human.
  - Verify: `.venv/bin/python -m pytest tests/test_ship_gates.py -q`.
  - Accept: three distinct gates; no autonomous promotion.
  - Rollback/authority: new module; reuses existing `enabled=False` boundary.

---

## Milestone M5 — Versioned parameterized workflow library (hotfix/feature/bug/chore) and capability routing/metrics

**Outcome:** four family templates + parameterized variants, a Factory Router binding lane/sandbox/resources/concurrency, and workflow-level metrics in the promotion packet.

- **M5-S1 — Parameterized + family templates (R2/F1).**
  - Operator-visible outcome: `hotfix`/`feature`/`bug`/`chore` templates with blueprint phase shapes, reusing M2 primitives; `canonical_product_build@1` stays the Fixed "verified-change" member.
  - Prereq: M4-S2 (typed analyzer for family selection).
  - Reuse (live symbols): `workflow_definition.py:13` `WORKFLOW_ID`, `:16` `NodeKind`, M2-S1 schema/validator.
  - New/Edit (labeled): NEW `src/devflow/loop/workflow_library.py` with the 4 family templates (parameterized variants). EDIT `workflow_definition.py` registry to register them (additive).
  - RED: `tests/test_workflow_families.py::test_four_family_templates` fails.
  - GREEN (minimal): 4 templates validate against the M2 schema; family selection uses the M4-S2 analyzer + ticket contract.
  - Verify: `.venv/bin/python -m pytest tests/test_workflow_families.py -q`.
  - Accept: Fixed + 3 family templates; no authority escalation.
  - Rollback/authority: additive templates; legacy workflow preserved.
- **M5-S2 — Factory Router (W3).**
  - Operator-visible outcome: a dedicated component binding lane/sandbox/model/resource/concurrency from routing + sandbox.
  - Prereq: M4, M3-S2.
  - Reuse (live symbols): `routing.py` role→model+endpoint+`cost_class`+profile; `git_sandbox.py:432` `create_sandbox` worktree choice.
  - New/Edit (labeled): NEW `src/devflow/control_plane/factory_router.py` composing lane/sandbox/model/resource/concurrency.
  - RED: `tests/test_factory_router.py::test_binds_lane_and_sandbox` fails.
  - GREEN (minimal): router returns a bound execution plan for a given ticket; reuses existing resolvers.
  - Verify: `.venv/bin/python -m pytest tests/test_factory_router.py -q`.
  - Accept: dedicated router; no new model resolution logic.
  - Rollback/authority: new module; additive.
- **M5-S3 — Metrics aggregation into promotion packet (M1).**
  - Operator-visible outcome: per-workflow cost/route/retries/history aggregated into the M1-S5 packet.
  - Prereq: M1-S5, M4-S1.
  - Reuse (live symbols): `local_audition_*` metrics (duration/tokens/quality); `model_catalog.py` history; `reliability.py`; M1-S5 `build_promotion_packet`.
  - New/Edit (labeled): EDIT `obsidian/promotion_packet.py` to accept an aggregated metrics object; NEW `src/devflow/loop/metrics_aggregator.py`.
  - RED: `tests/test_promotion_metrics.py::test_packet_contains_workflow_metrics` fails.
  - GREEN (minimal): packet includes aggregated per-run metrics; review fields remain `not_run` until M4-S4 produces them.
  - Verify: `.venv/bin/python -m pytest tests/test_promotion_metrics.py -q`.
  - Accept: metrics wired; no fabricated review.
  - Rollback/authority: additive aggregation; packet generator unchanged in authority.

---

## Milestone M6 — Validated generated workflow proposals with explicit approval

**Outcome:** a model may propose a purpose-built graph for novel tasks; DevFlow validates, estimates, displays, freezes it, and requires explicit human approval before execution (§6.4, §12.5).

- **M6-S1 — Workflow generator + schema validation.**
  - Operator-visible outcome: a generator proposes a graph validated against the M2 schema + budget/gate/promotion-policy pass.
  - Prereq: M5-S1 (schema/validator), M2-S1.
  - Reuse (live symbols): `workflow_definition.py:56` `validate_references`; M2-S1 validator extensions.
  - New/Edit (labeled): NEW `src/devflow/loop/workflow_generator.py` emitting a candidate graph; validate via M2 schema.
  - RED: `tests/test_workflow_generator.py::test_generated_graph_validates` fails.
  - GREEN (minimal): a generated graph passes the validator or is rejected with reasons.
  - Verify: `.venv/bin/python -m pytest tests/test_workflow_generator.py -q`.
  - Accept: generated graph validated; no execution.
  - Rollback/authority: new module; additive.
- **M6-S2 — Resource estimation + visible approval.**
  - Operator-visible outcome: estimate cost/risk; present phases; require human approval (reuse `human_decision.py:262` boundary). A generated workflow cannot grant itself more authority than policy allows (§6.3).
  - Prereq: M6-S1.
  - Reuse (live symbols): `human_decision.py:262` `record_operator_decision`; `result_branch.py` `enabled=False` boundaries.
  - New/Edit (labeled): NEW `src/devflow/control_plane/generated_approval.py` with estimate + approval gate.
  - RED: `tests/test_generated_approval.py::test_generated_cannot_self_promote` fails.
  - GREEN (minimal): approval required; generated workflow authority capped at policy.
  - Verify: `.venv/bin/python -m pytest tests/test_generated_approval.py -q`.
  - Accept: explicit human approval; no self-escalation.
  - Rollback/authority: new module; reuses human-decision boundary.

---

## Milestone M7 — Adaptive evaluation / replay / template improvement under human control

**Outcome:** the system improves from evidence while humans approve changes to control logic (§12.5, §13 reusability).

- **M7-S1 — Benchmark + replay suite.**
  - Operator-visible outcome: replay tooling over the ledger + route-quality history; uses the frozen legacy replay corpus from M2-S2.
  - Prereq: M2-S2, M4.
  - Reuse (live symbols): `workflow_ledger.py:316` `replay_workflow_run`; `routing.py` provenance; M2-S2 legacy replay fixtures.
  - New/Edit (labeled): NEW `tests/benchmarks/` + `src/devflow/loop/replay_bench.py` running the frozen corpus.
  - RED: `tests/test_replay_benchmark.py::test_frozen_corpus_replays` fails.
  - GREEN (minimal): frozen corpus replays byte/semantically identical; route quality recorded.
  - Verify: `.venv/bin/python -m pytest tests/test_replay_benchmark.py -q`.
  - Accept: replay proves legacy preservation; no writer retired without this.
  - Rollback/authority: test/bench only; no production writer change.
- **M7-S2 — Human-approved template refinements.**
  - Operator-visible outcome: proposed workflow refinements surface for explicit human approval; no self-modifying policy.
  - Prereq: M7-S1, M5-S1.
  - Reuse (live symbols): `human_decision.py:262` boundary; `workflow_library.py` templates.
  - New/Edit (labeled): NEW `src/devflow/control_plane/template_refinement.py` presenting refinements for approval.
  - RED: `tests/test_template_improvement.py::test_refinement_requires_human` fails.
  - GREEN (minimal): a refinement cannot apply without a recorded human decision.
  - Verify: `.venv/bin/python -m pytest tests/test_template_improvement.py -q`.
  - Accept: human-approved only; no self-modifying policy.
  - Rollback/authority: new module; additive.

---

## Migration gates (F.21 — must hold before any writer is retired)

1. **Frozen legacy replay corpus.** The M2-S2 fixtures (`tests/fixtures/legacy_receipts/`) are the frozen corpus. Any ledger/schema change must keep them replaying byte/semantically unchanged (asserted in `tests/test_node_lifecycle.py` + M7-S1).
2. **Canonical/noncanonical compatibility.** `is_canonical_workflow_run` (`workflow_ledger.py:344`) gates the new read model; noncanonical runs keep `LoopStage` + `adapter.py` loop-state. No migration of historical runs is forced.
3. **Post-schema validators.** Every schema/validator change (M2-S1, M5-S1, M6-S1) ships with a validator test proving the legacy `canonical_product_build@1` graph still validates.
4. **No post-gate evidence reuse.** Promotion-packet review/adversarial fields stay `not_available`/`not_run` (M1-S5) until M4-S4 actually produces them; a later milestone may upgrade the field but may not back-date fake evidence.
5. **Full suite + spine fixture + named release gate.** Before any milestone is declared done: full V2 suite (`.venv/bin/python -m pytest` or `make test`) + `PYTHONPATH=src .venv/bin/python -m devflow.cli loop spine-fixture --json` exit 0 with `final_stage=complete` + `make verify` (the release gate from `Makefile`/`scripts/release-check.sh`, also run in `.github/workflows/ci.yml`). The fixed `canonical_product_build@1` path must remain green at every step.

---

## Rollout gates / regression / release

- **Per-slice RED→GREEN:** every slice starts from a failing test; no slice merges without its focused test green and `git diff --check` clean.
- **Full regression / release gate:** before any milestone is declared done, run `make test` (full V2 suite, ≥150 Phase tests + new milestone tests) and `PYTHONPATH=src .venv/bin/python -m devflow.cli loop spine-fixture --json` must exit 0 with `final_stage=complete`, then `make verify` (the named CI release gate). The fixed `canonical_product_build@1` path must remain green at every step.
- **Independent review:** each milestone's slices are reviewed by a worker from a *different* family than the implementer (implementer = coding model; reviewer = independent_review route, per §7.4 non-overlap already enforced in `run_integration.py:234`). Promotion-packet, control-plane, and ship-gate slices require a human reviewer sign-off.
- **Migration / compatibility strategy (#26/#27):** canonical state is read via the new additive read model (`read_model.py`, M0-S1) for canonical-marked runs; `LoopStage` and loop-state persistence remain for noncanonical/historical compatibility. Runs without the canonical marker retain saved-state and inference path without migration. No forced re-run; new runs use the generalized VM only after M2 lands. **No global collapse erases noncanonical compatibility state** (C.11).
- **No autonomous promotion:** every promotion/push/PR/deploy stays behind explicit human authority and `enabled=False` defaults (`result_branch.py`). Obsidian projections are read-only-first (§10.8); editing a note never mutates canonical state.
- **Explicit postponements:** visual workflow editor, raw-log duplication into vault, self-modifying policies, OS-level network isolation, and generated-workflow authority escalation are out of scope (blueprint §12.5).

---

## Per-milestone blueprint mapping + coverage table (F.20)

| Blueprint ref | Domain | Gap IDs | Milestone(s) | Status note |
|---|---|---|---|---|
| §4 / §4.1 | Architecture / Control plane | C1, C2 | M4 (C1), M2/M4 (C2) | C2 PARTIAL; C1 MISSING→M4 |
| §4.2 | Workflow plane | R1–R7 | M2, M3 | R1 PARTIAL, R2 PARTIAL, R3 PARTIAL, R4 MISSING, R5 PARTIAL, R6 MISSING, R7 PARTIAL |
| §4.3 | Worker plane | W1, W2, W3 | M2, M5 | all PARTIAL |
| §4.4 | Evidence/projection | E1, E2, O1–O4 | M1, M4 | E1 PARTIAL, E2 MISSING, O1 MISSING, O2 MISSING, O3 MISSING/DEFERRED, O4 PARTIAL |
| §4.5 | Canonical flow | C1, C3, R1, W3 | M4, M2, M5 | — |
| §5 / §5.1 | Lifecycle / states | C1, Q1, R4 | M4, M3, M2 | R4 MISSING→M2 |
| §5.2 | Blocker/Decision/Handoff | V2 | M4-S5 | PARTIAL |
| §6 / §6.2–6.3 | Compiler + validation | R1 | M2-S1, M5 | PARTIAL |
| §6.4 | Workflow classes | R2, F1 | M5 | PARTIAL/F1 MISSING |
| §6.5 | Primitives | R3 | M2-S1, M3 | PARTIAL (misaligned) |
| §6.6 | Runtime responsibilities | R7 | M2, M3 | PARTIAL |
| §7 / §7.1–7.2 | Contracts | W1 | M2-S3 | PARTIAL |
| §7.4 | Capability routes | W2 | M2-S4 | PARTIAL |
| §7.5 | Conflict parallelism | R5 | M3-S2 | PARTIAL |
| §8 / §8.1–8.4 | Families | F1, R2 | M5 | MISSING/F1 |
| §8.5 | Patterns | R6 | M3-S3 | MISSING |
| §9 / §9.1–9.3 | Verification/trust | V1 | M4-S4 | PARTIAL |
| §9.4 | Promotion packet | E2, C2 | M1-S5, M4 | E2 MISSING (honest), C2 PARTIAL |
| §10 / §10.1–10.3 | Canonical state | E1, O1–O2 | M1, M4 | E1 PARTIAL, O1/O2 MISSING |
| §10.4 | Projection service | O1 | M1 | MISSING (service) |
| §10.5–10.7 | Vault views | O2 | M1 | MISSING |
| §10.8 | Read-only first | O3 | M1 (deferred) | MISSING/DEFERRED |
| §11 | UX / progressive disclosure | O4 | M1, existing | PARTIAL |
| §12 | Roadmap | all | M0–M7 | staged |
| §13 | Success criteria | see below | — | — |

**§13 success-criteria coverage:**

| §13 criterion | Gap ID | Milestone | Conservative status |
|---|---|---|---|
| Durability (resume after failure) | R7 | M2, M3, M7-S1 | PARTIAL — replay/recovery/cancellation exist; explicit pause, full timeout/budget/no-progress/checkpoint semantics not all complete |
| Traceability (frozen contract + history) | E1, R4 | M1, M2-S2 | PARTIAL — append-only ledger/receipts implemented; blueprint-normalized artifact registry/classes (risk/follow-up/costs/history/handoffs) incomplete |
| Safety (no out-of-envelope write; no self-escalation) | C2, V1, M6-S2 | M2, M4, M6 | PARTIAL — typed decision + result-branch admission implemented; distinct merge/full-verify/ship authorization missing |
| Verification (deterministic + independent review) | V1 | M4-S4 | PARTIAL — deterministic + judge verification present; distinct independent reviewer + workflow repair loop incomplete |
| Portability (capability requests) | W2, W3 | M2-S4, M5-S2 | PARTIAL — resolution machinery present; named routes/Factory Router incomplete |
| Boundedness (explicit limits) | R4, V1 | M2-S2, M4-S4 | PARTIAL — retries/recovery exist; full timeout/budget/no-progress/checkpoint bounds incomplete |
| Operator clarity (one screen) | O4 | M1, existing | PARTIAL — browser status board exists; Command Center computed status/evidence/next-action views incomplete |
| Human control (merge/promotion under authority) | C2 | M4-S6 | PARTIAL — typed decision + result-branch admission implemented; distinct merge/full-verify/ship gates missing |
| Efficiency (per-run cost/route/retries) | M1 | M5-S3 | PARTIAL — raw metrics present; not aggregated into packet |
| Reusability (versioned/comparable) | M2, F1, M7 | M5, M7 | MISSING — no parameterized/generated library yet |

---

## Next action (smallest first slice, after human approval) — F.22

**M0-S1 — Add a canonical run read-model adapter (additive, zero writer changes):** add `src/devflow/loop/read_model.py` with `derive_canonical_run_model(snapshot)` that builds a frozen `CanonicalRunModel` purely from `rebuild_workflow_snapshot` (`workflow_ledger.py:334`) for canonical-marked runs (`is_canonical_workflow_run`, `:344`); assert in `tests/test_loop_read_model.py::test_derive_from_snapshot` that the model is computed from the snapshot, not persisted as truth. **This is the smallest safe additive read-model slice — it introduces no state collapse, changes no existing writer, and keeps `LoopStage` (`models.py:18`) and loop-state persistence (`adapter.py`) intact for noncanonical/historical compatibility.** It unblocks every later milestone's honest public read model without touching canonical writes.

---

## Delegation execution map (per global rules) — F.23

- **Scouts (read-only):** orient on the exact owning module before any edit (`mcp__context_map__orient`); verify `file:line` symbols; never modify. Used in M0/M2/M4 prep.
- **Implementers:** bounded vertical slices, one RED→GREEN per slice; prefer cheapest capable worker for deterministic/CLI slices, coding-specialized worker for runtime/compiler slices (§7.4 `bounded_coding`).
- **Testers:** author the RED test for each slice; run focused suite; confirm `git diff --check` clean.
- **Independent reviewers:** a *different* model family than the implementer; for promotion-packet, control-plane, and ship-gate slices require human reviewer sign-off (§7.4 `independent_review`, non-overlap enforced by `run_integration.py:234`).
- **Frontier supervisor boundary:** only for difficult ambiguity / policy exception / high-risk verdict (§7.6) and only when evidence shows lower tiers insufficient; never for promotion.
- **Evidence / route accounting:** every worker records `resolved_via` + model/route in run evidence (existing `routing.py` provenance); each slice's acceptance artifact (test output, generated vault note, or receipt) is referenced in the PR/summary. No slice is "done" without its acceptance evidence file present.
- **Explicit no-autonomous-promotion policy:** no slice may promote, push, open a PR, or deploy. Promotion/push/PR/deploy remain behind explicit human authority and `enabled=False` defaults (`result_branch.py`). Obsidian projections are read-only-first (§10.8); editing a note never mutates canonical state. This policy is non-negotiable and is preserved across every milestone above.

*Planning-only. No code was written. See `docs/DEVFLOW_BLUEPRINT_GAP_ASSESSMENT.md` for gap detail and `docs/DEVFLOW_SOURCE_OF_TRUTH.md` for current implementation.*
