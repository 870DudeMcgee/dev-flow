---
name: improve-codebase-architecture
description: Use when finding, scoring, or executing architecture rehab opportunities with Graphify evidence, Ponytail simplification gates, shallow modules, coupling hotspots, testability gaps, or Loop-Goal-Script goal loops.
---

# Improve Codebase Architecture

Use this skill to turn Graphify evidence into small architecture slices that improve **depth**, **locality**, and **leverage**. Dev-Flow supplies scorecards, slice rules, prompts, and loop-ready goals. Loop-Goal-Script owns the iteration loop.

## Core Rules

- Graphify is evidence, not authority. Verify claims against source and tests.
- Graphify HTML evidence is mandatory. When `graphify-out/graph.html`,
  call-flow HTML, or `architecture-review-*.html` exists, visually inspect the
  rendered HTML and save screenshots before recommending slices or claiming an
  improvement.
- Ponytail gate every slice: delete or reuse before adding a seam; add no module unless it hides real implementation or deletes more complexity than it introduces.
- One loop iteration works on one safe architecture slice.
- Progress requires code evidence, focused tests, and before/after graph delta evidence.
- Do not commit generated `graphify-out/` files.
- Do not push, publish, open PRs, promote, or merge without explicit human approval.

## Reference Routing

- Architecture vocabulary: read [LANGUAGE.md](LANGUAGE.md) before writing recommendations.
- Review report flow and visual evidence gate: use [HTML-REPORT.md](HTML-REPORT.md), [DEEPENING.md](DEEPENING.md), and [INTERFACE-DESIGN.md](INTERFACE-DESIGN.md) for one-off candidate reports and interface exploration.
- Rehab gates: read [AI-RUNAWAY-REHAB.md](AI-RUNAWAY-REHAB.md) when a codebase shows over-abstraction, plan churn, fake progress, or AI-generated sprawl.
- Scorecards: read [GRAPHIFY-SCORING.md](GRAPHIFY-SCORING.md) before computing baselines or deltas.
- Subagents: read [SUBAGENT-REHAB.md](SUBAGENT-REHAB.md) before dispatching graph scouts, implementers, reviewers, or synthesizers.
- Loop integration: read [LOOP-GOAL-SCRIPT-INTEGRATION.md](LOOP-GOAL-SCRIPT-INTEGRATION.md) before starting, watching, pausing, resuming, injecting, or stopping a rehab loop.
- Work queue: use [REHAB-WORK-QUEUE.md](REHAB-WORK-QUEUE.md) to record candidate packets.

## Script Quick Start

From a target repo:

```bash
python skills/improve-codebase-architecture/scripts/graphify_rehab_score.py --repo .
python skills/improve-codebase-architecture/scripts/start_rehab_loop.py --repo . --candidate "Collapse shallow task projection" --dry-run
python skills/improve-codebase-architecture/scripts/start_rehab_loop.py --repo . --candidate "Subagent-capable rehab" --worker codex55 --dry-run
python skills/improve-codebase-architecture/scripts/rehab_loop_status.py --repo . --slug <loop-slug>
```

`start_rehab_loop.py` launches Loop-Goal-Script only without `--dry-run`. It defaults to `--worker local-fast` (`--profile dflocalfast`) and supports `--worker codex55` (`--profile dfcodex55`) for Hermes GPT Codex 5.5 work that needs stronger tool/subagent behavior. Real starts are preflighted. Validation must not start a model unless the user explicitly approves an integration smoke.

## Visual HTML Evidence Gate

Before acting on Graphify or architecture-review HTML, inspect the rendered page
visibly. Do not rely only on `GRAPH_REPORT.md`, `graph.json`, source text, or
DOM text. This applies to:

- `graphify-out/graph.html`
- `graphify-out/*callflow*.html`
- `architecture-review-*.html`
- local absolute paths and `file://` review URLs

Required evidence:

1. Open the rendered HTML in a browser. If `file://` is blocked, serve the
   containing directory with `python3 -m http.server <free-port> --bind
   127.0.0.1` and browse the localhost URL.
2. Capture at least one overview screenshot and one focused screenshot for each
   hotspot or before/after comparison used in the recommendation.
3. Save screenshots under `.devflow/architecture-rehab/screenshots/` in the
   repo being reviewed, or under the controlling repo's `.devflow/` directory
   when the reviewed path is temporary.
4. Cite the screenshot paths in the handoff, scorecard, or recommendation.

For improvement work, capture before and after screenshots from the same report
view when practical. Never claim the graph or review improved without visual
evidence plus source/test evidence.

## Prompt Templates

Use the templates in [prompts/](prompts/) as starting points:

- `graph-scout.md`
- `ponytail-reviewer.md`
- `implementation-worker.md`
- `graph-delta-reviewer.md`
- `final-synthesizer.md`
