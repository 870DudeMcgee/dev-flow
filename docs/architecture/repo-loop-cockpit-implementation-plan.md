# Repo Loop Cockpit Implementation Plan

Status: active implementation ledger  
Date: 2026-07-06  
Related: [ADR 0002](../adr/0002-repo-loop-cockpit-over-hermes-runtime.md), [../control-room-mvp.md](../control-room-mvp.md), [local-operating-layer-ui.md](local-operating-layer-ui.md), [../../CONTEXT.md](../../CONTEXT.md)

## Contract Summary

Dev-Flow is narrowing from broad command center to selected-repo loop cockpit.

Obsidian Command Center owns broad capture, durable project context, daily context, parking lots, and cross-project knowledge. Dev-Flow owns the guided repo execution pipeline: repo picker, Brainstorm, classification, readiness packet, free-form Hermes loop packet editing, validation, launch, live monitoring, steering, review, verification, and promotion gates.

Hermes remains the runtime for deterministic tool lanes, the working loop machinery, fleet routing, local model lifecycle, codebase mapping, compression, builder/judge execution, and handoff mechanics. Dev-Flow wraps those capabilities; it does not rebuild them in V1.

The newest runtime correction is tool-first: when a repo operation is mechanical enough for a parser, dependency analyzer, extractor, verifier, or failure classifier to do exactly, Dev-Flow should route the packet to that deterministic Hermes lane before involving local models. Models are escalation and generation surfaces, not mandatory ceremony around exact code movement.

## V1 Product Spine

```text
Obsidian curated handoff or direct repo entry
  -> Repo picker
  -> Brainstorm
  -> Classification gate
  -> Supervisor intent summary
  -> Builder-Judge readiness packet
  -> Free-form Hermes loop packet preview/edit
  -> Packet validation gate
  -> Hermes runtime route: deterministic tool lane or loop preset
  -> Loop run monitor and steering controls
  -> Loop review gate
  -> Dev-Flow verification gate
  -> Promote or request changes
  -> Obsidian status write-back
```

## Non-Goals

- Do not rebuild Hermes loop internals inside Dev-Flow.
- Do not make Dev-Flow a second Obsidian browser or project library.
- Do not migrate existing Brainstorm or Task state in V1.
- Do not redesign all model routing before the cockpit path works.
- Do not delete or rewrite Hermes model assets as part of the cockpit implementation.
- Do not reintroduce Ornith 9B as a Dev-Flow loop-routing fallback.
- Do not make every pipeline step a full Dev-Flow Task.
- Do not send parser-exact code movement or verification work through a model loop unless the deterministic tool lane cannot classify, complete, or explain the failure.

## Active Fleet Policy For The Cockpit

This is the target routing language for packets and UI labels after deterministic tooling has been considered. It is not a V1 mandate to rewrite the current loop setup.

| Model route | Role | V1 posture |
| --- | --- | --- |
| Cloud/frontier | Intent inference, product judgment, gap-bridging between operator request and final code/product | Required for supervisor intent summaries and hard product decisions |
| Ornith 35B | Primary scout/builder; fast generalist; supports `-np 3` parallel scout/build work; useful for code generation, mapping, compression, and surveys | Use through Hermes tooling as the active scout/build lane |
| Qwen 27B MTP | Dense thinking judge; best for precision review, validation, final approval, and strict packets | Swap to Qwen only after Ornith scout/build work completes |
| Ornith 9B / Qwopus 35B / Qwen3-Coder-Next | Retired from active DevFlow use | Do not route scout, builder, judge, UI, fallback, or emergency work to these lanes |

## Tool-First Runtime Correction

The high-level correction from the Hermes learning session is that some previous loop complexity was scaffolding around missing deterministic tools. The cockpit should preserve the guided pipeline, but it should not force every edit-shaped job through a builder-judge model loop.

