# DevFlow Local Model Runtime Boundary

This document outlines the architectural boundaries and best practices for integrating local large language models (LLMs) with the DevFlow engineering control room.

## Architectural Boundaries

DevFlow is designed around a local-first engineering philosophy where the execution engine is strictly separated from LLM reasoning runtimes.

1. **Weight Isolation**: Do NOT load model weights (such as 27B or 35B parameter models) directly inside the DevFlow Python application process space. Doing so introduces massive resource overhead, memory leak risks, and tight coupling between coding assistance and runtime execution.
2. **Runtime Boundary**: DevFlow interacts with local models exclusively over a stable, local network socket using an OpenAI-compatible HTTP interface. 
3. **No `transformers.pipeline`**: Avoid using libraries like `transformers` or `torch` in DevFlow code. GGUF runtimes hosted on optimized external servers provide superior performance, VRAM management, and concurrency.
4. **Hugging Face and GGUF**: Hugging Face is used solely for hosting, version control, and downloading model weights. GGUF format combined with `llama.cpp` (or similar runners) is the preferred runtime path.
5. **Qwopus is Replaceable**: Qwopus is a powerful local model option served behind the OpenAI-compatible API boundary. It is not hardcoded as a core concept of DevFlow; operators can seamlessly swap it for other coding models by changing environment variables.

---

## Local Setup Examples

### 1. Host with `llama.cpp` (Preferred)

Ensure `llama.cpp` is installed on your machine:
```bash
brew install llama.cpp
```

Start the model server using the standard GGUF weights:
```bash
llama-server -hf Jackrong/Qwopus3.6-35B-A3B-v1-GGUF:Q4_K_M
```

Configure your environment variables:
```bash
export LOCAL_MODEL_BASE_URL='http://127.0.0.1:8080/v1'
export LOCAL_MODEL_ID='Jackrong/Qwopus3.6-35B-A3B-v1-GGUF:Q4_K_M'
```

Run the standard smoke test to verify connectivity:
```bash
python scripts/local_model_smoke.py
```

### 2. Alternative Local Runtimes (Ollama, LM Studio, vLLM)

If Qwopus (or another coding model) is served through Ollama, LM Studio, vLLM, or another OpenAI-compatible local server, only `LOCAL_MODEL_BASE_URL` and `LOCAL_MODEL_ID` need to change. 

For example, when using Ollama:
```bash
export LOCAL_MODEL_BASE_URL='http://127.0.0.1:11434/v1'
export LOCAL_MODEL_ID='qwopus'
python scripts/local_model_smoke.py
```

---

## Bounded Packet Review Command

To generate visible local-model proposal evidence without executing workers, loading model weights, or mutatively modifying task and workspace files:

1. Start your local OpenAI-compatible endpoint server (e.g. `llama-server`, Ollama, LM Studio, or vLLM).
2. Export your environment variables:
   ```bash
   export LOCAL_MODEL_BASE_URL='http://127.0.0.1:8080/v1'
   export LOCAL_MODEL_ID='Jackrong/Qwopus3.6-35B-A3B-v1-GGUF:Q4_K_M'
   ```
3. (Optional) Run the text packet preview to inspect the bounded context that will be provided to the model:
   ```bash
   devflow task packet task-0001 --text
   ```
4. Execute the packet review command:
   ```bash
   devflow task local-review task-0001
   ```
   You can also override environment defaults directly via CLI options:
   ```bash
   devflow task local-review task-0001 --base-url 'http://127.0.0.1:8080/v1' --model 'Jackrong/Qwopus3.6-35B-A3B-v1-GGUF:Q4_K_M'
   ```
5. Review the assistant's structured advisory proposal evidence in the generated folder:
   ```bash
   cat .devflow/tasks/task-0001/local-model-runs/<run-id>/response.md
   ```
6. Explicitly choose your next DevFlow action.

