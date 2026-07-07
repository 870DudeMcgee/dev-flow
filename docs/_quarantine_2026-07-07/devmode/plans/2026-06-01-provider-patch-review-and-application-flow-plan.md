# Provider Patch Review and Application Flow Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use devmode:subagent-driven-development (recommended) or devmode:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Implement a pure Python patch parser and applier with smart agent patch selection, absolute directory containment safety, atomic matching, event logging, and CLI integration.

**Architecture:** A separate validation engine parses unified diff patches, performs path safety/symlink checks, dry-runs hunk context matching on line-by-line basis with a moving offset, and commits updates atomically. A service layer coordinates search and idempotency, and Typer commands register the CLI interface.

**Tech Stack:** Python 3.12, Typer, Git, Pytest.

---

### Task 1: Create Custom Patch Errors & Base Parser Structures

**Files:**
- Create: `src/devflow/control_room/patch_applier.py`
- Test: `tests/test_patch_applier.py`

- [ ] **Step 1: Write the failing tests for base parsing and exceptions**
  ```python
  import pytest
  from pathlib import Path
  from devflow.control_room.patch_applier import (
      PatchError,
      PatchParseError,
      PatchSelectionError,
      PatchApplicationError,
      parse_unified_diff,
  )

  def test_exceptions_exist():
      assert issubclass(PatchSelectionError, PatchError)
      assert issubclass(PatchParseError, PatchError)
      assert issubclass(PatchApplicationError, PatchError)

  def test_parse_empty_diff_raises_parse_error():
      with pytest.raises(PatchParseError, match="Empty diff"):
          parse_unified_diff("")
  ```

- [ ] **Step 2: Run test to verify it fails**
  Run: `PYTHONPATH=src .venv/bin/pytest tests/test_patch_applier.py -v`
  Expected: FAIL with "ImportError: cannot import name"

- [ ] **Step 3: Write minimal implementation for exceptions**
  Write this in `src/devflow/control_room/patch_applier.py`:
  ```python
  from __future__ import annotations
  from dataclasses import dataclass
  from pathlib import Path
  from typing import Literal

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

  @dataclass
  class Hunk:
      old_start: int
      old_lines: int
      new_start: int
      new_lines: int
      lines: list[str]  # prefixed with ' ', '-', '+'

  @dataclass
  class PatchFile:
      source_file: str  # e.g., 'a/file.py' or '/dev/null'
      target_file: str  # e.g., 'b/file.py' or '/dev/null'
      hunks: list[Hunk]

  def parse_unified_diff(diff_text: str) -> list[PatchFile]:
      if not diff_text.strip():
          raise PatchParseError("Empty diff")
      return []
  ```

- [ ] **Step 4: Run test to verify it passes**
  Run: `PYTHONPATH=src .venv/bin/pytest tests/test_patch_applier.py -v`
  Expected: PASS

- [ ] **Step 5: Commit**
  ```bash
  git add src/devflow/control_room/patch_applier.py tests/test_patch_applier.py
  git commit -m "feat(patch): add patch exceptions and basic structures"
  ```

---

### Task 2: Implement Complete Unified Diff Parser with Metadata Handling

**Files:**
- Modify: `src/devflow/control_room/patch_applier.py`
- Modify: `tests/test_patch_applier.py`

- [ ] **Step 1: Write test for diff parsing including allowed metadata and rejected metadata**
  Add this to `tests/test_patch_applier.py`:
  ```python
  def test_parse_valid_diff_with_ignored_metadata():
      diff = (
          "diff --git a/hello.txt b/hello.txt\n"
          "index abc123..def456 100644\n"
          "--- a/hello.txt\n"
          "+++ b/hello.txt\n"
          "@@ -1,3 +1,3 @@\n"
          " hello\n"
          "-world\n"
          "+universe\n"
          " ok\n"
      )
      files = parse_unified_diff(diff)
      assert len(files) == 1
      assert files[0].source_file == "hello.txt"
      assert files[0].target_file == "hello.txt"
      assert len(files[0].hunks) == 1
      assert files[0].hunks[0].old_start == 1

  def test_parse_rejected_metadata_raises():
      diff_with_mode = (
          "diff --git a/hello.txt b/hello.txt\n"
          "new file mode 100644\n"
          "--- /dev/null\n"
          "+++ b/hello.txt\n"
      )
      with pytest.raises(PatchParseError, match="Unsupported metadata: new file mode"):
          parse_unified_diff(diff_with_mode)
  ```