| Work shape | First route | Escalate when |
| --- | --- | --- |
| Move known functions/classes/constants into a module | Deterministic extractor from a manifest | Dependency cycle, ambiguous seam, monkeypatch behavior unclear, verifier failure cannot be classified |
| Update facade reexports after extraction | Deterministic AST/import writer | Public API equivalence is ambiguous |
| Run focused tests/lint and classify common failures | Deterministic verifier/failure classifier | Failure needs diagnosis beyond known classes |
| Shape messy operator intent into product outcome | Cloud/frontier supervisor | Always use the intent bridge before worker execution when intent is messy |
| Build new behavior or UI | Builder-Judge or UI-oriented loop | Deterministic tools can verify and summarize, but should not invent product behavior |

Expected Hermes-side tool contract, pending exact implementation details from the Hermes work:

- manifest input such as `.devflow/slices/<slice>.yaml`
- command-style execution such as `extract_module.py --manifest ... --verify ... --write-json ...`
- compact JSON verdict under `.devflow/evidence/` or the pipeline run artifacts directory
- clear classification of changed files, preserved public API, verification result, and escalation reason if blocked

Do not hardcode those Hermes paths until the Hermes implementation lands. The Dev-Flow slice should define an adapter boundary that can call the exact command later and can be mocked first.

## Pipeline Run Filesystem Contract

V1 introduces a repo-local execution spine under:

```text
.devflow/pipeline-runs/<run_id>/
```

Minimum files:

| File | Purpose |
| --- | --- |
| `intent.md` | Cloud/frontier supervisor intent summary |
| `source.json` | Repo, branch, Obsidian source links, handoff metadata |
| `brainstorm.md` | Brainstorm transcript summary or pointer to existing Brainstorm session |
| `classification.json` | Work type, rationale, eligible loop presets, chosen preset |
| `readiness-packet.md` | Builder-Judge readiness packet |
| `loop-packet.md` | Free-form Hermes packet as edited and launched |
| `validation.json` | Blocking safety errors and advisory quality warnings |
| `run-log.jsonl` | Hermes lifecycle events, checkpoints, steering events |
| `artifacts.json` | Changed files, evidence paths, deterministic tool verdict paths, handoff paths, verification outputs |
| `review.md` | Loop review, verification decision, promotion/request-changes decision |

V1 links existing artifacts instead of replacing them:

- `.devflow/brainstorms/<session_id>/...` remains the source for existing Brainstorm evidence.
- `.devflow/tasks/<task_id>/...` remains available for compatibility with existing verification and promotion code.
- Pipeline runs become the primary cockpit record.

## Loop Job Presets

All four presets are edit-capable through the same Hermes edit-loop mechanics. They differ by default write budget, risk gate, and expected artifact.

The deterministic tool lane is not a fifth loop preset. It is a Hermes runtime route that a packet may choose when the classification and manifest make the operation exact enough to run without model reasoning.

| Preset | Main job | Default write budget | Primary output |
| --- | --- | --- | --- |
| Spec/Planning Loop | Turn intent into an implementation-ready packet | Planning docs, packet files, dependency/tool notes, test-plan notes, small probe scripts only with approval | `readiness-packet.md` |
| Builder-Judge Loop | Normal bounded implementation | Implementation files and directly related tests named in the packet | changed files plus loop evidence |
| Verify-Fix Loop | Fix failed verification efficiently | Files implicated by failed verification plus related tests | passing/failing verification evidence and narrow fix summary |
| Refactor/Recovery Loop | Recover from bad runs or handle architecture cleanup | Plan artifact first; code edits need bounded file list or second approval | recovery/refactor plan, then bounded changes |

Builder-Judge cannot launch until a readiness packet exists with:

- clear objective
- selected repo
- exact file targets or discovery scope
- dependencies/tooling notes
- machine-specific quirks
- API/data contracts involved
- acceptance criteria
- verification commands
- allowed write scope
- stop conditions
- supervisor intent summary

## Existing Seams To Reuse

Backend:

