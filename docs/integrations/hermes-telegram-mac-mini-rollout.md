# Hermes Telegram Mac Mini Local Model Rollout

Status: active setup goal

This rollout turns Hermes and Telegram into a safe operator surface for DevFlow local-model work across Josh's Mac mini and Mac Studio.

DevFlow remains the source of truth for task state, worker evidence, verification, and promotion. Hermes is an external operator gateway over supervisor-safe DevFlow commands. Local models produce evidence, not truth.

## Objective

Set up Hermes/Telegram so Josh can use the Mac mini M1 for lightweight local model work through the local Hermes Qwen endpoint while keeping heavy local reasoning and implementation profiles on machines that can safely run them.

## Success Criteria

- Hermes can route Telegram text through `devflow supervisor route-message "<raw text>" --json`.
- Hermes can auto-run only supervisor-safe read-only commands.
- Hermes can inspect local model profiles and discovered local endpoints with `devflow agent catalog --json`, `devflow agent list --json`, `devflow agent show <profile-id> --json`, and `devflow agent policy --json`.
- Hermes can preview local worker-pool runs with `devflow agent run --task <task-id> --profile <profile-id> --dry-run --json`.
- Real local-model worker-pool runs require explicit human approval and write only WorkerEvidence under `.devflow/tasks/<task-id>/local-model-runs/<run-id>/`.
- Mac mini model availability is verified from the active Hermes config and local `/v1/models` response before a profile is trusted.
- DevFlow classifies current machine RAM and marks discovered models as preferred, allowed, or not recommended.
- DevFlow exposes `qwen35-9b-mtp` on provider `custom:qwen35-mtp` as the preferred Mac mini local default when ready.
- DevFlow enforces one local model run at a time across all local providers/models.
- Mac Studio heavy profiles remain assigned to `mac_studio` unless real evidence supports moving them.
- No Hermes path hardcodes Mac Studio checkout folders as portable authority.

## Machine Roles

Mac mini small-worker class:

- `qwen35-9b-mtp` via Hermes provider `custom:qwen35-mtp`: default local chat, Brainstorm, short planning, status brief, summary, docs review.
- `qwen2.5-coder:7b-instruct`: small code review, syntax fixes, small test help.
- `qwen2.5-coder:1.5b`: classifier/router utility and short extraction.

Either/configurable class:

- `qwen2.5-coder:14b`: medium planning and test help if Mac mini performance is acceptable.
- `gemma4:latest`: legacy/local fallback only when explicitly selected and verified. It is not the default local model.

Mac Studio heavy-worker class:

- `qwopus:latest`: deep reasoning, architecture review, task decomposition, patch proposal path.
- `qwen3.6:latest`: local supervisor/planner if distinct from Qwopus after manifest review.
- `qwen2.5-coder:32b-instruct`: heavy local coding specialist.
- `gemma4-review:latest`: dense judge/reviewer alias for `gemma4:31b` that should preserve the operator's large local context window on capable machines (for example `num_ctx 262144`).

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

### 2. Discover And Verify Mac Mini Hermes/Qwen

```bash
PYTHONPATH=src .venv/bin/python -m devflow.cli agent catalog --json
curl http://127.0.0.1:8080/v1/models
```

Expected result:

- `local_model_policy.default_model` is `qwen35-9b-mtp`.
- `local_model_policy.default_provider_id` points at the discovered Hermes Qwen provider.
- `local_model_policy.machine.total_memory_gb` reflects the current Mac.
- `local_model_policy.local_model_concurrency.mode` is `single_flight`.
- `/v1/models` advertises `qwen35-9b-mtp`.

If the endpoint is not ready, do not fall back to a copied Mac Studio local model config. Fix Hermes/Qwen or use a remote advisory model until DevFlow marks a local model ready.

### 3. Verify Endpoint Boundary

Use the Hermes/llama.cpp local OpenAI-compatible endpoint for Qwen:

```bash
curl http://127.0.0.1:8080/v1/models
```

For explicit DevFlow local OpenAI-compatible profiles, prefer the discovered base URL from `devflow agent catalog --json`, typically:

```bash
--base-url http://127.0.0.1:8080/v1
```

The worker-pool or advisory command uses the selected profile's model ID. Do not set a remote provider URL for Mac mini local profiles.

### 4. Verify Hermes Read-Only Operator Commands

```bash
PYTHONPATH=src .venv/bin/python -m devflow.cli supervisor route-message "status please" --json
PYTHONPATH=src .venv/bin/python -m devflow.cli supervisor route-message "run devflow agent list --json" --json
PYTHONPATH=src .venv/bin/python -m devflow.cli supervisor route-message "run devflow agent catalog --json" --json
PYTHONPATH=src .venv/bin/python -m devflow.cli supervisor route-message "run devflow agent policy --json" --json
```

Expected result: read-only commands return `operator_plan.next_step: run_recommended_command`; real worker runs, task creation, verification, patch application, promotion, merge, and push return approval-required plans.

### 5. First Local Qwen Smoke

If the catalog offers registration actions for `qwen35-mtp`, approve and run the exact `devflow agent add-provider ...` and `devflow agent add-model ...` commands shown by the catalog. Then run a bounded advisory or Brainstorm smoke against profile `local-qwen35-mtp`.

For task-local worker-pool smoke, create a low-risk task:

```bash
PYTHONPATH=src .venv/bin/python -m devflow.cli task create "Hermes Mac mini local model smoke"
```

Preview:

```bash
PYTHONPATH=src .venv/bin/python -m devflow.cli agent run --task <task-id> --profile local-qwen35-mtp --dry-run --json
```

After explicit approval, run:

```bash
PYTHONPATH=src .venv/bin/python -m devflow.cli agent run --task <task-id> --profile local-qwen35-mtp --base-url http://127.0.0.1:8080/v1 --json
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
- Another local model is already running on the machine.
- DevFlow marks the selected model as `not_recommended` for the current machine RAM class.
- WorkerEvidence is missing or includes claims that the model edited files, verified, committed, merged, pushed, or promoted.

## Next Safe Action

Run `devflow agent catalog --json`, confirm `qwen35-9b-mtp` is the ready default with `single_flight` local concurrency, then perform one dry-run preview with `local-qwen35-mtp` before enabling Telegram-triggered read-only auto-runs.
