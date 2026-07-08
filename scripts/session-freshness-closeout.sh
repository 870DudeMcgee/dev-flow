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

if [[ -f "CODE_MAP.md" ]]; then
  run_capture "devflow map check" "$EVIDENCE_DIR/map-check.txt" env PYTHONPATH=src:. "$PYTHON_BIN" -m devflow.cli map check
else
  record_warn "CODE_MAP.md is missing; map check skipped"
fi

if [[ -x "$HOME/.hermes/scripts/model-router" ]]; then
  run_capture "model-router status" "$EVIDENCE_DIR/model-router-status.txt" "$HOME/.hermes/scripts/model-router" status
else
  record_warn "model-router script missing at $HOME/.hermes/scripts/model-router"
fi

run_capture "local-ai snapshot" "$EVIDENCE_DIR/local-ai-snapshot.json" env PYTHONPATH=src:. "$PYTHON_BIN" -m devflow.cli local-ai snapshot --json

if env PYTHONPATH=src:. "$PYTHON_BIN" - <<'PY' >"$EVIDENCE_DIR/context-quality-import.txt" 2>&1
try:
    from devflow.context_quality import ContextQualityService  # noqa: F401
    print("devflow.context_quality.ContextQualityService")
except Exception:
    from devflow.control_room.context_quality import ContextQualityService  # noqa: F401
    print("devflow.control_room.context_quality.ContextQualityService")
PY
then
  echo "[ok] ContextQualityService import"
else
  record_warn "ContextQualityService is not wired in this checkout; using devflow agent loop as orientation fallback"
fi

if env PYTHONPATH=src:. "$PYTHON_BIN" -m devflow.cli agent loop \
  --task "$RUN_ID" \
  --skill local-fleet-efficiency \
  --file-to-touch src/devflow/control_room/local_model_server.py \
  --manual-read-count 0 \
  --json >"$EVIDENCE_DIR/agent-loop-orientation.json" 2>"$EVIDENCE_DIR/agent-loop-orientation.err"; then
  if env PYTHONPATH=src:. "$PYTHON_BIN" - <<PY
import json
from pathlib import Path
path = Path("$EVIDENCE_DIR/agent-loop-orientation.json")
data = json.loads(path.read_text())
stage = data.get("stage")
allowed = data.get("allowed_to_edit")
if stage != "scout_complete" or allowed is not True:
    raise SystemExit(f"unexpected agent loop state: stage={stage!r}, allowed_to_edit={allowed!r}")
print(f"agent loop fallback grounded: stage={stage}, allowed_to_edit={allowed}")
PY
  then
    echo "[ok] agent loop orientation fallback"
  else
    record_warn "agent loop orientation returned unexpected state; see $EVIDENCE_DIR/agent-loop-orientation.json"
  fi
else
  record_fail "agent loop orientation failed; see $EVIDENCE_DIR/agent-loop-orientation.err"
fi

cat >"$EVIDENCE_DIR/summary.json" <<JSON
{
  "schema_version": 1,
  "run_id": "$RUN_ID",
  "repo_root": "$REPO_ROOT",
  "status": "$STATUS",
  "evidence_dir": "$EVIDENCE_DIR",
  "notes": [
    "ContextQualityService is attempted first when present.",
    "This checkout currently uses devflow agent loop as the closeout orientation fallback."
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
