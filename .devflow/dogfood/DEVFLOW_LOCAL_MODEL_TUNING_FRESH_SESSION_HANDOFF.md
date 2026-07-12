# Fresh-session prompt: DevFlow local-model reliability tuning

You are the primary Codex agent continuing a live DevFlow local-model
qualification program in `/Users/josh/Desktop/Dev-Flow`. Treat this document as
a detailed handoff, not as authority: verify material claims against current
source, tests, process state, and persisted evidence before acting.

## Mission

Run a disciplined, delegation-heavy iterative program that makes DevFlow's
local planner, builder, planning-judge, build-judge, verifier, and final-judge
behavior materially more reliable. Tune prompts, constrained output contracts,
decoder settings, and deterministic host-side gates before considering any
fine-tuning. Score models per role. Never infer a global model ranking.

Qwythos v1 is retired. Do not run, tune, benchmark, restore, or silently route
any new call to it. Qwythos v2 is a new candidate with zero inherited role
credit; historical v1 failures may inform adversarial cases, but its scores do
not transfer.

## How to work

Operate primarily as overseer, experimental designer, integrator, and proof
owner. Delegate bounded independent reading, research, case design, result
audits, and implementation slices to sub-agents. Keep enough primary context
to control the experiment and integrate evidence. Do not dump code into chat;
make scoped workspace changes and report outcomes and proof.

When the orchestration surface exposes worker-model selection, prefer
`hy3:free` for suitable bounded sub-agent work because it has been useful and
free. Never claim Hy3—or any other model—was selected unless the surface
actually exposes and confirms that control. Cloud sub-agents may research,
audit, or implement bounded support work; the measured DevFlow role calls in
this experiment must remain local. The primary agent is responsible for all
integration, safety, ground truth, and final conclusions.

Send concise progress updates during long work, at least once per minute. Lead
with outcomes and blockers. Preserve a dense primary context by asking agents
for compact evidence with exact paths, commands, IDs, and conclusions.

## Authority and safety

1. Read `AGENTS.md`, `docs/DEVFLOW_SOURCE_OF_TRUTH.md`, and
   `docs/local-worker-policy.md` first.
2. Orient from current source and tests. Do not trust old handoffs blindly.
3. Active runtime surfaces are `src/devflow/loop/`,
   `src/devflow/control_room/`, `src/devflow/control_room/chat.py`, and
   `src/devflow/cli.py`.
4. The browser is the unified brainstorm/status surface. Hermes is the bounded
   orchestration harness. Local models are replaceable labor, never authority.
5. Keep the work bounded. Do not add a broad dashboard, hidden automation,
   model zoo, compatibility shim, or speculative architecture.
6. The worktree already contains user work. Inspect `git status`; preserve all
   unrelated and overlapping edits. Never reset or revert them.
7. Do not commit, push, publish, open a PR, promote a model, or change a
   production profile without explicit human approval.
8. Never run two local model roles concurrently on this 16 GB machine.
9. Before any model start/swap, inspect the DevFlow runtime lock, port 8088,
   router PID/process arguments, `/health`, `/v1/models`, and Ollama residency.
10. A healthy endpoint is not proof of model identity. Persist and validate the
    actual served model for every call.
11. Builders never approve their own work. Model verdicts never override
    deterministic evidence or unresolved human decisions.

## Machine and active fleet

Host: Mac mini M1 with 16 GB unified memory. Keep one llama.cpp model resident
at a time on loopback port 8088. Start with 8192 context and a 512 MiB cache.
Speculation/MTP is off for the baseline.

Current intended artifacts:

- `~/models/qwen2.5-coder-7b-q4_k_m.gguf` — Qwen2.5 Coder 7B, planner/builder
  candidate.
- `~/models/ornith-9b-q4_k_m.gguf` — Ornith 1.0 9B, judge candidate.
- `~/models/qwythos-9b-v2-q4_k_m.gguf` — Qwythos-9B v2, new unqualified
  candidate.
- `~/models/qwythos-9b-q4_k_m.gguf` — v1 historical path; the artifact should
  be absent and the registry entry retired.

Qwythos v2 provenance:

- Official repository:
  `https://huggingface.co/empero-ai/Qwythos-9B-v2-GGUF`
