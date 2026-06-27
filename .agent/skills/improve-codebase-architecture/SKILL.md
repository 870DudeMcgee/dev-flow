---
name: improve-codebase-architecture
description: Use when finding architecture refactoring and deepening opportunities, especially with Graphify evidence, tightly-coupled modules, testability gaps, or AI-navigability problems.
---

# Improve Codebase Architecture

Surface architectural friction and propose **deepening opportunities** — refactors that turn shallow modules into deep ones. The aim is testability and AI-navigability.

## Glossary

Use these terms exactly in every suggestion. Consistent language is the point — don't drift into "component," "service," "API," or "boundary." Full definitions in [LANGUAGE.md](LANGUAGE.md).

- **Module** — anything with an interface and an implementation (function, class, package, slice).
- **Interface** — everything a caller must know to use the module: types, invariants, error modes, ordering, config. Not just the type signature.
- **Implementation** — the code inside.
- **Depth** — leverage at the interface: a lot of behaviour behind a small interface. **Deep** = high leverage. **Shallow** = interface nearly as complex as the implementation.
- **Seam** — where an interface lives; a place behaviour can be altered without editing in place. (Use this, not "boundary.")
- **Adapter** — a concrete thing satisfying an interface at a seam.
- **Leverage** — what callers get from depth.
- **Locality** — what maintainers get from depth: change, bugs, knowledge concentrated in one place.

Key principles (see [LANGUAGE.md](LANGUAGE.md) for the full list):

- **Deletion test**: imagine deleting the module. If complexity vanishes, it was a pass-through. If complexity reappears across N callers, it was earning its keep.
- **The interface is the test surface.**
- **One adapter = hypothetical seam. Two adapters = real seam.**

This skill is _informed_ by the project's domain model. The domain language gives names to good seams; ADRs record decisions the skill should not re-litigate.

## Dev-Flow Graphify Rule

For Dev-Flow, start architecture reviews from fresh Graphify evidence unless the user explicitly asks for a purely local code read. Graphify is evidence, not authority: use it to choose where to inspect, then verify claims against source, tests, and Dev-Flow behavior before calling anything an improvement.

Do not commit generated `graphify-out/` files. Commit only lightweight checkpoint docs or skill/source changes selected by the task.

## Process

### 1. Refresh Graphify evidence

Read the project's domain glossary and any ADRs in the area you're touching first.

In Dev-Flow, run the owned audit command from `<repo-root>`:

```bash
env PYTHONPATH=src:. .venv/bin/python -m devflow.cli architecture audit --write-doc
```

If the `devflow` console script is installed, `devflow architecture audit --write-doc` is equivalent. If Graphify is missing and the user has approved installation, use `--install-graphify`; otherwise stop with the install guidance.

After the run:

- Compare `git rev-parse --short HEAD` with the "Built from commit" line in `graphify-out/GRAPH_REPORT.md`.
- Read `docs/architecture/control-room-architecture-audit.md` for metrics, hotspots, diagnostic status, and recommended cleanup targets.
- Treat diagnostic issues as evidence to inspect, not automatic refactor directives.

### 2. Probe graph and source

Use Graphify to narrow the review before opening broad source files. Start with the audit targets, then run focused probes:

```bash
.venv/bin/graphify diagnose multigraph --json --graph graphify-out/graph.json
.venv/bin/graphify explain "control_room_service" --graph graphify-out/graph.json
.venv/bin/graphify path "devflow_cli" "control_room_service" --graph graphify-out/graph.json
.venv/bin/graphify affected "control_room_task_next_gate" --graph graphify-out/graph.json
.venv/bin/graphify query "Which modules mix operating-layer UI projection with task execution policy?" --graph graphify-out/graph.json --budget 2000
```

Change node names to match the area under review. If a query result becomes part of the decision trail, save useful or corrected results with `graphify save-result`; when memory accumulates, run `graphify reflect` and inspect the lessons before repeating old conclusions.

Then inspect source and tests around the graph-selected modules. Don't follow rigid heuristics; note where understanding one concept requires bouncing between many modules:

