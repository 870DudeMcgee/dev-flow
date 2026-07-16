# DevFlow — Blueprint Gap Assessment (Current State → Software-Factory Blueprint)

**Status:** Authoritative current-state gap assessment. Planning/documentation only; no code, tests, or config changed.
**As-of:** 2026-07-14
**Baseline SHA:** `6122fb5` (`test: make git fixtures branch deterministic`)
**Baseline evidence:** 150 targeted Phase tests passed (real `pytest` run, exit 0) against the fixed `canonical_product_build@1` spine. Old canonical Phases 1–6 are a hardened subset of blueprint Stage 1 / runtime foundation, **not** completion of the blueprint's six roadmap stages.

---

## Authority statement

- **Blueprint (highest *target direction*):** `docs/DevFlow_Software_Factory_Vision_Architecture_Blueprint.docx` — defines the *target* product, architecture, workflow-runtime, worker contracts, human authority, and Obsidian integration. It describes the north star, not what is implemented today.
- **Live source/tests (operative *current-implementation facts*):** `src/devflow/loop/`, `src/devflow/control_room/`, `src/devflow/cli.py`, `tests/` — define what is *actually implemented now*. Where this assessment cites `file:line`, it was read directly from live source; where a prose doc and live code disagree on what exists today, live code wins.
- **Current-implementation reference (subordinate current-runtime orientation):** `docs/DEVFLOW_SOURCE_OF_TRUTH.md` — records current runtime/orientation; it may lag live code (it even admits stale sentences) and is re-pointed by this packet, so it sits *below* live source/tests for "what is implemented now."
- **This document (dated derived doc):** subordinate to the blueprint and to live source/tests; it maps current implementation to blueprint gaps and names the closure plan (`docs/superpowers/plans/2026-07-14-devflow-software-factory-gap-closure.md`).
- All existing Phase 1–6 primitives are **preserved and generalized**, not rewritten.

---

## Where we are after the old Phase 6

The old canonical Phases 1–6 built a **fixed, linear, 11-stage product-build loop** (`canonical_product_build@1`) with the following proven, test-backed machinery:

- An **event-sourced workflow ledger** with append-only receipts and deterministic replay/rebuild.
- A **frozen, secret-safe source snapshot** taken through a temporary Git index (operator checkout never touched).
- **Host-owned preparation gates**: packet-DAG ready-set, typed allowlisted validators (`shell=False`, bounded timeout, no-network/no-extra-permission declarations), exact-bind authorization.
- **Bounded Git sandboxes** rooted only at the authorized snapshot commit, with positive ownership and fail-closed cleanup.
- A **single mutating advancement entry point** (`advance_run`) with claims/attempts/recovery, immutable binary-safe packet patch capture, and dependency-order integration with independent, model-family-non-overlap verification.
- **Human authority that cannot be bypassed**: a typed immutable `DecisionReceipt` (`accept` only sets `promotion_eligible`); a real, create-only `refs/heads/devflow/results/<run_id>` branch gated on a live, clean, independently-verified integration head; push/PR/deploy freeze as disabled-by-default typed commands; the repeat-only supervisor stops at `human_decision` and never self-accepts/promotes/touches `main`/merges/pushes/deploys.

This satisfies much of blueprint §12.1–12.2 (MVP runtime foundation) and §13 (durability, traceability, safety, human control). It does **not** satisfy the rest of the blueprint: there is no control plane, no workflow compiler beyond one frozen graph, no DAG/parallel runtime, no workflow families, no Obsidian Command Center projection, no structured promotion packet, and no adaptive improvement layer.

---

## Already real / preserve (Phases 1–6 primitives)

Do not rebuild these. Reuse the exact symbols below when closing gaps.

