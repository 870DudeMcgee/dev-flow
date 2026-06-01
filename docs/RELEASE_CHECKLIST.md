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
- [ ] Confirm that no un-tested remote provider adapters (such as `openai_chat`, `anthropic_messages`, `gemini`, `openai_compatible`) are marked enabled or as stable runtimes; `ollama_chat` may execute only through approved local patch-runtime agents such as `qwopus-implementer`.

---

### 3. Comprehensive Automated Test Suite Execution

Run the complete pytest regression suite and ensure 100% compliance:

- [ ] Execute the full suite:
  ```bash
  PYTHONPATH=src:. .venv/bin/pytest --ignore=scratch
  ```
- [ ] Verify that **all** tests pass successfully without a single failure or unexpected error.
- [ ] Confirm that new concurrency locking, log size limits, and environment allowlist checks pass and have active test coverage.
- [ ] Confirm task event hash-chain validation detects malformed or edited `events.jsonl` records.

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
- [ ] Build the source distribution and wheel:
  ```bash
  python -m build
  ```
- [ ] Validate built distributions:
  ```bash
  python -m twine check dist/*
  ```
- [ ] Install the built wheel into a clean virtual environment and run CLI smoke checks:
  ```bash
  python -m venv /tmp/devflow-release-smoke
  /tmp/devflow-release-smoke/bin/python -m pip install dist/*.whl
  /tmp/devflow-release-smoke/bin/devflow --help
  /tmp/devflow-release-smoke/bin/devflow task --help
  ```

---

### 6. Executable Companion Release Check

Verify using the automated companion script:

- [ ] Run the executable release-check script:
  ```bash
  ./scripts/release-check.sh
  ```
  Note: The script is a helper to run compilation, syntax check, the pytest suite, command help smoke validation, and built wheel verification. It complements but does not replace the manual checklist.

---

### 7. Version, Changelog, And State Compatibility

Confirm the release can be understood and upgraded safely:

- [ ] Update `CHANGELOG.md` for the exact version being tagged.
- [ ] Confirm the version in `pyproject.toml` matches the tag.
- [ ] Verify that broad lower-bound dependencies in `pyproject.toml` are correctly documented as alpha-compatible (and that production-grade strict environment verification is managed via separate clean virtualenvs and the CI matrix).
- [ ] Document every state-shape change affecting `.devflow/config.yaml`, `task.yaml`, `verification.json`, `merge-readiness.json`, task event records, or workspace layout.
- [ ] For each state-shape change, provide one of: backward compatibility, a migration path, or a clear refusal/upgrade message.
- [ ] Confirm `README.md` describes the stable runtime surface without implying provider-backed execution, autonomous routing, web dashboard, database state, or git worktree orchestration are currently supported.

---

### 8. Release Publication

Only after the checks above pass:

- [ ] Tag the release from a clean `main` checkout.
- [ ] Build final artifacts from the tag, not from an untagged working tree.
- [ ] Publish the GitHub release with links to `CHANGELOG.md` and the built artifacts.
- [ ] If publishing to a package index, verify the installed console script with a fresh `pipx` or virtualenv install after upload.
