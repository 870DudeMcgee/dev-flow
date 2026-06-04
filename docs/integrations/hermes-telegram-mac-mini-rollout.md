# Hermes Telegram Mac Mini Local Model Rollout

Status: active setup goal

This rollout turns Hermes and Telegram into a safe operator surface for DevFlow local-model work across Josh's Mac mini and Mac Studio.

DevFlow remains the source of truth for task state, worker evidence, verification, and promotion. Hermes is an external operator gateway over supervisor-safe DevFlow commands. Local models produce evidence, not truth.

## Objective

Set up Hermes/Telegram so Josh can use the Mac mini M1 for lightweight local model work while keeping heavy local reasoning and implementation profiles on the Mac Studio.

## Success Criteria

- Hermes can route Telegram text through `devflow supervisor route-message "<raw text>" --json`.
- Hermes can auto-run only supervisor-safe read-only commands.
- Hermes can inspect local model profiles with `devflow agent list --json`, `devflow agent show <profile-id> --json`, and `devflow agent policy --json`.
- Hermes can preview local worker-pool runs with `devflow agent run --task <task-id> --profile <profile-id> --dry-run --json`.
- Real local-model worker-pool runs require explicit human approval and write only WorkerEvidence under `.devflow/tasks/<task-id>/local-model-runs/<run-id>/`.
- Mac mini model availability is verified with `ollama show` manifests before a profile is trusted.
- Mac Studio heavy profiles remain assigned to `mac_studio` unless real evidence supports moving them.
- No Hermes path hardcodes Mac Studio checkout folders as portable authority.

## Machine Roles

Mac mini small-worker class:

- `gemma4:latest`: fast Telegram/default chat, summary, status brief, docs review.
- `qwen2.5-coder:7b-instruct`: small code review, syntax fixes, small test help.
- `qwen2.5-coder:1.5b`: classifier/router utility and short extraction.

Either/configurable class:

- `qwen2.5-coder:14b`: medium planning and test help if Mac mini performance is acceptable.

Mac Studio heavy-worker class:

- `qwopus:latest`: deep reasoning, architecture review, task decomposition, patch proposal path.
- `qwen3.6:latest`: local supervisor/planner if distinct from Qwopus after manifest review.
- `qwen2.5-coder:32b-instruct`: heavy local coding specialist.
- `gemma4:31b`: dense judge/reviewer.

## Setup Sequence

Run commands from `<repo-root>` unless noted otherwise.

Do not use the quarantined old checkout path `/Users/jewelbait/Desktop/DevFlow` for current work.

### 1. Sync And Inspect

```bash
git status --short --branch
git pull --ff-only origin main
PYTHONPATH=src .venv/bin/python -m devflow.cli doctor
PYTHONPATH=src .venv/bin/python -m devflow.cli supervisor policy --json
PYTHONPATH=src .venv/bin/python -m devflow.cli agent policy --json
```

Expected result: clean checkout, readable supervisor policy, readable agent policy.

### 2. Install And Verify Mac Mini Models

```bash
ollama pull gemma4:latest
ollama pull qwen2.5-coder:7b-instruct
ollama pull qwen2.5-coder:1.5b
ollama pull qwen2.5-coder:14b
```

Capture manifests:

```bash
mkdir -p .devflow/local-models/manifests
ollama show gemma4:latest > .devflow/local-models/manifests/gemma4-latest.txt
ollama show qwen2.5-coder:7b-instruct > .devflow/local-models/manifests/qwen2-5-coder-7b-instruct.txt
ollama show qwen2.5-coder:1.5b > .devflow/local-models/manifests/qwen2-5-coder-1-5b.txt
ollama show qwen2.5-coder:14b > .devflow/local-models/manifests/qwen2-5-coder-14b.txt
```

Expected result: each `ollama show` succeeds. If any model is missing, do not use the matching profile from Hermes yet.

### 3. Verify Endpoint Boundary

Use Ollama's local OpenAI-compatible endpoint for worker-pool runs:

```bash
curl http://127.0.0.1:11434/api/tags
```

For explicit DevFlow worker-pool runs, prefer:

```bash
--base-url http://127.0.0.1:11434/v1
```

The worker-pool command uses the selected profile's model ID. Do not set a remote provider URL for Mac mini local profiles.

### 4. Verify Hermes Read-Only Operator Commands

```bash
PYTHONPATH=src .venv/bin/python -m devflow.cli supervisor route-message "status please" --json
PYTHONPATH=src .venv/bin/python -m devflow.cli supervisor route-message "run devflow agent list --json" --json
PYTHONPATH=src .venv/bin/python -m devflow.cli supervisor route-message "run devflow agent policy --json" --json
PYTHONPATH=src .venv/bin/python -m devflow.cli supervisor route-message "run devflow agent run --task task-0001 --profile local-gemma4-summarizer --dry-run --json" --json
```

Expected result: read-only commands return `operator_plan.next_step: run_recommended_command`; real worker runs, task creation, verification, patch application, promotion, merge, and push return approval-required plans.

### 5. First Worker-Pool Smoke

Create a low-risk task:

```bash
PYTHONPATH=src .venv/bin/python -m devflow.cli task create "Hermes Mac mini local model smoke"
```

Preview:

```bash
PYTHONPATH=src .venv/bin/python -m devflow.cli agent run --task <task-id> --profile local-gemma4-summarizer --dry-run --json
```

After explicit approval, run:

```bash
PYTHONPATH=src .venv/bin/python -m devflow.cli agent run --task <task-id> --profile local-gemma4-summarizer --base-url http://127.0.0.1:11434/v1 --json
```

Expected result: DevFlow writes WorkerEvidence only under `.devflow/tasks/<task-id>/local-model-runs/<run-id>/`. It must not edit source, write `proposal.patch`, apply patches, verify, commit, merge, push, or promote.

### 6. Telegram/Hermes Rollout

Configure the dedicated Hermes DevFlow profile with:

- command prefix: `PYTHONPATH=src .venv/bin/python -m devflow.cli`
- working directory: `<repo-root>`
- read-only default
- allowlist from `docs/integrations/hermes-command-allowlist.md`
- routing through `devflow supervisor route-message "<raw Telegram text>" --json`
- exact approval prompt from `operator_plan.approval_prompt_hint`
- one-shot execution for `operator_plan.pending_action`

Telegram replies should preserve the routing footer:

```text
route: <route>
model: <model-or-none>
action: <action>
```

## Stop Conditions

- `git status --short --branch` is dirty before a worker run.
- The selected profile's `required_verification_command` fails.
- `devflow supervisor classify <command> --json` does not match the command's expected safety class.
- Hermes proposes a mutation command that did not come from `operator_plan.pending_action`.
- The local model endpoint is unreachable.
- WorkerEvidence is missing or includes claims that the model edited files, verified, committed, merged, pushed, or promoted.

## Next Safe Action

Run the Mac mini model manifest capture, then perform one dry-run preview with `local-gemma4-summarizer` before enabling Telegram-triggered read-only auto-runs.