- Pinned revision: `97c11b03687f194b300efbdb4760d9bc4021b759`
- Pinned file URL:
  `https://huggingface.co/empero-ai/Qwythos-9B-v2-GGUF/resolve/97c11b03687f194b300efbdb4760d9bc4021b759/Qwythos-9B-v2-Q4_K_M.gguf`
- Expected bytes: `5736063744`
- Expected SHA-256:
  `c0a588704f422b713eca29b2c1f192ae6f69aea3f9e7cb64f9ecdb76ff7a85f4`
- This is the normal/trunk-only Q4_K_M, not the MTP file. The publisher
  recommends Q4_K_M and keeps sensitive SSM tensors at higher precision. It is
  the sensible balance for this 16 GB M1 and for a non-speculative baseline.

The registry identities should be distinct:

- `qwythos-9b-mini`: `available: false`, `retired: true`, historical v1 only.
- `qwythos-9b-v2-mini`: available, audition-only, path above, initially claims
  only `structured_output`; no production role capabilities until qualification.

The standalone router default should point at the v2 path/alias so deleting v1
cannot leave a silent stale default. Production profiles must remain unchanged.

### Verified replacement receipt from July 12, 2026

The replacement completed successfully in the handoff session:

- The final v2 file matched `5736063744` bytes and SHA-256
  `c0a588704f422b713eca29b2c1f192ae6f69aea3f9e7cb64f9ecdb76ff7a85f4`.
- llama.cpp loaded it with 8192 context, one slot, 99 GPU layers, loopback-only
  port 8088, and alias `qwythos-9b-v2-mini`.
- `/health` returned `{"status":"ok"}` and `/v1/models` reported the exact v2
  alias, 8,953,803,264 parameters, and 8192 runtime context.
- A publisher-style reasoning request at 0.6/0.95/top-k 20 consumed its entire
  256-token allowance in `reasoning_content` without producing final content.
  This is useful evidence: explicitly control thinking and reserve adequate
  output budget rather than treating a length stop as semantic failure.
- With `chat_template_kwargs.enable_thinking=false` and native JSON Schema, the
  same runtime returned exactly `{"status": "ok", "sum": 5}` in 13 completion
  tokens. This proves constrained structured output works on the installed
  server; it does not qualify any DevFlow role.
- The router's default start exposed the exact v2 alias and then stopped cleanly.
- The stale-status shell bug was corrected from top-level `return` to `exit`.
- The v1 artifact (5,887,668,064 bytes; historical SHA-256
  `671c430bf18c961251338d639a3c02aac7451c39eed25874cad74287ac6cd38a`)
  was deleted only after v2 passed checksum, load, identity, and response checks.
- The complete pytest suite passed with two expected skips; CLI help,
  deterministic spine fixture, registry eligibility proof, router syntax,
  router start/stop, and `git diff --check` also passed.

## Existing implementation state

At handoff creation the tracked worktree included edits to:

- `docs/local-worker-policy.md`
- `src/devflow/loop/execution.py`
- `src/devflow/loop/model_router.py`
- `src/devflow/loop/routing.py`
- `tests/test_capability_routing.py`
- `tests/test_loop_execution.py`

Untracked source/tests implemented the local audition framework:

- `src/devflow/loop/local_audition_casebook.py`
- `src/devflow/loop/local_audition_gate.py`
- `src/devflow/loop/local_audition_qualification.py`
- `src/devflow/loop/local_audition_runner.py`
- `src/devflow/loop/local_audition_scorecard.py`
- matching `tests/test_local_audition_*.py`

Ignored dogfood includes batch runners, sandbox helpers/tests, and persisted
qualification evidence under `.devflow/dogfood/`. Inspect it; do not casually
rewrite fingerprint-bound historical files. In particular, old Qwythos aliases
inside completed harnesses/evidence are historical identities, not stale
production configuration.

## What the previous runs proved

The earlier five-iteration dogfood run IDs were:
`20260712-041134`, `042221`, `042740`, `043236`, `044607`, `045618`, `051720`,
and `055534`. Only `20260712-055534` passed the persisted reliability gate. It
ran four tests successfully in 447.891 seconds. Earlier runs contain parser,
materialization, restart, or ownership noise and must not be used as clean
capability proof.