- `src/devflow/control_room/operating_layer.py`: current snapshot composition.
- `src/devflow/control_room/operating_layer_server.py`: HTTP route table and mixin composition.
- `src/devflow/control_room/operating_layer_brainstorm_handlers.py`: Brainstorm routes.
- `src/devflow/control_room/brainstorm.py`: Brainstorm transcript/spec/plan/implementation artifacts.
- `src/devflow/control_room/brainstorm_pipeline.py`: current Brainstorm -> Pipeline projection.
- `src/devflow/control_room/operating_layer_first_viewport.py`: first-viewport Brainstorm/Pipeline/Worker/Review/Evidence presentation.
- `src/devflow/control_room/operating_layer_builder_judge_routes.py`: builder-judge route payloads.
- `src/devflow/control_room/builder_judge_loop.py`: current builder-judge content-quality loop.
- `src/devflow/control_room/builder_judge_async_runtime.py`: async builder-judge launch/status behavior.
- `src/devflow/control_room/operating_layer_refactor_handlers.py` and `src/devflow/control_room/refactor_loop.py`: existing refactor/recovery surface.
- `src/devflow/control_room/obsidian_task_bridge.py` and `src/devflow/control_room/operating_layer_obsidian_handlers.py`: existing Obsidian bridge to narrow rather than expand.
- `src/devflow/control_room/task_workbench.py` and `src/devflow/control_room/task_workbench_review.py`: existing review/evidence/task compatibility projections.
- `src/devflow/control_room/task_verification.py`, `src/devflow/control_room/verification.py`, and `src/devflow/control_room/promotion.py`: verification and promotion gates.

Frontend assets:

- `src/devflow/control_room/operating_layer_html.py`
- `src/devflow/control_room/operating_layer_script.py`
- `src/devflow/control_room/operating_layer_pipeline_script.py`
- `src/devflow/control_room/operating_layer_workbench_script.py`
- `src/devflow/control_room/operating_layer_styles.py`
- `src/devflow/control_room/static/app.css`

Hermes/fleet references:

- `~/.hermes/scripts/model-router`
- `~/.hermes/config.yaml` `local_runners.providers`
- `~/.hermes/skills/autonomous-ai-agents/hermes-loop/SKILL.md`
- `~/.hermes/skills/software-development/local-fleet-efficiency/SKILL.md`
- `~/.hermes/skills/software-development/multi-model-fleet/scripts/builder-judge-loop.sh`
- `~/.hermes/skills/software-development/local-fleet-efficiency/scripts/codebase_survey.py`
- `~/.hermes/skills/software-development/local-fleet-efficiency/scripts/compress_tool_output.py`
- `~/.hermes/skills/software-development/local-fleet-efficiency/scripts/local_test_runner.py`

Hermes deterministic tool lane references to confirm when the Hermes implementation lands:

- `scripts/extract_module.py`
- `scripts/verify_slice.py`
- `.devflow/slices/<slice>.yaml`
- `.devflow/evidence/<tool-verdict>.json`

## Implementation Ledger

Update this table after every slice. Do not mark a slice done without listed verification.

