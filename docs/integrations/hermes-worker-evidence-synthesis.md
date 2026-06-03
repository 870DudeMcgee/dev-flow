# Hermes Worker Evidence Synthesis

Status: integration guidance. This does not add Hermes cron runtime, autonomous delegation, direct repo mutation, or a second task source of truth.

Hermes should read and summarize Dev-Flow evidence. It must not own that evidence.

## Boundary

Worker flow:

```text
Dev-Flow task
-> eligible local worker profile
-> bounded TaskPacket
-> local model boundary
-> WorkerEvidence under .devflow/tasks/<task-id>/local-model-runs/<run-id>/
-> Hermes-readable JSON/status output
-> human review and Dev-Flow-controlled next action
```

Hermes may:

- read `agent list --json`, `agent show --json`, `agent policy --json`, task status, dashboard, and supervisor packets
- summarize WorkerEvidence for Josh
- alert on fresh, stale, failed, or low-quality evidence
- ask for explicit approval before any worker execution or mutation command
- store model-quality heuristics in Hermes memory as convenience context
- use session search to find old evidence summaries
- use `delegate_task` only for bounded synthesis/review, not direct repo mutation
- track review queues in Hermes todo

Hermes must not:

- treat Hermes memory as Dev-Flow truth
- directly edit source files or `.devflow/`
- run workers without approval
- mutate task state directly
- apply patches, verify, commit, merge, push, or promote
- spawn unbounded local workers
- use `/Users/jewelbait/Desktop/DevFlow` for current work

Dev-Flow artifacts beat Hermes memory every time.

## Recommended Briefs

### Morning Local-Worker Evidence Brief

Read-only inputs:

- `devflow status --json`
- `devflow dashboard --json`
- `devflow agent list --json`
- recent WorkerEvidence under active tasks

Output:

- fresh local worker runs
- failed worker runs
- review queue
- one next safe action

### Fresh Evidence Alert

Trigger when a new WorkerEvidence `run.json` appears.

Output:

- task id
- profile id
- model
- machine class
- weight class
- status
- response path
- whether Hermes delegation was allowed
- recommended human-safe next command

### Stale Worker Check

Read-only inputs:

- task list/status
- WorkerEvidence timestamps
- verification state

Output:

- stale runs without follow-up
- failed runs without human review
- tasks with evidence but no verification or promotion preview

### Model Quality Trend Summary

Hermes may summarize model-quality heuristics, but not canonical task truth:

- profiles that produced useful summaries
- profiles that produced empty, noisy, risky, or misleading output
- alias warnings such as `qwopus:latest` and `qwen3.6:latest` sharing an Ollama ID until manifests prove otherwise
- machine-allocation observations such as Mac mini pressure or Mac Studio heavy-model latency

## Dogfood Loop

The improvement path is real Dev-Flow use, not a synthetic profiling platform:

1. Run approved workers.
2. Inspect WorkerEvidence.
3. Compare evidence against actual task outcomes and human review.
4. Adjust profile roles, prompts, machine assignment, and permissions.
5. Keep the registry as the authority.

Hermes can make this loop easier by summarizing evidence and surfacing patterns. It must not convert its summaries into automatic routing truth.

## Optional Future Conveniences

Text-to-speech briefs, mobile summaries, and scheduled digests are optional convenience layers. They must cite Dev-Flow evidence paths and preserve the same approval boundary.