The subsequent fixed-runtime qualification batch:

- run: `20260712-135443`
- runtime fingerprint:
  `b9f6b1c1ec221a5ee2d64163928ef6aab136098eba6042b920733fb346a8955a`
- 69/69 planned calls completed
- three repetitions per ground-truth case
- temperature 0.0, reasoning disabled
- no runtime or actual-model identity anomalies
- every identical repetition was byte-identical; that proves fixed-runtime
  consistency, not independent sampling or task coverage

Canonical evidence:

- `.devflow/dogfood/local-qualification/summary.json`
- `.devflow/dogfood/local-qualification/calls.jsonl`
- `.devflow/dogfood/local-qualification/runtime-validation.jsonl`
- `.devflow/dogfood/local-qualification/run-binding.json`

Role results:

- Qwen planner: 0/9. Constraints were largely preserved, but every response
  violated packet or target-file coupling.
- Qwen builder: 0/9. Every response used forbidden Markdown fences and failed
  materialization.
- Ornith planning judge: 9/12. Semantic verdicts were 12/12, but three outputs
  cited invalid evidence IDs.
- Qwythos v1 build judge: 6/15. It passed the known-good cases and falsely
  passed all nine known-bad trials: duplicate handling, exact-int/Boolean
  handling, and missing regression coverage.
- Qwythos v1 verifier aptitude: 6/12. It accepted missing identity and mishandled
  conflicting receipts. This was not full-path qualification.
- Ornith final-judge aptitude: 6/12. It qualified missing identity and held
  rather than blocked an unresolved human choice. This was not full-path
  qualification.

No role qualified. Verifier and final-judge results are aptitude-only until the
real DevFlow execution paths are exercised.

## Research conclusions to apply

Use official/primary sources when refreshing technical facts:

- llama.cpp server API:
  `https://github.com/ggml-org/llama.cpp/blob/master/tools/server/README.md`
- llama.cpp grammars:
  `https://github.com/ggml-org/llama.cpp/blob/master/grammars/README.md`
- Qwen official model card/config for the exact installed model
- Ornith official GGUF/model card
- Qwythos v2 official repository above
- Anthropic agent-eval guidance:
  `https://www.anthropic.com/engineering/demystifying-evals-for-ai-agents`
- Google train/validation/test split guidance:
  `https://developers.google.com/machine-learning/crash-course/overfitting/dividing-datasets`
- Hanley and Lippman-Hand rule of three:
  `https://pubmed.ncbi.nlm.nih.gov/6827763/`

Key conclusions:

1. Prompt-only tuning is insufficient. llama.cpp supports
   `response_format`/JSON Schema and does not merely inject the schema as
   ordinary prompt prose. Use constrained structured output for planner,
   builder packet, and judge verdicts.
2. Move deterministic facts out of model judgment: actual model identity,
   test exit/result, receipt conflicts, missing required artifacts, missing
   regression tests, and mandatory unresolved human decisions belong in host
   gates.
3. Treat evidence IDs as schema enums or validate them deterministically. Do
   not ask a judge to reproduce arbitrary identifiers without enforcement.
4. Separate semantic correctness, protocol validity, materialization success,
   evidence validity, and runtime reliability. One aggregate score hides the
   actual failure mode.
5. Zero false accepts is the primary judge/verifier/final-judge objective.
   False rejection is secondary and reported separately.
6. Unique ground-truth cases are the experimental unit. Repeated identical
   trials diagnose determinism but do not increase coverage.
7. Maintain development, validation, and blind qualification partitions.
   Freeze prompts/settings before touching blind cases.
8. Use 20–30 unique critical cases as provisional evidence. For a rough 95%
   upper bound below 5% when observing zero failures, the rule of three implies
   about 59 independent critical cases.
9. Fine-tuning is a later intervention only after prompt/schema/host-gate and
   decoder experiments plateau. Never train on validation or blind cases.

## Initial decoder candidates

Keep 8192 context initially and record every parameter. Test one factor at a
time after prompt/schema contracts are stable enough to measure.

Qwen2.5 Coder official starting point:

