# MLX All-Model Smoke Test Run Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Prove which downloaded local MLX/HF models can load, run a one-iteration LoRA/QLoRA smoke when appropriate, reload the written adapter, and produce a cautious trainability matrix without deleting, publishing, or overclaiming.

**Architecture:** Use the existing `devflow training mlx` command lane as the evidence writer. A single executor runs MLX commands serially to avoid overlapping Metal memory. Read-only scouts and reviewers inspect cache state, logs, adapter files, matrix rows, and stale claims around the serial execution lane.

**Tech Stack:** Dev-Flow CLI, `mlx-lm[train]` through `uvx`, optional `mlx-vlm` direct load smoke for VLM-only rows, Hugging Face local cache, `.devflow/training/<run-id>/` evidence.

---

## Subagent Execution

- Coordinator: main thread owns the run queue, stop/go decisions, and final acceptance.
- Read-only scouts: `gpt-5.4-mini`, medium thinking.
  - Scout A: inventory downloaded HF/MLX model IDs and build the exact manifest.
  - Scout B: resource preflight and contention check.
  - Scout C: evidence projection and stale-claim review.
- Execution worker: one worker at a time only. Preferred model is `gpt-5.3-codex-spark`; if quota-blocked, use `gpt-5.4` medium and say so before starting. No parallel MLX execution.
- Reviewer scouts: `gpt-5.4-mini`, medium thinking.
  - Reviewer A: command safety and no-publish/no-delete check.
  - Reviewer B: evidence completeness and adapter-file check.
  - Reviewer C: matrix wording and missing/failed rows check.

## Files And Evidence

No source-code changes are required for the standard MLX-LM run.

Generated evidence:

- `.devflow/training/mlx-local-trainability-20260702/data/train.jsonl`
- `.devflow/training/mlx-local-trainability-20260702/models/<slug>/load-smoke.json`
- `.devflow/training/mlx-local-trainability-20260702/models/<slug>/load-smoke.log`
- `.devflow/training/mlx-local-trainability-20260702/models/<slug>/lora-smoke.json`
- `.devflow/training/mlx-local-trainability-20260702/models/<slug>/lora-smoke.log`
- `.devflow/training/mlx-local-trainability-20260702/models/<slug>/adapters/`
- `.devflow/training/mlx-local-trainability-20260702/models/<slug>/adapter-reload.log`
- `.devflow/training/mlx-local-trainability-20260702/trainability-matrix.json`
- `.devflow/training/mlx-local-trainability-20260702/result.md`
- `.devflow/training/mlx-local-trainability-20260702/downloaded-models.json`

Tracked files should not change during the run. `.devflow/training/` stays ignored generated evidence.

## Stop Criteria

Stop the run immediately when any of these occurs:

- `df -g .` reports less than 50 GB free.
- Another heavy MLX/Metal model process is active and cannot be safely stopped by the operator.
- A smoke reports Metal allocation failure, OOM, or process timeout.
- LoRA log shows NaN, exploding loss, or tokenizer/template mismatch.
- LoRA exits 0 but no `adapters.safetensors` exists.
- The prepared dataset redaction status is not `pass`.
- A command includes upload, publish, delete, push, `mlx_lm.fuse --upload-repo`, or Hugging Face write flags.

## Task 1: Preflight And Lock

**Files:**
- Generated: `.devflow/training/mlx-local-trainability-20260702/preflight.md`

- [ ] **Step 1: Set run variables**

Run:

```bash
RUN_ID=mlx-local-trainability-20260702
RUN_DIR=.devflow/training/$RUN_ID
mkdir -p "$RUN_DIR"
```

Expected: `$RUN_DIR` exists.

- [ ] **Step 2: Check machine and disk**

Run:

```bash
{
  echo "# MLX Preflight"
  echo
  echo "date: $(date -u +%Y-%m-%dT%H:%M:%SZ)"
  echo "arch: $(uname -m)"
  echo "uvx: $(command -v uvx || true)"
  echo
  df -g .
  echo
  pgrep -fl 'mlx_lm|mlx_vlm|ollama|python.*mlx' || true
} | tee "$RUN_DIR/preflight.md"
```

Expected:

- `arch: arm64`
- `uvx` path is non-empty.
- Available disk is at least 50 GB.
- No unexpected heavy MLX process is running.

- [ ] **Step 3: Stop if preflight fails**

Run:

