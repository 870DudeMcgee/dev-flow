# CURRENT_MVP.md

# Current Dev-Flow MVP

## Goal

Build the smallest possible local-first Dev-Flow kernel.

The first milestone must work without AI using only explicit shell commands.

This MVP is a file-based control-room kernel for running, observing, and verifying shell-worker tasks inside isolated scratchpad workspaces.

The frozen command, filesystem, and safety contract lives at `docs/mvp-contract.md`.

## Non-Goals

Do not build these yet:

* AI agent adapters,
* model routing,
* vector memory,
* SQLite or any database,
* graph/DAG planners,
* plugin frameworks,
* browser or terminal dashboard,
* web server,
* git worktree orchestration,
* automatic merging,
* PR automation,
* complex sandboxing,
* multi-agent role systems,
* legacy workflow rituals.

If a feature does not help the shell-worker MVP, defer it.

## Source of Truth

The filesystem is the source of truth.

Do not add a database for the MVP.

Task directories under `.devflow/tasks/` are the task index.

`task.yaml` is the canonical current task state.

`events.jsonl` is append-only historical evidence.

`questions.jsonl` is append-only human-input evidence.

`verification.json` stores the latest verification result.

`logs/` stores raw stdout/stderr.

`result.md` is a human-readable summary, not source of truth.

## Frozen File Layout

```text
.devflow/
  tasks/
    task-0001/
      task.yaml
      events.jsonl
      verification.json
      logs/
        worker.log
        verify.log
  workspaces/
    task-0001/
```

Other implementation artifacts may exist while the rebuild is in progress, but they are not part of the frozen MVP contract.

## MVP Commands

The stable command contract is:

```text
devflow --help
devflow task --help
devflow task create "example task"
devflow task run <id> --shell "echo hello > result.txt"
devflow task verify <id> --shell "test -f result.txt"
devflow task show <id>
devflow task list
```

## Command Behavior

### `devflow task create "title"`

Creates a new task directory with a unique ID.

Writes:

* `task.yaml`,
* empty `events.jsonl`,
* placeholder `verification.json`,
* `logs/worker.log`,
* `logs/verify.log`,
* workspace directory under `.devflow/workspaces/<task-id>/`.

### `devflow task list`

Prints a scannable text list of task IDs, statuses, titles, and latest update time.

### `devflow task show <id>`

Shows:

* title,
* status,
* workspace path,
* created time,
* updated time,
* latest events,
* latest verification result,
* result summary if present.

### `devflow task run <id> --shell "echo hello > result.txt"`

Runs the explicit shell command inside `.devflow/workspaces/<task-id>/`.

Captures:

* command,
* cwd,
* start time,
* end time,
* exit code,
* stdout log,
* stderr log,
* status transition,
* event entries.

This command should update task state and append events.

### `devflow task verify <id> --shell "test -f result.txt"`

Runs the explicit verification command inside the isolated workspace.

Captures:

* command,
* cwd,
* start time,
* end time,
* exit code,
* stdout/stderr logs,
* verification status.

Marks task as:

* `verified` if command exits successfully,
* `verification_failed` if command exits unsuccessfully.

Verification passing does not mean approved or promoted. It means eligible for review.

Dashboard UI is outside the frozen MVP contract.

## MVP Isolation

For the MVP, Dev-Flow uses practical scratchpad isolation, not hardened security.

For each task, Dev-Flow creates:

```text
.devflow/workspaces/<task-id>/
```

Worker commands run with this workspace as the current working directory.

The workspace is a copied scratchpad of the project files.

Default copy exclusions should include:

* `.git`,
* `.devflow`,
* `node_modules`,
* `dist`,
* `build`,
* `coverage`,
* `.venv`,
* `__pycache__`,
* common cache directories.

Do not claim this is a perfect security sandbox.

Strong sandboxing is future work.

MVP safety comes from:

* running only inside the scratchpad cwd,
* using explicit user-provided shell commands,
* refusing obvious destructive command patterns unless explicitly allowed,
* logging every command,
* preserving evidence,
* never mutating the primary working directory through worker execution.

The MVP also refuses tampered workspace paths before shell or verification commands execute and skips symlinks while copying the scratchpad workspace.

## Minimal `task.yaml`

```yaml
id: task-0001
title: Example task
status: created
created_at: "2026-05-28T00:00:00Z"
updated_at: "2026-05-28T00:00:00Z"
workspace: ".devflow/workspaces/task-0001"
worker: shell
last_event: null
last_exit_code: null
verification_status: not_run
```

Suggested statuses:

```text
created
running
blocked
completed
failed
verification_failed
verified
```

Avoid adding more statuses until needed.

## Minimal `events.jsonl`

Each line is one JSON object.

Example:

```json
{"ts":"2026-05-28T00:00:00Z","type":"task.created","message":"Task created","status":"created"}
{"ts":"2026-05-28T00:01:00Z","type":"command.started","command":"echo hello","cwd":".devflow/workspaces/task-0001"}
{"ts":"2026-05-28T00:01:01Z","type":"command.finished","exit_code":0,"status":"completed"}
```

Events are evidence. They are not the canonical current status.

Current status lives in `task.yaml`.

Question workflows and dashboard layouts are future work.

## First Vertical Slice

The frozen MVP is real when Dev-Flow can create one shell task, run `echo hello > result.txt`, verify `test -f result.txt`, list it, and show it.

For each task, the user should be able to see:

* task status,
* command run,
* workspace path,
* logs,
* exit code,
* latest event,
* result summary,
* verification status,
* suggested next action.

All of this must work without mutating the primary working directory.

## Decision Filter

Before making a change, ask:

1. Does this help the shell-worker MVP?
2. Does this make work more visible?
3. Does this make work safer?
4. Does this make work easier to resume?
5. Does this make failure easier to understand?
6. Does this make verification stronger?
7. Does this reduce what the human has to keep in their head?

If not, defer it.