- [ ] **Step 2: Run test to verify it fails**
  Run: `PYTHONPATH=src .venv/bin/pytest tests/test_patch_applier.py -v`
  Expected: FAIL (assertion errors or raises failures)

- [ ] **Step 3: Implement parse_unified_diff parsing logic**
  Implement in `src/devflow/control_room/patch_applier.py`:
  ```python
  def parse_unified_diff(diff_text: str) -> list[PatchFile]:
      if not diff_text.strip():
          raise PatchParseError("Empty diff")

      rejected_prefixes = (
          "Binary files ", "old mode ", "new mode ", "deleted file mode ",
          "new file mode ", "rename from ", "rename to ", "similarity index ",
          "dissimilarity index ", "copy from ", "copy to "
      )

      files: list[PatchFile] = []
      current_file: PatchFile | None = None
      current_hunk: Hunk | None = None

      lines = diff_text.splitlines(keepends=True)
      i = 0
      while i < len(lines):
          line = lines[i]
          
          # Check for explicitly rejected prefixes
          if any(line.startswith(p) for p in rejected_prefixes):
              raise PatchParseError(f"Unsupported metadata: {line.strip()}")

          # Parse headers
          if line.startswith("--- "):
              # Extract path, stripping a/ prefix or handling /dev/null
              src_path = line[4:].strip()
              if src_path != "/dev/null":
                  if src_path.startswith("a/"):
                      src_path = src_path[2:]
              
              if i + 1 >= len(lines) or not lines[i + 1].startswith("+++ "):
                  raise PatchParseError("Missing matching +++ header line")
              
              next_line = lines[i + 1]
              dst_path = next_line[4:].strip()
              if dst_path != "/dev/null":
                  if dst_path.startswith("b/"):
                      dst_path = dst_path[2:]

              current_file = PatchFile(source_file=src_path, target_file=dst_path, hunks=[])
              files.append(current_file)
              current_hunk = None
              i += 2
              continue

          elif line.startswith("@@ "):
              if not current_file:
                  raise PatchParseError("Hunk starts without a file header")
              
              # Parse @@ -old_start,old_lines +new_start,new_lines @@
              parts = line.split(" ")
              if len(parts) < 4:
                  raise PatchParseError(f"Malformed hunk header: {line.strip()}")
              
              try:
                  # Parse old (source) spec
                  old_spec = parts[1].removeprefix("-")
                  if "," in old_spec:
                      old_start, old_lines = map(int, old_spec.split(","))
                  else:
                      old_start, old_lines = int(old_spec), 1
                  
                  # Parse new (destination) spec
                  new_spec = parts[2].removeprefix("+")
                  if "," in new_spec:
                      new_start, new_lines = map(int, new_spec.split(","))
                  else:
                      new_start, new_lines = int(new_spec), 1
              except ValueError as exc:
                  raise PatchParseError(f"Malformed hunk integers: {line.strip()}") from exc

              current_hunk = Hunk(
                  old_start=old_start,
                  old_lines=old_lines,
                  new_start=new_start,
                  new_lines=new_lines,
                  lines=[]
              )
              current_file.hunks.append(current_hunk)
              i += 1
              continue

          # Inside a hunk
          if current_hunk is not None:
              if line.startswith(("+", "-", " ")):
                  current_hunk.lines.append(line)
              elif line.startswith("\\ No newline at end of file"):
                  # Keep track of no newline metadata
                  current_hunk.lines.append(line)
              else:
                  # Not part of a hunk, reset current_hunk
                  current_hunk = None
          
          i += 1

      if not files:
          raise PatchParseError("No valid file patches parsed")
      return files
  ```

- [ ] **Step 4: Run test to verify it passes**
  Run: `PYTHONPATH=src .venv/bin/pytest tests/test_patch_applier.py -v`
  Expected: PASS

- [ ] **Step 5: Commit**
  ```bash
  git add src/devflow/control_room/patch_applier.py tests/test_patch_applier.py
  git commit -m "feat(patch): implement unified diff parser with strict prefix rejection"
  ```

---

### Task 3: Implement Hunk Application & Context Matching Engine

**Files:**
- Modify: `src/devflow/control_room/patch_applier.py`
- Modify: `tests/test_patch_applier.py`