```bash
test "$(uname -m)" = "arm64"
test -n "$(command -v uvx)"
python3 - <<'PY'
import shutil
free_gb = shutil.disk_usage(".").free // (1024 ** 3)
raise SystemExit(0 if free_gb >= 50 else 1)
PY
```

Expected: exit code `0`.

## Task 2: Build Downloaded Model Manifest

**Files:**
- Generated: `.devflow/training/mlx-local-trainability-20260702/downloaded-models.json`

- [ ] **Step 1: Write the manifest from known targets and downloaded cache**

Run:

```bash
RUN_ID=mlx-local-trainability-20260702
RUN_DIR=.devflow/training/$RUN_ID
env PYTHONPATH=src:. .venv/bin/python - <<'PY'
import json
from pathlib import Path

run_dir = Path(".devflow/training/mlx-local-trainability-20260702")
cache = Path.home() / ".cache" / "huggingface" / "hub"

models = [
    {"model": "lmstudio-community/Qwen3.6-27B-MLX-4bit"},
    {"model": "lmstudio-community/Qwen3.6-27B-MLX-8bit"},
    {"model": "mlx-community/Qwen3.6-27B-OptiQ-4bit"},
    {"model": "mlx-community/Qwen3.6-35B-A3B-OptiQ-4bit"},
]

seen = {item["model"].lower() for item in models}
for path in sorted(cache.glob("models--*")):
    # Hugging Face cache directories encode repo IDs as models--owner--repo.
    # Review this derived ID before execution; unusual repo names can be lossy.
    model = path.name.removeprefix("models--").replace("--", "/", 1)
    lowered = model.lower()
    if not any(token in lowered for token in ("qwopus", "gemma-4", "gemma4")):
        continue
    if lowered in seen:
        continue
    item = {"model": model}
    if "gguf" in lowered or lowered.endswith(".gguf"):
        item.update(runtime_family="gguf", training_surface="inference_only", claim_basis="cache_inventory")
    elif "vl" in lowered or "vision" in lowered:
        item.update(input_modalities=["text", "image"], claim_basis="cache_inventory")
    else:
        item.update(runtime_family="mlx_lm", training_surface="mlx_lm_text_trainable", claim_basis="cache_inventory")
    models.append(item)
    seen.add(lowered)

run_dir.mkdir(parents=True, exist_ok=True)
(run_dir / "downloaded-models.json").write_text(json.dumps({"models": models}, indent=2, sort_keys=True) + "\n")
print(run_dir / "downloaded-models.json")
PY
```

Expected: manifest exists and contains known target IDs plus reviewed downloaded cache IDs.

- [ ] **Step 2: Review the manifest before execution**

Run:

```bash
jq -r '.models[] | [.model, (.runtime_family // "mlx_lm"), (.training_surface // "auto")] | @tsv' \
  .devflow/training/mlx-local-trainability-20260702/downloaded-models.json
```

Expected: Qwopus and Gemma 4 rows use reviewed downloaded IDs. GGUF/Ollama rows are not marked trainable.

## Task 3: Prepare MLX-LM Dataset

**Files:**
- Generated: `.devflow/training/mlx-local-trainability-20260702/data/train.jsonl`

- [ ] **Step 1: Prepare dataset**

Run:

```bash
env PYTHONPATH=src:. .venv/bin/python -m devflow.cli training mlx prepare \
  --run-id mlx-local-trainability-20260702 \
  --max-examples 500 \
  --json | tee .devflow/training/mlx-local-trainability-20260702/prepare.json
```

Expected:

- `redaction.status` is `pass`.
- `data/train.jsonl` exists.
- Rows are shaped as `{"text": "..."}`.

- [ ] **Step 2: Verify secret scan result**

Run:

```bash
jq -e '.redaction.status == "pass"' .devflow/training/mlx-local-trainability-20260702/prepare.json
```

Expected: `true`.

## Task 4: Load-Smoke Every Manifest Row

**Files:**
- Generated: each row gets `load-smoke.json` and `load-smoke.log` when supported by `mlx_lm.generate`.

- [ ] **Step 1: Run load smokes serially**

Run:

```bash
jq -r '.models[] | select((.runtime_family // "mlx_lm") == "mlx_lm") | .model' \
  .devflow/training/mlx-local-trainability-20260702/downloaded-models.json |
while IFS= read -r MODEL; do
  echo "== load smoke: $MODEL =="
  env PYTHONPATH=src:. .venv/bin/python -m devflow.cli training mlx load-smoke \
    --model "$MODEL" \
    --run-id mlx-local-trainability-20260702 \
    --timeout-seconds 1800 \
    --json || exit 1
done
```