### Replaceability & Safety
- **Qwopus is Replaceable**: The `Jackrong/Qwopus3.6-35B-A3B-v1-GGUF:Q4_K_M` model is featured here as a canonical example. However, any compatible local OpenAI completion server and model will function seamlessly.
- **Direct Weight Loading**: DevFlow does not load model weights inside the DevFlow execution runtime process space.
- **Advisory/Proposal-Only**: This command is strictly advisory and proposal-only. It writes evidence inside the task's isolated local runs folder and does not mutate source files, apply patches, run automatic verification, or promote changes.

---

## Registry-Backed Local Worker Pool

The practical worker-pool path uses registry profiles rather than environment-only model selection:

```bash
PYTHONPATH=src .venv/bin/python -m devflow.cli agent list --json
PYTHONPATH=src .venv/bin/python -m devflow.cli agent show local-qwopus-inspector --json
PYTHONPATH=src .venv/bin/python -m devflow.cli agent policy --json
PYTHONPATH=src .venv/bin/python -m devflow.cli agent run --task <task-id> --profile local-qwopus-inspector --dry-run --json
PYTHONPATH=src .venv/bin/python -m devflow.cli agent run --task <task-id> --profile local-qwopus-inspector --json
```

Worker-pool profiles include model allocation metadata for Josh's heterogeneous local fleet:

- `mac_mini`: small utility/control-loop workers such as `gemma4:latest`, `qwen2.5-coder:7b-instruct`, and `qwen2.5-coder:1.5b`.
- `either`: configurable medium workers such as `qwen2.5-coder:14b`.
- `mac_studio`: heavy local reasoning, implementation, and review workers such as `qwopus:latest`, `qwen3.6:latest`, `qwen2.5-coder:32b-instruct`, and `gemma4-review:latest` (a tuned `gemma4:31b` review alias that should preserve the operator's large local context window, e.g. `num_ctx 262144` on capable machines).

Model names are starter assumptions, not proof. Prefer actual manifests:

```bash
mkdir -p .devflow/local-models/manifests
ollama show <model> > .devflow/local-models/manifests/<safe-model-name>.txt
```

If two tags report the same Ollama ID, Dev-Flow should treat them as aliases or duplicate tags until `ollama show` proves meaningful differences.

Worker-pool runs write generalized WorkerEvidence under `.devflow/tasks/<task-id>/local-model-runs/<run-id>/` and do not write `proposal.patch`, edit source files, apply patches, verify, commit, merge, push, or promote.

---

## Future Design & Extension Roadmap

The following architectural concepts are designed for future milestones and should not be implemented in the core runtime yet:

### 1. Skills as Artifact Transformations
Transforming goal definitions, grill files, or user requests into shippable vertical task slices using declarative transformations rather than ad-hoc scripts.

### 2. Deterministic Lifecycle Hooks
Supporting strict, local lifecycle events (`pre-scaffold`, `post-scaffold`, `pre-verify`, `post-promote`) to allow user-defined scripts or automated triggers to hook into goal progression.

### 3. AFK vs HITL Classification
Classifying task slices into AFK (Away From Keyboard - completely autonomous execution) vs HITL (Human In The Loop - requiring checkpoint validation or interactive approval) based on calculated risk profiles.

### 4. Dependency DAG
Introducing a Directed Acyclic Graph (DAG) for tasks to model multi-stage plans where tasks declare explicit `blocks` or `blocked_by` relationships.

### 5. Future `local_model_adapter`
A robust local model adapter mapping diverse API flavors and local configuration parameters under a unified interface inside `src/devflow/control_room/`.

### 6. Token/Context Waste Metrics
Adding instrumentation to track context budget efficiency, context window usage, and identify context-poisoning/token waste during worker runs.

### 7. Fine-tuning/Evaluation Data Capture
Automating the capture of high-quality execution trajectories (successful patches, manual overrides, verification logs) to feed back into local model fine-tuning pipelines.