- [ ] **Step 1: Write tests for hunk matching, no newline endings, and offset shifts**
  Add this to `tests/test_patch_applier.py`:
  ```python
  from devflow.control_room.patch_applier import apply_patch_files

  def test_apply_modify_exact_match(tmp_path: Path):
      target = tmp_path / "hello.txt"
      target.write_text("line one\nline two\nline three\n", encoding="utf-8")
      diff = (
          "--- a/hello.txt\n"
          "+++ b/hello.txt\n"
          "@@ -2,2 +2,2 @@\n"
          " line two\n"
          "-line three\n"
          "+line beautiful three\n"
      )
      patch_files = parse_unified_diff(diff)
      apply_patch_files(tmp_path, patch_files)
      assert target.read_text(encoding="utf-8") == "line one\nline two\nline beautiful three\n"

  def test_apply_offset_multi_hunk(tmp_path: Path):
      target = tmp_path / "hello.txt"
      target.write_text("one\ntwo\nthree\n", encoding="utf-8")
      diff = (
          "--- a/hello.txt\n"
          "+++ b/hello.txt\n"
          "@@ -1,2 +1,3 @@\n"
          " one\n"
          "+inserted\n"
          " two\n"
          "@@ -3 +4 @@\n"
          "-three\n"
          "+four\n"
      )
      patch_files = parse_unified_diff(diff)
      apply_patch_files(tmp_path, patch_files)
      assert target.read_text(encoding="utf-8") == "one\ninserted\ntwo\nfour\n"

  def test_apply_hunk_mismatch_raises_application_error(tmp_path: Path):
      target = tmp_path / "hello.txt"
      target.write_text("one\ndirty\nthree\n", encoding="utf-8")
      diff = (
          "--- a/hello.txt\n"
          "+++ b/hello.txt\n"
          "@@ -1,2 +1,2 @@\n"
          " one\n"
          "-two\n"
          "+inserted\n"
      )
      patch_files = parse_unified_diff(diff)
      with pytest.raises(PatchApplicationError, match="Mismatch at line 2"):
          apply_patch_files(tmp_path, patch_files)
  ```

- [ ] **Step 2: Run test to verify it fails**
  Run: `PYTHONPATH=src .venv/bin/pytest tests/test_patch_applier.py -v`
  Expected: FAIL

