# Milestone 15B Real Multi-Project Control Room Dogfood Design

## Goal

Prove the multi-project control-room path against a durable active project after Milestone 15 registry hygiene archived the stale temporary project records.

## Current State

The global registry at `/Users/josh/.devflow/registry/projects.json` now has no active projects. The five previous `/private/tmp/...` records are archived and remain visible with:

```bash
DEVFLOW_HOME=/Users/josh/.devflow PYTHONPATH=src:. .venv/bin/devflow project list --include-archived
```

The bounded all-project freshness run no longer stops on missing paths:

```bash
DEVFLOW_HOME=/Users/josh/.devflow PYTHONPATH=src:. .venv/bin/devflow freshness run --all-projects --max-iterations 1 --json
```

That is necessary but not sufficient. Multi-project behavior is currently not exercising a real active project, and the registry still reports an old temporary `projects_root` value until a durable root is explicitly set by project creation/import.

## Scope

This is a dogfood and evidence slice, not a new feature expansion.

Included:

- Create or import one durable local project under `/Users/josh/DevFlow Projects`.
- Confirm the registry no longer points at the old `/private/tmp/...` projects root.
- Create one project-scoped task in the durable project.
- Run one shell worker through `--project`.
- Run one verification command through `--project`.
- Confirm project-scoped task state, logs, verification evidence, dashboard output, status JSON, and all-project freshness all resolve through the registered project root.
- Capture a compact handoff with the durable project id, task id, evidence commands, and one next safe action.

Excluded:

- No provider-backed workers.
- No autonomous routing.
- No Hermes runtime behavior.
- No pull request automation.
- No automatic commits, pushes, publication, promotion, or goal completion.
- No database state.
- No use of temporary `/private/tmp/...` project roots.

## Durable Project Policy

Use `/Users/josh/DevFlow Projects` as the dogfood projects root. Do not create the dogfood project under `/private/tmp`, the Dev-Flow source checkout, or a task workspace.

Recommended project command:

```bash
DEVFLOW_HOME=/Users/josh/.devflow PYTHONPATH=src:. .venv/bin/devflow project create "Milestone 15B Dogfood Project" --projects-root "/Users/josh/DevFlow Projects"
```

Expected project id:

```text
milestone-15b-dogfood-project
```

This project should be local Git by default, with no remote, no push permission, and its own project-local `.devflow/` state.

## Required Dogfood Flow

After creating or importing the project, run this end-to-end sequence:

```bash
DEVFLOW_HOME=/Users/josh/.devflow PYTHONPATH=src:. .venv/bin/devflow project status milestone-15b-dogfood-project
DEVFLOW_HOME=/Users/josh/.devflow PYTHONPATH=src:. .venv/bin/devflow task create --project milestone-15b-dogfood-project "Milestone 15B shell dogfood"
DEVFLOW_HOME=/Users/josh/.devflow PYTHONPATH=src:. .venv/bin/devflow task run task-0001 --project milestone-15b-dogfood-project --worker shell -- /bin/sh -c "mkdir -p evidence && printf 'milestone-15b\n' > evidence/result.txt"
DEVFLOW_HOME=/Users/josh/.devflow PYTHONPATH=src:. .venv/bin/devflow task verify task-0001 --project milestone-15b-dogfood-project --shell "test -f evidence/result.txt && grep -q milestone-15b evidence/result.txt"
DEVFLOW_HOME=/Users/josh/.devflow PYTHONPATH=src:. .venv/bin/devflow task show task-0001 --project milestone-15b-dogfood-project
DEVFLOW_HOME=/Users/josh/.devflow PYTHONPATH=src:. .venv/bin/devflow dashboard --all-projects
DEVFLOW_HOME=/Users/josh/.devflow PYTHONPATH=src:. .venv/bin/devflow status --all-projects --json
DEVFLOW_HOME=/Users/josh/.devflow PYTHONPATH=src:. .venv/bin/devflow freshness run --all-projects --max-iterations 1 --json
```

The exact task id may differ if the dogfood project already has tasks. If so, use the task id printed by `task create` and record it in the handoff.

## Acceptance Criteria

- `project list` shows one active durable project with `Path status: present`.
- `project list --include-archived` still shows the archived stale records for audit history.
- `status --all-projects --json` reports `active_projects: 1` and `missing_projects: 0`.
- `dashboard --all-projects` shows the durable project and the project-scoped task.
- The shell worker writes `evidence/result.txt` inside the project task workspace, not in the Dev-Flow source checkout.
- `task verify --project` passes and writes project-local verification evidence.
- `freshness run --all-projects --max-iterations 1 --json` does not stop on missing registry paths.
- The Dev-Flow source repository remains clean and synced unless docs or handoff files are intentionally updated and committed.

## Self-Check

- This builds the control room, not another coding agent.
- The slice makes multi-project work more visible and recoverable.
- State remains project-local; the registry stays an index.
- Workers remain replaceable because only the shell-worker contract is exercised.
- The project is durable enough for follow-up work and avoids reintroducing stale temporary registry context.
