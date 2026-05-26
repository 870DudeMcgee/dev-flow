# Local Worker Setup Guide (Mac Mini M1 16GB - mini Profile)

Date: 2026-05-26
Status: ACTIVE
Scope: Local model worker environment mapping to the `mini` profile on a Mac Mini M1 (16GB RAM)

---

## 1. Optimal Profile Selection

Because this machine is a **Mac Mini M1 with 16 GB unified memory**, the resource balance between operating systems, IDE orchestrators, and local model workers is highly constrained. 

`devflow`'s auto-detection logic (`scripts/local_agent_runner.py`) handles memory profiles as follows:
* **System memory > 8 GB and <= 32 GB**: Maps to the **`mini`** profile.
* **Assigned Model**: `qwen2.5-coder:7b-instruct` (approx. 4.7 GB GGUF model).
* **RAM footprint**: Approximately 5.5 GB in-memory during active generation, leaving ~10 GB free for macOS system operations and the Google Antigravity Cloud orchestrator context.

---

## 2. Ollama Configuration & Performance Checklist

To ensure stable, high-performance inner-loop operations:

### A. Download the Core Model (Required)
If you have not already, pull the designated 7B model:
```bash
ollama pull qwen2.5-coder:7b-instruct
```

### B. Optimal Temperature Settings
For software development tasks (code generation, refactoring, formatting), configure local requests with:
* **Temperature**: `0.0` to `0.2` (for highly deterministic, structurally valid patches).
* **System Prompts**: Standard role instructions mapping to `coder`, `tester`, or `reviewer`.

### C. Ollama Keep-Alive Optimization
To avoid latency overhead from cold-booting models on consecutive `devflow` task runs, set the Ollama keep-alive duration to keep the model resident in memory:
```bash
# Keep model loaded for 30 minutes in macOS launchd/shell environment
export OLLAMA_NUM_PARALLEL=1
```

---

## 3. Preflight Health Verification

Always run this quick diagnostic sequence before claiming or running any tasks:

```bash
# 1. Probe Ollama Version
curl -sS http://127.0.0.1:11434/api/version

# 2. Verify model availability and tags
curl -sS http://127.0.0.1:11434/api/tags

# 3. Test local runner generation with the mini profile
PYTHONPATH=src .venv/bin/python scripts/local_agent_runner.py --profile mini "Write a python sum function"
```

Expected output:
* API responses are well-formed JSON.
* Active generation prints the selected model `qwen2.5-coder:7b-instruct` to stderr and the output code block to stdout.
