# Repository Cleanup Plan

Date: 2026-07-02
Status: Accepted cleanup plan and ledger seed

This document records the accepted rules for Dev-Flow repository cleanup. The
goal is to reduce misleading authority in the repo without damaging the active
operating layer, task state contract, verification evidence, or future roadmap
material.

Repository cleanup means source-tree hygiene. It is distinct from Dev-Flow task
cleanup commands that preview or remove task-owned runtime artifacts.

## Authority Chain

Use two authority tracks:

1. Product intent authority: `AGENTS.md`, `docs/control-room-mvp.md`,
   `docs/operator-centered-mission.md`.
2. Current-state authority: code, tests, live Dev-Flow commands/UI, and fresh
   Graphify evidence.

Historical plans, handoffs, and generated Graphify output are evidence only.
They can help find candidates and explain context, but they do not authorize
deletion by themselves.

If docs conflict with current state, classify the doc as a stale context
candidate and reconcile it against product intent, code/tests, live behavior,
and fresh architecture evidence.

## Classifications

Every cleanup candidate must be classified before it is changed, archived,
untracked, or deleted.

| Classification | Meaning | Default action |
|---|---|---|
| Active product | Current operating-layer, task, evidence, verification, review, or promotion behavior | Preserve; refactor only through focused product work |
| Compatibility bridge | Transitional code, tests, docs, or tooling that keeps old imports or workflows resolving | Remove only in a coordinated slice |
| Generated/local runtime state | Local evidence, scoreboards, events, caches, or task/goal runtime state | Untrack or delete after seed/runtime split is explicit |
| Historical reference | Useful explanation of why something exists, but not current authority | Delete when replacement authority or tombstone is present |
| Future roadmap | Explicitly preserved future direction that is not active runtime authority | Preserve or mark clearly; do not delete as stale by default |
| Stale context candidate | Document or reference whose current accuracy is untrusted | Reconcile, then update, tombstone, or delete |
| Stale artifact | One-off or obsolete file with no active reference and no roadmap value | Safe first-slice deletion after reference check |

## Accepted Rules

- Park current dirty MLX training work. Repository cleanup must not touch the
  MLX training files unless a later human decision explicitly absorbs them.
- Optimize for less misleading authority, not maximum line deletion.
- Keep a tiny tombstone/index for deleted historical docs: path pattern, date,
  reason, and replacement authority. Do not preserve long stale summaries in
  the repo.
- Use a cleanup ledger for deletion actions. Use ADRs only for major,
  irreversible architecture decisions where a future reader would need the
  trade-off context.
- Graphify is required for structural cleanup slices and optional for trivial
  stale artifact or tombstone-only slices.
- Local Gemma 4 E4B read-only scouts should be used for cheap breadth when
  available through native Codex agents or the Hermes curl workflow documented
  in `/Users/jewelbait/.codex/AGENTS.md`. Treat their output as advisory
  evidence, not deletion authority.
- Active Graphify hotspots such as `src/devflow/cli.py`,
  `src/devflow/control_room/operating_layer_script.py`,
  `src/devflow/control_room/operating_layer_styles.py`, and
  `src/devflow/control_room/dogfood.py` are later refactor/thinning targets,
  not repository cleanup deletion targets.
- Hyperplane material is quarantined roadmap/reference unless a specific file is
  proven stale and disconnected from active roadmap docs.

## Parked Work

The cleanup plan must avoid the current MLX training work until it is committed,
parked elsewhere, or explicitly accepted into a cleanup branch.

Known parked paths from the 2026-07-02 cleanup grilling session:

- `src/devflow/control_room/training_command.py`
- `src/devflow/control_room/training_mlx_matrix.py`
- `src/devflow/control_room/training_mlx_projection.py`
- `src/devflow/control_room/training_mlx_runner.py`
- `tests/test_training_mlx_command.py`
- `tests/test_training_mlx_matrix.py`
- `tests/test_training_mlx_projection.py`
- `tests/test_training_mlx_runner.py`
- `docs/architecture/soc-architectural-direction.md`
- `docs/superpowers/plans/2026-07-02-mlx-all-model-smoke-test-run.md`

## Subagent Contract

Every non-trivial cleanup slice should have explicit lanes:

| Lane | Preferred model | Role |
|---|---|---|
| Dependency scout | Local Gemma 4 E4B read-only via native agent or Hermes curl workflow, otherwise `gpt-5.4-mini` | Find references, tests, imports, and authority conflicts |
| Coding worker | `gpt-5.3-codex-spark` | Make the bounded patch for a disjoint write scope |
| Reviewer/verifier | Local Gemma 4 E4B read-only via native agent or Hermes curl workflow, otherwise `gpt-5.4-mini` | Check classification, references, and verification evidence |

Scout output is advisory evidence. Deletion decisions still require current docs,
code/tests, and verification.

## Slice Plan

### Slice 1: Ledger And Stale Root Artifacts

Scope:

- Create or extend the cleanup ledger and tombstone/index mechanism.
- Delete only stale artifacts that have no current code/test/doc references.
- Do not touch parked MLX work, `public/`, `_legacy`, top-level shims,
  tracked `.devflow/`, or repo-local skill trees.