| ID | Status | Slice | Target files | Dependencies | Verification |
| --- | --- | --- | --- | --- | --- |
| RLC-00 | in_progress | Contract alignment: glossary, ADR, active docs, this ledger | `CONTEXT.md`, `docs/adr/0002-repo-loop-cockpit-over-hermes-runtime.md`, `docs/control-room-mvp.md`, `docs/architecture/local-operating-layer-ui.md`, this file | none | `git diff --check`; stale-context search |
| RLC-00B | done | Scout-first agent operating contract and two-model fleet alignment | `AGENTS.md`, `CONTEXT.md`, `docs/agent-operating-contract.md`, `docs/fleet-debrief.md`, `docs/fleet-routing-brief.md`, `docs/local-worker-policy.md`, `docs/codex-efficient-workflow.md`, `docs/integrations/ornith-hermes-local.md`, `.devflow/fleet-contract.json` | RLC-00 | `git diff --check` PASS; stale-context search PASS for active stale phrases |
| RLC-00C | done | `devflow agent preflight` and `devflow agent scout` receipts | `src/devflow/control_room/agent_workflow_receipts.py`, `src/devflow/control_room/agent_command.py`, `tests/test_agent_cli.py` | RLC-00B | `local_test_runner.py --pytest "tests/test_agent_cli.py" --ruff "src/devflow/control_room/agent_command.py src/devflow/control_room/agent_workflow_receipts.py tests/test_agent_cli.py"` PASS: 44 passed, ruff clean; evidence `.devflow/evidence/test-results-rlc-00c-agent-preflight-scout-final.json`; Qwen judge approved `.devflow/evidence/judge-rlc-00c-qwen27.txt` |
| RLC-01 | done | Pipeline run storage model | new `src/devflow/control_room/pipeline_run.py`, new `tests/test_pipeline_run.py` | RLC-00 | `local_test_runner.py --pytest "tests/test_pipeline_run.py" --ruff "src/devflow/control_room/pipeline_run.py tests/test_pipeline_run.py"` PASS: 26 passed, ruff clean; evidence `.devflow/evidence/test-results-rlc-01.json` |
| RLC-02 | pending | Pipeline run projection in operating snapshot | `operating_layer.py`, `operating_layer_first_viewport.py`, `tests/test_operating_layer.py` or focused new test | RLC-01 | snapshot includes latest run, selected run, status, next action |
| RLC-03 | pending | Narrow curated handoff intake | `obsidian_task_bridge.py`, `operating_layer_obsidian_handlers.py`, `operating_layer_server.py`, `tests/test_obsidian_task_bridge.py`, `tests/test_operating_layer_obsidian_routes.py` | RLC-01 | accepts curated packet; does not browse/import broad vault data |
| RLC-04 | pending | Brainstorm-to-classification gate | `brainstorm_pipeline.py`, `brainstorm.py`, `operating_layer_brainstorm_handlers.py`, focused Brainstorm tests | RLC-01 | writes `classification.json`; exposes rationale, deterministic-tool eligibility, and eligible presets |
| RLC-05 | pending | Supervisor intent summary artifact | new `pipeline_intent.py` or folded into `pipeline_run.py`, Brainstorm/packet tests | RLC-04 | `intent.md` generated or imported before readiness validation |
| RLC-06 | pending | Builder-Judge readiness packet builder | new `pipeline_readiness.py`, `brainstorm_task_bridge.py`, focused packet tests | RLC-04, RLC-05 | validates required readiness fields before Builder-Judge |
| RLC-07 | pending | Free-form Hermes loop packet preview/edit | new `pipeline_packet.py`, server route mixin, JS editor surface, tests | RLC-06 | edited packet persisted; no launch before validation |
| RLC-08 | pending | Packet validation gate | `pipeline_packet.py`, new `tests/test_pipeline_packet_validation.py` | RLC-07 | safety blockers vs advisory warnings are separated; deterministic-tool misuse is flagged |
| RLC-09A | pending | Deterministic tool lane adapter | new `hermes_tool_runtime.py` or folded into `hermes_loop_runtime.py`, `pipeline_packet.py`, mocked tests | RLC-08 | mocked manifest command writes verdict, artifacts, and run-log events without starting a model route |
| RLC-09 | pending | Hermes runtime bridge V1 | new `hermes_loop_runtime.py`, server route mixin, mocked tests | RLC-08, RLC-09A | chooses deterministic tool lane when declared; otherwise wraps current working loop command/path and preserves current-loop compatibility |
| RLC-10 | pending | Loop run monitor and steering controls | `hermes_loop_runtime.py`, `operating_layer_script.py`, route tests | RLC-09 | appends `run-log.jsonl`; supports pause/resume/stop/inject/checkpoint where the selected Hermes route supports it |
| RLC-11 | pending | Loop review gate | new `pipeline_review.py`, task workbench review projection, tests | RLC-10 | reads artifacts, changed files, handoffs, claimed completion; no auto-promotion |
| RLC-12 | pending | Dev-Flow verification gate integration | `task_verification.py`, `verification.py`, `pipeline_review.py`, focused tests | RLC-11 | promotion path requires Dev-Flow-owned verification evidence |
| RLC-13 | pending | Compatibility Task bridge | `pipeline_run.py`, existing task bridge modules, tests | RLC-12 | creates/links Task only where verification/promotion requires it |
| RLC-14 | pending | Cockpit UI first vertical slice | first-viewport/pipeline JS/CSS/HTML modules, visual QA | RLC-02, RLC-07, RLC-10 | browser smoke, no horizontal overflow, first viewport shows repo cockpit path |
| RLC-15 | pending | Obsidian status write-back | new/narrow Obsidian bridge route and tests | RLC-11 | writes/sends only status/evidence links, not broad Dev-Flow dashboard state |
| RLC-16 | pending | Active fleet policy cleanup in Dev-Flow UI | local model/fleet projection docs/UI labels | RLC-09 | Ornith 9B absent from cockpit routing; Hermes config not deleted |
| RLC-17 | pending | End-to-end dogfood path | dogfood/visual QA tests and handoff | RLC-14, RLC-15 | curated handoff -> packet -> mock Hermes run -> review -> verify gate |