| Phase | Capability | Key symbols (live `file:line`) | Tests |
|---|---|---|---|
| 1 | Workflow ledger: append-only events, immutable receipts, deterministic replay + rebuildable snapshot | `workflow_ledger.py:316` `replay_workflow_run`; `:334` `rebuild_workflow_snapshot`; `:386` `record_node_outcome`; `:448` `record_decision`; `:344` `is_canonical_workflow_run`; `NodeReceipt:47`; `DecisionReceipt:93`; `WorkflowSnapshot:69` | `test_workflow_ledger`, `test_workflow_ledger_decision` |
| 2 | Source snapshot: frozen commit via temp index, run-scoped ref, secret policy, fail-closed | `source_snapshot.py:301` `create_source_snapshot`; `:205` `_reject_ignored_paths`; `:182` `_is_sensitive_path` | `test_source_snapshot`, `test_source_snapshot_adversarial` |
| 3 | Preparation/authorization: typed plan validators, packet-DAG ready-set, exact-bind checks | `execution_authorization.py:133` `authorize_execution`; `:155` staleness checks; `validator_service` (typed argv, `shell=False`); `packet_dag.py:19` `validate_packet_dag`; `:54` `ready_packet_ids` | `test_execution_authorization`, `test_packet_dag` |
| 4 | Sandbox/worktree: linked worktree from authorized snapshot, ownership, cleanup receipts | `git_sandbox.py:432` `create_sandbox`; `:403` `_validate_packet_binding`; `:294` `_verify_owned_worktree` | `test_git_sandbox` |
| 5 | Advancement + integration/verification: sole mutating entry, claims/attempts/recovery, immutable patches, independent verification | `run_advancement.py:484` `save_advancement_command`; `:143` `AdvanceCommand`; `run_integration.py:1` + `IntegrationVerificationReceipt:234`; `conflicting_paths:140` | `test_run_advancement`, `test_run_integration` |
| 6 | Human decision (typed immutable receipt, fail-closed) + result-branch promotion (create-only, ref-safe, no auto-promote) | `human_decision.py:262` `record_operator_decision`; `result_branch.py:382` `create_result_ref`; `:126` `PromotionReceipt`; `run_supervisor.py` hard `human_decision` boundary; push/deploy `enabled=False` | `test_result_branch`, `test_run_supervisor`, `test_workflow_ledger_decision` |

---

## Comprehensive blueprint gap matrix

Legend — **Status:** IMPLEMENTED / PARTIAL / MISSING. **Layer:** Infra = canonical Phase 1–6 foundation already built; Product = product-level wiring to blueprint behavior. **Dependency:** gap IDs this depends on. **Data present** means the structured fields/artifacts exist but are not yet wired into the full blueprint behavior.

### Control plane

| # | Blueprint domain (ref) | Status | Layer | Evidence (file:line) | Tests | Dep | Acceptance outcome | Data present vs full wiring |
|---|---|---|---|---|---|---|---|---|
| C1 | Control plane — tickets, projects, milestones, dependency state, ready queue, merge/full-verify/ship (§4.1, §5) | MISSING | Product | No first-class control-plane aggregate found in the inspected active surfaces (`src/devflow/loop/`, `src/devflow/control_room/`, `src/devflow/cli.py`): lifecycle is spread ad-hoc across `human_decision.py:262`, `result_branch.py:382`, `run_integration.py`; there is no `control_plane/` module and no `ticket`/`project`/`milestone` owning class. (This is a concrete owning-module finding, not a claim that every ad-hoc string is absent.) | none | — | Named control-plane module owning ticket/project/milestone state, ready queue, merge/full-verify/ship tracking. | None. |
| C2 | Control-plane human authority / promotion distinctions (§9.4, §4.1) | PARTIAL | Product | `workflow_ledger.py:448` `record_decision`; `DecisionReceipt:93` (accept only sets `promotion_eligible`); `result_branch.py:382` `create_result_ref`; `run_supervisor.py` hard boundary; push/deploy `enabled=False`. | `test_workflow_ledger_decision`, `test_result_branch`, `test_run_supervisor` | — | Typed decision + result-branch admission are implemented, but the blueprint's *distinct* Ready Queue admission, merge authorization, full-verification acceptance, and ship/deploy authorization are **not** separated (all collapse into the single `human_decision` boundary today). | Data/primitive present: typed decision + result-branch admission. Missing: distinct merge / full-verify / ship authorization gates (see M4-S6). |
| C3 | Task Analyzer — intake / classify / scope / risk / required approvals → workflow family (§4.5, §5.2) | PARTIAL | Infra | `scout_discovery.py:408` `discover_agent_scout_context` builds scope/title/verification/risks; `brief_intelligence`. No formal analyzer emitting workflow-family + risk + required-approvals object. | `test_brief_intelligence`, scout tests | C1 | Analyzer emits classification object that drives the compiler (R1). | Scope/risk text present; no typed family+approvals object. |