- temperature 0.7
- top_p 0.8
- top_k 20
- repeat penalty 1.1
- thinking off for bounded packet generation

Compare that with a low-entropy candidate around temperature 0.2/top_p 0.9 and
a top_k 1/greedy diagnostic. Do not assume temperature 0 is best merely because
it is reproducible.

Ornith reasoning starting point:

- temperature 0.6
- top_p 0.95
- top_k 20

Test thinking on/off and a low-entropy constrained alternative. Keep verdict
fields schema-constrained and evidence IDs enumerated.

Qwythos v2 publisher starting point:

- temperature 0.6
- top_p 0.95
- top_k 20
- optional repeat penalty 1.05
- max new tokens up to 16384 when the task genuinely needs it

It is a reasoning model. Test bounded reasoning deliberately. Do not enable the
MTP/speculative path in the baseline, and make no more v1 calls.

If the current `LocalModelClient` cannot express top_p, top_k, repeat penalty,
reasoning/template controls, seed, or JSON Schema, extend the smallest owning
contract with tests and persist those settings in call evidence. Do not claim a
publisher preset was tested if the client did not actually send it.

## Six-iteration program

Recommend six macro iterations, with a hard cap of eight. Budget roughly
250–350 tuning calls plus a separate blind qualification batch. Stop early when
the next experiment has no evidence-backed chance to change a decision.

### Iteration 1 — protocol and deterministic gates (20–30 calls)

- Implement/version JSON schemas for every measured role output.
- Enforce no-fence builder materialization structurally rather than through
  prose alone.
- Host-check model identity, tests, artifact presence, conflicts, evidence IDs,
  and mandatory human choices.
- Establish failure taxonomy and exact per-call evidence fields.
- Re-run a small set of prior failures to prove each gate catches the intended
  fault without asking the model.

Exit: malformed/protocol outputs cannot become valid passes; known deterministic
bad states are rejected or escalated by host logic.

### Iteration 2 — prompt screening (70–100 calls)

- Create 3–5 materially different prompt variants per role, not cosmetic edits.
- Use concise contracts, explicit decision tables, positive and negative
  examples, allowed evidence IDs, and a clear abstain/review state.
- Screen on development cases only, balanced across known-good and known-bad.
- Eliminate prompts with any false accept or poor protocol/materialization rate.

Exit: one or two prompt finalists per model-role, selected by safety first and
then coverage/latency.

### Iteration 3 — decoder screening (60–80 calls)

- Freeze prompt/schema finalists.
- Compare official presets, low-entropy constrained settings, and greedy/top_k1
  diagnostics.
- Run multiple seeds where sampling is enabled; persist seed and actual request.
- Measure semantic correctness, false accepts/rejects, protocol validity,
  latency, token count, and repetition/loop symptoms separately.

Exit: one frozen decoder configuration per surviving model-role.

### Iteration 4 — failure-directed hardening (50–70 calls)

- Build new adversarial development cases from observed failure classes without
  copying validation/blind cases.
- Test missing identity, stale/wrong receipt, conflicting receipts, unsupported
  evidence ID, scope expansion, partial regression coverage, duplicate edge
  handling, Boolean-as-int traps, unresolved human choice, and tempting
  near-correct implementations.
- Change one layer at a time: host gate, schema, prompt, then decoder.

Exit: all known development failure classes are either deterministically gated
or handled by the model with no false accepts.

### Iteration 5 — untouched validation (50–80 calls)

- Freeze code, schemas, prompts, settings, and routing.
- Evaluate only untouched validation cases.
- Do not repair against these cases inside the same candidate generation.
- Compare model-role candidates using paired cases and report uncertainty.

Exit: only candidates with zero critical false accepts, clean identity/runtime
evidence, high protocol/materialization success, and acceptable false rejects
advance.

### Iteration 6 — blind fixed-runtime qualification

- Seal a fingerprinted runtime and case manifest.
- Use untouched blind cases and repeated calls for reliability diagnostics.
- Exercise verifier and final judge through the full production-shaped DevFlow
  paths, not direct aptitude prompts.
- Persist raw request/response, parsed packet, deterministic gate results,
  actual model, process args, runtime fingerprint, case hash, prompt/schema
  version, decoder settings, seed, duration, tokens, and outcome.
