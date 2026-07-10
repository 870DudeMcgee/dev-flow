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
REPO_ROOT=$(pwd -P)
echo "✓ Confirmed repository root"

if [[ -n "${PYTHON:-}" ]]; then
  PYTHON_BIN=("$PYTHON")
elif [[ -x ".venv/bin/python" ]]; then
  PYTHON_BIN=(".venv/bin/python")
else
  PYTHON_BIN=("python3")
fi

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
PYTHONPATH=src:. "${PYTHON_BIN[@]}" -m compileall src  # compileall needs PYTHONPATH since it doesn't read pyproject.toml
echo "✓ All source files compiled successfully"

# 4. Lint Check (ruff)
echo -e "\n------------------------------------------------------------------------------"
echo "🧹 Running Ruff Lint Check"
echo "------------------------------------------------------------------------------"
# Prefer the venv ruff; fall back to module invocation. Ruff config lives in
# pyproject.toml ([tool.ruff]). This gate keeps the static-check target honest:
# 'make lint' clean == release gate clean.
if [[ -f ".venv/bin/ruff" ]]; then
  RUFF_BIN=(".venv/bin/ruff")
elif "${PYTHON_BIN[@]}" -c "import ruff" >/dev/null 2>&1; then
  RUFF_BIN=("${PYTHON_BIN[@]}" "-m" "ruff")
else
  echo "❌ Error: ruff is not installed. Install dev tools with: pip install -e \".[dev]\"" >&2
  exit 1
fi
"${RUFF_BIN[@]}" check .
echo "✓ Ruff lint check passed"

# 5. Pytest Regression Suite
echo -e "\n------------------------------------------------------------------------------"
echo "🧪 Running Pytest Regression Suite"
echo "------------------------------------------------------------------------------"
# Verify pytest plugin requirements for this suite.
if ! PYTHONPATH=src:. "${PYTHON_BIN[@]}" -c "import xdist, pytest_timeout" >/dev/null 2>&1; then
  echo "❌ Error: Required pytest plugins are not installed. Install dev tools with: pip install -e \".[dev]\"" >&2
  exit 1
fi

# Use the local virtual environment pytest if available, fallback to python3 -m pytest.
# Export PYTHONPATH for subprocess CLI tests (`python -m devflow.cli`) that do not read pytest's config.
if [[ -f ".venv/bin/pytest" ]]; then
  PYTHONPATH=src:. .venv/bin/pytest -n auto --timeout=60 --ignore=scratch -m "not ui_browser and not ui_browser_live" -q --tb=short
else
  PYTHONPATH=src:. "${PYTHON_BIN[@]}" -m pytest tests/ -n auto --timeout=60 --ignore=scratch -m "not ui_browser and not ui_browser_live" -q --tb=short
fi
echo "✓ Pytest suite completed successfully"

# 6. V2 CLI and fixture smoke checks
echo -e "\n------------------------------------------------------------------------------"
echo "🖥 Running V2 CLI and deterministic fixture smoke checks"
echo "------------------------------------------------------------------------------"
# Run these checks from a fresh install so this gate proves packaging/import
# behavior without PYTHONPATH or the developer's editable environment.
CLI_SMOKE_VENV=$(mktemp -d -t devflow-cli-smoke-XXXXXX)
cleanup_cli_smoke() {
  rm -rf "$CLI_SMOKE_VENV"
}
trap cleanup_cli_smoke EXIT

"${PYTHON_BIN[@]}" -m venv "$CLI_SMOKE_VENV"
env -u PYTHONPATH "$CLI_SMOKE_VENV/bin/python" -m pip install -q "$REPO_ROOT"
RUN_CLI=(env -u PYTHONPATH "$CLI_SMOKE_VENV/bin/devflow")
CLI_FIXTURE_JSON=$(mktemp -t devflow-cli-fixture-XXXXXX.json)

"${RUN_CLI[@]}" --help >/dev/null
"${RUN_CLI[@]}" status --help >/dev/null
"${RUN_CLI[@]}" loop --help >/dev/null
"${RUN_CLI[@]}" loop spine-fixture --target-file src/devflow/loop/models.py --json > "$CLI_FIXTURE_JSON"
"${CLI_SMOKE_VENV}/bin/python" -c '
import json
import sys

payload = json.load(open(sys.argv[1]))
assert payload["final_stage"] == "complete", payload
' "$CLI_FIXTURE_JSON"
rm -f "$CLI_FIXTURE_JSON"
echo "✓ V2 CLI help and deterministic fixture commands succeed"

# 7. Packaging & Distribution Smoke Check (if tools available)
echo -e "\n------------------------------------------------------------------------------"
echo "📦 Packaging & Smoke Install Gating"
echo "------------------------------------------------------------------------------"

BUILD_PROBE_DIR=$(mktemp -d -t devflow-build-probe-XXXXXX)
if ! (cd "$BUILD_PROBE_DIR" && env -u PYTHONPATH "${PYTHON_BIN[@]}" -m build --version >/dev/null 2>&1); then
  rm -rf "$BUILD_PROBE_DIR"
  echo "[info] python-build is not installed. Skipping distribution compilation check."
  echo "       To test packaging, run: pip install build twine"
else
  rm -rf "$BUILD_PROBE_DIR"
  echo "Building distributions..."
  BUILD_RUN_DIR=$(mktemp -d -t devflow-build-run-XXXXXX)
  (cd "$BUILD_RUN_DIR" && env -u PYTHONPATH "${PYTHON_BIN[@]}" -m build --outdir "$REPO_ROOT/dist" "$REPO_ROOT" >/dev/null)
  rm -rf "$BUILD_RUN_DIR"
  echo "✓ Distribution build succeeded"

  if ! "${PYTHON_BIN[@]}" -c "import twine" >/dev/null 2>&1; then
    echo "[info] twine is not installed. Skipping package metadata verification."
  else
    echo "Checking distributions with twine..."
    env -u PYTHONPATH "${PYTHON_BIN[@]}" -m twine check "$REPO_ROOT"/dist/*
    echo "✓ Package twine check passed"
  fi

  # Smoke install wheel in a temporary virtual environment
  echo "Smoke installing wheel in temporary virtualenv..."
  TEMP_SMOKE_VENV=$(mktemp -d -t devflow-release-smoke-XXXXXX)
  "${PYTHON_BIN[@]}" -m venv "$TEMP_SMOKE_VENV"
  env -u PYTHONPATH "$TEMP_SMOKE_VENV/bin/python" -m pip install -q "$REPO_ROOT"/dist/*.whl
  env -u PYTHONPATH "$TEMP_SMOKE_VENV/bin/devflow" --help >/dev/null
  env -u PYTHONPATH "$TEMP_SMOKE_VENV/bin/devflow" status --help >/dev/null
  env -u PYTHONPATH "$TEMP_SMOKE_VENV/bin/devflow" loop --help >/dev/null
  env -u PYTHONPATH "$TEMP_SMOKE_VENV/bin/devflow" loop spine-fixture --target-file src/devflow/loop/models.py --json >/dev/null
  rm -rf "$TEMP_SMOKE_VENV"
  echo "✓ Fresh wheel installation and CLI help invocation smoke check succeeded"
fi

echo -e "\n=============================================================================="
echo "🎉 SUCCESS: Dev-Flow is fully validated and ready for release!"
echo "=============================================================================="
