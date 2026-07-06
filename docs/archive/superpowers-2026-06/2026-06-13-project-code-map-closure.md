# Project Code Map Closure Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Close Milestone 11 by dogfooding `CODE_MAP.md` in Dev-Flow and aligning docs with the already-implemented map and task-packet excerpt behavior.

**Architecture:** This is a documentation and root-orientation closure slice. It creates one human-authored root `CODE_MAP.md`, updates active docs that still describe Project Code Map as future or in progress, then verifies the existing map command and task-packet excerpt tests.

**Tech Stack:** Markdown docs, existing Typer CLI (`devflow map`), existing task-packet Python tests, DevFlow Git bridge commands.

---

## Working Rules

- Use `devflow git status` before edits and before checkpointing.
- Do not edit `src/devflow/_legacy/`.
- Do not add provider adapters, routing, autonomous execution, Idea Foundry commands, or dashboard changes.
- Use `apply_patch` for manual file edits.
- Use DevFlow Git bridge commands: `devflow git checkpoint --message "docs: close project code map milestone" --yes`, then ask before `devflow push-main`.
- Keep this slice to docs and root `CODE_MAP.md` unless verification exposes a real source bug.

## File Structure

- Create `CODE_MAP.md`
  - Human-authored root orientation file for Dev-Flow.
  - Must pass `devflow map check`.
- Modify `README.md`
  - Stop describing Project Code Map as future-only.
  - Add `devflow map init/show/check` to stable orientation commands or product contract prose.
- Modify `docs/control-room-mvp.md`
  - Add map commands to the current stable command list and explain the root map + task packet excerpt behavior.
- Modify `docs/mvp-contract.md`
  - Add `devflow map init/show/check` to stable command surfaces and command maturity language.
- Modify `docs/roadmap.md`
  - Mark Milestone 11 implemented after this closure.
  - Change the stale next-priority callout away from `11E`.
- Modify `docs/architecture/project-code-map-mvp.md`
  - Update status from docs-only/future to current implementation.
  - Mark acceptance criteria complete, except `.code-map.yaml` as reserved future metadata.
- Optional modify `docs/architecture/patch-evidence-ladder.md`
  - Only if stale milestone status language still claims Milestone 11 is future-only after the active docs are updated.

---

### Task 1: Confirm Baseline And Stale Targets

**Files:**
- Read only: `README.md`
- Read only: `docs/control-room-mvp.md`
- Read only: `docs/mvp-contract.md`
- Read only: `docs/roadmap.md`
- Read only: `docs/architecture/project-code-map-mvp.md`
- Read only: `docs/architecture/patch-evidence-ladder.md`

- [ ] **Step 1: Check Git state**

Run:

```bash
devflow git status
```

Expected: clean `main`, no operation in progress. Stop and report if the tree is dirty before edits.

- [ ] **Step 2: Confirm the missing root map**

Run:

```bash
PYTHONPATH=src:. .venv/bin/devflow map check
```

Expected before implementation: exit code `1` with:

```text
Error: CODE_MAP.md not found. Run 'devflow map init' to scaffold one.
```

- [ ] **Step 3: Locate stale Project Code Map wording**

Run:

```bash
rg -n "Project Code Map|CODE_MAP|devflow map|11E|future context intake|These commands do not exist yet|Next Priority" README.md docs/control-room-mvp.md docs/mvp-contract.md docs/roadmap.md docs/architecture/project-code-map-mvp.md docs/architecture/patch-evidence-ladder.md
```

Expected: matches identify exactly which docs need alignment. Use these matches to keep edits targeted.

---

### Task 2: Add Root `CODE_MAP.md`

**Files:**
- Create: `CODE_MAP.md`

- [ ] **Step 1: Create the root map**

Create `CODE_MAP.md` with this content:

```markdown
# Code Map

## What this repo does

Dev-Flow is a local-first control room for parallel AI coding workers. It owns task state, isolated workspaces, locks, logs, verification evidence, review readiness, and human-controlled promotion while keeping workers replaceable.

## Layout

- `src/devflow/control_room/` - active control-room implementation. New product behavior belongs here.
- `src/devflow/cli.py` - Typer CLI entry point and command wiring.
- `src/devflow/_legacy/` - quarantined legacy software-factory code. Do not add features here.
- `tests/` - pytest coverage for control-room commands, projections, dogfood, release gates, and safety behavior.
- `docs/` - active contracts, architecture notes, roadmap, and handoffs.
- `docs/superpowers/specs/` - approved design specs for larger slices.
- `docs/superpowers/plans/` - implementation plans for agent handoff.
- `.devflow/` - local runtime state and evidence. Do not edit manually unless a specific Dev-Flow command or handoff asks for it.

## Entry points

- CLI: `src/devflow/cli.py`
- Task lifecycle writes: `src/devflow/control_room/task_lifecycle.py`
- Core task service: `src/devflow/control_room/service.py`
- Task packets: `src/devflow/control_room/task_packet.py`
- Project code map: `src/devflow/control_room/code_map.py`
- Freshness loop: `src/devflow/control_room/freshness.py`
- Operating layer snapshot: `src/devflow/control_room/operating_layer.py`
- Release readiness gate: `src/devflow/control_room/release_readiness.py`

## What to read first (worker orientation)

1. `AGENTS.md` - mandatory repo operating rules.
2. `docs/devmode-contract.md` - DevMode discipline and handoff format.
3. `PRODUCT_NORTH_STAR.md` - product identity and periodic self-check.
4. `docs/control-room-mvp.md` - current MVP authority and stable command contract.
5. `docs/roadmap.md` - current sequencing and deferred work.
6. `docs/agent-handoff.md` - active handoff and architecture boundary notes.

## What to skip

- `src/devflow/_legacy/` - quarantined legacy code; do not modify or treat as authority.
- Archived workflow docs or stale plans that conflict with the control-room MVP.
- `.devflow/workspaces/`, `.devflow/worktrees/`, `.devflow/dogfood/`, and `.devflow/release-readiness/` unless the current task explicitly needs local evidence.
- Provider-backed adapters, autonomous routing, memory, or dashboard expansion unless an approved current spec promotes that slice.

## Owners / contacts

- Primary: Josh

## Last reviewed

2026-06-13
```

- [ ] **Step 2: Verify the root map passes**

Run:

```bash
PYTHONPATH=src:. .venv/bin/devflow map check
```

Expected: exit code `0`, output starts with:

```text
CODE_MAP.md check passed
checked entry points:
```

Expected checked paths include:

```text
src/devflow/cli.py
src/devflow/control_room/task_lifecycle.py
src/devflow/control_room/service.py
src/devflow/control_room/task_packet.py
src/devflow/control_room/code_map.py
src/devflow/control_room/freshness.py
src/devflow/control_room/operating_layer.py
src/devflow/control_room/release_readiness.py
```

---

### Task 3: Align Active Documentation

**Files:**
- Modify: `README.md`
- Modify: `docs/control-room-mvp.md`
- Modify: `docs/mvp-contract.md`
- Modify: `docs/roadmap.md`
- Modify: `docs/architecture/project-code-map-mvp.md`
- Optional modify: `docs/architecture/patch-evidence-ladder.md`

- [ ] **Step 1: Update `README.md`**

Replace the sentence that says Project Code Map is a future context intake layer with prose that distinguishes current and future pieces:

```markdown
The staged evidence path for proposal patches, patch review, patch dry-run preview, explicit patch application, verification, and human-controlled promotion is documented in [docs/architecture/patch-evidence-ladder.md](docs/architecture/patch-evidence-ladder.md). Project Code Map is now the current human-authored orientation layer through root `CODE_MAP.md`, `devflow map init/show/check`, and bounded `devflow task packet` excerpts. Idea Foundry remains a future roadmap concept.
```

Add a stable command bullet near the command list:

```markdown
- **Project Orientation**: `devflow map init`, `devflow map show`, `devflow map check`
```

- [ ] **Step 2: Update `docs/control-room-mvp.md`**

