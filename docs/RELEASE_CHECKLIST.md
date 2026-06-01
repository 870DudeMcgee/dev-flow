# Dev-Flow Release Checklist

This document outlines the strict validation procedure that must be executed and fully passed before tagging, building, or promoting a new release of **Dev-Flow**.

## Pre-Release Validation Steps

Follow these steps in sequence on a clean, isolated staging check-out of the codebase.

---

### 1. Clean Git State Check

Ensure that the repository has zero uncommitted changes and no untracked file contamination:

- [ ] Execute `git status`.
- [ ] Verify that the output shows `nothing to commit, working tree clean`.
- [ ] If any modifications or untracked test fixtures exist, stash, commit, or discard them before proceeding.

---

### 2. Strict Production Readiness Doctor Scan

Verify that the runtime directories and agent configurations meet production safety requirements:

- [ ] Run the strict doctor CLI command:
  ```bash
  python -m devflow doctor --strict
  ```
- [ ] Assert that every diagnostic check outputs `ok`.
- [ ] Confirm that no un-tested experimental provider adapters (such as `openai_chat`, `anthropic_messages`, `gemini`, `ollama_chat`, `openai_compatible`) are marked enabled or as stable runtimes.

---

### 3. Comprehensive Automated Test Suite Execution

Run the complete pytest regression suite and ensure 100% compliance:

- [ ] Execute the full suite:
  ```bash
  PYTHONPATH=src:. .venv/bin/pytest --ignore=scratch
  ```
- [ ] Verify that **all** tests pass successfully without a single failure or unexpected error.
- [ ] Confirm that new concurrency locking, log size limits, and environment allowlist checks pass and have active test coverage.

---

### 4. Code & CLI Command Surface Alignment

Assert that the documented CLI command surface and user manuals perfectly match the physical code implementation:

- [ ] Inspect the CLI help surface:
  ```bash
  python -m devflow --help
  python -m devflow task --help
  ```
- [ ] Confirm that every subcommand and flag described in `README.md` and `docs/control-room-mvp.md` exists and behaves identically.
- [ ] Ensure any experimental CLI commands remain hidden under standard execution unless `DEVFLOW_EXPERIMENTAL=1` is explicitly set.

---

### 5. Packaging & Distribution Integrity

Verify the installability and packaging metadata constraints:

- [ ] Inspect `pyproject.toml` configuration.
- [ ] Verify Python requirement pins are set correctly (`requires-python = ">=3.11"`).
- [ ] Ensure that a clean pip installation succeeds:
  ```bash
  pip install -e .
  ```
