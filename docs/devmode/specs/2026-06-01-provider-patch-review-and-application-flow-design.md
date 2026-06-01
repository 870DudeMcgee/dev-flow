# Design Spec: Provider Patch Review and Application Flow (P3)
**Date: 2026-06-01**

## 1. Goal Description
Implement CLI and service layer utilities (`devflow task apply-patch <task_id>`) to validate and apply unified diffs from the generated `proposal.patch` files on-demand to the task's isolated workspace. This keeps LLM execution separated from direct file modification while allowing human-in-the-loop validation of generated diffs.

---

## 2. Component Design & Architecture

### A. Pure Python Patch Applier Engine (`src/devflow/control_room/patch_applier.py`)
This module provides text-only unified diff parsing, validation, and atomic matching/writing inside the isolated task workspace.

#### Supported Operations
* **Modify existing file**: Standard patch hunk application. Target file must exist.
* **Create new text file**: Triggered explicitly when the source header is `--- /dev/null`.
* **Delete file**: Triggered explicitly when the target header is `+++ /dev/null`.

#### Explicitly Rejected Features (Raises `PatchParseError` or `PatchApplicationError`)
* Binary patches (lines matching `Binary files ... differ` or containing null bytes).
* Rename-only patches.
* Mode-only/Chmod changes (`old mode ...`, `new mode ...`).
* Untracked or arbitrary git metadata headers not understood by the parser.
* Path traversal / absolute paths escaping the workspace boundary.
* Writes traversing or targeting symlinks.

#### Algorithm and Newline Handling
1. **Path Safety & Symlink Check**:
   - The resolved absolute target path must be strictly within the workspace root directory.
   - We reject writing through any symlinks for safety.
2. **In-Memory File Matching & Line-by-Line Context Validation**:
   - Files are loaded and processed as a list of lines with line endings preserved.
   - Unified diff trailing newlines (e.g. `\ No newline at end of file`) are correctly parsed and preserved.
   - Dynamic hunk application is done using an accumulated `line_offset` per file. When hunks add or remove lines, the line index offsets are updated dynamically for subsequent hunks.
3. **Atomic Commit**:
   - All validation and dry-runs must pass 100% across all files and hunks before writing any changes. If any conflict or mismatch is encountered, a detailed list of mismatches is raised, and nothing is written to disk.

---

### B. Service Layer (`src/devflow/control_room/service.py`)
We expose `apply_task_patch(root: Path, task_id: str, agent_id: str | None = None) -> TaskRecord`:

1. **Smart Automatic Search**:
   - Look under `.devflow/tasks/{task_id}/agents/` for subdirectories.
   - If `agent_id` is passed, check `agents/{agent_id}/proposal.patch`.
   - If omitted:
     - Find all `proposal.patch` files.
     - If exactly one exists, use it.
     - If multiple exist, raise `PatchSelectionError` listing the options.
     - If none exist, raise `PatchSelectionError`.
2. **Hash & Apply**:
   - Compute the SHA-256 hash of the target `proposal.patch`.
   - Invoke `patch_applier.py` to atomically apply the patch inside `.devflow/workspaces/{task_id}`.
3. **Task State & Event Trail**:
   - Update task status to show the patch was applied (e.g., status is `complete` but with verification status updated/needs verification).
   - Append a `patch_applied` event to `events.jsonl` with:
     - `task_id`
     - `agent_id`
     - `patch_path`
     - `patch_hash` (SHA-256)
     - `changed_files` (list of paths with operations: `created`, `modified`, `deleted`)
     - `timestamp`
   - Re-render `merge-readiness.json` (marking it false/pending verification) and `summary.json`.

---

### C. CLI Layer (`src/devflow/cli.py`)
We add `@task_app.command("apply-patch")`:
```bash
devflow task apply-patch <task_id> [--agent <agent_id>]
```

#### Behavior & Output
* **Success Output**:
  ```text
  Successfully applied patch from agent '<agent_id>' to task workspace '<task_id>'.
  Workspace: .devflow/workspaces/<task_id>
  Patch Hash: <sha256>

  Modified files:
    - src/foo.py (modified)
    - tests/test_foo.py (created)

  Next:
    devflow task verify <task_id> --shell "<command>"
  ```
* **Failure Output**:
  Catch specific `PatchApplicationError` / `PatchParseError` / `PatchSelectionError` and print structured errors to stderr:
  ```text
  Error: Failed to apply proposed patch due to mismatch/conflict.
  File: src/foo.py
  Hunk #1 Mismatch at line 12:
    Expected: 'def hello_world():'
    Found:    'def hello_universe():'
  ```

---

## 3. Verification Plan

### Automated Tests
* **Unit Tests**:
  - `tests/test_patch_applier.py`: Validate path safety, symlink rejection, binary rejection, mode change rejection, correct newline handling (`\ No newline at end of file`), multi-hunk offset accumulation, and atomic application.
  - `tests/test_apply_patch_service.py`: Verify automatic agent searching, selection error cases (multiple/zero patches), and event logging (with SHA-256 hash and operation details).
* **CLI Tests**:
  - `tests/test_apply_patch_cli.py`: Mock the applier/service and verify the CLI commands output correct formatting, exit codes, and next-action advice.
