# Milestone 22 Question & Blocker Resume Loop Design

## Status

Implemented in the active Milestone 22 branch. This file is retained as the design record; current runtime authority lives in the active docs and code.

## Context

Before Milestone 22, Dev-Flow could project parallel work through task state, goal freshness, scheduler batches, review readiness, manual worker evidence, and operating-layer inbox items, but the human decision loop was still passive. Milestone 22 implements a first-class CLI for listing open questions, answering them, resolving stale blockers, and feeding explicit resume recommendations back into scheduler and supervisor projections.

The North Star says Dev-Flow should let the user see what parallel workers are doing, stop them, answer questions, review their work, and trust that they will not silently damage repos. Milestone 22 promotes "answer questions" from passive visibility into an explicit local-first control-room workflow.

## Product Goal

Make human-blocked work recoverable by turning worker and freshness question evidence into stable question records with explicit answer, resolve, and resume recommendations.

Success check:

```text
Can Dev-Flow show all open worker/blocker questions, record a human answer without mutating worker output, and point the scheduler at the next explicit resume command?
```

## Non-Goals

Milestone 22 must not add:

- provider-backed execution
- autonomous routing
- automatic worker resume after an answer
- background daemons
- auto-verification
- auto-promotion, auto-commit, auto-push, or pull requests
- database storage
- hidden memory, vector search, RAG, embeddings, or training
- browser-side mutation beyond the existing exact verification and exact promotion approvals
- worker-owned readiness or completion certification

## User-Facing Contract

Add a `question` command group:

```bash
devflow question list
devflow question list --json
devflow question show <question_id>
devflow question show <question_id> --json
devflow question answer <question_id> --answer "<answer>"
devflow question answer <question_id> --answer "<answer>" --resume-command "devflow task next-action <task_id>"
devflow question answer <question_id> --answer "<answer>" --json
devflow question resolve <question_id> --reason "<reason>"
devflow question resolve <question_id> --reason "<reason>" --json
```

`list` and `show` are read-only projections. They scan existing task-local question evidence and existing `.devflow/questions/*.json` records. They must not write an index as a side effect.

`answer` is an evidence-writing command. It records a human answer and a recommended resume command, but does not run the command.

`resolve` is an evidence-writing command. It marks a question no longer actionable, but does not delete source question evidence.

## Question Identity

Open questions receive deterministic ids derived from stable source evidence:

```text
Q-<task_id>-<12-char-hash>
```

Hash input:

```text
task_id | agent_id | source_path | line_number | question
```

This lets `question list` produce stable ids without writing state. If the same source line changes, it is treated as a different question, which is acceptable because worker question evidence is append-only.

## Data Model

Create `src/devflow/control_room/question_resume.py`.

Core models:

```python
QuestionStatus = Literal["open", "answered", "resolved"]

class QuestionRecord(BaseModel):
    schema_version: int = 1
    question_id: str
    status: QuestionStatus
    task_id: str
    agent_id: str | None = None
    source_path: str
    source_line: int | None = None
    question: str
    blocking_reason: str | None = None
    required_decision: str | None = None
    answer: str | None = None
    answered_at: str | None = None
    resolved_at: str | None = None
    resolved_reason: str | None = None
    recommended_resume_command: str
    answer_path: str | None = None
    evidence_paths: list[str] = Field(default_factory=list)
```

Persisted answer records live at:

```text
.devflow/questions/<question_id>.json
```

Task-local answer mirrors live at:

```text
.devflow/tasks/<task_id>/question-answers/<question_id>.json
```

The task-local mirror keeps the answer discoverable when inspecting one task. The project-level record lets all-question surfaces list answered/resolved questions without rescanning every task history artifact.

## Source Evidence

Milestone 22 should ingest, without mutating, these sources:

- `.devflow/tasks/<task_id>/questions.jsonl`
- `.devflow/tasks/<task_id>/agents/<agent_id>/questions.jsonl`
- freshness findings that include a `question` field, projected as human-decision questions
- future canonical question records under `.devflow/questions/*.json`

Worker `questions.jsonl` records keep their existing contract:

```json
{
  "type": "blocked_question",
  "task_id": "task-0001",
  "agent_id": "devflow-manual-codex-worker",
  "question": "Which API shape should I preserve?",
  "blocking_reason": "Two public call sites disagree.",
  "required_decision": "Choose the API shape to preserve."
}
```

Invalid question evidence should be surfaced as a projection warning in `question list --json`, not silently ignored when it could affect the operator's next action.

## State Rules

Question state is deterministic:

- If a persisted record exists with `status == "answered"`, show the question as answered.
- If a persisted record exists with `status == "resolved"`, show it as resolved.
- If no persisted record exists and source evidence is valid blocked-question evidence, show it as open.
- If source evidence disappeared but a persisted answered/resolved record remains, keep the persisted record visible with a warning that source evidence is missing.

Default `question list` shows open questions. `--json` includes open, answered, resolved, warnings, counts, and evidence paths. A future `--all` flag may be added later, but Milestone 22 can keep the human-facing text output focused on open questions while JSON carries full state for tests and integrations.

## Answer Semantics

`devflow question answer`:

- requires a non-empty answer
- refuses unknown question ids
- writes the project-level answer record
- writes the task-local answer mirror
- appends a task event named `question_answered`
- preserves original worker `questions.jsonl`
- does not change task status
- does not clear worker evidence
- does not run workers, verification, promotion, or freshness commands

Default recommended resume command:

```bash
devflow task next-action <task_id>
```

If the operator supplies `--resume-command`, Dev-Flow records it as a recommendation only. It should be validated as a Dev-Flow command string and classified through the supervisor classifier for display, but it must not execute.

## Resolve Semantics

`devflow question resolve`:

- requires a non-empty reason
- writes or updates the project-level record with `status == "resolved"`
- writes the task-local mirror
- appends a task event named `question_resolved`
- preserves original question evidence
- does not mark the task unblocked by itself

Resolution is for stale or no-longer-actionable blockers. Answering is preferred when work can resume from a human decision.

## Surface Integration

Milestone 22 should surface question records in:

- `devflow question list/show/answer/resolve`
- `devflow scheduler status --json`
- `devflow status --json`
- `devflow supervisor packet --json`
- operating-layer snapshot `questions` and inbox items
- task show/dashboard where a task has open or answered questions
- production-readiness dogfood

Scheduler integration:

- open questions mark the related task `blocked`
- the blocked task next action becomes `devflow question answer <question_id> --answer "<answer>"`
- answered questions appear as evidence paths and should allow scheduler to recommend the existing conservative resume command, usually `devflow task next-action <task_id>`
- resolved questions should no longer count as open blockers, but source question evidence remains inspectable

Supervisor integration:

- `devflow question list` and `devflow question show` are pure read-only
- `devflow question answer` and `devflow question resolve` are approval-required evidence-writing commands
- all `question` commands remain forbidden for browser execution unless the existing operating-layer Action Rail explicitly supports only read-only command execution

## Dogfood Case

Add a production-readiness case named `question-blocker-resume-loop`.

It should build a deterministic scratch repo with:

- one manual worker question under `.devflow/tasks/<task_id>/agents/devflow-manual-codex-worker/questions.jsonl`
- one malformed question line to verify warning visibility
- one task blocked by that question
- one answer command execution
- one scheduler status projection after the answer

The case should assert:

- `question list --json` shows one open question with a deterministic id
- `question answer` writes project-level and task-local answer records
- task event history includes `question_answered`
- the source `questions.jsonl` file remains unchanged
- scheduler status no longer treats the answered question as an open blocker
- no worker, verification, promotion, commit, push, provider call, database, or background process is invoked by question commands

## Documentation Updates

The implementation updates active docs to say:

- Milestone 21 is complete in the local main checkout.
- Milestone 22 is promoted in the local main checkout.
- The question/resume loop is evidence-only and explicit-command driven.
- Provider adapters, autonomous routing, browser mutation expansion, auto-resume, and automatic verification/promotion remain excluded.

## Acceptance Criteria

Milestone 22 is complete when:

- focused question tests pass
- scheduler, supervisor, operating-layer, and dogfood integrations pass
- production-readiness dogfood remains Silver or better
- full release check passes on promoted `main`
- stale-context scans do not leave active docs claiming question answering is future-only after implementation
- the handoff leaves exactly one safe next action