- [ ] **Step 3: Implement full dry-run apply and matching logic**
  Implement `apply_patch_files` in `src/devflow/control_room/patch_applier.py`:
  ```python
  import tempfile
  from dataclasses import dataclass

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

  def apply_patch_files(
      workspace_root: Path,
      patch_files: list[PatchFile],
      dry_run: bool = False
  ) -> PatchApplyResult:
      workspace_root = workspace_root.resolve()
      
      # 1. Validate paths and resolve changes in-memory
      file_updates: dict[Path, list[str]] = {}
      changed_files_list: list[ChangedFile] = []
      deleted_files_list: list[Path] = []

      for pf in patch_files:
          is_creation = pf.source_file == "/dev/null"
          is_deletion = pf.target_file == "/dev/null"

          # Determine target path relative to workspace root
          rel_target_path = pf.target_file if not is_deletion else pf.source_file
          target_abs = (workspace_root / rel_target_path).resolve()
          
          # Path safety: resolved target must be within workspace_root
          try:
              target_abs.relative_to(workspace_root)
          except ValueError as exc:
              raise PatchApplicationError(f"Target path escapes workspace boundary: {rel_target_path}") from exc

          # Symlink checks for target path
          p = target_abs
          while p != workspace_root:
              if p.is_symlink():
                  raise PatchApplicationError(f"Writes through symlinks are rejected: {p}")
              p = p.parent

          if is_creation:
              if target_abs.exists():
                  raise PatchApplicationError(f"File already exists: {rel_target_path}")
              original_lines: list[str] = []
          else:
              if not target_abs.exists():
                  raise PatchApplicationError(f"File not found for modification: {rel_target_path}")
              original_lines = target_abs.read_text(encoding="utf-8", errors="replace").splitlines(keepends=True)

          # Hunk matching with offset shifting
          modified_lines = list(original_lines)
          line_offset = 0
          additions = 0
          deletions = 0

          for idx, hunk in enumerate(pf.hunks):
              # Check base index adjustment
              expected_old_start = hunk.old_start - 1  # 0-indexed
              actual_start = expected_old_start + line_offset
              
              if actual_start < 0 or (actual_start > len(modified_lines) and not is_creation):
                  raise PatchApplicationError(
                      f"File {rel_target_path} Hunk #{idx+1} matching failed: "
                      f"Expected start {actual_start} beyond file length {len(modified_lines)}"
                  )

              # Match lines and apply diff
              source_cursor = actual_start
              new_lines_hunk: list[str] = []
              
              for hl in hunk.lines:
                  if hl.startswith("\\ No newline at end of file"):
                      # Handle newline truncation on previous written line
                      if new_lines_hunk:
                          last_line = new_lines_hunk[-1]
                          if last_line.endswith("\n"):
                              new_lines_hunk[-1] = last_line.rstrip("\r\n")
                      continue
                  
                  prefix = hl[0]
                  content = hl[1:]
                  
                  if prefix in (" ", "-"):
                      # Must match exact original content
                      if source_cursor >= len(modified_lines):
                          raise PatchApplicationError(
                              f"File {rel_target_path} Hunk #{idx+1} mismatch at line {source_cursor+1}: "
                              f"Expected '{content.strip()}', Found EOF"
                          )
                      current_line = modified_lines[source_cursor]
                      if current_line.rstrip("\r\n") != content.rstrip("\r\n"):
                          raise PatchApplicationError(
                              f"File {rel_target_path} Hunk #{idx+1} mismatch at line {source_cursor+1-line_offset}:\n"
                              f"  Expected: '{content.strip()}'\n"
                              f"  Found:    '{current_line.strip()}'"
                          )
                      
                      if prefix == " ":
                          new_lines_hunk.append(current_line)
                          source_cursor += 1
                      else: # '-'
                          source_cursor += 1
                          deletions += 1
                  elif prefix == "+":
                      # additions do not consume a source line
                      new_lines_hunk.append(content)
                      additions += 1

              # Check that we fully processed the hunk's old block length
              expected_consumed = hunk.old_lines
              actual_consumed = source_cursor - actual_start
              # (For new creations, we can tolerate zero matching context lines)
              if not is_creation and actual_consumed != expected_consumed:
                  raise PatchApplicationError(
                      f"File {rel_target_path} Hunk #{idx+1} mismatch: "
                      f"Consumed {actual_consumed} lines, expected {expected_consumed}"
                  )

              # Perform in-memory block replacement
              modified_lines[actual_start : source_cursor] = new_lines_hunk
              
              # Shift line_offset for subsequent hunks
              line_offset += len(new_lines_hunk) - (source_cursor - actual_start)

          if is_deletion:
              # For deletes, check that the resulting content is empty
              non_empty = [l for l in modified_lines if l.strip()]
              if non_empty:
                  raise PatchApplicationError(f"Deleted file {rel_target_path} must be empty after deletion")
              deleted_files_list.append(target_abs)
              changed_files_list.append(ChangedFile(path=rel_target_path, operation="deleted", additions=additions, deletions=deletions))
          elif is_creation:
              file_updates[target_abs] = modified_lines
              changed_files_list.append(ChangedFile(path=rel_target_path, operation="created", additions=additions, deletions=deletions))
          else:
              file_updates[target_abs] = modified_lines
              changed_files_list.append(ChangedFile(path=rel_target_path, operation="modified", additions=additions, deletions=deletions))

      if dry_run:
          import hashlib
          return PatchApplyResult(changed_files=changed_files_list, patch_hash="")

      # 2. Validation passed! Commit disk writes atomically using temp-file replacement
      for path, lines_content in file_updates.items():
          path.parent.mkdir(parents=True, exist_ok=True)
          dir_path = path.parent
          
          # Write to temp file in the same folder first
          with tempfile.NamedTemporaryFile("w", dir=dir_path, delete=False, encoding="utf-8") as temp_f:
              temp_f.write("".join(lines_content))
              temp_path = Path(temp_f.name)
          
          # Rename atomically to target file
          temp_path.replace(path)

      for path in deleted_files_list:
          if path.exists():
              path.unlink()

      return PatchApplyResult(changed_files=changed_files_list, patch_hash="")
  ```

- [ ] **Step 4: Run test to verify it passes**
  Run: `PYTHONPATH=src .venv/bin/pytest tests/test_patch_applier.py -v`
  Expected: PASS

- [ ] **Step 5: Commit**
  ```bash
  git add src/devflow/control_room/patch_applier.py tests/test_patch_applier.py
  git commit -m "feat(patch): implement line-by-line context matching engine"
  ```

---

