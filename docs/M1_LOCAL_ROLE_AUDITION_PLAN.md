# M1 Local Model Role Audition Plan

Status: harness contracts implemented; first live calibration awaits approval

Authority: task-scoped and subordinate to
[`DEVFLOW_SOURCE_OF_TRUTH.md`](DEVFLOW_SOURCE_OF_TRUTH.md). This plan discovers
M1 role fitness; it does not define universal routing, the M4 fleet, or the
meaning of deployment profiles.

This document owns the task-specific workflow for discovering which small local
models can reliably serve each DevFlow role. It does not change the M4's normal
model profiles, router, settings, or role assignments.

## Objective

Use the M4's capacity to evaluate the actual M1 local-model artifacts quickly,
while preserving the M1 runtime envelope inside each isolated test lane. Test
every eligible model against every DevFlow role, identify strengths and
weaknesses, and present evidence-backed M1 profile changes for explicit human
approval.

The current candidate set is:

- Qwen2.5 Coder 7B Q4_K_M;
- Ornith 1.0 9B Q4_K_M;
- Qwythos-9B v2 Q4_K_M, as an unqualified candidate;
- Qwythos-9B v1 remains retired and excluded.

The role matrix covers brainstorm, planner, planning judge, builder, build
judge, verifier, and final judge. No model receives a role in advance.

## Sol/Hermes Operating Contract

GPT-5.6 Sol in Codex is the supervisor and final accountable party. Its context
should remain input-heavy: current authority, exact anchors, compact worker
receipts, diffs, verification output, unresolved decisions, and the evidence
needed for final judgment. Sol should minimize production output that a bounded
worker can safely produce.

Hermes workers perform bounded discovery, compression, planning,
implementation, test analysis, and independent review. The default worker is
the synchronous bounded Hermes adapter. It resolves the free OpenRouter route,
exposes no worker tools, permits one response turn, emits a terminal JSON
receipt, and falls back to Luna only when HY3 fails. It has no default hard
deadline; a caller may request one for a bounded smoke test:

```bash
/Users/jewelbait/.hermes/hermes-agent/venv/bin/python \
  /Users/jewelbait/.hermes/scripts/hermes_hy3_worker.py \
  --packet-id '<stable packet ID>' \
  --prompt '<bounded task packet>' \
  --receipt-path '.devflow/runtime/hermes-receipts/<stable packet ID>.json'
```

Fallback is never silent. The receipt must name the failed primary route, the
failure reason, any retry, and the fallback that actually served the packet.
`NEED_CONTEXT` is a request for better anchors, not a provider failure.

Do not use raw `hermes -z` / `--cli` calls as worker dispatch. That path loads
the full CLI tool surface, auto-approves tools, and cannot receive the terminal
result of Hermes's background-only top-level delegation. Use the adapter above
for Codex and other nonpersistent callers. Native Hermes TUI delegation is
separately pinned to HY3 with bounded child settings.

Use as many useful bounded Hermes workers as the task permits. Prefer parallel
dispatch for independent packets only when Hermes returns distinct terminal
receipts. If concurrent Hermes launches collide, hang, or return no receipt,
stop the affected workers and dispatch sequentially. A missing receipt is a
failed delegation, never evidence of completion.

There is no fixed Hermes worker count. Start independent packets concurrently,
increase only while every packet returns a distinct terminal receipt, and back
off to the last proven count after the first collision, hang, empty receipt, or
provider rate limit. The worker count is a throughput control, not evidence of
task progress.

The HY3 capacity proven by distinct terminal receipts on 2026-07-13 is two
workers. Start at two or below, and increase by one only after every packet
returns valid receipts. Persist the last proven count, probe result, timestamp, and failure
reason in `.devflow/runtime/hermes-worker-capacity.json`; do not infer capacity
from launched process count.

Sol retains responsibility for translating intent, choosing exact anchors,
validating worker claims, integrating edits, running repository verification,
rejecting invented facts, writing the final Human Decision block, and applying
an M1 profile change only after explicit human approval.

## Delegation Packet And Receipt

Every Hermes packet is self-contained and bounded:

```text
Packet ID:
Objective:
Role: scout | compress | plan | build | review | reader-test
Exact source anchors:
Allowed files or evidence:
Required output schema:
Acceptance evidence:
Token/output cap:
Forbidden actions:
If context is insufficient: return NEED_CONTEXT with the missing anchor
Next Action:
```

Machine-consumed edit packets are anchor-first. They identify exact files,
copy current source anchors, describe insertion or deletion boundaries, and
return operation data before a patch. A worker does not guess when an anchor
does not match the live checkout.

Sol retains only the compact receipt and the minimum source evidence required
to review it:

```text
Packet ID:
Requested route:
Actual route/model:
Status: complete | partial | NEED_CONTEXT | failed
Claims:
Files or artifacts changed:
Verification performed:
Evidence paths or hashes:
Unresolved risks:
Fallback used and reason:
Next Action:
```

Long raw transcripts, broad searches, and logs stay outside Sol's context unless
a contradiction requires exact evidence. Worker output is compact JSON or
tightly structured Markdown, normally under 1,500 words.

## M1-via-M4 Test Boundary

The M4 is an execution host, not the product under change.

- Do not edit the M4's normal profiles, `models.yaml`, `model_router.py`,
  `routing.py`, or external router settings for this work.
- Each candidate uses an ephemeral test-only loopback port, process group,
  runtime directory, output directory, and cleanup receipt.
- Preserve the M1 envelope inside each lane: the exact candidate artifact,
  8,192-token context, one in-flight call, 99 GPU layers, 512 MiB cache RAM,
  180-second startup timeout, speculation/MTP disabled, loopback-only binding,
  and the fingerprinted llama.cpp binary.
- Different candidate lanes may run concurrently. One candidate lane may not
  run more than one attempt at a time.
- Each candidate first passes one serial, no-semantic calibration attempt that
  proves artifact fingerprint, served identity, runtime settings, and cleanup.
- The scheduler then keeps healthy candidate lanes busy with independent role
  attempts. Contention and timing are recorded separately from semantic scores.
- Do not share output directories, splice fingerprints, reconstruct incomplete
  output, or let two workers mutate the same pipeline run.

## Audition Matrix And Evidence

The atomic unit is one `model x role x case x repeat x fingerprint` attempt.
Every attempt persists the request, expected model, served model, runtime and
artifact fingerprints, timing, usage, raw output, parsed packet, deterministic
checks, reliability outcome, quality outcome, failure classification, and
terminal status.

Each model-role-case combination runs three repeats under one frozen
fingerprint. Results from different fingerprints remain separate.

The fixed casebook combines minimal deterministic fixtures with real DevFlow
regressions. It includes good cases, known-bad cases, ambiguity, scope traps,
malformed evidence, missing identity, failed tests, failed review, and receipt
conflicts.

Failures are classified as model capability, prompt/context packaging,
tool/runtime, orchestration/guardrail, ground-truth/scorer, or infrastructure.

Reliability is an eligibility gate. Any critical false accept, identity drift,
unsafe override of deterministic evidence, scope violation, malformed required
packet, or unreliable failure behavior makes that model ineligible for the role
under that fingerprint. Quality, consistency, speed, and token efficiency rank
only candidates that clear the reliability gate.

## Human Decision And M1 Promotion

Audition output is provisional evidence and never edits an M1 profile
automatically. Every completed matrix persists a Human Decision block with:

- every model-role recommendation and ineligibility result;
- reliability, quality, consistency, speed, and efficiency evidence;
- the exact M1 profile fields that would change;
- a prominent `no profile changes applied` state;
- the exact first command or patch that applies the approved change;
- remaining risks and rollback instructions.

When the user approves that block, the next slice applies the named M1 profile
change and verifies the real M1 route. This promotion step is required; the
project must not end after producing recommendations.

The decision artifacts live at
`.devflow/dogfood/m1-role-audition/<run_id>/human-decision.json` and
`human-decision.md`. The JSON record contains `status` (`pending`, `approved`,
or `rejected`), the exact proposed role mappings, evidence fingerprints,
approval timestamp when present, verification commands, and rollback patch.
Only a human action changes `status` from `pending`.

