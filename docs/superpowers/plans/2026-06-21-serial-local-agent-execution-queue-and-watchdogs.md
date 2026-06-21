# Serial Local-Agent Execution Queue and Watchdogs Plan

Date: 2026-06-21
Status: ready for implementation handoff
Scope: implementation plan only; no code changes in this document.

> **For Hermes:** Use `devflow-analysis`, `subagent-driven-development`, and `subagent-driven-development/references/serial-local-agent-pipeline.md` before supervising implementation. Local Qwen/Qwopus workers are bounded implementers, not final verifiers. The supervisor owns diff review, allowlist checks, verification, commits, and pushes.

## Goal

Turn the plan-only serial local-agent contract into durable DevFlow machinery for creating bounded local-worker packets, tracking serial phase state, and running independent watchdog/verification gates without launching duplicate local model runs.

The protected execution contract is:

```text
implementer -> verifier -> tiny_repair -> supervisor_final_gate
```

Each phase must leave durable evidence and one visible next safe action. Worker self-report is never final proof.

## Architecture

DevFlow should own the evidence contract and packet/run-directory generation. Hermes or another supervisor may still launch the actual `qwen-worker` process, but the launch packet, preflight snapshot, allowed files, verification commands, and final status should be generated from a stable DevFlow record instead of ad hoc one-off scripts.

The first milestone is deliberately conservative: **packet-only / evidence-only**. It writes run directories, manifests, packets, verification command lists, and optional watchdog scripts, but does not start models, apply patches, stage, commit, push, or promote.

## Existing Surfaces To Reuse

| Surface | Current role | Reuse rule |
|---|---|---|
| `src/devflow/control_room/orchestration_plan.py` | Exposes `serial_local_agent_pipeline` as plan-only evidence. | Treat this as the policy source for phase order and final-gate ownership. |
| `src/devflow/control_room/local_model_runtime_lock.py` | Provider/model-scoped single-flight runtime lock. | Use for preflight and launch blocking; stale locks are reported, not silently deleted. |
| `src/devflow/control_room/local_ollama_worker.py` / `ollama_worker.py` | Existing DevFlow local model worker runtimes. | Do not replace these; the new machinery is for supervisor packet/run coordination. |
| `src/devflow/control_room/operating_layer.py` | Read-only snapshot projection. | Later slices may surface serial run status here. |
| `docs/local-model-runtime.md` | Documents runtime boundary and serial specialist contract. | Extend, do not rewrite. |
| `~/.hermes/devflow-qwen-runs/` | Current manually generated Hermes/Qwen run directories. | Use as operational evidence for fields/scripts, but do not hardcode this path into DevFlow state. |

## Non-Goals

- No automatic Qwen/Ollama launch in the first slice.
- No background scheduler integration until packet/run evidence is stable.
- No new model provider abstraction.
- No bypass of local model single-flight locks.
- No autonomous git stage/commit/push/promotion.
- No broad operating-layer UI rewrite.

---

# Prioritized Gaps

## P0-1 — Worker packets are still hand-written

### Current producer

The supervisor currently creates `worker-packet.md`, launch scripts, progress watchdogs, and completion watchdogs manually under `~/.hermes/devflow-qwen-runs/...`.

### Impact

Manual packet generation makes it easy to forget allowed files, non-goals, baseline git state, exact verification commands, or lock metadata. It also makes local-model learning metrics inconsistent.

### Required contract

A deterministic packet/run-directory builder should produce:

```text
run.json
worker-packet.md
verification-commands.json
preflight.json
allowlist.txt
non-goals.txt
```

The builder should be packet-only and should not launch a worker.

## P0-2 — Verification failure classes are not durable

The serial pipeline distinguishes:

```text
test_harness_setup
diff_hygiene
product_behavior
off_allowlist
context_budget_exhausted
model_runtime_locked
stale_runtime_lock
```

Today those labels live in chat. They should become stable fields in the run manifest/final report so repeated failures can be compared across local models.

## P0-3 — Watchdog scripts are one-off

Progress and completion watchdogs worked, but each slice used custom scripts. DevFlow should generate a standard completion verifier from the allowed file list and verification commands.

The verifier must report:

```text
SERIAL_PHASE_VERIFY=PASS|FAIL
failure_class=<class>
changed_files=<paths>
untracked_files=<paths>
commands=<exit codes>
```

## P1 — Snapshot visibility is missing

Operators need a read-only summary of the latest serial run phase: pending/running/verify_failed/accepted. This should be projected after the run evidence format is stable.

---

# Recommended Implementation Order