### Task 4: Add Path Safety Symlink Diagnostics and Hunk Delete Verification Tests

**Files:**
- Modify: `tests/test_patch_applier.py`

- [ ] **Step 1: Write edge-case safety and traversal/symlink verification tests**
  Add this to `tests/test_patch_applier.py`:
  ```python
  def test_symlink_rejection(tmp_path: Path):
      # Create outside target
      outside = tmp_path / "outside.txt"
      outside.write_text("unmodified outside\n", encoding="utf-8")
      
      # Create symlink inside workspace pointing outside
      workspace = tmp_path / "workspace"
      workspace.mkdir()
      sym = workspace / "link.txt"
      sym.symlink_to(outside)
      
      diff = (
          "--- a/link.txt\n"
          "+++ b/link.txt\n"
          "@@ -1 +1 @@\n"
          "-unmodified outside\n"
          "+hacked!\n"
      )
      patch_files = parse_unified_diff(diff)
      with pytest.raises(PatchApplicationError, match="symlinks are rejected"):
          apply_patch_files(workspace, patch_files)
      
      assert outside.read_text(encoding="utf-8") == "unmodified outside\n"

  def test_atomic_partial_failure_prevention(tmp_path: Path):
      file1 = tmp_path / "file1.txt"
      file1.write_text("one\n", encoding="utf-8")
      file2 = tmp_path / "file2.txt"
      file2.write_text("two\n", encoding="utf-8")
      
      # Valid modify for file1, but invalid modify for file2
      diff = (
          "--- a/file1.txt\n"
          "+++ b/file1.txt\n"
          "@@ -1 +1 @@\n"
          "-one\n"
          "+one modified\n"
          "--- a/file2.txt\n"
          "+++ b/file2.txt\n"
          "@@ -1 +1 @@\n"
          "-mismatch\n"
          "+two modified\n"
      )
      patch_files = parse_unified_diff(diff)
      with pytest.raises(PatchApplicationError, match="mismatch"):
          apply_patch_files(tmp_path, patch_files)
      
      # Check file1 was NOT updated on disk (atomic failure)
      assert file1.read_text(encoding="utf-8") == "one\n"
  ```

- [ ] **Step 2: Run test to verify it fails/passes**
  Run: `PYTHONPATH=src .venv/bin/pytest tests/test_patch_applier.py -v`
  Expected: PASS (all path safety logic behaves correctly)

- [ ] **Step 3: Commit**
  ```bash
  git commit -am "test(patch): add symlink safety and atomicity prevention unit tests"
  ```

---

### Task 5: Implement `apply_task_patch` Service Layer Coordinating Search & Idempotency

**Files:**
- Modify: `src/devflow/control_room/service.py`
- Create: `tests/test_apply_patch_service.py`

- [ ] **Step 1: Write tests for service patch selection, hashing, and idempotency**
  Write this in `tests/test_apply_patch_service.py`:
  ```python
  import pytest
  import shutil
  import json
  from pathlib import Path
  from devflow.control_room.service import create_task, apply_task_patch
  from devflow.control_room.patch_applier import PatchSelectionError, PatchApplicationError

  def test_service_apply_patch_flow(tmp_path: Path):
      shutil.copytree(Path.cwd() / "src", tmp_path / "src", symlinks=True)
      shutil.copytree(Path.cwd() / "tests", tmp_path / "tests", symlinks=True)
      
      # Create a task
      task = create_task(tmp_path, "apply patch service task")
      task_path = tmp_path / ".devflow" / "tasks" / task.id
      workspace_path = tmp_path / ".devflow" / "workspaces" / task.id
      
      # Create target workspace file
      hello_file = workspace_path / "hello.txt"
      hello_file.write_text("Hello World\n", encoding="utf-8")
      
      # Set up mock patch
      agent_dir = task_path / "agents" / "test_agent"
      agent_dir.mkdir(parents=True)
      patch_file = agent_dir / "proposal.patch"
      diff = (
          "--- a/hello.txt\n"
          "+++ b/hello.txt\n"
          "@@ -1 +1 @@\n"
          "-Hello World\n"
          "+Hello service World\n"
      )
      patch_file.write_text(diff, encoding="utf-8")
      
      # Apply patch
      updated_task = apply_task_patch(tmp_path, task.id)
      assert hello_file.read_text(encoding="utf-8") == "Hello service World\n"
      
      # Verify event log exists
      events_file = task_path / "events.jsonl"
      assert events_file.exists()
      lines = events_file.read_text(encoding="utf-8").splitlines()
      applied_events = [json.loads(line) for line in lines if "patch_applied" in line]
      assert len(applied_events) == 1
      assert applied_events[0]["payload"]["agent_id"] == "test_agent"
      assert len(applied_events[0]["payload"]["changed_files"]) == 1
      assert applied_events[0]["payload"]["changed_files"][0]["path"] == "hello.txt"
      
      # Idempotency block
      with pytest.raises(PatchApplicationError, match="patch already applied"):
          apply_task_patch(tmp_path, task.id)
  ```

