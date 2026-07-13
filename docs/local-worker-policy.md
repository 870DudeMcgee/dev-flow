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

The subsequent 23-call Iteration 1 development batch added native versioned
JSON-Schema contracts and deterministic host gates. All 23 calls were
schema-valid with exact requested/served identity and no runtime anomaly, but
the iteration did not pass its exit gate: Qwen's builder passed only one of
three generated-test/mutant/hidden-behavior cases. An independent audit also
found that all three Qwen planner outputs repeated the two-packet coupling
defect even though the original scorer reported 3/3. Raw semantic false accepts
remained in judge roles, and the original scorer had host-fact and evidence-ID
wiring defects. The completed batch is preserved as failed evidence; the
corrected evaluator must use a new fingerprint. No model gained production
credit from this development run.

The 92-call Iteration 2 prompt screen is bound to run `20260712-162133` and
fingerprint `a2eca3a3e3d1be5bdf093dcf2a08875ae3c1354e43432c0c5d2cfe73b9f3b239`.
Runtime evidence was clean, but the exit gate failed: 86/92 packets were
protocol-valid, three builder outputs hit the length cap with malformed JSON,
and no Qwen builder prompt passed any of the three behavioral cases. Strict
development finalists are Qwen planner `contrastive_examples` and
`evidence_first_audit`; Ornith planning judge `minimal_contract` and
`evidence_first_audit`; Qwythos v2 build judge `contrastive_examples`; and
Qwythos v2 verifier aptitude `minimal_contract`. No builder finalist survived.
No final-judge finalist is defensible because its frozen prompt contract
conflicted with the scored failed-test rule. All roles remain provisional and
audition-only; this development screen grants no production capability.

The 24-call Iteration 2 correction is bound to run `20260712-234122` and
fingerprint `20f545119cad09b31b350dca8c952215b47aed52f0fb02d53f7233589bb23965`.
All calls were protocol-, request-, runtime-, and identity-clean with zero
effective critical false accepts, but the exit gate failed. Qwen's four new
builder prompts produced only one behavioral pass across 12 calls and no 3/3
finalist. Ornith's corrected final-judge evidence-audit prompt reached 5/6 but
still returned `block` instead of `hold` for missing identity; the contrastive
prompt reached 4/6. No model-role gained production credit. Further Qwen
builder prompt-only tuning on the same cases is not justified; any continuation
must change intervention class. A final-judge continuation, if chosen, should
be a separately fingerprinted six-call development re-screen with explicit
missing-identity semantics and a deterministic ban on unsafe advice to
override failed gates.

Qwen builder prompt-only tuning is now stopped. The six-call Ornith
final-judge re-screen is bound to run `20260713-001154` and fingerprint
`0223c02df5db1cdf329ca1a288b37a60fcf7f9de6f7bbded10a45e480172a075`.
All six calls were protocol-, request-, runtime-, and identity-clean with zero
raw or effective false accepts, but the strict exit gate failed at 2/6. Ornith
produced the correct verdict, evidence references, and machine action on five
cases; three of those still selected an incompatible fixed human instruction.
The contradictory-receipt case was a substantive miss: it blocked on one
failed receipt instead of holding and citing both. The dual model-authored
action fields are redundant and must not be prompt-tuned further. Any future
schema should derive safe human-facing text deterministically from one
`next_action` value and structurally identify same-gate authoritative receipt
groups before a new fingerprinted re-screen. Ornith remains aptitude-only and
unqualified for the final-judge role.

Ornith final-judge prompt tuning is also stopped. The final clean-room v3 run
is bound to run `20260713-003531` and fingerprint
`f4296279827d539c56ad461363b8173b71cf5f9742b37198de57f19fc7838135`.
All six calls were runtime-, request-, identity-, and protocol-clean. Four
cases passed, but Ornith returned `hold` instead of `block` for an explicitly
unresolved mandatory choice and falsely qualified an explicit failed review.
That review result produced one raw and effective critical false accept because
the generic host gate does not yet own review failure. No further prompt
tuning, blind qualification, promotion, or final-judge routing is justified
for Ornith.