## Slice 1 — SerialLocalRun Packet Contract

Why first: it removes ad hoc packet writing without launching any local model.

Allowed files:

```text
src/devflow/control_room/serial_local_agent_run.py
tests/test_serial_local_agent_run.py
docs/local-model-runtime.md
```

Acceptance:

- creates a deterministic run directory under `.devflow/local-agent-runs/<run-id>/`;
- writes `run.json`, `worker-packet.md`, `allowlist.txt`, `non-goals.txt`, and `verification-commands.json`;
- records phase, provider, model, allowed files, verification commands, baseline branch/HEAD, and git dirty state;
- refuses empty allowed-file and verification-command lists;
- does not start a model, modify source files, stage, commit, push, or promote.

Suggested tests:

```bash
env PYTHONPATH=src:. .venv/bin/python -m pytest tests/test_serial_local_agent_run.py -q
```

## Slice 2 — Runtime Lock Preflight Projection

Allowed files:

```text
src/devflow/control_room/serial_local_agent_run.py
src/devflow/control_room/local_model_runtime_lock.py
tests/test_serial_local_agent_run.py
tests/test_local_model_runtime_lock.py
```

Acceptance:

- packet preflight records `free`, `running`, or `stale` for the requested provider/model;
- live same provider/model lock blocks launch-packet readiness;
- stale same provider/model lock is reported and not automatically removed;
- different provider/model locks do not block;
- preflight output includes the lock path and owner metadata when present.

## Slice 3 — Completion Verifier Script Generator

Allowed files:

```text
src/devflow/control_room/serial_local_agent_run.py
tests/test_serial_local_agent_run.py
```

Acceptance:

- generated `completion-verifier.py` runs only the provided verification commands;
- verifier checks changed/untracked files against the allowlist;
- verifier emits `SERIAL_PHASE_VERIFY=PASS|FAIL`;
- verifier classifies `off_allowlist`, `diff_hygiene`, `test_failure`, and `missing_command`;
- verifier writes `verification-report.json`;
- tests execute the generated verifier against temporary git repos.

## Slice 4 — CLI Packet-Only Command

Allowed files:

```text
src/devflow/cli.py
src/devflow/control_room/serial_local_agent_run.py
tests/test_agent_cli.py
tests/test_serial_local_agent_run.py
```

Acceptance:

- adds a packet-only CLI command that writes a serial local-agent run directory;
- command requires explicit phase, provider, model, allowed files, and verification commands;
- command prints the run directory and next safe manual launch instruction;
- command refuses to run models;
- existing local worker commands remain unchanged.

Possible command shape, subject to implementation review:

```bash
devflow agent serial-packet \
  --phase implementer \
  --provider ollama \
  --model qwen3.6-32b-256k:latest \
  --allowed-file src/devflow/control_room/foo.py \
  --verify "env PYTHONPATH=src:. .venv/bin/python -m pytest tests/test_foo.py -q"
```

## Slice 5 — Read-Only Snapshot Surface

Allowed files:

```text
src/devflow/control_room/operating_layer.py
tests/test_operating_layer.py
src/devflow/control_room/serial_local_agent_run.py
tests/test_serial_local_agent_run.py
```

Acceptance:

- operating-layer snapshot shows latest serial local-agent run status;
- status is read-only and evidence-backed;
- no browser action can launch a model unless a later approved plan explicitly adds that capability;
- stale/running lock information remains visible through existing local model runtime projection.

---

# Supervisor Packet Template

Every generated packet should include:

```markdown
# Serial Local-Agent Packet: <phase>

## Mission
<one phase only>

## Allowed Files
<exact list>

## Non-Goals
- no git stage/commit/push
- no broad refactor
- no off-allowlist edits
- no local model concurrency

## Verification Commands
<exact commands>

## Output Required
- changed files
- self-checks / verification output
- risks and blockers
- whether any off-allowlist file was touched
```

---

# Verification Policy For This Plan

This is a documentation-only plan. Required verification before committing this document is:

```bash
git diff --check -- \
  docs/superpowers/plans/2026-06-20-module-connection-gap-closure-and-qwen-supervision.md \
  docs/superpowers/plans/2026-06-21-serial-local-agent-execution-queue-and-watchdogs.md
```

Also keep the completed prior-plan aggregate result in the closure record:

```text
166 passed in 48.35s
```

## Next Safe Action

Implement **Slice 1 — SerialLocalRun Packet Contract**. Start with tests for deterministic run-directory generation and packet content. Do not launch Qwen/Ollama in Slice 1.
