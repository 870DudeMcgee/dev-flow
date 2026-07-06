# Hermes Local Async Supervisor Loop Implementation Plan

Status: historical/superseded orchestration plan. Current local-worker
selection is `docs/local-worker-policy.md`: opt-in Qwen 3.6 27B Q5 MTP as the
single normal lane, with other local routes as explicit exceptions.

> **For Hermes:** This plan is about using Hermes's async/background subagent capabilities as the supervisory control layer, with local Qwen-class models as bounded implementation workers. Do not confuse this with DevFlow's internal `devflow task run --worker ...` runtime; that remains an evidence/worker lane and comparison target, but the orchestration described here is Hermes-led.

**Goal:** Use Hermes as the supervisor that dispatches small, local-model-sized coding chunks asynchronously, verifies the result, repairs failures, records local-model performance evidence, and only then moves to the next chunk.

**Architecture:** Hermes remains the controller. Local Qwen 3.6 35B is the primary implementation worker behind Hermes delegation or a spawned Hermes worker profile. Each coding chunk is isolated, has a small allowed file set, a definition of done, a test command, and a measured output record. The supervisor performs verification and review after every chunk, not the worker that wrote the code.

**Tech Stack:** Hermes `delegate_task(background=true)`, Hermes `delegation.provider` / `delegation.model` configuration, optional spawned Hermes worker profiles, DevFlow filesystem evidence, `.devflow/` task artifacts, Python/pytest, operating-layer browser smoke tests, Ollama/OpenAI-compatible local endpoint where applicable.

---

## Product Intent

This plan exists because the operator wants DevFlow to become both:

1. a useful product for converting ideas into verified work; and
2. a test bench for learning how capable local models behave as agentic coding workers.

The process should answer:

```text
Can Qwen 3.6 35B take a bounded DevFlow implementation slice,
produce usable code,
and survive independent verification?
```

It should also answer:

```text
What prompt size, context window, task size, file count, and verification loop
make the local model reliable instead of flaky?
```

---

## Current Baseline

Codex has just finished implementing Idea Greenhouse V1. The working tree is expected to be dirty until that work is reviewed and checkpointed.

Current Greenhouse V1 changed-file shape observed before this plan was written:

```text
AGENTS.md
PRODUCT_NORTH_STAR.md
README.md
docs/control-room-mvp.md
docs/mvp-contract.md
src/devflow/cli.py
src/devflow/control_room/idea_foundry.py
src/devflow/control_room/operating_layer.py
src/devflow/control_room/operating_layer_html.py
src/devflow/control_room/operating_layer_script.py
src/devflow/control_room/operating_layer_server.py
src/devflow/control_room/operating_layer_styles.py
src/devflow/control_room/operating_layer_visual_qa.py
src/devflow/control_room/supervisor_surface.py
tests/test_idea_foundry.py
tests/test_operating_layer.py
tests/test_operator_ui_browser.py
tests/test_supervisor_operating_surface.py
docs/superpowers/plans/2026-06-19-idea-greenhouse-v1.md
```

Before any local async worker begins new work, Greenhouse V1 must be either:

- reviewed and accepted as the baseline; or
- explicitly reverted/parked by the human.

Do **not** launch local workers into an unstable baseline without a supervisor snapshot of the starting state.

---

## Supervisor Roles

| Role | Actor | Responsibility |
|---|---|---|
| Human owner | Joshua | Approves scope, accepts/rejects final changes, decides commits/pushes. |
| Hermes supervisor | Current Hermes session | Decomposes work, dispatches async workers, verifies, repairs, records metrics, protects focus. |
| Local implementer | Hermes async subagent using Qwen 3.6 35B | Implements one bounded chunk at a time. |
| Spec reviewer | Separate Hermes subagent or supervisor pass | Checks exact compliance with the chunk spec. |
| Quality reviewer | Separate Hermes subagent or stronger reviewer model | Checks design, safety, maintainability, no scope creep. |
| Verification runner | Hermes supervisor | Runs test commands and browser/static checks; worker self-reports do not count. |

Important rule:

