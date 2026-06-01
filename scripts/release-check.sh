#!/usr/bin/env bash
# ==============================================================================
# Dev-Flow Release Readiness Automated Validation Companion
# ==============================================================================
set -euo pipefail

# 1. Header & Location Check
echo "=============================================================================="
echo "⚡ Starting Dev-Flow Release Readiness Check"
echo "=============================================================================="

# Confirm running from repo root
if [[ ! -f "pyproject.toml" || ! -d "src/devflow" ]]; then
  echo "❌ Error: This script must be run from the repository root." >&2
  exit 1
fi
echo "✓ Confirmed repository root"

# 2. Git Status Check
echo -e "\n------------------------------------------------------------------------------"
echo "🔍 Checking Git State"
echo "------------------------------------------------------------------------------"
# Filter out .devflow paths and check if there are other uncommitted files
GIT_DIRTY_FILES=$(git status --porcelain | grep -v '^\?\? \.devflow/' | grep -v '^ M \.devflow/' || true)

if [[ -n "$GIT_DIRTY_FILES" ]]; then
  echo "❌ Error: Working tree has uncommitted or untracked non-devflow changes:"
  echo "$GIT_DIRTY_FILES"
  echo "Please stash, commit, or clean up your Git worktree before validating a release."
  exit 1
fi
echo "✓ Git worktree is clean (excluding .devflow paths)"

# 3. Compilation Syntax Check
echo -e "\n------------------------------------------------------------------------------"
echo "⚙ Verifying Python Syntax (compileall)"
echo "------------------------------------------------------------------------------"
PYTHONPATH=src:. python3 -m compileall src
echo "✓ All source files compiled successfully"

# 4. Pytest Regression Suite
echo -e "\n------------------------------------------------------------------------------"
echo "🧪 Running Pytest Regression Suite"
echo "------------------------------------------------------------------------------"
# Use the local virtual environment pytest if available, fallback to python3 -m pytest
if [[ -f ".venv/bin/pytest" ]]; then
  PYTHONPATH=src:. .venv/bin/pytest --ignore=scratch -q --tb=short
else
  PYTHONPATH=src:. python3 -m pytest tests/ --ignore=scratch -q --tb=short
fi
echo "✓ Pytest suite completed successfully"

# 5. CLI Help Smoke Checks & Hiding Gating
echo -e "\n------------------------------------------------------------------------------"
echo "🖥 Running CLI Help Smoke & Experimental Command Hiding Checks"
echo "------------------------------------------------------------------------------"
# Setup standard command runner
RUN_CLI="python3 -m devflow.cli"
if [[ -f ".venv/bin/python" ]]; then
  RUN_CLI=".venv/bin/python -m devflow.cli"
fi

# Assert basic help command works
$RUN_CLI --help >/dev/null
$RUN_CLI task --help >/dev/null
echo "✓ Basic CLI help commands succeed"

# Assert experimental commands are hidden from standard help
STANDARD_HELP=$($RUN_CLI --help)
STANDARD_TASK_HELP=$($RUN_CLI task --help)

for cmd in "supervise" "context"; do
  if echo "$STANDARD_HELP" | grep -q "$cmd"; then
    echo "❌ Error: Experimental command '$cmd' is exposed in standard '--help'." >&2
    exit 1
  fi
done

for cmd in "fit" "pack" "scout" "route" "scorecard"; do
  if echo "$STANDARD_TASK_HELP" | grep -q "$cmd"; then
    echo "❌ Error: Experimental task subcommand '$cmd' is exposed in standard 'task --help'." >&2
    exit 1
  fi
done
echo "✓ Experimental commands are hidden in standard help"

# Assert experimental commands are shown when DEVFLOW_EXPERIMENTAL=1
EXP_HELP=$(DEVFLOW_EXPERIMENTAL=1 $RUN_CLI --help)
EXP_TASK_HELP=$(DEVFLOW_EXPERIMENTAL=1 $RUN_CLI task --help)

for cmd in "supervise" "context"; do
  if ! echo "$EXP_HELP" | grep -q "$cmd"; then
    echo "❌ Error: Experimental command '$cmd' is NOT shown under DEVFLOW_EXPERIMENTAL=1." >&2
    exit 1
  fi
done

for cmd in "fit" "pack" "scout" "route" "scorecard"; do
  if ! echo "$EXP_TASK_HELP" | grep -q "$cmd"; then
    echo "❌ Error: Experimental task subcommand '$cmd' is NOT shown under DEVFLOW_EXPERIMENTAL=1." >&2
    exit 1
  fi
done
echo "✓ Experimental commands are successfully exposed under DEVFLOW_EXPERIMENTAL=1"

# 6. Packaging & Distribution Smoke Check (if tools available)
echo -e "\n------------------------------------------------------------------------------"
echo "📦 Packaging & Smoke Install Gating"
echo "------------------------------------------------------------------------------"

if ! python3 -c "import build" >/dev/null 2>&1; then
  echo "[info] python-build is not installed. Skipping distribution compilation check."
  echo "       To test packaging, run: pip install build twine"
else
  echo "Building distributions..."
  python3 -m build >/dev/null
  echo "✓ Distribution build succeeded"

  if ! python3 -c "import twine" >/dev/null 2>&1; then
    echo "[info] twine is not installed. Skipping package metadata verification."
  else
    echo "Checking distributions with twine..."
    python3 -m twine check dist/*
    echo "✓ Package twine check passed"
  fi

  # Smoke install wheel in a temporary virtual environment
  echo "Smoke installing wheel in temporary virtualenv..."
  TEMP_SMOKE_VENV=$(mktemp -d -t devflow-release-smoke-XXXXXX)
  python3 -m venv "$TEMP_SMOKE_VENV"
  "$TEMP_SMOKE_VENV/bin/python" -m pip install -q dist/*.whl
  "$TEMP_SMOKE_VENV/bin/devflow" --help >/dev/null
  "$TEMP_SMOKE_VENV/bin/devflow" task --help >/dev/null
  rm -rf "$TEMP_SMOKE_VENV"
  echo "✓ Fresh wheel installation and CLI help invocation smoke check succeeded"
fi

echo -e "\n=============================================================================="
echo "🎉 SUCCESS: Dev-Flow is fully validated and ready for release!"
echo "=============================================================================="