### Compiler / runtime

| # | Blueprint domain (ref) | Status | Layer | Evidence (file:line) | Tests | Dep | Acceptance outcome | Data present vs full wiring |
|---|---|---|---|---|---|---|---|---|
| R1 | Workflow compiler — validated graph emission incl. family selection + budget/gate/policy pass (§6.2–6.3) | PARTIAL | Product | `workflow_definition.py:56` `validate_references` (cycle/ref/terminal checks); `canonical_product_build_v1` (`workflow_definition.py:23`). No ticket→template selection, no budget/gate/promotion-policy validation pass. | `test_workflow_definition` | C3, R4 | Compiler that selects a family template and validates budgets, gates, promotion policy. | Graph validation present; no family selection or budget/gate policy pass. |
| R2 | Workflow classes — Fixed / Parameterized / Generated (§6.4) | PARTIAL (Fixed only) | Product | Only `canonical_product_build@1` (`workflow_definition.py:13`). No parameterized or generated classes, no generator. | none | R1 | ≥3 workflow classes; generated path with schema validation + explicit approval. | Fixed class present; parameterized/generated absent. |
| R3 | Runtime primitives — sequence/parallel/dag/agent/command/gate/conditional/loop/human_gate/artifact_emit (§6.5) | PARTIAL (misaligned) | Infra→Product | `workflow_definition.py:16` `NodeKind` = human/agent/code only; linear success/failure chain. No dag/parallel/loop/gate/conditional/artifact_emit executors. `packet_dag.py` ready-set is per-packet, not phase DAG. | `test_packet_dag` | R1, R4 | Real executors for the blueprint primitive set. | Sequence/agent/command realized implicitly; dag/parallel/loop/gate/conditional/artifact_emit absent. |
| R4 | Node lifecycle states — planned→ready→running→verified, retrying, blocked, awaiting_gate, failed, cancelled (§5.1) | MISSING | Product | `NodeReceipt` (`workflow_ledger.py:47`) carries only `success`/`failure`. `LoopStage` (`models.py:18`) is a coarse 11-stage chain. No per-node state machine. | none | — | Per-node state machine with defined terminals + terminal workflow states (`completed`/`awaiting_promotion`/`needs_rework`/`failed`/`cancelled`/`shipped`). | None. |
| R5 | Conflict-aware scheduling — dependency/file/resource/semantic (§7.5) | PARTIAL | Infra | Dependency ready-set (`packet_dag.py`); file/path conflict (`run_integration.py:140` `conflicting_paths`, `result_branch.py:455`). No `heavy_model_slots`/resource or semantic-conflict scheduler. | `test_packet_dag`, `test_run_integration` | R3 | Resource + semantic conflict scheduling honoring blueprint rules. | Dependency + file conflict present; resource/semantic absent. |
| R6 | Reusable orchestration patterns — scatter-gather / competing / adversarial / map-verify-reduce / convergence (§8.5) | MISSING | Product | None present. | none | R3 | The 5 patterns as composable primitives. | None. |
| R7 | Durability — resume / cancel / checkpoint / replay (§6.6, §4.2) | PARTIAL | Product | `run_advancement.py` `advance_run`; replay/projection; `run_supervisor.py` repeat-only; `pipeline_run.py:364` `cancellation_requested`; `loop spine-fixture` exits 0. Replay/recovery/cancellation exist, but explicit pause, full timeout/budget/no-progress/checkpoint semantics are **not all complete** (no first-class node lifecycle, see R4). | `test_run_advancement`, `test_run_advancement_recovery`, `test_run_supervisor` | — | Deterministic replay green; add explicit pause, timeout/budget/no-progress/checkpoint semantics. | Replay/recovery/cancellation present; full lifecycle/pause/checkpoint semantics incomplete. |