- [ ] **Step 2: Run test to verify it fails**
  Run: `PYTHONPATH=src .venv/bin/pytest tests/test_apply_patch_service.py -v`
  Expected: FAIL with "ImportError: cannot import name 'apply_task_patch'"

- [ ] **Step 3: Implement apply_task_patch coordinating logic**
  Open `src/devflow/control_room/service.py` and modify imports:
  ```python
  # Add imports around lines 37-41:
  from devflow.control_room.patch_applier import (
      PatchError,
      PatchSelectionError,
      PatchParseError,
      PatchApplicationError,
      parse_unified_diff,
      apply_patch_files,
  )
  ```
  And add the function implementation to `src/devflow/control_room/service.py`:
  ```python
  def apply_task_patch(root: Path, task_id: str, agent_id: str | None = None) -> TaskRecord:
      import hashlib
      task_path = task_dir(root, task_id)
      task = get_task(root, task_id)
      workspace = _resolve_task_workspace(root, task)

      agents_dir = task_path / "agents"
      if not agents_dir.exists() or not list(agents_dir.iterdir()):
          raise PatchSelectionError(f"No patches found for task {task_id}")

      target_patch: Path | None = None
      selected_agent: str | None = None

      if agent_id:
          agent_patch = agents_dir / agent_id / "proposal.patch"
          if not agent_patch.exists():
              raise PatchSelectionError(f"No patch found for agent {agent_id}")
          target_patch = agent_patch
          selected_agent = agent_id
      else:
          # Search for proposal.patch in all agent subdirectories
          found_patches: list[tuple[str, Path]] = []
          for child in agents_dir.iterdir():
              if child.is_dir() and (child / "proposal.patch").exists():
                  found_patches.append((child.name, child / "proposal.patch"))
          
          if not found_patches:
              raise PatchSelectionError(f"No patches found under {agents_dir}")
          elif len(found_patches) > 1:
              agents_list = ", ".join(f"'{name}'" for name, _ in found_patches)
              raise PatchSelectionError(
                  f"Multiple proposal patches found: {agents_list}. "
                  "Please specify which one to apply using --agent."
              )
          else:
              selected_agent, target_patch = found_patches[0]

      # Compute SHA-256 hash of the proposal.patch
      patch_content = target_patch.read_text(encoding="utf-8")
      patch_hash = hashlib.sha256(patch_content.encode("utf-8")).hexdigest()

      # Idempotency check: check in events.jsonl
      events_file = task_path / "events.jsonl"
      if events_file.exists():
          for line in events_file.read_text(encoding="utf-8").splitlines():
              if not line.strip():
                  continue
              try:
                  evt = json.loads(line)
                  if evt.get("event") == "patch_applied" and evt.get("payload", {}).get("patch_hash") == patch_hash:
                      raise PatchApplicationError("Patch was already applied to this workspace")
              except json.JSONDecodeError:
                  pass

      # Parse and apply patch
      patch_files = parse_unified_diff(patch_content)
      result = apply_patch_files(workspace, patch_files)
      result.patch_hash = patch_hash

      # Event logging
      changed_files_payload = [
          {"path": f.path, "operation": f.operation, "additions": f.additions, "deletions": f.deletions}
          for f in result.changed_files
      ]
      
      _append_event(root, task_id, "patch_applied", {
          "agent_id": selected_agent,
          "patch_path": _relative(root, target_patch),
          "patch_hash": patch_hash,
          "changed_files": changed_files_payload,
      })

      # Preserve status, update metadata & merge-readiness to false/pending verification
      task.updated_at = utc_now()
      task.last_event = "patch_applied"
      _save_task(task_path, task)
      _write_merge_readiness(root, task_path, task)
      return task
  ```

