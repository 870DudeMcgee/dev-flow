# Graphify Ponytail Rehab Program Design

## Goal

Create a repeatable architecture rehab program for Dev-Flow that uses Graphify
evidence, Ponytail gates, and isolated subagent lanes to improve the codebase in
small, verified chunks.

## Current Evidence

The capped planner-worker-judge loop exposed a high-value foundation issue:
Loop Goal Script accepted non-empty planner stdout as a worker plan even when
the output was only a Hermes warning:

```text
Warning: Unknown toolsets: devflow, messaging, moa
```

That warning was saved as a worker-plan artifact and the worker was spawned.
The run was stopped before any worker implementation completed. This makes the
first rehab target the loop contract itself: no worker starts until the planner
artifact is structurally valid.

## Program Architecture

The rehab program uses six lanes:

1. **Foundation lane** hardens Loop Goal Script and Dev-Flow rehab scripts so
   automation cannot claim progress without valid evidence.
2. **Graph scout lane** reads Graphify artifacts and source code to create
   candidate packets. Scouts do not implement.
3. **Ponytail review lane** rejects broad rewrites, fake seams, one-adapter
   abstractions, and framework-shaped work.
4. **Implementation lane** executes one small, test-backed slice at a time.
   Parallel implementation is allowed only when file ownership does not overlap.
5. **Graph delta lane** refreshes scorecards and checks that generated
   `graphify-out/` files remain uncommitted.
6. **Synthesis lane** writes the operator handoff with changed files,
   verification, risks, and the next safe action.

This is a queue-driven program, not one mega-loop. Unlimited capture is allowed;
active execution is deliberately constrained.

## Foundation Slice

The first slice is mandatory before more live worker loops:

- Require planner output to include `# Worker Plan` plus all required section
  headings before saving it as usable worker guidance.
- Treat warning-only stdout, empty output, non-zero planner exits, and missing
  headings as planner-blocked states.
- Save a blocked handoff and do not spawn a worker when the planner output is
  invalid.
- Keep the fix in Loop Goal Script; do not patch individual callers.

Focused verification:

```bash
cd /Users/josh/Desktop/Loop\ Goal\ Script
/Users/josh/Desktop/Dev-Flow/.venv/bin/python -m pytest \
  test_structured_handoff.py::test_request_worker_plan_rejects_stdout_without_required_plan_headings \
  test_structured_handoff.py::test_request_worker_plan_uses_planner_profile_and_graphify_ponytail_prompt \
  test_task_store_sync.py::test_run_loop_sends_planner_plan_to_worker_before_spawn \
  -q
```

## Candidate Packet Contract

Every ready architecture candidate must include:

- Graphify evidence: report commit, scorecard path, hotspot or node IDs, and
  freshness result.
- Source evidence: exact files inspected and the behavior or coupling observed.
- Ponytail gate: existing code reused or deleted, deletion test, seam test, and
  one-slice limit.
- Conflict map: files touched and which candidates cannot run in parallel.
- Verification: focused test command and after-scorecard command.
- Next safe action: one command or one decision.

A candidate without Graphify evidence and source evidence remains an idea, not
a ready slice.

## Subagent Rules

Graph scouts and Ponytail reviewers can run in parallel because they should not
mutate source files. Implementation workers need isolated worktrees or serialized
execution. Two implementation workers must not touch the same source or test
files in parallel.

Accepted implementation progress requires:

- focused tests pass
- scorecard freshness passes
- the diff deletes, reuses, or concentrates complexity
- no new one-adapter seam appears
- the handoff names files changed, verification, risks, and next safe action

## Initial Targets

After the foundation slice, the first candidate queue should prioritize:

1. Dogfood harness mechanics around `CaseResultRecorder`.
2. High-degree control-room files surfaced by Graphify.
3. Repeated task/log/evidence projection paths in the operating layer.
4. Shallow adapter or manager modules that can be deleted or folded into deeper
   behavior.

Each target must be reduced to one small implementation slice before entering a
worker lane.

## Stop Conditions

Stop the program or the current slice when:

- Graphify evidence is stale and cannot be refreshed cheaply.
- A candidate needs product direction instead of architecture judgment.
- A worker expands beyond the current small fix.
- Progress is only a renamed file, rephrased plan, or scorecard without source
  and test evidence.
- A generated artifact would need to be committed.

## Acceptance Criteria

The program is working when:

- invalid planner output blocks worker launch
- ready candidates are captured as small packets
- implementation slices are isolated by file ownership
- every accepted slice has focused tests plus Graphify before/after evidence
- handoffs make the operator's next action obvious
- no push, PR, promotion, merge, or cleanup runs without explicit approval
