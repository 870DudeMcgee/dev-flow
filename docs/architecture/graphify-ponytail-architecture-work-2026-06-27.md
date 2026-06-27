# Graphify + Ponytail Architecture Work Queue

Date: 2026-06-27
Status: ready for implementation handoff

This document records the work found in the 2026-06-27 Graphify architecture pass
combined with the Ponytail simplification filter. It is the durable version of
the temporary HTML report at `/tmp/architecture-review-20260627T155650Z.html`.

## Evidence Snapshot

Fresh command run from `<repo-root>`:

```bash
env PYTHONPATH=src:. .venv/bin/python -m devflow.cli architecture audit --write-doc
```

Observed result:

- Graphify artifacts regenerated under ignored `graphify-out/`.
- Built from commit: `818ddfd`
- Current `git rev-parse --short HEAD`: `818ddfd`
- Metrics: 9,099 nodes, 21,657 edges, 545 communities.
- Diagnostic: `ok`, issue count `3`.
- Checkpoint doc: `docs/architecture/control-room-architecture-audit.md`

Installed skill evidence:

- `ponytail` installed to `/Users/josh/.codex/skills/ponytail`
- `ponytail-review` installed to `/Users/josh/.codex/skills/ponytail-review`
- `ponytail-audit` installed to `/Users/josh/.codex/skills/ponytail-audit`

Restart Codex before expecting those skills to appear in the automatic skill
list. Until then, apply Ponytail manually: delete/reuse before adding seams, and
only introduce a seam when a second adapter or concentrated implementation
justifies it.

## Current Dirty Tree Warning

At the time this work queue was written, the repository already had uncommitted
changes in:

```text
.agent/skills/improve-codebase-architecture/SKILL.md
docs/architecture/control-room-architecture-audit.md
skills/improve-codebase-architecture/SKILL.md
src/devflow/control_room/browser_action_policy.py
src/devflow/control_room/dogfood.py
src/devflow/control_room/dogfood_case_result.py
src/devflow/control_room/operating_layer_server.py
tests/test_operating_layer.py
src/devflow/control_room/dogfood_case_scratch.py
```

Treat those changes as user or previous-agent work. Do not revert them. Before
implementation, inspect `git status --short` and the relevant diffs.

## Work Item 1: Delete Operating-Layer Task Workbench Mirroring

Recommendation: Strong

Module goal:

Deepen the Task workbench module as the task-centered interface for the
operating layer. `operating_layer.py` should assemble the broader snapshot, not
mirror the Task workbench model surface.

Graphify evidence:

- Audit target: `src/devflow/control_room/operating_layer.py`
- Node: `control_room_operating_layer`
- Degree: 103, highest control-room file degree in the fresh graph.
- `build_operating_layer_snapshot()` affects CLI, Dogfood, visual QA, and more
  than 25 operating-layer tests.
- Path to Task workbench:

```text
operating_layer.py --contains--> build_operating_layer_snapshot()
  --calls--> build_task_workbench()
  <--contains-- task_workbench.py
```

Source evidence:

- `src/devflow/control_room/operating_layer.py` defines task-oriented
  `OperatingLayer*` models around lines 74-272.
- `src/devflow/control_room/task_workbench.py` defines matching
  `TaskWorkbench*` models around lines 37-198.
- `_operating_task_from_workbench()` mostly drops internal fields before
  constructing the duplicate operating-layer task model.

Desired end state:

- The Task workbench remains the task-centered interface.
- The operating-layer snapshot consumes Task workbench projection data directly
  where browser contract allows it.
- Duplicate task-centered model definitions and conversions are deleted when
  tests prove they are not part of a required public contract.
- No new adapter module is added just to move the duplication elsewhere.

Primary files:

- `src/devflow/control_room/operating_layer.py`
- `src/devflow/control_room/task_workbench.py`
- `tests/test_operating_layer.py`
- `tests/test_task_workbench_projection.py`

Focused verification:

```bash
PYTHONPATH=src:. .venv/bin/python -m pytest tests/test_task_workbench_projection.py tests/test_operating_layer.py -q
.venv/bin/graphify explain "control_room_operating_layer" --graph graphify-out/graph.json
.venv/bin/graphify explain "control_room_task_workbench" --graph graphify-out/graph.json
```

Risk:

This work touches the browser snapshot contract and conflicts with Idea
greenhouse extraction because both edit `operating_layer.py` and
`tests/test_operating_layer.py`.

## Work Item 2: Split Agent Catalog Projection From Onboarding Mutations

Recommendation: Worth exploring

