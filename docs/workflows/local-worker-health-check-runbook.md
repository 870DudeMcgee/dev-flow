# Local Worker Health Check Runbook

Date: 2026-05-26
Status: ACTIVE

## Purpose

Provide one repeatable preflight sequence for local model workers before any orchestrator starts a `devflow` task run.

Model selection is profile-based:
- `studio` -> `qwen2.5-coder:32b-instruct`
- `mini` -> `qwen2.5-coder:14b`
- `mini-fast` -> `qwen2.5-coder:7b-instruct`
- `baseline` -> `qwen2.5-coder:1.5b`

For this Mac mini M1 with 16 GB RAM, the expected auto-detected profile is `mini`.

## Scope

- Orchestrators: Codex Desktop, VS Code/Copilot, Antigravity
- Worker endpoint: `http://127.0.0.1:11434`
- Preferred Mac mini M1 16 GB coding worker: `qwen2.5-coder:14b`
- Fast fallback worker: `qwen2.5-coder:7b-instruct`
- Minimum baseline worker: `qwen2.5-coder:1.5b`

## Fast Preflight (Required)

From repo root:

```bash
bash scripts/local_models_doctor.sh
curl -sS http://127.0.0.1:11434/api/version
curl -sS http://127.0.0.1:11434/api/tags
```

If you override to another profile, pull the corresponding model for that profile.

Expected:
- API version request returns JSON.
- API tags request lists at least one model.

## Generation Probe (Required)

```bash
python3 scripts/local_agent_runner.py "Return only: LOCAL_WORKER_OK"
```

Expected:
- output includes `LOCAL_WORKER_OK`
- command returns zero exit status

## Task-Role Probe (Recommended)

```bash
python3 scripts/local_agent_runner.py "You are a coder. Write a unified diff that changes one line from hello to hello world."
python3 scripts/local_agent_runner.py "You are a reviewer. List two risks in this patch: diff --git a/a.txt b/a.txt"
python3 scripts/local_agent_runner.py "You are a tester. Propose one Python unittest for a sum(a, b) helper."
```

Expected:
- responses are role-appropriate and deterministic enough for bounded worker jobs

## Failure Handling

If preflight fails:
1. verify Ollama app/process is running
2. rerun doctor script
3. verify model availability with `ollama list`
4. pull the preferred coding worker if missing:

```bash
ollama pull qwen2.5-coder:14b
```

5. if the preferred worker causes memory pressure, pull and select the faster fallback:

```bash
ollama pull qwen2.5-coder:7b-instruct
LOCAL_AI_PROFILE=mini-fast python3 scripts/local_agent_runner.py "Return only: LOCAL_WORKER_OK"
```

6. if still unstable, run task in manual mode:
   - orchestrator writes unified diff without local worker calls

Checkpoint branch edge case observed during proving:
- if apply immediately follows preview and both calls occur in the same second, a timestamp-based checkpoint branch name may collide
- recovery: rerun `devflow run <task> --yes` from a clean worktree; the next timestamp resolves the collision

## Logging Convention

For each task run, add worker preflight notes in section 4 (Required Context) of the task file:

- endpoint reachable: yes/no
- preferred model available: yes/no
- fallback model used: yes/no
- probe result: pass/fail
- manual mode used: yes/no

## Integration Rule

This runbook does not change MVP execution semantics:

- `devflow run` stays model-agnostic
- local workers produce artifacts for orchestrators
- orchestrators commit artifacts to task markdown and run `devflow` safety gates