## Slice Details

### RLC-01 Pipeline run storage model

Add a small persistence module with typed helpers:

- `pipeline_runs_dir(root)`
- `new_pipeline_run_id()`
- `create_pipeline_run(root, source)`
- `load_pipeline_run(root, run_id)`
- `update_pipeline_run_record(root, run_id, file_name, content)`
- `append_pipeline_event(root, run_id, event)`

Keep it filesystem-backed and boring. Do not add a database.

### RLC-02 Snapshot projection

Add a compact `pipeline_run` field to `OperatingLayerSnapshot` that includes:

- selected/current run id
- stage
- chosen preset
- validation status
- Hermes run status
- next safe action
- key artifact paths

Do not copy large artifacts into `/api/snapshot`.

### RLC-03 Curated handoff intake

Convert Obsidian integration from broad card browsing toward narrow packet intake.

Accepted packet fields:

- source app/name/path
- selected repo or repo hint
- operator intent
- supporting note/card links
- constraints
- acceptance criteria
- suggested loop preset
- known docs/files

The route may preview and create a pipeline run, but it must not launch Hermes.

### RLC-04 Classification gate

Classification is visible and editable. It should output:

- work type
- rationale
- deterministic tool eligibility
- eligible presets
- recommended preset
- why alternatives were not recommended

This can begin rule-based and become model-assisted later.

### RLC-05 Supervisor intent summary

Generate or import:

```text
Intent Summary:
- User wants:
- Product outcome:
- Non-negotiables:
- Things workers may misunderstand:
- What done feels like:
```

Cloud/frontier owns this bridge because it has the best chance of interpreting messy human intent.

### RLC-06 Readiness packet

Builder-Judge readiness packet must include all required fields from the contract. If any are missing, the cockpit routes to Spec/Planning rather than launch.

### RLC-07 Free-form packet preview/edit

Primary UX is a free-form text editor over `loop-packet.md`.

The UI may show helpers or generated sections, but it must not force a field-by-field wizard.

### RLC-08 Validation gate

Blocking safety errors:

- no selected repo
- no goal/objective
- unsafe write scope
- destructive command
- impossible or unavailable runtime route
- unsupported deterministic tool command when a tool lane is selected
- missing stop condition
- missing verification path for code-changing runs

Advisory warnings:

- broad scope
- weak acceptance criteria
- missing docs
- likely stale file targets
- model loop selected for a deterministic-tool-supported operation
- non-optimal model choice
- no Obsidian source link

### RLC-09A Deterministic tool lane adapter

Add the runtime adapter shape before wiring a live Hermes command. The adapter should accept a validated packet that declares:

- tool route id
- manifest path
- allowed write scope
- verification command
- verdict output path
- escalation conditions

The mocked adapter must prove that Dev-Flow can record a deterministic tool verdict, changed files, verification status, and escalation reason without starting a model worker.

### RLC-09 Hermes runtime bridge V1

Wrap the current working loop setup with minimal changes. Prefer a command/adapter boundary that can be mocked in tests.

The V1 bridge first checks for a deterministic tool route. If the packet selects one, it uses the deterministic tool adapter. Otherwise it may launch existing Hermes loop commands or produce an exact command for manual approval if direct launch is too risky for the first slice. It must write lifecycle events under the pipeline run.

### RLC-10 Monitor and steering

Support:

- live output stream
- compact checkpoints
- pause
- resume
- stop
- inject direction
- request checkpoint
- mark needs review

Do not silently rewrite the packet mid-run.

### RLC-11 Review gate

Review displays:

- changed files
- run artifacts
- runtime route and model/fleet route when applicable
- transcript/handoff
- claimed completion
- verification commands
- request changes / rerun / verify / park actions

### RLC-12 Verification gate

Dev-Flow-owned verification is required before promotion. Hermes checks are evidence, not proof.

### RLC-13 Compatibility Task bridge

Create linked Task records only when an existing verifier/promoter requires them. The Pipeline run remains the primary cockpit object.

### RLC-14 UI vertical slice

First usable cockpit should show:

- repo picker doorway
- Brainstorm
- classification card
- readiness packet status
- free-form loop packet editor
- validation result
- launch/monitor placeholder or mocked run status
- review/verification next action

### RLC-15 Obsidian write-back

Write back only:

- pipeline run id
- current stage/status
- evidence/review links
- next action

Do not push Dev-Flow task boards or broad diagnostics into Obsidian.

### RLC-16 Fleet policy cleanup in Dev-Flow UI

Remove retired models from cockpit routing labels and loop recommendations. The active local fleet is Ornith 35B (:8084) for scout/build work and Qwen 27B (:8083) for judging. Do not delete Hermes config or assets in this slice. This slice affects model routes only; deterministic tool lanes are separate.

### RLC-17 End-to-end dogfood

Use a mocked Hermes runtime first. Live Hermes dogfood is a separate approval because it may start long-running model work.

## Verification Policy

For documentation-only contract updates:

```bash
git diff --check
rg -n "Idea Greenhouse|Command Center|multi-project|Ornith 9B|repo loop cockpit|pipeline-runs|deterministic tool|extract_module|verify_slice" docs PRODUCT_NORTH_STAR.md CONTEXT.md
```

For focused backend slices:

```bash
PYTHONPATH=src:. .venv/bin/python -m pytest <focused tests> -q
```

For operating-layer UI slices:

```bash
PYTHONPATH=src:. .venv/bin/python -m pytest tests/test_operating_layer.py <focused route/static tests> -q
PYTHONPATH=src:. .venv/bin/python -m devflow.cli operating-layer visual-qa
```

Use browser/live proof when the first real UI vertical slice lands.

## Open Questions

- Exact Hermes V1 launch command or API boundary for direct cockpit launch.
- Exact Hermes path, arguments, and verdict schema for `extract_module.py` and `verify_slice.py`.
- Which V1 operations besides module extraction should be eligible for deterministic tool routing.
- Whether Spec/Planning should call cloud/frontier directly from Dev-Flow or request the supervisor intent summary from Obsidian/Codex.
- Exact shape of UI-heavy classification that enables Qwopus.
- Whether pipeline run ids should be timestamp slugs, short hashes, or tied to Obsidian source ids.
- How much of the current Workbench/Task Control UI should remain visible after the repo cockpit slice lands.

## Current Next Safe Action

Start RLC-02 by adding a compact `pipeline_run` field to `OperatingLayerSnapshot` that projects the current/latest run id, stage, chosen preset, validation status, Hermes run status, next safe action, and key artifact paths without copying large artifacts into `/api/snapshot`.