In the stable command list, add:

```bash
devflow map init
devflow map show
devflow map check
```

Add a short paragraph near the task-packet or context sections:

```markdown
The Project Code Map form is `CODE_MAP.md` plus `devflow map init`, `devflow map show`, and `devflow map check`. The map is a human-authored orientation artifact. When present, `devflow task packet <task_id>` includes a bounded excerpt so workers can orient before broad repo scans. The map is read-only context, not canonical task state, and it does not route models, call providers, or generate itself from source.
```

- [ ] **Step 3: Update `docs/mvp-contract.md`**

Add these commands to the stable command block and maturity description:

```bash
devflow map init
devflow map show
devflow map check
```

Add this command contract paragraph:

```markdown
`devflow map init`, `devflow map show`, and `devflow map check` manage the optional root `CODE_MAP.md` orientation artifact. `map init` scaffolds a human-authored template, `map show` prints the current map, and `map check` validates required sections plus entry-point paths. These commands do not generate maps from source, route tasks, call providers, mutate task state, or make promotion decisions. When `CODE_MAP.md` exists, `devflow task packet` may include a bounded read-only excerpt for worker orientation.
```

- [ ] **Step 4: Update `docs/roadmap.md`**

Change Milestone 11 status to implemented after this closure:

```markdown
Status: implemented and dogfooded in Dev-Flow. The 11A contract, 11B `map init`, 11C `map show`, 11D `map check`, and 11E bounded `CODE_MAP.md` task-packet excerpt are complete.
```

Replace the stale next-priority callout with:

```markdown
> [!IMPORTANT]
> **Next Priority**: Milestone 12 Idea Foundry MVP design. Start with a design/spec for human-reviewed idea capture and promotion. Do not implement provider-backed adapters, autonomous routing, databases, or automatic task creation as part of the Idea Foundry design slice.
```

- [ ] **Step 5: Update `docs/architecture/project-code-map-mvp.md`**

Change the header metadata to:

```markdown
**Milestone**: 11 (Project Code Map MVP)
**Status**: implemented; Dev-Flow root dogfood added in closure slice
**Boundary**: `CODE_MAP.md` is human-authored read-only orientation context. `.code-map.yaml` remains reserved future metadata.
```

Replace the old "CLI Commands (future, not active)" section heading with:

```markdown
## CLI Commands
```

Replace "These commands do not exist yet" with:

```markdown
These commands are current stable orientation helpers. They do not call providers, route workers, mutate task state, or generate maps from source.
```

Update acceptance criteria to checked boxes for implemented behavior:

```markdown
- [x] `CODE_MAP.md` schema documented and stable
- [x] `.code-map.yaml` schema documented as reserved future metadata
- [x] `devflow map init` scaffolds `CODE_MAP.md`
- [x] `devflow map show` prints the map
- [x] `devflow map check` lints for broken entry-point paths
- [x] `devflow task packet` includes a bounded map excerpt when `CODE_MAP.md` is present
- [x] No provider API, routing, database, or autonomous behavior introduced
```

- [ ] **Step 6: Check optional `docs/architecture/patch-evidence-ladder.md` wording**

Run:

```bash
rg -n "Project Code Map|Milestone 11|future context intake" docs/architecture/patch-evidence-ladder.md
```

If the file still says Project Code Map is future-only without distinguishing that commands are now current, make the smallest wording update. If it only lists sequencing history, leave it alone.

---

### Task 4: Verify Focused Behavior

**Files:**
- Read only: `CODE_MAP.md`
- Read only: `tests/test_code_map.py`
- Read only: `tests/test_code_map_show.py`
- Read only: `tests/test_code_map_check.py`
- Read only: `tests/test_task_packet.py`

- [ ] **Step 1: Run map service and CLI tests**

Run:

```bash
PYTHONPATH=src:. .venv/bin/pytest tests/test_code_map.py tests/test_code_map_show.py tests/test_code_map_check.py -v
```

Expected: all selected tests pass.

