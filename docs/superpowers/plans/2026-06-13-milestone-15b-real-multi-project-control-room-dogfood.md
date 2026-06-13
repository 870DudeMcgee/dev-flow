# Milestone 15B Real Multi-Project Control Room Dogfood Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Create one durable registered project and prove the project-scoped control-room path end to end.

**Architecture:** Use the existing project registry and project-local `.devflow/` state. The global registry remains an index; all task, worker, verification, dashboard, status, and freshness evidence must resolve through the registered project root.

**Tech Stack:** Dev-Flow CLI, filesystem-backed `.devflow/` artifacts, local Git, shell worker, pytest only if code changes become necessary.

---

### Task 1: Establish A Durable Active Project

**Files:**
- Mutates: `/Users/josh/.devflow/registry/projects.json`
- Mutates: `/Users/josh/.devflow/events.jsonl`
- Creates or uses: `/Users/josh/DevFlow Projects/milestone-15b-dogfood-project/`

- [ ] **Step 1: Confirm source repo baseline**

Run:

```bash
PYTHONPATH=src:. .venv/bin/devflow git status
```

Expected: clean `main`, ahead `0`, behind `0`.

- [ ] **Step 2: Confirm global registry has no active missing projects**

Run:

```bash
DEVFLOW_HOME=/Users/josh/.devflow PYTHONPATH=src:. .venv/bin/devflow project list
DEVFLOW_HOME=/Users/josh/.devflow PYTHONPATH=src:. .venv/bin/devflow status --all-projects --json
```

Expected: no active projects or no missing projects.

- [ ] **Step 3: Create the durable dogfood project**

Run:

```bash
DEVFLOW_HOME=/Users/josh/.devflow PYTHONPATH=src:. .venv/bin/devflow project create "Milestone 15B Dogfood Project" --projects-root "/Users/josh/DevFlow Projects"
```

Expected: project id `milestone-15b-dogfood-project`; path `/Users/josh/DevFlow Projects/milestone-15b-dogfood-project`; local Git initialized; no remote.

If the project already exists or is already registered, do not delete it. Instead run:

```bash
DEVFLOW_HOME=/Users/josh/.devflow PYTHONPATH=src:. .venv/bin/devflow project import "/Users/josh/DevFlow Projects/milestone-15b-dogfood-project"
```

- [ ] **Step 4: Verify registry and project metadata**

Run:

```bash
DEVFLOW_HOME=/Users/josh/.devflow PYTHONPATH=src:. .venv/bin/devflow project list
DEVFLOW_HOME=/Users/josh/.devflow PYTHONPATH=src:. .venv/bin/devflow project doctor milestone-15b-dogfood-project
DEVFLOW_HOME=/Users/josh/.devflow PYTHONPATH=src:. .venv/bin/devflow project status milestone-15b-dogfood-project
```

Expected: path status present, metadata ok, local Git repo ok, no remote ok.

### Task 2: Run Project-Scoped Shell Work

**Files:**
- Mutates: `/Users/josh/DevFlow Projects/milestone-15b-dogfood-project/.devflow/tasks/`
- Mutates: `/Users/josh/DevFlow Projects/milestone-15b-dogfood-project/.devflow/workspaces/`

- [ ] **Step 1: Create a project-scoped task**

Run:

```bash
DEVFLOW_HOME=/Users/josh/.devflow PYTHONPATH=src:. .venv/bin/devflow task create --project milestone-15b-dogfood-project "Milestone 15B shell dogfood"
```

Expected: output includes `Created milestone-15b-dogfood-project:<task-id>`. Record the task id.

- [ ] **Step 2: Run the shell worker**

Replace `<task-id>` with the id from Step 1:

```bash
DEVFLOW_HOME=/Users/josh/.devflow PYTHONPATH=src:. .venv/bin/devflow task run <task-id> --project milestone-15b-dogfood-project --worker shell -- /bin/sh -c "mkdir -p evidence && printf 'milestone-15b\n' > evidence/result.txt"
```

Expected: task completes and worker log is written in the registered project root.

- [ ] **Step 3: Verify the task**

Run:

```bash
DEVFLOW_HOME=/Users/josh/.devflow PYTHONPATH=src:. .venv/bin/devflow task verify <task-id> --project milestone-15b-dogfood-project --shell "test -f evidence/result.txt && grep -q milestone-15b evidence/result.txt"
```

Expected: verification passed.

- [ ] **Step 4: Inspect task evidence**

Run:

```bash
DEVFLOW_HOME=/Users/josh/.devflow PYTHONPATH=src:. .venv/bin/devflow task show <task-id> --project milestone-15b-dogfood-project
DEVFLOW_HOME=/Users/josh/.devflow PYTHONPATH=src:. .venv/bin/devflow task log <task-id> --project milestone-15b-dogfood-project --tail 20
```

Expected: task ref includes `milestone-15b-dogfood-project:<task-id>`, status is verified, evidence paths point inside `/Users/josh/DevFlow Projects/milestone-15b-dogfood-project`.

### Task 3: Prove Multi-Project Visibility

**Files:**
- Reads: `/Users/josh/.devflow/registry/projects.json`
- Reads: project-local `.devflow/` state

- [ ] **Step 1: Render all-project dashboard**

Run:

```bash
DEVFLOW_HOME=/Users/josh/.devflow PYTHONPATH=src:. .venv/bin/devflow dashboard --all-projects
```

Expected: shows one active project, zero missing projects, and the dogfood task.

- [ ] **Step 2: Render all-project status JSON**

Run:

```bash
DEVFLOW_HOME=/Users/josh/.devflow PYTHONPATH=src:. .venv/bin/devflow status --all-projects --json
```

Expected: `active_projects: 1`, `missing_projects: 0`, `projects[0].project_id: "milestone-15b-dogfood-project"`.

- [ ] **Step 3: Run bounded all-project freshness**

Run:

```bash
DEVFLOW_HOME=/Users/josh/.devflow PYTHONPATH=src:. .venv/bin/devflow freshness run --all-projects --max-iterations 1 --json
```

Expected: does not stop on missing project paths. A `max_iterations_reached` result is acceptable when the single iteration has no missing-project blockers.

### Task 4: Close With Evidence

**Files:**
- Create: `docs/handoffs/2026-06-13-milestone-15b-real-multi-project-dogfood-complete.md`
- Modify active docs only if the dogfood exposes a stale claim or command mismatch.

- [ ] **Step 1: Record compact handoff**

Create a handoff with:

- project id
- project root
- task id
- key command outputs
- risks
- one next safe action

- [ ] **Step 2: Verify source repo cleanliness**

Run:

```bash
PYTHONPATH=src:. .venv/bin/devflow git status
```

Expected: clean if no docs were changed; dirty only with the intentional handoff/doc file.

- [ ] **Step 3: If docs or handoff were changed, checkpoint and push after approval**

Only after human approval:

```bash
PYTHONPATH=src:. .venv/bin/devflow git checkpoint --message "docs: hand off milestone 15b dogfood evidence" --yes
PYTHONPATH=src:. .venv/bin/devflow push-main
```