```text
The worker may write code.
The supervisor decides whether the code is real.
```

---

## Hermes Async Agent Modes

Hermes gives us two useful async patterns. Use them deliberately.

### Mode A — Native Hermes background delegation

Use `delegate_task(background=true)` when:

- the task is bounded;
- the worker can finish without user interaction;
- the result can return as a later message;
- the parent supervisor session can continue doing other work.

Example shape:

```python
delegate_task(
    background=True,
    goal="Implement Slice 1: idea detail drawer read-only snapshot support.",
    context="<complete task packet here>",
    toolsets=["file", "terminal"]
)
```

Model routing note:

- Hermes subagents inherit the parent model by default.
- Hermes supports delegation-level provider/model overrides via `delegation.provider` and `delegation.model` in `config.yaml`.
- Therefore, to use Qwen 3.6 35B for delegated workers, configure the Hermes delegation model to the local Qwen provider/model or use Mode B.

### Mode B — Spawned Hermes worker process/profile

Use spawned Hermes processes when:

- each worker needs a distinct profile/model;
- the worker may run for a long time;
- we want full process isolation;
- we want a dedicated `qwen-worker` profile with local-model configuration.

Expected command pattern after profile/model setup:

```bash
hermes -p qwen-worker chat -q "<bounded worker packet>"
```

For interactive long-running workers, use tmux or a background process. The spawned worker must still write explicit artifacts and must not commit/push.

### Mode C — DevFlow local worker lane as comparison/evidence

DevFlow's own local worker path remains useful for comparison:

```bash
.venv/bin/python -m devflow.cli task run <task-id> --worker <local-worker-profile>
```

Use it when the goal is to compare Hermes async workers against DevFlow's internal agent runtime. Do not mix Mode A/B/C inside one implementation slice unless the purpose is explicitly an evaluation.

---

## Hard Rules

1. **No parallel code writers on overlapping files.**
2. **No worker self-verification accepted as final.**
3. **No commits, resets, cleans, pushes, or broad git operations without human approval.**
4. **No 8K local context neutering.** Start at a 32K minimum and record actual context usage.
5. **No huge packets.** If a worker packet needs more than a focused slice, split the slice.
6. **No hidden UI dead ends.** Every new state must have a visible next action.
7. **No placeholder commands may execute from the browser.**
8. **No automatic task/goal creation from raw ideas.** Human approval remains required.
9. **No model triage/scoring until the basic idea-to-work bridge is real.**
10. **If three repair attempts fail, stop and escalate instead of thrashing.**

---

## Preflight Before First Local Async Worker

### Step 0.1 — Baseline gate

Confirm Greenhouse V1 is complete enough to stand on:

```bash
PYTHONPATH=src:. .venv/bin/python -m pytest \
  tests/test_idea_foundry.py \
  tests/test_supervisor_operating_surface.py \
  tests/test_operating_layer.py \
  -q
```

Then run the JavaScript syntax check:

```bash
PYTHONPATH=src:. .venv/bin/python - <<'PY'
from pathlib import Path
from devflow.control_room.operating_layer_script import APP_JS
Path('/tmp/devflow-operating-layer.js').write_text(APP_JS, encoding='utf-8')
PY
node --check /tmp/devflow-operating-layer.js
```

If browser tests are available:

```bash
PYTHONPATH=src:. .venv/bin/python -m pytest tests/test_operator_ui_browser.py -q
```

Expected: pass, or browser dependency limitation explicitly documented.

### Step 0.2 — Record starting state

Read-only commands:

```bash
git status --short --branch
git diff --stat
```

Write a short supervisor note under a run directory such as:

```text
.devflow/reports/hermes-local-async-supervisor-runs/<run-id>/baseline.md
```

The note should include:

- branch;
- changed files;
- target feature;
- selected worker model;
- selected verification commands;
- known risks.

### Step 0.3 — Verify local Qwen model facts

Do not trust the nickname. Discover the exact local model tag and runtime facts:

```bash
ollama list
ollama show <exact-qwen-3.6-35b-tag>
```

Record:

| Field | Why it matters |
|---|---|
| exact model tag | prevents routing to wrong model |
| context length | prevents accidental 8K cap |
| parameter size | explains speed/quality tradeoff |
| quantization | affects VRAM/RAM and output quality |
| capabilities | tools/thinking/vision/FIM if advertised |

If Hermes is using an OpenAI-compatible local endpoint, also record endpoint and model slug. Do not store API keys or secrets.

### Step 0.4 — Configure Hermes delegation or worker profile

Preferred path:

```text
Hermes supervisor model: strong cloud/frontier model or current session model
Hermes delegation model: local Qwen 3.6 35B
```

Use Hermes config keys:

```text
delegation.provider
delegation.model
delegation.base_url, if required by the local provider
```

If per-call local model routing is not available in the active Hermes session, create/use a separate Hermes profile such as:

```text
qwen-worker
```

and spawn workers with Mode B.

### Step 0.5 — Smoke-test async worker capability

Before touching DevFlow code, run a harmless local worker task:

```text
Goal: read one small doc file and summarize what it says in 5 bullets.
Toolsets: file only.
Expected output: summary, no file writes.
```

The supervisor passes only if:

- worker returns within acceptable time;
- no unauthorized file writes;
- summary is grounded in the file;
- no context/window failure symptoms.

---

## Worker Packet Template

Every local async coding worker receives a packet in this structure.

```markdown
# Worker Packet: <slice name>

## Mission
<One sentence.>

## Context
<Why this slice exists and where it fits in DevFlow.>

## Allowed Files
- path/to/file.py
- tests/test_file.py

Do not edit other files without stopping and explaining why.

## Non-Goals
- Do not implement future scoring.
- Do not add provider calls.
- Do not commit/push.

## Required Behavior
- [ ] behavior 1
- [ ] behavior 2

## TDD Requirement
1. Add or update the smallest failing test.
2. Run the target test and confirm RED.
3. Implement minimal code.
4. Run the target test and confirm GREEN.
5. Stop and report exact commands/output.

## Verification Commands
```bash
<targeted command 1>
<targeted command 2>
```

## Output Required
Return:
- files changed;
- tests added/changed;
- commands run;
- pass/fail output;
- known risks;
- if blocked, exact blocker and smallest next question.
```

---

## Supervisor Loop

For each slice:

```text
1. Create worker packet.
2. Dispatch Hermes async worker.
3. Continue monitoring other state while worker runs.
4. When worker returns, inspect diff and artifacts.
5. Run supervisor-owned tests.
6. If tests fail, dispatch repair packet with exact failure evidence.
7. If tests pass, dispatch spec review.
8. If spec review passes, dispatch quality review.
9. If quality review passes, record metrics and mark slice complete.
10. Move to next slice only after gates are clear.
```

A worker result is not accepted unless the supervisor has independent evidence.

---

## Gate Taxonomy

| Gate | Entry condition | Pass condition | Fail action |
|---|---|---|---|
| Pre-flight | Before worker launch | clean enough baseline, exact task packet, model verified | stop and fix setup |
| Revision | Worker returns code | targeted tests pass, diff limited to allowed files | send repair packet |
| Escalation | repeated failure or unclear scope | human answers question or scope changes | park task or split smaller |
| Abort | unsafe/broad/unbounded behavior | no unsafe behavior detected | stop worker path, preserve evidence |

---

## Metrics To Capture Per Worker Run

Store under:

```text
.devflow/reports/hermes-local-async-supervisor-runs/<run-id>/<slice-id>/metrics.md
```

Capture at minimum:

| Metric | Source | Why |
|---|---|---|
| model tag | preflight / Hermes config | exact reproducibility |
| context target | config / run packet | prevents silent 8K regressions |
| prompt size estimate | packet length or worker logs | chunk sizing |
| wall-clock time | supervisor timestamps | speed planning |
| files allowed vs changed | git diff | scope control |
| tests requested vs run | worker report + supervisor run | truth vs self-report |
| patch validity | supervisor diff/review | coding usefulness |
| verification result | pytest/node/browser output | acceptance gate |
| repair count | supervisor loop | reliability measure |
| failure class | supervisor label | optimization target |