Module goal:

Separate the Agent catalog read projection from provider/model onboarding
mutations. The catalog should be a read-heavy module consumed by the operating
layer, server, and CLI; onboarding should own registry writes and validation.

Graphify evidence:

- Audit target: `src/devflow/control_room/agent_onboarding.py`
- Node: `control_room_agent_onboarding`
- Degree: 70, second-highest control-room file degree in the fresh graph.
- `build_agent_catalog()` affects CLI, operating layer, and server.
- `add_provider()` affects only CLI.

Source evidence:

- `agent_onboarding.py` currently owns `add_provider()`, `add_model()`,
  `render_agent_definition()`, `build_agent_catalog()`, local discovery
  projection, and Hermes config parsing.
- `build_agent_catalog()` is a read projection; `add_provider()` and
  `add_model()` are mutation paths.

Desired end state:

- A read projection module owns `build_agent_catalog()` and helper logic for
  provider rows, profile rows, local model discovery rows, Hermes rows, runtime
  contract rows, and catalog actions.
- `agent_onboarding.py` keeps mutation-oriented functions:
  `add_provider()`, `add_model()`, `render_agent_definition()`, validation, and
  registry payload writes.
- Existing public imports are preserved with compatibility aliases if needed.
- No constants-only module is introduced just to share five safety strings.

Primary files:

- `src/devflow/control_room/agent_onboarding.py`
- New module only if it carries real implementation, likely
  `src/devflow/control_room/agent_catalog.py`
- `src/devflow/control_room/operating_layer.py`
- `src/devflow/control_room/operating_layer_server.py`
- `src/devflow/cli.py`
- `tests/test_agent_onboarding.py`
- `tests/test_operating_layer.py`

Focused verification:

```bash
PYTHONPATH=src:. .venv/bin/python -m pytest tests/test_agent_onboarding.py tests/test_operating_layer.py::test_operating_layer_snapshot_exposes_agent_catalog_and_model_actions -q
.venv/bin/graphify explain "control_room_agent_onboarding" --graph graphify-out/graph.json
```

Risk:

This can conflict with Work Item 1 if both edit `operating_layer.py`. Core
catalog extraction can happen independently, but integration into the operating
layer should be serialized.

## Work Item 3: Extract Idea Greenhouse Projection

Recommendation: Worth exploring

Module goal:

Deepen the Idea greenhouse projection as its own module. The operating layer
should assemble the snapshot; Idea greenhouse should own idea lanes, cards,
lineage, evidence paths, summaries, and primary actions.

Graphify evidence:

- `control_room_operating_layer` degree 103.
- Idea greenhouse implementation is embedded inside the same high-degree file
  as goal board, spec board, mission feed, multi-project card, local model
  cards, and agent catalog cards.
- Path to supervisor classification currently runs through
  `_idea_concrete_action()`.

Source evidence:

- `operating_layer.py` idea projection spans around lines 674-931.
- `tests/test_operating_layer.py::test_operating_layer_projects_idea_greenhouse_lanes`
  verifies the behavior through the full operating-layer snapshot.
- The domain context treats unlimited idea capture and visible greenhouse lanes
  as first-class operator-centered product behavior.

Desired end state:

- A module such as `src/devflow/control_room/idea_greenhouse_projection.py`
  owns Idea greenhouse models or projection helpers if those models are no
  longer operating-layer-only.
- The operating layer calls one projection function and adds the result to the
  snapshot.
- Idea tests can target the projection directly instead of only testing through
  the full snapshot.
- No database, model call, background process, or auto-promotion behavior is
  introduced.

Primary files:

- `src/devflow/control_room/operating_layer.py`
- `src/devflow/control_room/idea_foundry.py`
- New module only if it carries real implementation:
  `src/devflow/control_room/idea_greenhouse_projection.py`
- `tests/test_operating_layer.py`
- Optional focused test file: `tests/test_idea_greenhouse_projection.py`

Focused verification:

```bash
PYTHONPATH=src:. .venv/bin/python -m pytest tests/test_idea_foundry.py tests/test_operating_layer.py::test_operating_layer_projects_idea_greenhouse_lanes -q
.venv/bin/graphify explain "control_room_operating_layer" --graph graphify-out/graph.json
```

Risk:

This conflicts with Work Item 1 because both edit `operating_layer.py` and
`tests/test_operating_layer.py`. Do Work Item 1 first, then extract Idea
greenhouse from the thinner snapshot module.

## Work Item 4: Tighten Dogfood Harness Mechanics

Recommendation: Worth exploring

