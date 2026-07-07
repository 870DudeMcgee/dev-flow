# Project Task Lifecycle Contract

Status: Active control-room contract

Dev-Flow's goal loop depends on stable project and task identity. A project is a self-contained local workspace with its own `.devflow/` state. A task belongs to exactly one project. The project-local `.devflow/` directory is authoritative for task state, events, verification evidence, workspaces, and goal links.

The global registry is only an index for discovery and explicit cross-project selection. It must not become the source of truth for task correctness.

## Authority Rules

- Project metadata lives at `.devflow/project/project.yaml`.
- Task state lives under `.devflow/tasks/<task_id>/`.
- Task events are append-only evidence under the same project-local `.devflow/`.
- Workspaces and worktrees are project-local runtime artifacts.
- Dashboard output, summaries, registry rows, reports, and status text are projections.

Derived files must be rebuildable or disposable. They cannot be required for canonical task correctness.

## Resolution Rules

Task commands resolve project state through one path:

1. If `--project <project_id>` is supplied, resolve the root from the global registry and then use that project's local `.devflow/`.
2. If no project is supplied, walk upward from the current directory to the nearest ancestor containing `.devflow/`.
3. If no ancestor contains `.devflow/`, use the current directory for bootstrap-compatible local commands.

This preserves the MVP workflow while preventing nested subdirectories from creating accidental split-brain task state. Running from a project root and running from a nested subdirectory must target the same project-local `.devflow/`.

## Registry Failure Behavior

If a registry entry points to a missing path, project registry commands must report that clearly. If a project directory still exists but its registry entry is removed, project-local commands run from inside that project must still read the local `.devflow/` state.

The registry discovers projects. The project directory defines the project.

## Non-Goals

This contract does not add databases, remotes, GitHub automation, provider adapters, background schedulers, remote sync, or autonomous routing. It tightens local-first state handling so future goal-loop and parallel-worker work has a stable base.