- [ ] **Step 4: Run test to verify it passes**
  Run: `PYTHONPATH=src .venv/bin/pytest tests/test_apply_patch_service.py -v`
  Expected: PASS

- [ ] **Step 5: Commit**
  ```bash
  git add src/devflow/control_room/service.py tests/test_apply_patch_service.py
  git commit -m "feat(service): implement apply_task_patch service layer coordinating patch application"
  ```

---

### Task 6: Implement CLI Typer Command `devflow task apply-patch` & Register Diffs

**Files:**
- Modify: `src/devflow/cli.py`
- Create: `tests/test_apply_patch_cli.py`

- [ ] **Step 1: Write test for the CLI `task apply-patch` command outputs**
  Write this in `tests/test_apply_patch_cli.py`:
  ```python
  import os
  import json
  import tempfile
  from pathlib import Path
  from typer.testing import CliRunner
  from devflow.cli import app

  runner = CliRunner()

  def test_cli_apply_patch_not_found():
      old_cwd = Path.cwd()
      with tempfile.TemporaryDirectory() as tmp:
          try:
              os.chdir(tmp)
              runner.invoke(app, ["init"])
              runner.invoke(app, ["task", "create", "test task"])
              
              res = runner.invoke(app, ["task", "apply-patch", "task-0001"])
              assert res.exit_code == 1
              assert "Error: No patches found" in res.output
          finally:
              os.chdir(old_cwd)
  ```

- [ ] **Step 2: Run test to verify it fails**
  Run: `PYTHONPATH=src .venv/bin/pytest tests/test_apply_patch_cli.py -v`
  Expected: FAIL (command doesn't exist yet)

- [ ] **Step 3: Implement and register apply-patch in `src/devflow/cli.py`**
  Modify imports in `src/devflow/cli.py`:
  ```python
  # Add around line 24-25:
  from devflow.control_room.service import (
      create_task,
      doctor,
      get_task,
      init_control_room,
      promotion_readiness_errors,
      run_shell_task,
      verify_task,
      apply_task_patch,  # Add this import
  )
  from devflow.control_room.patch_applier import (
      PatchError,
      PatchSelectionError,
      PatchParseError,
      PatchApplicationError,
  )
  ```
  And add the command definition under `task_app` in `src/devflow/cli.py` around line 635:
  ```python
  @task_app.command("apply-patch")
  def task_apply_patch(
      task_id: str,
      agent: str | None = typer.Option(None, "--agent", help="The specific agent's patch to apply."),
  ) -> None:
      """Apply a proposed patch from a worker agent to the isolated task workspace."""
      root = Path.cwd()
      try:
          task = apply_task_patch(root, task_id, agent_id=agent)
          
          # Retrieve the latest patch_applied event to print details
          task_path = root / ".devflow" / "tasks" / task.id
          events_file = task_path / "events.jsonl"
          patch_hash = "unknown"
          agent_id = agent or "default"
          changed_files = []
          if events_file.exists():
              for line in events_file.read_text(encoding="utf-8").splitlines():
                  if not line.strip():
                      continue
                  try:
                      evt = json.loads(line)
                      if evt.get("event") == "patch_applied":
                          payload = evt.get("payload", {})
                          patch_hash = payload.get("patch_hash", "unknown")
                          agent_id = payload.get("agent_id", agent_id)
                          changed_files = payload.get("changed_files", [])
                  except Exception:
                      pass

          typer.echo(f"Successfully applied patch from agent '{agent_id}' to task workspace '{task.id}'.")
          typer.echo(f"Workspace: .devflow/workspaces/{task.id}")
          typer.echo(f"Patch Hash: {patch_hash}")
          typer.echo("")
          typer.echo("Modified files:")
          for cf in changed_files:
              typer.echo(f"  - {cf['path']} ({cf['operation']})")
          typer.echo("")
          typer.echo("Next:")
          typer.echo(f"  devflow task verify {task.id} --shell \"<command>\"")

      except PatchError as exc:
          typer.echo(f"Error: {exc}", err=True)
          raise typer.Exit(code=1) from exc
  ```

- [ ] **Step 4: Run test to verify it passes**
  Run: `PYTHONPATH=src .venv/bin/pytest tests/test_apply_patch_cli.py -v`
  Expected: PASS

- [ ] **Step 5: Commit**
  ```bash
  git add src/devflow/cli.py tests/test_apply_patch_cli.py
  git commit -m "feat(cli): implement devflow task apply-patch command"
  ```