- Where does understanding one concept require bouncing between many small modules?
- Where are modules **shallow** — interface nearly as complex as the implementation?
- Where have pure functions been extracted just for testability, but the real bugs hide in how they're called (no **locality**)?
- Where do tightly-coupled modules leak across their seams?
- Which parts of the codebase are untested, or hard to test through their current interface?

Apply the **deletion test** to anything you suspect is shallow: would deleting it concentrate complexity, or just move it? A "yes, concentrates" is the signal you want. A candidate is not ready unless it cites both graph evidence and source evidence.

### 3. Present candidates as an HTML report

Write a self-contained HTML file to the OS temp directory so nothing lands in the repo. Resolve the temp dir from `$TMPDIR`, falling back to `/tmp` (or `%TEMP%` on Windows), and write to `<tmpdir>/architecture-review-<timestamp>.html` so each run gets a fresh file. Open it for the user — `xdg-open <path>` on Linux, `open <path>` on macOS, `start <path>` on Windows — and tell them the absolute path.

The report uses **Tailwind via CDN** for layout and styling, and **Mermaid via CDN** for diagrams where a graph/flow/sequence reliably communicates the structure. Mix Mermaid with hand-crafted CSS/SVG visuals — use Mermaid when relationships are graph-shaped (call graphs, dependencies, sequences), and hand-built divs/SVG when you want something more editorial (mass diagrams, cross-sections, collapse animations). Each candidate gets a **before/after visualisation**. Be visual.

For each candidate, the same template as before, but rendered as a card:

- **Files** — which files/modules are involved
- **Graphify evidence** — audit target, graph node IDs, key `explain`/`path`/`affected`/`query` findings, and whether diagnostics were clean or relevant
- **Problem** — why the current architecture is causing friction
- **Solution** — plain English description of what would change
- **Benefits** — explained in terms of locality and leverage, and how tests would improve
- **Before / After diagram** — side-by-side, custom-drawn, illustrating the shallowness and the deepening
- **Recommendation strength** — one of `Strong`, `Worth exploring`, `Speculative`, rendered as a badge

End the report with a **Top recommendation** section: which candidate you'd tackle first and why. Prefer candidates where Graphify, source inspection, and test pain all point at the same shallow module cluster. Do not propose interfaces yet.

**Use CONTEXT.md vocabulary for the domain, and [LANGUAGE.md](LANGUAGE.md) vocabulary for the architecture.** If `CONTEXT.md` defines "Order," talk about "the Order intake module" — not "the FooBarHandler," and not "the Order service."

**ADR conflicts**: if a candidate contradicts an existing ADR, only surface it when the friction is real enough to warrant revisiting the ADR. Mark it clearly in the card (e.g. a warning callout: _"contradicts ADR-0007 — but worth reopening because…"_). Don't list every theoretical refactor an ADR forbids.

See [HTML-REPORT.md](HTML-REPORT.md) for the full HTML scaffold, diagram patterns, and styling guidance.

After the file is written, ask the user: "Which of these would you like to explore?"

### 4. Grilling loop

Once the user picks a candidate, drop into a grilling conversation. Walk the design tree with them — constraints, dependencies, the shape of the deepened module, what sits behind the seam, what tests survive.

Side effects happen inline as decisions crystallize:

- **Naming a deepened module after a concept not in `CONTEXT.md`?** Add the term to `CONTEXT.md` — same discipline as `/grill-with-docs` (see [CONTEXT-FORMAT.md](../grill-with-docs/CONTEXT-FORMAT.md)). Create the file lazily if it doesn't exist.
- **Sharpening a fuzzy term during the conversation?** Update `CONTEXT.md` right there.
- **User rejects the candidate with a load-bearing reason?** Offer an ADR, framed as: _"Want me to record this as an ADR so future architecture reviews don't re-suggest it?"_ Only offer when the reason would actually be needed by a future explorer to avoid re-suggesting the same thing — skip ephemeral reasons ("not worth it right now") and self-evident ones. See [ADR-FORMAT.md](../grill-with-docs/ADR-FORMAT.md).
- **Want to explore alternative interfaces for the deepened module?** See [INTERFACE-DESIGN.md](INTERFACE-DESIGN.md).
