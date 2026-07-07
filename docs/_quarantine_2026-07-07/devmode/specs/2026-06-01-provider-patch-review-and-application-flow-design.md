# Design Spec: Provider Patch Review and Application Flow (P3)
**Date: 2026-06-01**

## 1. Goal Description
Implement CLI and service layer utilities (`devflow task apply-patch <task_id>`) to validate and apply unified diffs from the generated `proposal.patch` files on-demand to the task's isolated workspace. This keeps LLM execution separated from direct file modification while allowing human-in-the-loop validation of generated diffs.

---

## 2. Component Design & Architecture

### A. Pure Python Patch Applier Engine (`src/devflow/control_room/patch_applier.py`)
This module provides text-only unified diff parsing, validation, and atomic matching/writing inside the isolated task workspace.

#### Custom Exception Hierarchy
```python
class PatchError(Exception):
    """Base class for all patch errors."""
    pass

class PatchSelectionError(PatchError):
    """Raised when there is an issue selecting/locating the patch."""
    pass

class PatchParseError(PatchError):
    """Raised when parsing the unified diff fails."""
    pass

class PatchApplicationError(PatchError):
    """Raised when patch application fails due to safety or mismatch conflicts."""
    pass
```

#### Metadata Handling
To prevent valid proposals produced by common tools from failing unnecessarily, the parser distinguishes between metadata lines:

##### Allow and Ignore
* `diff --git ...`
* `index ...`
* `--- ...`
* `+++ ...`
* `@@ ...`

##### Explicitly Reject
* Binary patches (lines matching `Binary files ... differ` or containing null bytes).
* `old mode ...`
* `new mode ...`
* `deleted file mode ...`
* `new file mode ...`
* `rename from ...`
* `rename to ...`
* `similarity index ...`
* `dissimilarity index ...`
* `copy from ...`
* `copy to ...`

#### Operations Supported
* **Modify existing file**: Standard patch hunk application. Target file must exist.
* **Create new text file**: Triggered explicitly when the source header is `--- /dev/null`.
* **Delete file**: Triggered explicitly when the target header is `+++ /dev/null`.
  - To delete a file, the source file must exist, and all removed/context lines must match the file contents exactly.

#### Line Endings & Trailing Newlines
- Files are represented internally as a list of lines with line endings preserved.
- Unified diff trailing newlines (e.g. `\ No newline at end of file`) are correctly parsed and handled to prevent adding/removing trailing newlines.

#### Multi-Hunk Line Offset Matching
- Applying hunks must use a moving offset per file.
- After an earlier hunk adds or removes lines in a file, all subsequent hunk line numbers are dynamically matched against the updated in-memory file by accumulating a `line_offset`.

#### Path Safety & Symlink Rejection
- All target paths are checked to prevent directory traversal.
- For existing files, the target absolute path is resolved using `.resolve()` and must reside strictly within the workspace root.
- For new files (where the parent directories might not exist yet):
  - Ensure the path is relative and has no traversal segments (`..`).
  - Validate that the target path resolves inside the workspace root.
  - Verify that every existing parent directory in the path is not a symlink.
- Reject writing through, or creating, symlinks entirely.

#### Atomic Disk Writes
- Dry-run validation is completely atomic across all files in the patch.
- Disk writes occur only after 100% of the validation and hunks pass.
- File writes use a temp-file replacement pattern (`Path.replace()`) within the same directory, and any deleted files are only removed during this final commit phase.
- If any write fails mid-commit, a clear error is reported.

#### Structured Output
```python
@dataclass
class ChangedFile:
    path: str
    operation: Literal["created", "modified", "deleted"]
    additions: int
    deletions: int

@dataclass
class PatchApplyResult:
    changed_files: list[ChangedFile]
    patch_hash: str
```

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
2. **Idempotency Protection**:
   - If the patch's SHA-256 hash was already applied for this task (exists in the event history), raise a `PatchApplicationError` stating "patch already applied".
3. **Hash & Apply**:
   - Compute the SHA-256 hash of the target `proposal.patch`.
   - Invoke `patch_applier.py` to atomically apply the patch inside `.devflow/workspaces/{task_id}`.
4. **Task State & Event Trail**:
   - Update the task status metadata:
     - Mark task status to `patch_applied` (or preserve the existing task status like `complete` and record the state in the auxiliary metadata, `merge-readiness.json` and `summary.json`, ensuring `merge_readiness.ready` is strictly `False` until verification has passed).
     - Append a `patch_applied` event to `events.jsonl` with:
       - `task_id`
       - `agent_id`
       - `patch_path`
       - `patch_hash` (SHA-256)
       - `changed_files` (list of `ChangedFile` structured details)
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
  Catch specific `PatchError` and print structured context to stderr:
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
* **Unit Tests (`tests/test_patch_applier.py`)**:
  - `test_path_safety_traversal_escape`: Test traversal attempts `../outside.py`.
  - `test_path_safety_absolute`: Test absolute paths `/tmp/foo.py`.
  - `test_symlink_file_rejection`: Test writing to a symlinked file fails.
  - `test_symlink_directory_rejection`: Test writing inside a symlinked directory fails.
  - `test_valid_metadata_ignored`: Test diffs with index/git headers are successfully applied.
  - `test_unsupported_metadata_rejected`: Test binary/mode renames fail.
  - `test_atomic_all_or_nothing`: Confirm that if one file in a two-file patch has a mismatch, neither file is modified.
  - `test_nested_parent_directory_creation`: Test creating parent folders.
  - `test_new_file_collision`: Fail if new file already exists.
  - `test_delete_file_strict`: Test deletes verify exact content match.
  - `test_crlf_endings`: Test CRLF files match correctly.
  - `test_multi_hunk_offset_matching`: Test that applying multiple hunks adjusts line indexes correctly.
* **Service Tests (`tests/test_apply_patch_service.py`)**:
  - Automatic agent selection and error scenarios.
  - Idempotency checks.
  - Verification of `patch_applied` event payloads (hash and file details).
* **CLI Tests (`tests/test_apply_patch_cli.py`)**:
  - Verify output formatting, status codes, and user guidance.
