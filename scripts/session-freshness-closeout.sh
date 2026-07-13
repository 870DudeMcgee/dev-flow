#!/usr/bin/env bash
set -euo pipefail

if [[ $# -gt 0 ]]; then
  REPO_ROOT="$1"
else
  REPO_ROOT="$(pwd -P)"
fi

if [[ ! -d "$REPO_ROOT" ]]; then
  echo "[fail] repo root does not exist: $REPO_ROOT" >&2
  exit 2
fi

cd "$REPO_ROOT"

if [[ ! -f "pyproject.toml" || ! -d "src/devflow" ]]; then
  echo "[fail] not a DevFlow repo root: $REPO_ROOT" >&2
  exit 2
fi

PYTHON_BIN="${PYTHON:-}"
if [[ -z "$PYTHON_BIN" ]]; then
  if [[ -x ".venv/bin/python" ]]; then
    PYTHON_BIN=".venv/bin/python"
  else
    PYTHON_BIN="python3"
  fi
fi

RUN_ID="session-closeout-$(date -u +%Y%m%dT%H%M%SZ)"
EVIDENCE_DIR=".devflow/evidence/${RUN_ID}"
mkdir -p "$EVIDENCE_DIR"

echo "== DevFlow session freshness closeout =="
echo "repo: $REPO_ROOT"
echo "evidence: $EVIDENCE_DIR"
echo

STATUS="pass"

record_warn() {
  STATUS="partial"
  echo "[warn] $*"
}

record_fail() {
  STATUS="fail"
  echo "[fail] $*" >&2
}

run_capture() {
  local label="$1"
  local outfile="$2"
  shift 2
  echo "-- $label"
  if "$@" >"$outfile" 2>&1; then
    echo "[ok] $label"
  else
    local code=$?
    record_warn "$label exited $code; see $outfile"
  fi
}

run_capture "git status" "$EVIDENCE_DIR/git-status.txt" git status --short --untracked-files=all
run_capture "git head" "$EVIDENCE_DIR/git-head.txt" git rev-parse HEAD

if [[ -x "$HOME/.hermes/scripts/model-router" ]]; then
  run_capture "model-router status" "$EVIDENCE_DIR/model-router-status.txt" "$HOME/.hermes/scripts/model-router" status
else
  record_warn "model-router script missing at $HOME/.hermes/scripts/model-router"
fi

run_capture "DevFlow CLI help" "$EVIDENCE_DIR/devflow-cli-help.txt" env PYTHONPATH=src:. "$PYTHON_BIN" -m devflow.cli --help
run_capture "V2 loop spine fixture" "$EVIDENCE_DIR/loop-spine-fixture.json" env PYTHONPATH=src:. "$PYTHON_BIN" -m devflow.cli loop spine-fixture --json

if env PYTHONPATH=src:. "$PYTHON_BIN" - <<PY >"$EVIDENCE_DIR/context-quality-orientation.json" 2>&1
import json
from devflow.context_quality import ContextQualityService

packet = ContextQualityService().orient(
    "verify local orientation freshness for session closeout",
    repo="$REPO_ROOT",
)
print(json.dumps(packet, indent=2, sort_keys=True))
if packet["status"] != "grounded":
    raise SystemExit(f"orientation is not grounded: {packet}")
PY
then
  echo "[ok] ContextQualityService orientation"
else
  record_fail "ContextQualityService orientation failed; see $EVIDENCE_DIR/context-quality-orientation.json"
fi

cat >"$EVIDENCE_DIR/summary.json" <<JSON
{
  "schema_version": 1,
  "run_id": "$RUN_ID",
  "repo_root": "$REPO_ROOT",
  "status": "$STATUS",
  "evidence_dir": "$EVIDENCE_DIR",
  "notes": [
    "ContextQualityService provides deterministic local orientation.",
    "Closeout does not start an agent or local model lane for orientation."
  ]
}
JSON

echo
echo "summary: $EVIDENCE_DIR/summary.json"
echo "status: $STATUS"

if [[ "$STATUS" == "fail" ]]; then
  exit 1
fi
exit 0
