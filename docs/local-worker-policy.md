# Local Worker Policy

Status: active

DevFlow's product and workflow authority is
[`DEVFLOW_SOURCE_OF_TRUTH.md`](DEVFLOW_SOURCE_OF_TRUTH.md). This document owns
only the current local-worker boundary and evaluation posture.

## Mac Mini fleet

The configured local fleet is three active llama.cpp GGUF models plus one
retired historical registry entry. They share one
loopback lane at `127.0.0.1:8088`; only one model may be resident or serving a
role at a time. `~/.hermes/scripts/model-router` owns explicit health checks and
model swaps. A healthy router process is not evidence that the intended model
served a call, so persisted worker evidence must also record the actual model.

| Model | Current audition use | Status |
| --- | --- | --- |
| Qwythos-9B v2 Q4_K_M | Unqualified structured-output auditions only | Provisional |
| Qwen2.5 Coder 7B Q4_K_M | Planning and bounded building | Provisional |
| Ornith 9B Q4_K_M | Planning judge and build judge trials | Provisional |
| Qwythos-9B v1 Q4_K_M | Historical evidence only; local artifact removed | Retired |

The Studio lanes and models are not active on this machine. Do not start model
servers blindly or run local roles concurrently. Inspect the router, endpoint
health, `/v1/models`, and the DevFlow runtime lock before starting or swapping a
model.

## Audition boundary

Local audition routing is an explicit per-run override. It may test a model in
a role whose production capabilities have not been established; it does not
grant capabilities, change the default deployment profile, or qualify that
model for production. Audition calls must remain local-only, serial, bounded,
and evidence-backed. Builders do not approve their own work.

The July 12 five-iteration dogfood batch is provisional:

- Qwythos produced consistent but verbose brainstorms and one clean build-judge
  pass; its single builder case missed an edge condition.
- Qwen2.5 Coder was fast and compact for planning and produced two verified
  builds, but one build required repeated revisions and many outputs used
  forbidden Markdown fences.
- Ornith was useful at planning review and found real implementation defects,
  but its build-judge calls were slow and hit token caps three times.
- only the final run, `20260712-055534`, passed the persisted reliability gate;
  earlier runs include parser, materialization, restart, or ownership noise.
- no model-backed verifier or final-judge call occurred, so the batch provides
  no evidence for either role.

The subsequent fixed-runtime qualification batch completed all 69 planned
calls with three repetitions per ground-truth case, temperature `0.0`,
reasoning disabled, and no model-identity mismatches. No tested model-role
assignment qualified:

The three repetitions were byte-identical for every case. They demonstrate
fixed-runtime consistency, not independent sampling or broader task coverage.

All Qwythos results below are for v1. That model is retired and must receive no
further tuning or qualification calls. Qwythos v2 is a distinct, unqualified
candidate; v1 evidence is useful for designing adversarial cases but does not
transfer as a v2 score or capability claim.

| Model and role | Result | Observed failure mode |
| --- | --- | --- |
| Qwen2.5 Coder planner | 0/9 (0%) | Preserved the requested constraints, but every response produced an invalid packet or target-file relationship. |
| Qwen2.5 Coder builder | 0/9 (0%) | Every response included forbidden Markdown fences and failed materialization. |
| Ornith planning judge | 9/12 (75%) | Reached the correct verdict on the scope-expansion defect but failed the exact evidence-reference contract in all three repetitions. |
| Qwythos build judge | 6/15 (40%) | Passed both good cases, but falsely passed all nine bad-case trials: duplicate handling, exact-`int`/Boolean handling, and missing required regression coverage. |
| Qwythos verifier | 6/12 (50%), aptitude only | Passed complete evidence and caught test failures, but accepted missing identity and treated conflicting receipts as a failure instead of requiring review. |
| Ornith final judge | 6/12 (50%), aptitude only | Handled ready and failed-test cases, but qualified missing identity and held rather than blocked an unresolved human choice. |

Verifier and final-judge results are direct bounded aptitude trials only. They
cannot qualify production authority because they did not execute through the
full DevFlow verifier and final-decision paths.

The evidence is bound to run `20260712-135443` and runtime fingerprint
`b9f6b1c1ec221a5ee2d64163928ef6aab136098eba6042b920733fb346a8955a`.
The canonical summary is
`.devflow/dogfood/local-qualification/summary.json`; per-call outputs are in
`.devflow/dogfood/local-qualification/calls.jsonl`; runtime validation and the
run binding are in
`.devflow/dogfood/local-qualification/runtime-validation.jsonl` and
`.devflow/dogfood/local-qualification/run-binding.json`.

Do not derive a global model ranking from this batch. Keep evaluation
role-specific and ground-truth-first, using real DevFlow packets, known-good and
known-bad outcomes, deterministic verification, actual-model identity, and
multiple clean repetitions. Never promote a model from a single score, a
self-judged result, or a run with unresolved reliability breaches.

## Next decision

Hold production qualification and keep all tested roles audition-only. The next
run tunes contracts, prompts, and decoding against development cases, then
validates frozen candidates on untouched cases before a blind fingerprinted
qualification batch. Qwythos v1 is excluded; Qwythos v2 starts from zero role
credit. Verifier and final judge additionally require full-path evidence before
any local assignment.