- [ ] **Step 2: Run focused task-packet map excerpt tests**

Run:

```bash
PYTHONPATH=src:. .venv/bin/pytest \
  tests/test_task_packet.py::test_task_packet_omits_code_map_excerpt_when_missing \
  tests/test_task_packet.py::test_task_packet_includes_bounded_code_map_excerpt \
  tests/test_task_packet.py::test_task_packet_truncates_code_map_excerpt_by_limit \
  tests/test_task_packet.py::test_task_packet_text_renders_code_map_excerpt \
  -v
```

Expected: all selected tests pass.

- [ ] **Step 3: Verify root map check**

Run:

```bash
PYTHONPATH=src:. .venv/bin/devflow map check
```

Expected: pass, with all entry-point paths checked.

- [ ] **Step 4: Run stale-context alignment search**

Run:

```bash
rg -n "future context intake|These commands do not exist yet|11E active|Next Priority.*11E|Project Code Map.*future" README.md docs/control-room-mvp.md docs/mvp-contract.md docs/roadmap.md docs/architecture/project-code-map-mvp.md docs/architecture/patch-evidence-ladder.md
```

Expected: no matches that describe Project Code Map as future-only or 11E as still active. Matches that explicitly describe `.code-map.yaml` or Idea Foundry as future are acceptable.

---

### Task 5: Checkpoint And Handoff

**Files:**
- Modified only as listed in this plan.

- [ ] **Step 1: Inspect final diff**

Run:

```bash
git diff -- README.md docs/control-room-mvp.md docs/mvp-contract.md docs/roadmap.md docs/architecture/project-code-map-mvp.md docs/architecture/patch-evidence-ladder.md CODE_MAP.md
```

Expected: diff is limited to root map creation and current-doc alignment. No source code changes unless a verified bug was found and fixed.

- [ ] **Step 2: Check DevFlow Git status**

Run:

```bash
devflow git status
```

Expected: dirty files are only the intended docs/root map files. `safe_for_worker_writes` should remain `yes`.

- [ ] **Step 3: Create checkpoint**

Run:

```bash
devflow git checkpoint --message "docs: close project code map milestone" --yes
```

Expected: checkpoint commit succeeds.

- [ ] **Step 4: Confirm clean checkpoint**

Run:

```bash
devflow git status
```

Expected: clean `main`, ahead of `origin/main` by `1`, `safe_for_push: yes`.

- [ ] **Step 5: Final handoff**

Use the standard handoff headings:

```markdown
## Status

complete

## Files Changed

- CODE_MAP.md (root orientation map for Dev-Flow)
- README.md (Project Code Map current-command alignment)
- docs/control-room-mvp.md (stable command and behavior alignment)
- docs/mvp-contract.md (stable command contract alignment)
- docs/roadmap.md (Milestone 11 closure and next priority alignment)
- docs/architecture/project-code-map-mvp.md (implemented-state alignment)
- docs/architecture/patch-evidence-ladder.md (only if stale wording required a small update)

## Verification

- `PYTHONPATH=src:. .venv/bin/pytest tests/test_code_map.py tests/test_code_map_show.py tests/test_code_map_check.py -v`: pass/fail + summary
- `PYTHONPATH=src:. .venv/bin/pytest tests/test_task_packet.py::test_task_packet_omits_code_map_excerpt_when_missing tests/test_task_packet.py::test_task_packet_includes_bounded_code_map_excerpt tests/test_task_packet.py::test_task_packet_truncates_code_map_excerpt_by_limit tests/test_task_packet.py::test_task_packet_text_renders_code_map_excerpt -v`: pass/fail + summary
- `PYTHONPATH=src:. .venv/bin/devflow map check`: pass/fail + summary
- stale-context alignment `rg`: pass/fail + relevant output
- `devflow git status`: pass/fail + clean/ahead status

## Risks

- Note if any docs still intentionally describe `.code-map.yaml` or Idea Foundry as future.
- Note whether the checkpoint is pushed or still local.

## Next Safe Action

- Ask Josh before running `devflow push-main`.
```