Expected: small and available text MLX-LM models report `success`. Missing, incompatible, or unavailable rows write failure evidence and stop the loop for review.

- [ ] **Step 2: Review load failures**

Run:

```bash
find .devflow/training/mlx-local-trainability-20260702/models -name load-smoke.json -print0 |
while IFS= read -r -d '' FILE; do
  jq -r 'select(.status != "success") | [.model, .status, (.failure_reason // "no reason")] | @tsv' "$FILE"
done
```

Expected: no output before continuing to LoRA smokes.

## Task 5: LoRA-Smoke Trainable Text Rows

**Files:**
- Generated: `lora-smoke.json`, `lora-smoke.log`, and `adapters/` for each passing trainable row.

- [ ] **Step 1: Run LoRA smokes serially for trainable text rows**

Run:

```bash
jq -r '.models[] | select((.training_surface // "mlx_lm_text_trainable") == "mlx_lm_text_trainable") | .model' \
  .devflow/training/mlx-local-trainability-20260702/downloaded-models.json |
while IFS= read -r MODEL; do
  SLUG=$(env PYTHONPATH=src:. .venv/bin/python -c 'from devflow.control_room.training_mlx_runner import model_slug; import sys; print(model_slug(sys.argv[1]))' "$MODEL")
  LOAD=".devflow/training/mlx-local-trainability-20260702/models/$SLUG/load-smoke.json"
  jq -e '.status == "success"' "$LOAD" >/dev/null || { echo "skip LoRA; load did not pass: $MODEL"; continue; }
  echo "== lora smoke: $MODEL =="
  env PYTHONPATH=src:. .venv/bin/python -m devflow.cli training mlx lora-smoke \
    --model "$MODEL" \
    --run-id mlx-local-trainability-20260702 \
    --iters 1 \
    --timeout-seconds 3600 \
    --json || exit 1
done
```

Expected: each completed row writes adapter files or explicit failure evidence.

- [ ] **Step 2: Verify every successful LoRA has adapter files**

Run:

```bash
find .devflow/training/mlx-local-trainability-20260702/models -name lora-smoke.json -print0 |
while IFS= read -r -d '' FILE; do
  STATUS=$(jq -r '.status' "$FILE")
  MODEL=$(jq -r '.model' "$FILE")
  ADAPTER=$(jq -r '.adapter_path // empty' "$FILE")
  if [ "$STATUS" = "success" ]; then
    test -n "$ADAPTER"
    test -f "$ADAPTER/adapters.safetensors"
    test -f "$ADAPTER/adapter_config.json"
    echo "adapter ok: $MODEL"
  fi
done
```

Expected: every successful LoRA row prints `adapter ok`.

## Task 6: Adapter Reload For Every Successful LoRA

**Files:**
- Generated: `adapter-reload.log` beside each model evidence directory.

- [ ] **Step 1: Run adapter reloads serially**

Run:

```bash
find .devflow/training/mlx-local-trainability-20260702/models -name lora-smoke.json -print0 |
while IFS= read -r -d '' FILE; do
  jq -e '.status == "success"' "$FILE" >/dev/null || continue
  MODEL=$(jq -r '.model' "$FILE")
  ADAPTER=$(jq -r '.adapter_path' "$FILE")
  DIR=$(dirname "$FILE")
  echo "== adapter reload: $MODEL =="
  uvx --python 3.12 --from 'mlx-lm[train]' mlx_lm.generate \
    --model "$MODEL" \
    --adapter-path "$ADAPTER" \
    --prompt "Reply with exactly: mlx adapter ok" \
    --max-tokens 8 \
    | tee "$DIR/adapter-reload.log"
  grep -q "mlx adapter ok" "$DIR/adapter-reload.log"
done
```

Expected: every successful LoRA adapter reload log includes `mlx adapter ok`.

## Task 7: VLM/Gemma 4 Load-Only Review

**Files:**
- Generated: `.devflow/training/mlx-local-trainability-20260702/vlm-load-smoke.md`

- [ ] **Step 1: Identify VLM rows**

Run:

```bash
jq -r '.models[] | select((.input_modalities // ["text"]) | index("image")) | .model' \
  .devflow/training/mlx-local-trainability-20260702/downloaded-models.json \
  | tee .devflow/training/mlx-local-trainability-20260702/vlm-rows.txt
```