### Worker contracts / routing / scheduling

| # | Blueprint domain (ref) | Status | Layer | Evidence (file:line) | Tests | Dep | Acceptance outcome | Data present vs full wiring |
|---|---|---|---|---|---|---|---|---|
| W1 | Agent contracts — id/purpose/capability/allowed/forbidden/inputs/outputs/evidence/completion/failure/handoff/resource (§7.1–7.2) | PARTIAL | Infra | `roles.py:28` `RoleDefinition` = capabilities + `preferred_cost_classes` only. No allowed/forbidden/evidence/completion/failure/handoff/resource fields or per-node enforcement. | `test_capability_routing` | R3 | Contract schema with enforcement of allowed/forbidden + evidence rules. | Capability + cost-class present; enforcement fields absent. |
| W2 | Capability routing — 6 provider-independent routes (§7.4) | PARTIAL | Infra | `routing.py:195` `resolve_role`, `:378` `resolve_role_compatible`; dynamic free-cloud catalog; `resolved_via` provenance. Blueprint's 6 named routes not modeled. | `test_capability_routing` | W1 | Map the 6 capability routes (repository_analysis/deep_planning/bounded_coding/independent_review/frontier_judgment/cheap_summary). | Resolution machinery present; named routes not typed. |
| W3 | Factory Router — lane/sandbox/model/resource/concurrency assignment (§4.5, §6.2) | PARTIAL | Infra | `routing.py` resolves role→model+endpoint+`cost_class`+profile; `git_sandbox.py` worktree choice. No dedicated component named Factory Router; concurrency policy minimal. | `test_capability_routing` | W2, R5 | Dedicated router component binding lane/sandbox/resources/concurrency. | Partial resolution present; no dedicated component. |
| (R5 above) | Conflict-aware scheduling | PARTIAL | — | see R5 | — | — | — | — |

### Verification / human authority

| # | Blueprint domain (ref) | Status | Layer | Evidence (file:line) | Tests | Dep | Acceptance outcome | Data present vs full wiring |
|---|---|---|---|---|---|---|---|---|
| V1 | Verification / judges / repair loops (§9.1–9.3) | PARTIAL | Product | `verification.py:35` `VerificationReceipt`; `builder_judge.py`, `planning_judge.py`; `execution.py` judge prompts; packet-level repair (3-attempt integration repair). No workflow-level bounded repair loop w/ no-progress detection; independent reviewer not distinct from `build_judge`. | `test_loop_verification`, `test_loop_builder_judge`, `test_planning_judge` | R4 | Independent reviewer + repair loop with no-progress/retry bounds. | Deterministic + judge verification present; workflow-level repair loop + distinct independent reviewer absent. |
| V2 | Blocker / Decision / Handoff first-class objects (§5.2) | PARTIAL | Product | `Decision` exists (`DecisionReceipt`). `Blocker`/`Handoff` not first-class — only ad-hoc strings in `control_room/server.py`. No counts/queues persisted. | none for blocker/handoff | C1 | Three first-class objects with cause/owner/resolution + counts. | Decision present; Blocker/Handoff ad-hoc only. |
| (C2 above) | Human authority / promotion | IMPLEMENTED | — | see C2 | — | — | — | — |

### Evidence / artifacts

| # | Blueprint domain (ref) | Status | Layer | Evidence (file:line) | Tests | Dep | Acceptance outcome | Data present vs full wiring |
|---|---|---|---|---|---|---|---|---|
| E1 | Artifact/evidence schemas + append-only state (§10.1–10.2, §4.4) | PARTIAL | Product | `workflow_ledger.py:28` append-only events; frozen `NodeReceipt`/`DecisionReceipt`; `pipeline_run.py` artifact store + receipts. The append-only ledger/receipts are implemented, but the blueprint-normalized artifact registry/classes (risk/follow-up/costs/history/handoffs, §10.2 §13) are **incomplete** — no typed `Risk`/`FollowUp`/`Cost`/`Handoff` classes persisted as first-class. | `test_workflow_ledger` | — | Add blueprint-normalized artifact classes and aggregate them into a promotion packet. | Ledger/receipts present; normalized artifact registry/classes incomplete. |
| E2 | Promotion packet materialization (§9.4, Appendix C) | MISSING | Product | `result_branch.py` does not emit `promotion-packet.md` (objective, diff/changed-path summary, deterministic verification, independent review/adversarial findings, open risks, recommended action). | none | V1, C2 | On `accept`, an inspectable `promotion-packet.md` is generated and linked from the vault; derived, non-authoritative. | Receipts + reliability-report + spec/plan fixtures present in run dir; no assembled packet. |