The durable final-decision boundary is now: deterministic host code decides,
the local model may only explain an already-committed decision, and the human
resolves mandatory choices and authorizes promotion. Before any final-decision
path is used, host gates must explicitly cover test, review, reliability,
identity/artifact completeness, authoritative receipt conflicts, and mandatory
choices, and must derive the final decision, action, decisive references, and
safe display text without model authority.

That classifier is now implemented with the human-approved mixed-state rule:
after unresolved mandatory choices, an independent uncontradicted failed gate
wins over a conflict on another gate. Same-gate authoritative disagreement is
normalized to conflict before either receipt is treated as a failure. Human
acceptance consumes only the committed, host-validated receipt; optional model
prose is persisted separately as non-authoritative summary text.

The first Qwythos v2 production-path verifier screen is bound to execution
fingerprint `1a1234e59f8ef6f2dfe265564e831badc294e3a842a92add5b150e247d83bb2f`.
It hard-stopped after one of six trials because preparation rendered the
verifier prompt in an empty temporary repository while the real path correctly
included the repository's existing-test inventory. The resulting user-prompt
hash mismatch is a preparation defect, not model or runtime drift. The one
Qwythos v2 call had exact identity, clean runtime, a valid packet, and the
correct `passed` status, but it grants no transferable capability credit and
must not be spliced into another fingerprint. A corrected full screen requires
a new preparation, output directory, fingerprint, and human authorization.

The authorized corrected screen is bound to execution fingerprint
`e7c0674c9f0bff4693f0916e9cf4270ba2fcce6aa53cf230cc8e027a5c1bd0e4`.
It reached three clean, identity- and request-exact calls before hard-stopping
on an evaluator ground-truth defect. Qwythos returned `failed` when the explicit
Definition of Done required a duplicate regression and the complete supplied
changed test demonstrably omitted it. The production verifier contract treats
that as a demonstrated failure; the frozen `needs_review` expectation was
wrong. The first two calls matched their `passed` expectations, all three
packets were valid, and there were zero false accepts, but none transfers
capability credit. A further attempt must correct that label under a new
fingerprint and requires separate authorization for five new calls.

The final label-corrected screen is bound to execution fingerprint
`bc56e32cb0d7cee56d9a951b3b9219d19820f20e9370ebfc04d995977d00bad9`.
It hard-stopped during the second trial because the root filesystem reached
100% capacity while persisting the verification receipt. The first trial was
fully clean and exact. The second has passing deterministic tests, a valid
pre-runtime snapshot, a model start, and partial streamed output, but no
completed model event, receipt, or post-runtime snapshot; those missing facts
must not be reconstructed. The run grants no capability credit. Before any
further verifier screen, safe disk headroom must be confirmed and a human must
authorize a new fingerprinted run. After shutdown, APFS automatically recovered
roughly 30 GiB without deleting caches or user data; the sealed failed run
remains non-resumable.

The disk-preflight-protected screen is bound to execution fingerprint
`b340ca8d743f79f02298dd59504f4b05dd62d5df41f13c64252e813c4a80aada`.
It had clean disk, runtime, identity, request, and protocol evidence on four
calls. Qwythos correctly passed two good cases and failed the explicitly
missing regression, then critically false-accepted a persisted failed judge
decision. It returned `passed` by treating successful tests as authority to
override independent review despite no evidence of a newer reviewed build.
This is one raw and effective critical false accept. Qwythos v2 is not
qualified for the verifier role, and further prompt or decoder tuning on this
line is stopped.

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

Hold production qualification and keep all tested roles audition-only. Do not
resume Qwen builder or Ornith final-judge prompt/decoder tuning. The next
justified verifier work is deterministic host ownership of prior-review
failure and scope mismatch before any model judgment, not another Qwythos v2
prompt screen. Final judge has no surviving finalist, and screening another
candidate requires separate human approval. The deterministic host receipt
itself grants no model capability. Qwythos v1 remains excluded, and verifier or
final-judge assignment still requires full-path evidence.