Expected: Gemma 4 or other VLM rows appear only if downloaded.

- [ ] **Step 2: Run direct VLM text-only load smoke for VLM rows**

This is a direct documented `mlx-vlm` check, not a `devflow training mlx` command. Keep this load-only evidence separate from the MLX-LM trainability matrix unless a later code slice adds a first-class Dev-Flow VLM command.

Run:

```bash
while IFS= read -r MODEL; do
  test -n "$MODEL" || continue
  echo "== mlx-vlm load smoke: $MODEL =="
  uvx --python 3.12 --from mlx-vlm mlx_vlm.generate \
    --model "$MODEL" \
    --prompt "Reply with exactly: mlx vlm load ok" \
    --max-tokens 8
done < .devflow/training/mlx-local-trainability-20260702/vlm-rows.txt \
  | tee .devflow/training/mlx-local-trainability-20260702/vlm-load-smoke.md
```

Expected: VLM rows are treated as load-smoke-only unless a documented training entrypoint is added in a separate code slice.

## Task 8: Write Final Matrix

**Files:**
- Generated: `.devflow/training/mlx-local-trainability-20260702/trainability-matrix.json`
- Generated: `.devflow/training/mlx-local-trainability-20260702/result.md`

- [ ] **Step 1: Write matrix from manifest and evidence**

Run:

```bash
env PYTHONPATH=src:. .venv/bin/python -m devflow.cli training mlx matrix \
  --run-id mlx-local-trainability-20260702 \
  --models .devflow/training/mlx-local-trainability-20260702/downloaded-models.json \
  --json | tee .devflow/training/mlx-local-trainability-20260702/matrix-command.json
```

Expected:

- Passing rows show `load_smoke: pass`.
- LoRA-tested passing rows show `lora_smoke: pass`.
- VLM-only rows show `lora_smoke: not_applicable`.
- Failed rows include `failure_reason`.
- Untested rows remain `missing`.

- [ ] **Step 2: Inspect the result wording**

Run:

```bash
sed -n '1,160p' .devflow/training/mlx-local-trainability-20260702/result.md
```

Expected: result says smoke evidence does not prove quality, convergence, benchmark quality, or production readiness.

## Task 9: Review And Handoff

**Files:**
- Generated: `.devflow/training/mlx-local-trainability-20260702/review.md`

- [ ] **Step 1: Summarize final evidence**

Run:

```bash
{
  echo "# MLX All-Model Smoke Review"
  echo
  echo "run_id: mlx-local-trainability-20260702"
  echo
  echo "## Matrix Rows"
  jq -r '.rows[] | "- \(.model): load=\(.load_smoke), lora=\(.lora_smoke), exit=\(.exit_code // "missing"), reason=\(.failure_reason // "none")"' \
    .devflow/training/mlx-local-trainability-20260702/trainability-matrix.json
  echo
  echo "## Adapter Files"
  find .devflow/training/mlx-local-trainability-20260702/models -path '*/adapters/adapters.safetensors' -print | sort
  echo
  echo "## Generated Evidence"
  git status --ignored --short .devflow/training graphify-out
} | tee .devflow/training/mlx-local-trainability-20260702/review.md
```

Expected: review file lists every row and confirms generated evidence remains ignored.

- [ ] **Step 2: Reviewer signoff**

Reviewer checks:

- No command deleted local models.
- No command uploaded, published, pushed, or fused adapters.
- Every `success` LoRA row has adapter files.
- Every adapter reload was attempted for successful LoRA rows.
- Matrix rows with no evidence are `missing`, not `pass`.
- VLM/multimodal rows are not presented as trainable unless a documented training command exists and was tested.

## Acceptance Criteria

- Preflight passed with at least 50 GB free.
- Dataset redaction passed.
- Every downloaded MLX-LM text row has load-smoke evidence.
- Every load-passing trainable text row either has LoRA evidence or a recorded stop reason.
- Every successful LoRA has adapter files and adapter reload evidence.
- Matrix and `result.md` are regenerated from evidence.
- Final report does not claim model quality.
- Generated evidence remains ignored and uncommitted unless the operator explicitly asks to version a summary.

## Execution Choice

Recommended execution is subagent-driven:

1. Read-only scouts build and review the manifest/preflight.
2. One execution worker runs MLX commands serially.
3. Reviewer scouts inspect logs, adapter files, matrix rows, and final wording.
