# Token Savings Workspace Template

This directory provides a reusable template for documenting token savings and local model execution statistics for DevFlow tasks.

## Purpose

When running local models (e.g., via Ollama, Qwen, Gemma) through DevFlow's local workers instead of using frontier API calls, we avoid commercial API token charges. Documenting these runs helps prove the effectiveness of the local dogfooding loop and tracks estimated cost savings.

## Files Included

1. **`token-savings-summary.md`**: Definitive markdown template containing the headings and placeholders for token metrics.
2. **`extract-token-stats.sh`**: Helper shell script that acts as a placeholder for future automated telemetry parsing.

## Usage Instructions

To use this template for a new task:

1. **Copy the directory**:
   Copy this `token-savings` folder into your active task's workspace:
   ```bash
   cp -r docs/examples/token-savings .devflow/workspaces/<task_id>/local-workers/
   ```

2. **Verify Interfaces**:
   Run the extractor script with the dry-run flag:
   ```bash
   chmod +x extract-token-stats.sh
   ./extract-token-stats.sh --dry-run
   ```

3. **Manual Validation & Populate**:
   Review `token-savings-summary.md` and populate the placeholders manually with actual run data (input/output tokens and estimated savings) gathered from the local worker execution logs or the `run.json` metadata.