### Workflow families

| # | Blueprint domain (ref) | Status | Layer | Evidence (file:line) | Tests | Dep | Acceptance outcome | Data present vs full wiring |
|---|---|---|---|---|---|---|---|---|
| F1 | Workflow families — hotfix / feature / bug / chore (§8.1–8.4) | MISSING | Product | No family templates; single `canonical_product_build@1` linear loop. | none | R1, R2 | 4 family templates with blueprint phase shapes. | None. |

### Ready queue / integration / ship

| # | Blueprint domain (ref) | Status | Layer | Evidence (file:line) | Tests | Dep | Acceptance outcome | Data present vs full wiring |
|---|---|---|---|---|---|---|---|---|
| Q1 | Ready queue / integration order / merge / full verification / ship (§4.1, §5.8–5.11) | PARTIAL | Product | `run_integration.py` integration manager + merge into worktree; `verification` stage = full verification. No multi-workflow ready queue; ship/merge-to-main disabled (`enabled=False`). | `test_run_integration` | C1, R5 | Ready queue of workflows + ship gating under human authority. | Single-workflow integration + merge present; multi-workflow queue + ship gate absent. |

### Obsidian projection / UX

| # | Blueprint domain (ref) | Status | Layer | Evidence (file:line) | Tests | Dep | Acceptance outcome | Data present vs full wiring |
|---|---|---|---|---|---|---|---|---|
| O1 | Obsidian projection service — watch/subscribe, atomic, deterministic counts (§10.4) | MISSING (service) | Product | No watch/subscribe service. `brief_intelligence/formatter.py:7` `format_obsidian` writes static `Obsidian/Brief.md`; `model_catalog_markdown.py:9` `START_MARKER`/`END_MARKER` + `:145` `update_model_dashboard` render inventory; `cli.py:48` `--obsidian-dashboard` one-shot. No Command Center dir generated (vault dirs absent on disk). | `test_model_catalog_markdown` | E1 | Projection service emitting deterministic, atomic Command Center views. | Ad-hoc markdown writers present; no projection service. |
| O2 | Vault views — Overview/Workflow/Tasks/Evidence/Decisions/Risks/History + `.generated/` (§10.5–10.7) | MISSING | Product | No generated vault org (find returned nothing). Only model-catalog inventory + brief note exist. | none | O1 | Views per §10.5; stable links to canonical artifacts. | None. |
| O3 | Read-only first, controlled actions later (§10.8) | MISSING / DEFERRED | Product | Observability-first projection is **not yet reached**: there is no projection service (O1), so the read-only-first boundary has no controlled-action surface to gate. Current writes are generate-only ad-hoc markdown writers (`brief_intelligence/formatter.py:7`, `model_catalog_markdown.py:9`). This is deferred, not N/A — it becomes actionable only after O1/O2 land. | — | O1, O2 | Defer; revisit after O1/O2 — controlled actions (approve/reject/pause/resume/cancel/repair/promote) send validated control requests to DevFlow, never mutate canonical state by editing a note. | None (prereq unmet). |
| O4 | Operator UX / progressive disclosure / status board (§11) | PARTIAL | Product | `control_room/server.py:1356` `run_server` status board (auto-refresh, progressive disclosure, refresh preserves selection per SOURCE_OF_TRUTH). The browser status board/progressive disclosure exists, but the blueprint Command Center, attention queues, and all computed status/evidence/next-action views over the Command Center are **incomplete** (no `Overview`/`Workflow`/`Tasks`/`Evidence`/`Decisions`/`Risks`/`History` Command Center views, no computed health/blocker/decision/handoff counts — see O1/O2). | `test_control_room_page` | — | Browser surface present; add Command Center computed views (O1/O2). | Status board present; Command Center computed views incomplete. |

