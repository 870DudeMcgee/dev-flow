# Graphify Architecture Baseline

Date: 2026-06-25
Status: Active cleanup baseline

Graphify is generated architecture evidence for cleanup decisions. It is not the
source of truth for product behavior, but it is the current map for checking
whether Dev-Flow is getting easier to understand as the local control-room
harness is simplified.

## Baseline Snapshot

Source evidence:

- Report: `graphify-out/GRAPH_REPORT.md`
- Graph data: `graphify-out/graph.json`
- Visual call flow: `graphify-out/dev-flow-callflow.html`
- Tree view: `graphify-out/GRAPH_TREE.html`
- Built from commit: `4e2d627e9b73f6456fe07216f1b2ae891d98eadf`

Baseline metrics from `graphify-out/GRAPH_REPORT.md`:

| Metric | Value |
|---|---:|
| Files | 606 |
| Approximate words | 616,383 |
| Nodes | 8,356 |
| Edges | 19,765 |
| Communities | 507 |
| Shown communities | 456 |
| Thin omitted communities | 51 |
| Extracted edges | 81% |
| Inferred edges | 19% |
| Ambiguous edges | 0% |

The current checkout has uncommitted work beyond the baseline commit. Treat this
baseline as fresh for the committed repository state and rerun Graphify after
major cleanup milestones or after code changes that materially alter module
boundaries.

## Read-Only Checks

Use these before deciding a major cleanup direction:

```bash
.venv/bin/graphify diagnose multigraph --json --graph graphify-out/graph.json
.venv/bin/graphify explain "devflow_cli" --graph graphify-out/graph.json
.venv/bin/graphify explain "control_room_service" --graph graphify-out/graph.json
.venv/bin/graphify explain "control_room_loop_engine" --graph graphify-out/graph.json
.venv/bin/graphify explain "control_room_task_next_gate" --graph graphify-out/graph.json
.venv/bin/graphify path "devflow_cli" "control_room_service" --graph graphify-out/graph.json
```

The baseline multigraph diagnostic reports no missing endpoints, dangling
endpoints, self-loops, exact duplicate edges, relation variant groups, or import
cycles.

Useful current node IDs:

| Area | Graphify node |
|---|---|
| CLI entry point | `devflow_cli` |
| Core task service facade | `control_room_service` |
| Loop controller | `control_room_loop_engine` |
| Task next-action gate | `control_room_task_next_gate` |
| Operating-layer projection | `control_room_operating_layer` |

Example baseline path:

```text
cli.py --contains--> task_create() --calls--> create_task() <--contains-- service.py
```

## Cleanup Targets

Use Graphify especially around these areas:

- `src/devflow/cli.py`
- `src/devflow/control_room/service.py`
- `src/devflow/control_room/loop_engine.py`
- `src/devflow/control_room/task_next_gate.py`
- operating-layer modules under `src/devflow/control_room/`
- compatibility and legacy/shim surfaces

For each major cleanup milestone, compare:

- node count, edge count, and community count
- the largest mixed-purpose communities
- whether `devflow_cli` remains a broad command dump or becomes easier to
  navigate through clearer module ownership
- whether `control_room_service` stays a stable facade while behavior moves
  behind task lifecycle, loop, verification, evidence, and promotion modules
- whether Graphify paths from CLI to service to task/evidence modules are short
  enough to explain without old docs or historical plans

Architecture is improving when the graph shows clearer harness clusters, not
merely when line count falls.

## Update Procedure

After each major cleanup milestone:

```bash
.venv/bin/graphify update .
.venv/bin/graphify export callflow-html
.venv/bin/graphify tree --label Dev-Flow
```

Then update this document or the milestone handoff with:

- commit or worktree state used for the new graph
- metrics delta from the baseline
- changed high-degree nodes or mixed communities
- Graphify commands run
- links to generated local artifacts

Do not blindly commit full `graphify-out/` output. Keep the generated graph,
HTML, and cache files as local/generated evidence unless a later decision
selects specific generated artifacts for versioning.