Module goal:

Deepen the existing Dogfood case result module so case functions stop repeating
result mechanics. Do not split every case into its own module unless a real
second interface appears.

Graphify evidence:

- Audit target: `src/devflow/control_room/dogfood.py`
- Node: `control_room_dogfood`
- Lines: 2,490
- Definitions: 40
- Degree: 40
- `run_dogfood_suite()` affects CLI and more than 20 harness tests.
- `control_room_dogfood_case_result` degree: 22.

Source evidence:

- `dogfood_case_result.py` already owns state creation, artifact recording,
  command recording, warnings, lessons, scoring, report rendering, and run YAML.
- `dogfood.py` still coordinates repeated state/artifact/point/cleanup mechanics
  in case functions.
- `dogfood_case_scratch.py` has already started moving scratch-repo mechanics
  out of the main Dogfood file.

Desired end state:

- Dogfood case bodies get shorter by using a deeper case result interface.
- Scoring, artifact, command, warning, lesson, cleanup, and finalization behavior
  concentrate in `dogfood_case_result.py`.
- `dogfood.py` remains a case suite module until there is a stronger reason to
  split individual cases.
- No new case registry abstraction is added unless it deletes more complexity
  than it introduces.

Primary files:

- `src/devflow/control_room/dogfood.py`
- `src/devflow/control_room/dogfood_case_result.py`
- `src/devflow/control_room/dogfood_case_scratch.py`
- `tests/test_dogfood_harness.py`

Focused verification:

```bash
PYTHONPATH=src:. .venv/bin/python -m pytest tests/test_dogfood_harness.py -q
.venv/bin/graphify explain "control_room_dogfood" --graph graphify-out/graph.json
.venv/bin/graphify explain "control_room_dogfood_case_result" --graph graphify-out/graph.json
```

Risk:

Dogfood tests can be slower than small unit tests. Use focused case tests while
editing and run the full harness test file before claiming completion.

## Explicit Non-Recommendations

- Do not create a safety-constants module just to share
  `PURE_READ_ONLY` / approval class strings between `supervisor_surface.py` and
  `browser_action_policy.py`. Ponytail result: one shallow module is worse than
  the current small duplication unless policy consolidation grows.
- Do not split Dogfood into one module per case as a first move. That creates a
  package of shallow files and makes case flow harder to scan.
- Do not use Hyperplane for this architecture cleanup verification. The repo
  instructions quarantine Hyperplane for ordinary smoke evidence.
- Do not commit generated `graphify-out/` artifacts unless a later task
  explicitly chooses a generated artifact for versioning.

## Parallelization Map

Parallel-safe with isolated worktrees:

- Work Item 4 can run in parallel with Work Item 1 because it is scoped to
  Dogfood files and Dogfood tests.
- Work Item 2 core extraction can run in parallel with Work Item 4 if it avoids
  editing `operating_layer.py` until integration.

Serialize:

- Work Item 1 and Work Item 3 both edit `operating_layer.py` and
  `tests/test_operating_layer.py`; run Work Item 1 first.
- Work Item 2 integration into the operating layer should happen after Work
  Item 1 or in a separate worktree with an explicit merge plan.

Suggested order:

1. Work Item 1: Task workbench mirroring deletion.
2. Work Item 4: Dogfood harness mechanics, in parallel with Work Item 1 if using
   an isolated worktree.
3. Work Item 2: Agent catalog extraction after the operating-layer edits settle.
4. Work Item 3: Idea greenhouse extraction from the thinner operating layer.

## Final Verification For The Cleanup Series

After implemented slices are merged into one worktree:

```bash
git diff --check
PYTHONPATH=src:. .venv/bin/python -m pytest tests/test_task_workbench_projection.py tests/test_operating_layer.py tests/test_agent_onboarding.py tests/test_dogfood_harness.py -q
PYTHONPATH=src:. .venv/bin/python -m pytest tests/test_architecture_boundaries.py tests/test_code_map_check.py tests/test_mvp_boundaries.py tests/test_project_scope_docs.py -q
env PYTHONPATH=src:. .venv/bin/python -m devflow.cli architecture audit --write-doc
.venv/bin/graphify diagnose multigraph --json --graph graphify-out/graph.json
```

Expected:

- Targeted tests pass.
- Architecture boundary tests pass.
- Graphify diagnostic remains `ok`.
- `control_room_operating_layer` degree does not increase from 103; a decrease
  is expected after Work Item 1 or Work Item 3.
- Any metric that does not improve is explained in the handoff with source
  evidence, not assumed acceptable.