- Have an independent audit sub-agent verify run binding and scoring after the
  batch; the primary agent reproduces key checks.

Exit: produce a role-by-role qualification decision. Do not change production
routing without the human's explicit promotion decision.

Iterations 7–8 are reserved only for a clearly diagnosed issue requiring one
targeted correction and a new untouched validation/blind set. Do not endlessly
tune on the same cases.

## Metrics and promotion gates

For each model-role report:

- critical false accepts (primary; required zero)
- false rejects
- semantic verdict accuracy
- protocol/schema validity
- builder materialization success
- evidence-reference validity
- deterministic host-gate catches
- model-identity and runtime anomalies
- latency and tokens
- repetition/loop behavior
- unique case count and category coverage
- development vs validation vs blind partition

Minimum qualitative gate:

- zero false accepts on all critical validation/blind cases
- zero identity/runtime anomalies
- zero invalid accepted packets
- zero self-approval paths
- deterministic conflicts/missing mandatory evidence cannot be qualified
- verifier/final judge proven through full paths
- sufficient independent case coverage for the strength of claim

A useful model may be assigned only the role it actually proves. High semantic
accuracy with invalid evidence references is not qualified judging. Byte-stable
wrong answers are not reliability. Passing known-good cases while passing
known-bad cases is unsafe, not balanced performance.

## Fine-tuning boundary

Consider LoRA/SFT only if iterations 1–5 show a stable, repeated semantic
failure that schemas, host gates, prompts, and decoding cannot solve. Before
training, require:

- enough clean role-specific examples
- a written target behavior and failure taxonomy
- a frozen untouched validation and blind set
- baseline vs tuned paired evaluation
- catastrophic-regression checks across other candidate roles
- reproducible base model, adapter, template, and inference settings

Do not fine-tune Qwythos v1. Do not use validation/blind examples for training.
Do not fine-tune merely to teach syntax that constrained decoding can enforce.

## Runtime and resumability

Every batch must be serial, bounded, fingerprinted, resumable, and append-only.
Before a call, validate the intended alias/path against `/v1/models` and process
arguments. After a call, persist actual identity and validation. On interruption,
resume only missing call IDs with the same fingerprint. If code, prompt, schema,
model artifact, or decoder setting changes, create a new fingerprint/run; never
mix results.

Use deterministic sandboxes for builder cases. Treat host tests as ground
truth. Keep known-good and known-bad fixtures immutable within a run. Never let
the candidate model write or score its own ground truth.

## Immediate continuation checklist

1. Inspect `git status`, all relevant diffs, current processes, router state,
   port 8088, Ollama residency, and model files/hashes.
2. Verify Qwythos v2 exists at the expected path, byte size, and SHA-256. Verify
   v1 is absent and retired in the registry. Verify router defaults and
   `/v1/models` agree on `qwythos-9b-v2-mini`.
3. Run focused registry/chat/routing tests, full relevant audition tests,
   import proof, CLI help, `git diff --check`, and a stale-context scan.
4. Inspect the ignored historical evidence; never edit completed fingerprints.
5. Delegate independent audits of the case split, schema/gate design, and
   experiment matrix. Prefer `hy3:free` only when worker selection is real and
   visible.
6. Produce a compact written experiment manifest before spending model calls.
7. Begin Iteration 1. Do not start with another unconstrained v1-style batch.

## Do not do these things

- Do not make another Qwythos v1 call.
- Do not inherit v1's capabilities or score into v2.
- Do not tune endlessly on repeated identical cases.
- Do not use one aggregate score or model self-judgment.
- Do not accept Markdown-fenced builder prose as a source patch.
- Do not ask a model to decide deterministic evidence facts.
- Do not run local roles concurrently or start servers blindly.
- Do not enable MTP/speculation until a non-speculative baseline is frozen.
- Do not promote from development results.
- Do not modify production profiles, commit, push, or publish without explicit
  human approval.

At the end of each macro iteration, present the human with: what changed, exact
evidence, failures by taxonomy, cost/time/call count, whether the exit gate was
met, and the smallest justified next experiment. Keep the final decision
explicitly human-owned.
