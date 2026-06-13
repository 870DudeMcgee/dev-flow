# Project Code Map MVP Contract

**Milestone**: 11 (Project Code Map MVP)
**Status**: implemented; Dev-Flow root dogfood added in closure slice
**Boundary**: `CODE_MAP.md` is human-authored read-only orientation context. `.code-map.yaml` remains reserved future metadata.

---

## Problem Statement

Workers entering a large or unfamiliar repository scan broad directory trees, read top-level files, and repeat that work across every task. There is no lightweight, stable orientation artifact they can trust before diving in. The result is:

- wasted tokens on redundant discovery
- inconsistent understanding of repo layout across task sessions
- no canonical place to record owner, entry-point, and "what to read first" guidance

The Project Code Map is a compact, human-maintained orientation file that workers can read once instead of scanning.

---

## Goals

- Give workers a bounded, reliable "read this first" artifact
- Record repo layout, key entry points, owned paths, and what to skip
- Keep it human-authored and human-reviewed — not auto-generated
- Integrate with Dev-Flow task context packing as an optional enrichment layer

---

## Non-Goals

- Automatic code-map generation from source (deferred)
- Embedding full file contents (out of scope)
- Replacing `task packet` or `token-context` as canonical evidence
- Routing or agent-selection logic based on the map
- Any provider API calls or external service integration

---

## Artifacts

### Primary: `CODE_MAP.md`

Placed at the repository root. Human-authored. Optional but recommended.

Required sections for `devflow map check`:

```markdown
# Code Map

## What this repo does
One paragraph. No marketing copy.

## Layout
- `src/` — production source
- `tests/` — test suite (mirrors `src/` structure)
- `docs/` — specs, contracts, architecture decisions
- `.devflow/` — Dev-Flow runtime state (do not edit manually)

## Entry points
- CLI: `src/devflow/cli.py` → `devflow` console script
- Core task lifecycle: `src/devflow/control_room/service.py`
- Promotion: `src/devflow/control_room/promotion.py`

## What to read first (worker orientation)
1. `docs/roadmap.md` — current direction and milestone status
2. `docs/control-room-mvp.md` — active spec
3. `AGENTS.md` — agent operating rules (mandatory)
4. `docs/devmode-contract.md` — DevMode discipline

## What to skip
- `src/devflow/_legacy/` — quarantined, do not modify
- `build/` — generated, ignored by git

## Owners / contacts
- Primary: [human reviewer handle]

## Last reviewed
YYYY-MM-DD
```

### Companion: `.code-map.yaml` (optional, future)

Machine-readable metadata companion. Reserved for future metadata-aware map behavior. Not active at runtime.

```yaml
version: 1
primary: CODE_MAP.md
entry_points:
  cli: src/devflow/cli.py
  core: src/devflow/control_room/service.py
skip_paths:
  - src/devflow/_legacy/
  - build/
last_reviewed: YYYY-MM-DD
```

---

## CLI Commands

| Command | Description |
|---|---|
| `devflow map init` | Scaffold a blank `CODE_MAP.md` in the project root |
| `devflow map show` | Print the current `CODE_MAP.md` to stdout |
| `devflow map check` | Lint the map for stale entry-point paths and missing sections |

These commands are current stable orientation helpers. They do not call providers, route workers, mutate task state, or generate maps from source.

---

## Integration with Task Context Packing

When `CODE_MAP.md` is present, `devflow task packet <task_id>` may optionally include a bounded excerpt (first N lines, configurable) in the packet's `context` section. This is an additive enrichment — the packet remains valid without the map.

The token-context artifact at `.devflow/token-context/current.md` may reference the map path as a suggested read but does not embed its contents.

---

## Acceptance Criteria (Milestone 11 full implementation)

- [x] `CODE_MAP.md` schema documented and stable
- [x] `.code-map.yaml` schema documented as reserved future metadata
- [x] `devflow map init` scaffolds `CODE_MAP.md`
- [x] `devflow map show` prints the map
- [x] `devflow map check` lints for broken entry-point paths
- [x] `devflow task packet` includes a bounded map excerpt when `CODE_MAP.md` is present
- [x] No provider API, routing, database, or autonomous behavior introduced

---

## Implementation Closure

Deliverables:
- Root `CODE_MAP.md` dogfooded in Dev-Flow
- Current `devflow map init/show/check` command behavior documented
- Bounded `CODE_MAP.md` task-packet excerpt documented
- Stale `Next Priority` callout in `docs/roadmap.md` corrected to Milestone 12 Idea Foundry design

No new provider, routing, database, dashboard, or autonomous behavior is part of this closure.

---

## Deferred

- Auto-generation of `CODE_MAP.md` from static analysis
- Map staleness detection in CI
- Web dashboard rendering of the map
- Idea Foundry integration (Milestone 12)
