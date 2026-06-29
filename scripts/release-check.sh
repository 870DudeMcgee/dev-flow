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

# 6. CLI Help Smoke Checks & Hiding Gating
echo -e "\n------------------------------------------------------------------------------"
echo "🖥 Running CLI Help Smoke & Experimental Command Hiding Checks"
echo "------------------------------------------------------------------------------"
# Run CLI smoke checks from a fresh install so this gate proves packaging/import
# behavior without PYTHONPATH or the developer's editable environment.
CLI_SMOKE_VENV=$(mktemp -d -t devflow-cli-smoke-XXXXXX)
cleanup_cli_smoke() {
  rm -rf "$CLI_SMOKE_VENV"
}
trap cleanup_cli_smoke EXIT

"${PYTHON_BIN[@]}" -m venv "$CLI_SMOKE_VENV"
env -u PYTHONPATH "$CLI_SMOKE_VENV/bin/python" -m pip install -q "$REPO_ROOT"
RUN_CLI=(env -u PYTHONPATH "$CLI_SMOKE_VENV/bin/devflow")

# Assert basic help command works
"${RUN_CLI[@]}" --help >/dev/null
"${RUN_CLI[@]}" task --help >/dev/null
echo "✓ Basic CLI help commands succeed"

# Assert experimental commands are hidden from standard help
STANDARD_HELP=$("${RUN_CLI[@]}" --help)
STANDARD_TASK_HELP=$("${RUN_CLI[@]}" task --help)

strip_ansi() {
  sed -E $'s/\x1B\\[[0-9;?]*[ -/]*[@-~]//g'
}

help_contains_command() {
  local help_text="$1"
  local cmd="$2"
  local clean_help
  clean_help=$(printf '%s\n' "$help_text" | strip_ansi)
  grep -Eq "(^|[^[:alnum:]_-])${cmd}([^[:alnum:]_-]|$)" <<<"$clean_help"
}

for cmd in "supervise" "context"; do
  if help_contains_command "$STANDARD_HELP" "$cmd"; then
    echo "❌ Error: Experimental command '$cmd' is exposed in standard '--help'." >&2
    exit 1
  fi
done

for cmd in "fit" "scout" "route" "scorecard"; do
  if ! help_contains_command "$STANDARD_TASK_HELP" "$cmd"; then
    echo "❌ Error: Stable task subcommand '$cmd' is NOT shown in standard 'task --help'." >&2
    exit 1
  fi
done

for cmd in "pack"; do
  if help_contains_command "$STANDARD_TASK_HELP" "$cmd"; then
    echo "❌ Error: Experimental task subcommand '$cmd' is exposed in standard 'task --help'." >&2
    exit 1
  fi
done
echo "✓ Stable routing evidence commands are shown and experimental commands are hidden in standard help"

# Assert experimental commands are shown when DEVFLOW_EXPERIMENTAL=1
EXP_HELP=$(DEVFLOW_EXPERIMENTAL=1 "${RUN_CLI[@]}" --help)
EXP_TASK_HELP=$(DEVFLOW_EXPERIMENTAL=1 "${RUN_CLI[@]}" task --help)

for cmd in "supervise" "context"; do
  if ! help_contains_command "$EXP_HELP" "$cmd"; then
    echo "❌ Error: Experimental command '$cmd' is NOT shown under DEVFLOW_EXPERIMENTAL=1." >&2
    exit 1
  fi
done

for cmd in "pack"; do
  if ! help_contains_command "$EXP_TASK_HELP" "$cmd"; then
    echo "❌ Error: Experimental task subcommand '$cmd' is NOT shown under DEVFLOW_EXPERIMENTAL=1." >&2
    exit 1
  fi
done
echo "✓ Experimental commands are successfully exposed under DEVFLOW_EXPERIMENTAL=1"

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
  env -u PYTHONPATH "$TEMP_SMOKE_VENV/bin/devflow" task --help >/dev/null
  rm -rf "$TEMP_SMOKE_VENV"
  echo "✓ Fresh wheel installation and CLI help invocation smoke check succeeded"
fi

echo -e "\n=============================================================================="
echo "🎉 SUCCESS: Dev-Flow is fully validated and ready for release!"
echo "=============================================================================="
