# Project Code Map Closure Design

Date: 2026-06-13
Status: Approved; ready for implementation handoff

## Purpose

Milestone 11 has drifted between docs and implementation state. The roadmap still names `11E` as the active next priority, but the runtime already includes `devflow map init`, `devflow map show`, `devflow map check`, and bounded `CODE_MAP.md` excerpt support in `devflow task packet`.

The missing closure step is to dogfood the feature in Dev-Flow itself and align active docs so later agents do not keep treating Project Code Map as planned work. This milestone should make the orientation layer real without starting Idea Foundry, provider-backed assignment, autonomous model selection, or a new worker runtime.

## Scope

This closure slice does three things:

1. Add a real root `CODE_MAP.md` for this repository.
2. Align active documentation so Project Code Map is documented as implemented current behavior.
3. Verify the existing map commands and task-packet excerpt path against the real root map.

The `CODE_MAP.md` should be compact, human-authored, and directly useful to an agent starting work in this repo. It should identify:

- what Dev-Flow is
- active source and test layout
- current control-room entry points
- mandatory read-first docs
- paths to skip or avoid treating as active authority
- owner/contact and review date

## Surfaces

### Root `CODE_MAP.md`

Create a repository-root orientation file that passes `devflow map check`. It should not be generated from source and should not try to document every file. It is a stable first-read map, not a complete architecture manual.

### `devflow map` Commands

Keep the existing CLI behavior:

- `devflow map init`
- `devflow map show`
- `devflow map check`

This milestone should document those commands as current stable orientation helpers, not future reserved identifiers.

### `devflow task packet`

Keep the existing bounded excerpt behavior:

- omit the map excerpt when `CODE_MAP.md` is missing
- include a bounded first-lines excerpt when present
- report truncation notes when the map is longer than the configured line limit

No new packet schema behavior is required unless verification shows a real bug.

## Documentation Alignment

Update active docs that currently describe Project Code Map as future or active-in-progress:

- `README.md`
- `docs/control-room-mvp.md`
- `docs/mvp-contract.md`
- `docs/roadmap.md`
- `docs/architecture/project-code-map-mvp.md`

The aligned docs should say:

- Milestone 11 Project Code Map MVP is implemented once this closure lands.
- `CODE_MAP.md` is optional for arbitrary projects but present and dogfooded in Dev-Flow.
- `devflow map init/show/check` are current commands.
- `devflow task packet` includes a bounded map excerpt when `CODE_MAP.md` exists.
- `.code-map.yaml` remains reserved future metadata, not active runtime.
- The next product direction after closure is Milestone 12 Idea Foundry design, not provider routing or autonomous routing.

## Data Flow

```text
CODE_MAP.md
-> devflow map check
-> devflow task packet <task_id>
-> bounded code_map_excerpt
-> worker orientation context
```

The map is not canonical task state. It is read-only context. Task state remains in `.devflow/tasks/<task_id>/task.yaml`, `events.jsonl`, verification artifacts, and related control-room evidence.

## Error Handling

No new error handling should be added unless verification exposes a bug. Current expected behavior is:

- missing `CODE_MAP.md`: `devflow map check` exits non-zero with a clear message to run `devflow map init`
- unfilled template sections: `map check` reports the section names
- broken entry-point paths: `map check` reports the invalid paths
- task packet map read failure: packet builds without crashing and records a truncation/read note

## Tests And Verification

The implementation should run focused tests around the existing map and packet surfaces:

- `tests/test_code_map.py`
- `tests/test_code_map_show.py`
- `tests/test_code_map_check.py`
- focused `tests/test_task_packet.py` cases for `CODE_MAP.md` excerpt inclusion, truncation, and rendering

It should also run `devflow map check` against the real repository root after creating `CODE_MAP.md`.

If only docs and the root map change, full pytest is not required for this closure. Run broader tests only if source or CLI code changes.

## Non-Goals

- No provider-backed adapters.
- No autonomous routing or model selection.
- No Idea Foundry commands.
- No dashboard or operating-layer UI changes.
- No automatic code-map generation.
- No `.code-map.yaml` runtime behavior.
- No changes under `src/devflow/_legacy/`.

## Approval

Josh approved this milestone direction on 2026-06-13 after release readiness passed and `main` was pushed. The implementation should be a focused closure slice, then checkpoint cleanly and ask before `devflow push-main`.
