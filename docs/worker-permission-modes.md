# Worker Permission Modes

## Purpose

This document defines the security boundaries, write constraints, and execution permissions applied to replaceable Worker Agents within Dev-Flow. It establishes clear gates preventing AI workers from polluting core files, escaping isolation, or silently corrupting system settings.

---

## Permission Modes Overview

Every task operates under specific permission modes depending on the lifecycle phase:
- `read_only`: Applied during planning, spec drafting, and initial inspection where no file writes are permitted.
- `workspace_write`: Applied during worker execution, granting write permissions constrained strictly to the task-local workspace.
- `verify_only`: Granted during verification command execution where only pre-defined tests run inside the sandbox.
- `promotion_candidate`: Marks a verified task as ready, awaiting **human approval** before promotion to the main checkout.

---

## 1. Sandbox Isolation

All worker operations must be physically quarantined.

* **Assigned Scoping:** A worker is restricted entirely to `.devflow/workspaces/<task_id>/`.
* **Path Validation:** Before any command is executed, the Dev-Flow Kernel validates that all referenced directories are subpaths of the task workspace. Any path outside this boundary triggers an immediate security refusal.
* **Symlink Skipping:** During workspace initialization, Dev-Flow skips copying symlinks. This prevents workers from traversing symlink bridges to mutate files or read secrets outside the repository checkout.

---

## 2. Allowed Write-Zones

Even within the isolated workspace, a worker's write capabilities are constrained:

* **Allowed Target Files:** The worker packet (`TaskPacket`) explicitly enumerates the files the worker is permitted to create or edit (e.g. `src/auth/verify.py`, `tests/test_auth.py`).
* **Focused Mutability:** The worker should only focus edits on these explicitly designated files. Edits to other files in the workspace are flagged during the control-room review phase as non-compliant.

---

## 3. Forbidden Zones

The following files and directories are strictly immutable. Workers must never write to, delete, or modify them under any circumstances:

* **The Main Checkout:** The active primary checkout directory must never be directly modified by a worker.
* **Git Core Directory (`.git/`):** The repository index, git config, commit database, hooks, and refs are off-limits.
* **Dev-Flow Metadata (`.devflow/tasks/`):** The canonical task states, system event records, and verification outcomes (`task.yaml`, `events.jsonl`, `verification.json`) must remain tamper-proof. Workers may only read these files or append questions via the kernel interface.
* **Top-Level Configuration Files:** Global project configs (e.g., `pyproject.toml`, `.gitignore`, `setup.py`) are protected.
* **Legacy Codebase (`src/devflow/_legacy/`):** Archived files are quarantined and read-only.
* **Platform Rules & Harnesses:** Harness configs (like `.antigravity/rules.md`, `CLAUDE.md`, `GEMINI.md`, `AGENTS.md`) must not be edited.

---

## 4. Execution Posture & Process Rights

The Dev-Flow Kernel controls worker command execution with locked-down process permissions:

* **Non-Sudo Execution:** Worker processes must always execute under standard user rights. Root or administrative execution (`sudo`) is strictly forbidden.
* **Locked Down Environment:** The environment block passed to the worker subprocess is stripped of sensitive keys (such as Supabase credentials, database passwords, or cloud provider API tokens) unless explicitly white-listed for the task.
* **Timeout Gating:** Every worker run command must specify an execution timeout. If a worker process hangs or stalls, the kernel terminates the process, records the exit state, and captures the trace logs in `logs/worker.log`.
* **Subprocess Redirection:** The kernel redirects worker standard output and standard error streams away from the global console and directly into append-only file descriptors (`logs/worker.log`).