Initial candidate decisions are recorded in
`docs/architecture/repository-cleanup-ledger.md`.

Future candidates in this slice should stay limited to root scratch artifacts,
historical handoff fragments, one-off generated result files, and generated
caches already covered by `.gitignore`. Add the ledger entry before deleting or
untracking the file.

Verification:

```bash
git diff --check
rg -n "deleted-path-or-term" AGENTS.md README.md CODE_MAP.md docs src tests
```

Expected hits should be limited to the active cleanup ledger or tombstone index.
If a deletion target is referenced by code or tests, stop and reclassify it as a
coordinated cleanup candidate.

### Slice 2: Delete Obsolete `public/`

Scope:

- Delete the obsolete `public/` UI surface.
- Remove or rewrite tests and legacy expectations that still pin it in place.
- Validate the active operating layer, not the old static UI.

Classification:

- `public/` is not active product.
- Existing references make it a compatibility bridge until removed with tests.

Verification should include targeted operating-layer tests and, when practical,
a served browser/cache-busted check of the real operating-layer UI.

### Slice 3: Purge Legacy Runtime And Shims

Scope:

- Remove `src/devflow/_legacy/`.
- Remove top-level legacy shim files that only re-export `_legacy` modules.
- Retire or rewrite compatibility tests in the same slice.
- Rewrite architecture-boundary tests from "legacy exists but is quarantined" to
  "legacy is gone and forbidden."
- Scan surviving registries, adapters, CLI entrypoints, and test fixtures for
  hidden references to removed modules before deleting files.
- Add or update minimal contract tests for the surviving active surfaces so the
  purge proves current behavior, not just absence of legacy imports.

Classification:

- `_legacy` and shim files are compatibility bridges until this coordinated
  purge lands.

Graphify must be refreshed before and after this structural cleanup.

### Slice 4: Delete Stale Historical Docs

Scope:

- Delete stale historical plans, handoffs, and specs after classification.
- Keep only a tiny tombstone/index with path pattern, deletion date, reason, and
  replacement authority.
- Update current docs that point to deleted paths.

Classification:

- Most old plans/handoffs are stale context candidates, not authority.
- Future roadmap material should be preserved when still directionally useful.

### Slice 5: Split Tracked `.devflow/`

Scope:

- Separate seed/template authority from generated/local runtime state.
- Keep or relocate registry examples, provider examples, project orientation,
  and required seed files.
- Untrack/delete old plans, scoreboards, event logs, questions, and runtime
  evidence that should not be source.

Classification:

- Seed files may be active template authority.
- Runtime files are generated/local runtime state.

Implementation decision:

- `src/devflow/control_room/seed.py` is the source-controlled seed/template
  authority.
- The root `.devflow/` tree is the ignored local materialization created by
  `devflow init` and runtime commands, including registry/provider examples,
  project orientation, task/goal state, scoreboards, plans, reports, and
  evidence.

This slice touches dogfood assumptions and should follow public/legacy cleanup.

### Slice 6: Consolidate Repo-Local Skill Trees

Scope:

- Decide the retained authority for `.agent/skills/` and `skills/`.
- Move useful material to the active external skill location or current docs if
  Dev-Flow should not own it.
- Remove duplicates after tests prove no active dependency remains.

Classification:

- Skill trees are compatibility/tooling bridges until dependency checks say
  otherwise.

Implementation decision:

- `skills/` is the retained repo-local skill authority, including the active
  architecture rehab scripts and token-optimization package.
- `.agent/workflows/` and `.agent/rules/` remain tool-specific DevMode shims,
  but `.agent/skills/` is a duplicate skill tree and should not be maintained.
- `.github/skills/` remains tool-specific routing material, not a second copy of
  the full repo-local skill tree.

### Slice 7: Refactor Active Graphify Hotspots

Scope:

- Thin active modules such as `src/devflow/cli.py`,
  `src/devflow/control_room/operating_layer_script.py`,
  `src/devflow/control_room/operating_layer_styles.py`,
  `src/devflow/control_room/operating_layer_server.py`, and
  `src/devflow/control_room/dogfood.py`.
- Measure improvement by clearer module boundaries and easier call paths, not
  line deletion alone.

Classification:

- These are active product code, not deletion targets.

Status:

- The accepted Slice 7 extraction scope is complete. The follow-up planning
  checkpoint for remaining active hotspots is
  `docs/architecture/control-room-hotspot-followup-plan-2026-07-02.md`.
- Future slices should keep using Graphify as evidence, not authority, and
  should preserve the current operating-layer asset facade unless focused tests
  justify changing it.

## Ledger Format

Use this format for deletion or untracking entries:

```md
| Path | Classification | Action | Reason | Replacement authority | Verification |
|---|---|---|---|---|---|
| `path/to/file` | stale artifact | delete | no active references | `docs/control-room-mvp.md` | `git diff --check`; `rg ...` |
```

## Tombstone Format

Use this format for deleted historical docs:

```md
| Deleted path pattern | Date | Reason | Replacement authority |
|---|---|---|---|
| `docs/handoffs/2026-06-*.md` | 2026-07-02 | stale context; no longer current authority | `AGENTS.md`, `docs/control-room-mvp.md`, `docs/operator-centered-mission.md` |
```
