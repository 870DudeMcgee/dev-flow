# Milestone 15 Multi-Project Control Room Hardening Design

## Goal

Make the existing multi-project registry, status, freshness, and dashboard surfaces reliable enough for routine control-room use when registered project paths are stale, temporary, or missing.

## Trigger Evidence

The live global registry at `/Users/josh/.devflow/registry/projects.json` currently contains five active records whose project paths were created under `/private/tmp/...` and no longer exist. The first handoff command reproduced the failure mode:

```bash
DEVFLOW_HOME=/Users/josh/.devflow PYTHONPATH=src:. .venv/bin/devflow project doctor approval-review-demo-project
```

Result:

```text
ok: registry record (approval-review-demo-project)
missing: project path (/private/tmp/devflow-ui-approval-projects-20260605T222631Z/approval-review-demo-project)
```

`devflow freshness run --all-projects --max-iterations 1 --json` checks all five records and correctly stops with `needs_human_decision`, but the next action still says "repair or archive" without a precise policy.

## Policy Decision

The registry is an index, not the source of project truth. A missing registered project path must never be auto-recreated, auto-removed, auto-archived, or treated as healthy.

Use this staged policy:

1. `devflow project doctor <project_id>` is the first diagnostic command for a missing path.
2. If the path is recoverable because the project still exists elsewhere, repair by explicitly importing or re-registering the real project root after human review.
3. If the project was temporary, deleted, or intentionally retired, use `devflow project archive <project_id>` as the default cleanup action. Archived projects remain audit-visible with `project list --include-archived` and are excluded from normal all-project scans.
4. Use `devflow project remove <project_id> --registry-only` only for junk records that should not remain in audit history, such as disposable UI smoke projects.
5. All-project freshness, dashboard, status, operating-layer, and supervisor surfaces should point missing active records to the same diagnostic-first cleanup path instead of inventing separate recovery language.

This keeps project-local `.devflow/` authority intact: Dev-Flow can mark or remove registry entries, but it cannot reconstruct missing project state from the global registry.

## Scope

Included:

- Clarify missing-project policy in user-facing docs and command next actions.
- Make multi-project projections use consistent missing-project next actions.
- Keep archived projects out of default all-project freshness and status scans.
- Add focused tests for missing active records, archived records, and registry-only removal guidance.
- Preserve existing project-local task state resolution and project-scoped task command behavior.

Excluded:

- No provider-backed workers.
- No autonomous routing.
- No database or remote state.
- No GitHub repository creation, push, pull request, or publication automation.
- No automatic registry mutation during freshness, dashboard, status, doctor, or operating-layer reads.
- No reconstruction of missing `.devflow/` state from registry records.

## UX Contract

For a missing active project:

- `project list` shows `Path status: missing`.
- `project show` shows the missing path and does not fail.
- `project doctor` exits non-zero with a failed `project path` check.
- `status --all-projects --json` includes the record with `path_status: "missing"` and `detail: "project path is missing"`.
- `freshness run --all-projects` stops with `needs_human_decision`.
- Operating-layer and supervisor next actions prefer `devflow project doctor <project_id>`.
- No read-only surface mutates the registry.

For an archived project:

- `project list` hides it by default.
- `project list --include-archived` shows it.
- `resolve_project_root(..., project_id=...)` refuses it as archived.
- All-project scans ignore it unless a future explicit include-archived mode is designed.

For a registry-only removal:

- The command requires `--registry-only`.
- It deletes only the registry entry and records a registry event.
- It must not delete or alter any project directory.

## Acceptance Criteria

- The live stale registry can be triaged with one documented sequence:

```bash
DEVFLOW_HOME=/Users/josh/.devflow PYTHONPATH=src:. .venv/bin/devflow project doctor <project_id>
DEVFLOW_HOME=/Users/josh/.devflow PYTHONPATH=src:. .venv/bin/devflow project archive <project_id>
```

- After all intentionally retired missing records are archived or removed by explicit human command, `DEVFLOW_HOME=/Users/josh/.devflow PYTHONPATH=src:. .venv/bin/devflow freshness run --all-projects --max-iterations 1 --json` no longer stops on those retired paths.
- Focused tests cover missing active records, archived records, registry-only removal, all-project freshness next action text, and operating-layer next action text.
- Full behavior remains local-first and read-mostly: no providers, no remote publication, no automatic registry cleanup.

## Implementation Notes

Likely files:

- `src/devflow/control_room/multi_project_freshness.py` for missing-project next action text.
- `src/devflow/control_room/operating_layer.py` for missing-project next action text.
- `src/devflow/control_room/project_registry.py` if archive/remove rendering needs clearer output, but the existing archive and remove primitives already match the policy.
- `tests/test_project_registry.py`, `tests/test_freshness_loop.py`, and `tests/test_operating_layer.py` for focused coverage.
- `docs/architecture/multi-project-registry.md`, `docs/control-room-mvp.md`, and `docs/mvp-contract.md` for active contract wording.

## Self-Check

- This is control-room work, not another coding agent.
- The change improves visibility and recoverability for parallel multi-project operation.
- State remains clearer because project-local `.devflow/` stays authoritative and the global registry remains an index.
- The policy works without frontier-model credits or remote services.
- Missing-path failures remain explicit and human-controlled.