The record uses schema version `1` with these required fields:
`schema_version: int`, `status: str`,
`proposed_role_mappings: dict[str, str]`, `evidence_fingerprints: list[str]`,
`approved_at: str | null`, `verification_commands: list[str]`,
`rollback_patch: str`, and `no_profile_changes_applied: bool`. While status is
`pending`, `approved_at` is null and `no_profile_changes_applied` is true.

The default promotion target is
`src/devflow/loop/profiles.yaml::profiles.mini-baseline.roles.<role>`.
`mini-ollama` is a legacy-named compatibility profile, not an assignment-equivalent
alias; it changes only when the Human Decision block explicitly proposes a
separate update. `models.yaml` is not a role
assignment surface and is changed only if a separate approved task updates
artifact metadata or eligibility.

## Harness-Only Implementation Plan

The first implementation slice makes no model calls, downloads no artifacts,
and starts no server.

1. Extend `src/devflow/loop/local_audition_casebook.py` with versioned fixture
   and regression cases for all seven roles.
2. Add `src/devflow/loop/local_audition_matrix.py` to expand candidate, role,
   case, repeat, and fingerprint inputs into immutable atomic attempts. Its
   transport and process operations remain dependency-injected.
3. Add scheduling that permits cross-candidate concurrency but enforces one
   in-flight attempt per candidate and deterministic receipt order.
4. Reuse `src/devflow/loop/local_audition_runner.py` for fail-closed identity,
   protocol, completion, and host-gate receipts. Extend its public receipt only
   when matrix metadata cannot remain in the matrix wrapper.
5. Extend `src/devflow/loop/local_audition_scorecard.py` so reliability is a
   separate gate and eligible candidates are ranked on quality, consistency,
   duration, and token use.
6. Extend `src/devflow/loop/local_audition_qualification.py` to remain
   provisional until reliability, complete three-repeat evidence, and
   independent review pass.
7. Add `src/devflow/loop/local_audition_decision.py` to render and persist the
   Human Decision block without modifying `profiles.yaml`.
8. Add focused tests for matrix expansion, fingerprint isolation,
   per-candidate serialization, cross-candidate concurrency, three repeats,
   failure classification, score gating, deterministic ordering, and unapplied
   profile recommendations.

Proposed focused tests are `tests/test_local_audition_matrix.py`, extensions to
the existing casebook, runner, scorecard, and qualification tests when their
public contracts change, and `tests/test_local_audition_decision.py`.

Verification for the harness-only slice:

```bash
PYTHONPATH=src .venv/bin/python -m pytest -q \
  tests/test_local_audition_casebook.py \
  tests/test_local_audition_runner.py \
  tests/test_local_audition_scorecard.py \
  tests/test_local_audition_qualification.py \
  tests/test_local_audition_matrix.py \
  tests/test_local_audition_calibration.py \
  tests/test_local_audition_decision.py
PYTHONPATH=src .venv/bin/python -m pytest -q
PYTHONPATH=src .venv/bin/python -m devflow.cli --help
PYTHONPATH=src .venv/bin/python -m devflow.cli loop spine-fixture --json
git diff --check
```

The diff must contain no changes to the M4's normal model registry, profiles,
routing, or external router configuration.

## Later Approval Gates

Separate human approval is required before downloading or copying model
artifacts, starting an ephemeral candidate lane, making the first semantic
model call, changing a frozen run after it begins, applying an M1 profile
recommendation, or changing any M4 profile, router, or runtime setting.

An M4 configuration change is outside this plan even if separately approved.
It must run as a distinct task and change window, with its own plan, diff,
verification, and rollback evidence; it cannot be bundled into the M1 audition.

## Next Action

The harness-only matrix, evidence, ranking, qualification, pending-decision,
and no-semantic calibration contracts are implemented. Obtain explicit human
approval for one ephemeral candidate lane, then perform exactly one serial
identity-only calibration and validate its durable receipt before making any
semantic matrix call. Do not alter `profiles.yaml`, the M4 registry/router, or
normal runtime settings. Use HY3:FREE for bounded scout/review packets and Luna
only for an explicitly recorded fallback.
