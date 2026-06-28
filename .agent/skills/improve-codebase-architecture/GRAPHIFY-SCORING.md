# Graphify Scoring

Graphify scoring turns generated artifacts into a small rehab scorecard. It does not replace source review.

## Freshness

Before trusting a graph, compare:

```bash
git rev-parse --short HEAD
rg -n "Built from commit" graphify-out/GRAPH_REPORT.md
python skills/improve-codebase-architecture/scripts/graphify_rehab_score.py --repo .
```

Freshness fails when the current commit does not match the report commit or `graph.json` commit.

## Refresh

For a full Dev-Flow audit checkpoint:

```bash
env PYTHONPATH=src:. .venv/bin/python -m devflow.cli architecture audit --write-doc
```

For score-only validation, update only ignored Graphify artifacts:

```bash
.venv/bin/graphify update .
```

## Baseline And Delta

Create a baseline before implementation:

```bash
python skills/improve-codebase-architecture/scripts/graphify_rehab_score.py --repo . --output .devflow/architecture-rehab/scorecards/before.json
```

Create an after scorecard:

```bash
python skills/improve-codebase-architecture/scripts/graphify_rehab_score.py --repo . --baseline .devflow/architecture-rehab/scorecards/before.json --output .devflow/architecture-rehab/scorecards/after.json
```

Useful deltas are directional evidence, not automatic success:

- Nodes down can mean deletion or lost extraction.
- Edges down can mean less coupling or less visible behavior.
- Max file degree down can mean a hotspot cooled.
- Communities down can mean consolidation; communities up can mean useful separation.

Always cite source and test evidence with the delta.

## Pass/Fail Thresholds

The helper script marks:

- `fresh_graph`: pass only when the graph matches current `HEAD`.
- `extracted_edges`: pass at 80% or higher.
- `ambiguous_edges`: pass at 1% or lower.

Failing thresholds block automated rehab progress. Refresh Graphify or inspect diagnostics before continuing.

## Generated Files

`graphify-out/` is generated evidence and must stay uncommitted. Commit only lightweight docs, skill files, tests, or source changes intentionally selected by the task.