### Metrics / durability / adaptive improvement

| # | Blueprint domain (ref) | Status | Layer | Evidence (file:line) | Tests | Dep | Acceptance outcome | Data present vs full wiring |
|---|---|---|---|---|---|---|---|---|
| M1 | Metrics / costs / history aggregated into promotion packet (§10.2, §13 efficiency) | PARTIAL | Infra→Product | `local_audition_*` metrics (duration/tokens/quality); `model_catalog.py` history; `reliability.py`. No per-workflow cost/token/retries aggregated into a promotion packet. | `test_local_audition_*` | E2 | Workflow-level cost/route/retries/history in promotion packet. | Raw metrics present; not aggregated into packet. |
| M2 | Generated workflows & adaptive improvement (§12.5, §6.4) | MISSING | Product | No workflow generator; `local_audition_decision.py` proposes role mappings only, not graphs. | none | R2, M7 | Generator + replay/benchmark + human-approved refinements. | None. |

---

## Cross-cutting contradictions

1. **Coexisting (not collapsed) canonical state models (#26).** Three overlapping persistence models coexist:
   - `models.py:18` `LoopStage` — coarse 11-stage chain, which `DEVFLOW_SOURCE_OF_TRUTH.md` itself calls "only a compatibility/UI projection."
   - `workflow_definition.py` `WorkflowNode` + `workflow_ledger.WorkflowSnapshot` rebuilt from events (`:69`, `:334`).
   - `pipeline_run.py` `LoopState` via adapter (`adapter.load_loop_state:74`, `save_loop_state:148`).
   The blueprint expects ONE canonical state **for canonical-marked runs only** (`is_canonical_workflow_run`, `:344`). **Resolution (strangler, not collapse, C.11):** add a canonical read model derived from `WorkflowSnapshot`; keep `LoopStage` and loop-state persistence for noncanonical/historical compatibility. Migrate canonical consumers incrementally; prove old receipts replay byte/semantically unchanged before retiring any writer. No global collapse erases noncanonical compatibility state.
2. **Single linear chain vs blueprint phase graph (#27).** The blueprint's branching, looped, DAG-based phase model (grounding→spec↔judge→impl DAG→per-slice verify→integration→review→promote, §8) is not realized; the live system is a fixed 11-node linear chain (`workflow_definition._SUCCESS_CHAIN`, `:185`–`230`) with success/failure edges only. This is the largest architecture divergence and underlies R1–R5, F1.
3. **Declarations vs OS enforcement.** Network/permission fields are fail-closed *declarations* with receipt evidence (`execution_authorization.py`, `validator_service`), not OS-level network isolation or privilege dropping. Validators run allowlisted argv with `shell=False`, relative cwd, bounded timeout — but there is no OS sandbox enforcement. Keep declarations; do not claim OS isolation.
4. **Stale docs.** The Phase 6 status sentence at `DEVFLOW_SOURCE_OF_TRUTH.md:401–403` ("…human acceptance, and local result-branch creation remain Phase 6 work") is stale now that Phase 6 is complete and verified; it has been repaired to point at this assessment. Other doc drift (e.g. linear-chain descriptions) should be reconciled as part of M0 read-model convergence.

---

## Prioritized gap clusters and explicit non-goals

**Prioritized clusters (closure order in plan):**
- **Cluster 0 — Read-model convergence (M0):** resolve #26/#27 and stale docs via a **strangler/additive read model** so `LoopStage` is kept for compatibility and a canonical read model is *derived* from the ledger for canonical-marked runs (no collapse, no writer change). No new behavior.
- **Cluster 1 — Observability (M1):** Obsidian Command Center projection (O1/O2) + promotion packet (E2) for the existing verified-change workflow. Lowest risk, highest operator value; honors "observability-first."
- **Cluster 2 — Generalized workflow VM (M2):** full runtime primitives (R3), node lifecycle (R4), contract schema (W1), capability routes (W2).
- **Cluster 3 — DAG + parallel (M3):** conflict-aware scheduling (R5), reusable patterns (R6), integration/ready-queue (Q1).
- **Cluster 4 — Control plane + human gates (M4):** tickets/projects/analyzer (C1/C3), independent review + repair loop (V1), first-class Blocker/Decision/Handoff (V2), distinct merge/full-verify/ship gates.
- **Cluster 5 — Workflow library + routing (M5):** parameterized/family templates (R2/F1), Factory Router (W3), metrics aggregation (M1).
- **Cluster 6 — Generated proposals (M6):** validated generated workflows with explicit approval.
- **Cluster 7 — Adaptive improvement (M7):** benchmark/replay/refine under human control (M2).

**Explicit non-goals (postponed per blueprint §12.5):**
- No autonomous promotion / push / PR / deploy from the vault or runtime.
- No visual workflow editor before schema + runtime stabilize.
- No copying of every raw log/artifact into Obsidian (link only, §10.3).
- No self-modifying workflow policies or unrestricted agent swarms.
- No generated workflows granted authority beyond policy (§6.3, §9.4).
- No OS-level network isolation / privilege dropping unless a later human-directed milestone adds it; declarations stay fail-closed.

---

## Evidence commands / results and freshness rule

Real commands run during this assessment (all exit 0 unless noted):

```bash
git rev-parse HEAD                                   # 6122fb5
PYTHONPATH=src .venv/bin/python -m devflow.cli loop spine-fixture --json   # exit 0 (chain idea→…→complete)
.venv/bin/python -m pytest tests/test_workflow_ledger.py test_workflow_ledger_decision.py \
      test_source_snapshot.py test_source_snapshot_adversarial.py \
      test_execution_authorization.py test_packet_dag.py test_git_sandbox.py \
      test_run_advancement.py test_run_integration.py test_result_branch.py \
      test_run_supervisor.py                         # 150 passed
# Targeted, honest searches (exact wording; each returns matches, NOT "0 matches" for a broad pattern):
#   - No workflow compiler / projection service exists:
grep -rnE "class WorkflowCompiler|def compile_workflow|WorkflowCompiler\(" src/   # 0 matches -> no compiler
grep -rnE "Command Center|projection service|watch|subscribe|emit_command_center" src/   # 0 matches -> no Obsidian Command Center projection service
#   - BUT ad-hoc Obsidian/markdown writers DO exist (so the absence claim is qualified, not "no Obsidian code"):
grep -rnE "obsidian|format_obsidian|update_model_dashboard|START_MARKER" src/   # matches: brief_intelligence/formatter.py:7, model_catalog_markdown.py:9/145
```

**Freshness rule:** any gap status in this document is valid only against baseline `6122fb5`. Before acting on a gap, re-run `git rev-parse HEAD` and the targeted test subset above; if HEAD moved or a cited `file:line` no longer matches, re-verify the specific symbol (`search_files`/`read_file`) before planning the slice. Treat `PYTHONPATH=src .venv/bin/python -m devflow.cli loop spine-fixture --json` exiting 0 as the regression gate that must remain green across every closure milestone.

**Replay-safety / canonical-state principle (C.11/C.12):** the append-only ledger is canonical **only for canonical-marked runs** (`is_canonical_workflow_run`, `workflow_ledger.py:344`); `LoopStage` and loop-state persistence remain for noncanonical/historical compatibility. `NodeReceipt` (`workflow_ledger.py:47`) is immutable and is **never replaced in place** — new lifecycle semantics are additive/versioned with backward-compatible replay fixtures. No writer is retired and no state is collapsed until legacy receipts are proven to replay byte/semantically unchanged.

---

*Subordinate to the blueprint (`docs/DevFlow_Software_Factory_Vision_Architecture_Blueprint.docx`) and to live source/tests, then to `docs/DEVFLOW_SOURCE_OF_TRUTH.md`. Closure plan (dated derived doc): `docs/superpowers/plans/2026-07-14-devflow-software-factory-gap-closure.md`.*