Failure classes:

```text
context_saturation
invalid_patch
syntax_error
test_failure
scope_creep
missing_requirement
hallucinated_file_or_api
slow_or_timeout
empty_or_truncated_output
unsafe_action
```

### Context saturation diagnostic

If available from Ollama/Hermes logs, always check:

```text
prompt_eval_count
num_ctx
eval_count
```

Red flag:

```text
prompt_eval_count ~= num_ctx
and eval_count <= 3
```

This usually means the prompt filled the context window and the model had no room to answer.

---

## First Target After Greenhouse V1

The first feature to run through this local async supervisor loop should be:

```text
Idea Shaping Bridge V1
```

Purpose:

```text
Idea card
  -> detail drawer
  -> classify/park/archive forms
  -> start brainstorm from idea
  -> preserve Idea -> Brainstorm -> Spec -> Plan -> Task lineage
```

Do not start with model scoring, clustering, Telegram capture, or daily digest.

---

## Proposed Slice Plan: Idea Shaping Bridge V1

### Slice 1 — Read-only idea detail drawer data

Allowed files:

```text
src/devflow/control_room/operating_layer.py
src/devflow/control_room/operating_layer_script.py
src/devflow/control_room/operating_layer_styles.py
tests/test_operating_layer.py
```

Goal:

```text
Clicking an idea card opens a detail view with raw metadata, lane, maturity, source, tags, evidence paths, and current next action.
```

Why this is first:

- It is mostly read-only.
- It tests whether local Qwen can safely extend snapshot/UI code.
- It does not add mutation complexity.

Verification:

```bash
PYTHONPATH=src:. .venv/bin/python -m pytest tests/test_operating_layer.py -q
node --check /tmp/devflow-operating-layer.js
```

### Slice 2 — Browser classify form

Allowed files:

```text
src/devflow/control_room/operating_layer_script.py
src/devflow/control_room/operating_layer_styles.py
src/devflow/control_room/operating_layer_server.py
tests/test_operating_layer.py
```

Goal:

```text
For Raw/Clarify ideas, show a form that runs approved `devflow idea classify <id> --maturity ... --note ...` without exposing placeholder command execution.
```

Verification:

```bash
PYTHONPATH=src:. .venv/bin/python -m pytest tests/test_operating_layer.py -q
```

### Slice 3 — Park/archive reason forms in detail drawer

Allowed files:

```text
src/devflow/control_room/operating_layer_script.py
src/devflow/control_room/operating_layer_styles.py
tests/test_operating_layer.py
```

Goal:

```text
Park/archive actions require concrete reasons and refresh the greenhouse lanes after execution.
```

Verification:

```bash
PYTHONPATH=src:. .venv/bin/python -m pytest tests/test_operating_layer.py -q
```

### Slice 4 — Start brainstorm from idea

Allowed files:

```text
src/devflow/control_room/brainstorm.py
src/devflow/control_room/operating_layer_server.py
src/devflow/control_room/operating_layer_script.py
tests/test_brainstorm_workbench.py
tests/test_operating_layer.py
```

Goal:

```text
A user can click `Start brainstorm from idea`; DevFlow creates or opens a brainstorm session seeded from the idea raw text and records `source_idea_id` lineage.
```

Verification:

```bash
PYTHONPATH=src:. .venv/bin/python -m pytest tests/test_brainstorm_workbench.py tests/test_operating_layer.py -q
```

### Slice 5 — Lineage carried into spec/plan/task

Allowed files:

```text
src/devflow/control_room/brainstorm.py
src/devflow/control_room/idea_execution_bridge.py
src/devflow/control_room/operating_layer.py
tests/test_brainstorm_workbench.py
tests/test_idea_foundry.py
tests/test_idea_execution_bridge.py
```

Goal:

```text
Spec, plan, and task artifacts created from a brainstorm retain links back to the source idea and brainstorm session.
```

Verification:

```bash
PYTHONPATH=src:. .venv/bin/python -m pytest \
  tests/test_brainstorm_workbench.py \
  tests/test_idea_foundry.py \
  tests/test_idea_execution_bridge.py \
  -q
```

### Slice 6 — Promotion wizard

Allowed files:

```text
src/devflow/control_room/operating_layer_script.py
src/devflow/control_room/operating_layer_styles.py
src/devflow/control_room/operating_layer_server.py
tests/test_operating_layer.py
```

Goal:

```text
Candidate ideas can be promoted to goal/task through a browser wizard that requires rationale and never auto-creates goals/tasks without explicit approval.
```

Verification:

```bash
PYTHONPATH=src:. .venv/bin/python -m pytest tests/test_operating_layer.py -q
```

### Slice 7 — End-to-end browser journey

Allowed files:

```text
tests/test_operator_ui_browser.py
src/devflow/control_room/operating_layer_visual_qa.py
```

Goal:

```text
Test or manually verify: capture idea -> classify -> start brainstorm -> generate spec -> generate plan -> create task with lineage.
```

Verification:

```bash
PYTHONPATH=src:. .venv/bin/python -m pytest tests/test_operator_ui_browser.py -q
```

If Playwright is unavailable, record environment limitation and run static visual QA plus manual browser verification.

---

## Chunk Sizing Rules For Qwen 3.6 35B

Start conservatively:

| Dimension | Initial limit |
|---|---|
| files per slice | 1-4 files |
| production files | 1-3 files |
| tests per slice | 1 focused test file |
| prompt size | small enough to leave generation room |
| implementation scope | one UI state or one backend behavior |
| time budget | 10-30 minutes per async worker run |
| repair attempts | max 2 automated repair rounds, then human/supervisor escalation |

Do not feed the entire DevFlow repo. The worker packet should contain exact snippets, file paths, and desired behavior.

---

## Optimization Experiments

Run these as evidence, not as guesses.

### Experiment 1 — Context window

Try the same small slice or synthetic coding task with:

```text
32K context
64K context
128K context, if stable
```

Record quality, latency, truncation, and memory pressure.

### Experiment 2 — Task packet size

Compare:

```text
minimal packet
medium packet with code snippets
large packet with docs/context
```

Goal: find the smallest packet that yields reliable code.

### Experiment 3 — Review model pairing

Compare:

```text
Qwen implements + Hermes supervisor verifies
Qwen implements + separate local reviewer checks spec
Qwen implements + GLM/OpenRouter audits only difficult failures
```

Do not let the same model rubber-stamp its own implementation.

### Experiment 4 — Output contract

Compare:

```text
free-form summary
strict changed-files/tests/risks format
patch-only format
```

Goal: determine which output shape is easiest for Hermes to verify and repair.

---

## Evidence Ledger Format

Each supervisor run should create or update:

```text
.devflow/reports/hermes-local-async-supervisor-runs/<run-id>/
  baseline.md
  supervisor-log.md
  model-facts.md
  slice-01-detail-drawer/
    worker-packet.md
    worker-result.md
    supervisor-verification.md
    metrics.md
  slice-02-classify-form/
    ...
  final-report.md
```

`final-report.md` should include:

```text
Model used:
Slices attempted:
Slices accepted:
Repair loops:
Average run time:
Common failure types:
Recommended Qwen settings:
Recommended next task size:
Do we trust this model for next slice? yes/no/conditional
```

---

## Definition Of Done

This plan is complete when:

- Hermes can dispatch at least one async local-model worker without blocking the supervisor.
- Qwen 3.6 35B or the selected local model completes a bounded DevFlow coding slice.
- Hermes independently verifies the worker's output.
- At least one repair loop is documented or explicitly not needed.
- Metrics are recorded for the local worker run.
- The supervisor can state whether the next slice should be same size, smaller, or larger.
- No commits/pushes occur without human approval.

---

## Immediate Next Action

After Greenhouse V1 is reviewed and checkpointed, do this first:

```text
Preflight a harmless Hermes async local-worker smoke test.
```

Only after that passes, start Slice 1 of Idea Shaping Bridge V1.
