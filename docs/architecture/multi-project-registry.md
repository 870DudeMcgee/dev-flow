# Multi-Project Registry

Status: Active first-class project-management slice
Date: 2026-06-03

## Decision

DevFlow-created projects are separate local project roots, usually independent local Git repositories, outside the DevFlow source repository by default.

Rules:

- DevFlow does not create GitHub repositories by default.
- DevFlow does not add Git remotes by default.
- DevFlow does not push by default.
- Each managed project owns its own `.devflow/` state.
- The global DevFlow registry is an index, not the source of project truth.
- GitHub is an optional remote publication layer requiring explicit policy and human approval.

## Model

DevFlow now separates three concepts:

```text
DevFlow tool repo
  Source code for DevFlow itself.

DevFlow home / registry
  Local index of projects DevFlow knows about.

Managed project
  A real project directory with its own .devflow/ control-room state.
```

The registry lives at `~/.devflow/registry/projects.json` unless `DEVFLOW_HOME` points elsewhere. The registry answers which projects DevFlow knows about and where they live. The project-local `.devflow/project/project.yaml` remains authoritative for project policy.

## Source Control Policy

Default `devflow project create "Name"` behavior:

1. Create a new folder under the configured projects root.
2. Initialize a local Git repo.
3. Do not create a GitHub repo.
4. Do not add a remote.
5. Do not push anything.
6. Create the per-project `.devflow/` scaffold.
7. Write project metadata with remote publication disabled.
8. Register the project in the global registry.

For managed projects with local Git enabled, `project create` does not create a hidden initial commit. Before creating project-scoped tasks, the human must establish an explicit local baseline from the project root, for example:

```bash
devflow git checkpoint --message "chore: initialize project baseline" --yes
```

Until that baseline exists, `devflow task create --project <project_id> ...` refuses to create a task so copied workspaces and promotion previews have a real `HEAD` to compare against.

Supported project source-control modes:

- `none`: no local Git repo.
- `local_git`: local Git repo with no remote; this is the default.
- `remote_git`: local Git repo with an explicit remote URL.
- `github_managed`: explicit remote metadata only; no GitHub API repository creation is performed by default.

`devflow push-main` refuses to push from a managed project when `.devflow/project/project.yaml` has `remote_publication.push_allowed: false`.

## Commands

```bash
devflow project create "Factory Scheduler"
devflow project create "Local Experiment" --source-control none
devflow project create "Client App" --source-control local-git --private-context
devflow project import /path/to/existing/repo
devflow project list
devflow project show factory-scheduler
devflow project status factory-scheduler
devflow project doctor factory-scheduler
devflow project archive factory-scheduler
devflow project remove factory-scheduler --registry-only
devflow project connect-github factory-scheduler --remote-url <url>
devflow dashboard --all-projects
devflow status --all-projects --json
devflow task create --project factory-scheduler "example task"
devflow task list --project factory-scheduler
devflow task show task-0001 --project factory-scheduler
devflow task run task-0001 --project factory-scheduler --worker shell -- /bin/sh -c "echo hello > result.txt"
devflow task verify task-0001 --project factory-scheduler --shell "test -f result.txt"
devflow task packet task-0001 --project factory-scheduler
devflow task review task-0001 --project factory-scheduler
devflow task next-action task-0001 --project factory-scheduler
devflow task log task-0001 --project factory-scheduler
devflow task review-patch task-0001 --project factory-scheduler
devflow task patch-dry-run task-0001 --project factory-scheduler
devflow task apply-patch task-0001 --project factory-scheduler --agent qwopus-implementer
devflow task promote-preview task-0001 --project factory-scheduler
devflow task promote task-0001 --project factory-scheduler
```

`connect-github` attaches an existing GitHub remote and leaves push disabled unless `--allow-push` is explicitly passed.

A missing registered project path is a human-decision condition. `devflow project doctor <project-id>` is the first diagnostic command. If the project still exists elsewhere, repair by explicitly importing or re-registering the real project root after human review. If the project was temporary, deleted, or intentionally retired, prefer `devflow project archive <project-id>` so the record stays audit-visible through `project list --include-archived` but is excluded from default project lists and all-project scans. Use `devflow project remove <project-id> --registry-only` only for junk records that should not remain in registry history. Read-only surfaces such as `dashboard --all-projects`, `status --all-projects --json`, and all-project freshness must report missing paths and route humans to `project doctor`; they must not auto-recreate, auto-archive, auto-remove, publish, push, or call providers.

Task files belong to the project root, not to the DevFlow source checkout. Project-scoped task commands resolve `<project-id>` through the global registry, then read or write `<project-root>/.devflow/tasks/` and `<project-root>/.devflow/workspaces/` as appropriate. The first implemented project-scoped task commands are create, list, show, run, verify, packet, review, next-action, log, review-patch, patch-dry-run, apply-patch, promote-preview, and promote. Project-scoped promote-preview is read-only. Project-scoped promote preserves the existing human confirmation and promotion safety gates while applying approved changes to the registered project root. Task IDs are unique per project; cross-project displays use `<project_id>:<task_id>` when a task command is scoped with `--project`.
