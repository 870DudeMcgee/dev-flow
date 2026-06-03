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
```

`connect-github` attaches an existing GitHub remote and leaves push disabled unless `--allow-push` is explicitly passed.
