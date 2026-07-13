# DevFlow M4 Max Migration and Operating Handoff

Status: active, temporary **machine-specific** migration evidence

Authority: subordinate to `docs/DEVFLOW_SOURCE_OF_TRUTH.md`. This handoff
records one M1-to-M4 transition; it does not define DevFlow's cross-machine
model architecture, current profile semantics, or universal fleet.

Prepared: July 13, 2026, America/Chicago

Repository: `https://github.com/870DudeMcgee/dev-flow.git`

Implementation checkpoint: `368913637950d169fe47a7ec50990640582172df`
(`Harden deterministic verifier preflight gates`)

This document is the detailed operating handoff for moving active DevFlow work
from the 16 GiB M1 Mac mini to the faster M4 Max. It directly supports the
current local-worker/runtime boundary and should be archived or removed after
the new machine is fully established and a replacement operational handoff is
written.

This file is guidance, not higher authority than current source. On every new
session, re-read current `AGENTS.md`, current source, current tests, current Git
state, and current process state before acting. If this handoff conflicts with
newer committed source, stop and understand the newer work.

## Immediate objective on the M4 Max

Bring up the exact committed DevFlow source safely, reproduce the deterministic
verification baseline without making a model call, install and fingerprint the
machine-local runtime, transfer and independently verify the preserved dogfood
evidence, and only then ask the human which new model or runtime experiment to
authorize.

Do not start by running a model. Do not treat faster hardware as authorization
to resume a stopped prompt-tuning line, qualify a model, change production
routing, or introduce parallel execution before the current single-flight path
has been reproduced on the new machine.

## Read first

From the repository root, read these in order:

```bash
sed -n '1,260p' AGENTS.md
sed -n '1,380p' docs/DEVFLOW_SOURCE_OF_TRUTH.md
sed -n '1,320p' docs/local-worker-policy.md
sed -n '1,520p' docs/M4_MAX_MIGRATION_HANDOFF.md
git status -sb
git log --oneline -8
```

Then orient from the active runtime owners:

```bash
sed -n '1,460p' src/devflow/loop/model_router.py
sed -n '1,280p' src/devflow/loop/models.yaml
sed -n '1,260p' src/devflow/loop/profiles.yaml
sed -n '1,260p' src/devflow/loop/routing.py
sed -n '2260,2545p' src/devflow/loop/execution.py
sed -n '500,720p' src/devflow/loop/local_audition_host_gates.py
sed -n '1,210p' src/devflow/loop/verification.py
```

Do not recover historical code, compatibility layers, deleted dashboards, or
older UI flows. The active runtime surfaces remain:

- `src/devflow/loop/`
- `src/devflow/control_room/`
- `src/devflow/control_room/chat.py`
- `src/devflow/cli.py`

## Product at 30,000 feet

DevFlow is the local operating layer that turns a rough idea into a verified
product implementation:

```text
Idea -> Brainstorm -> Spec -> Plan -> Planning Judge
     -> Assignment -> Build -> Build Judge -> Verify
     -> Next explicit human decision
```

The user owns intent, taste, priority, acceptance, promotion, and final
decisions. DevFlow owns active loop state, bounded work, evidence, deterministic
gates, and the next safe action. Git and the filesystem are source of record.
Hermes supplies messaging, tools, subscription-model transport, and bounded
worker orchestration. Local models are replaceable labor and never silent
authority.

The browser is the unified brainstorm and status surface. It combines a live
status/evidence workspace with brainstorm chat. Interactive status-board state
must survive refresh: selected worker output, expanded/collapsed state, open
artifact, and pane scroll positions cannot reset simply because the page
refreshes.

The main architectural direction is host-owned safety around fallible workers:

- deterministic state transitions;
- bounded assignments and declared file scope;
- persisted requested and served model identity;
- immutable verification receipts with local SHA-256 attestations;
- explicit ownership, cancellation, stalled-owner detection, and lock recovery;
- builder/reviewer separation;
- deterministic final acceptance;
- model judgment only for residual semantic questions that cannot be decided
  from authoritative host facts.

Do not reintroduce a broad dashboard, hidden automation, a model zoo, or a
speculative autonomous software factory.

## Current committed source state

The implementation checkpoint published before this handoff is:

```text
3689136 Harden deterministic verifier preflight gates
fa5ae35 Harden deterministic final decision gates
7c84e71 Add local model audition and retire Qwythos v1
754e9ac feat: harden second five-loop flow
7d3c880 feat: cloud-free-fast fleet, chat evidence + worker-feed hardening
```

The handoff itself is committed after `3689136`; on the M4, use the current
`origin/main` commit containing this file. Never reset back to the checkpoint
merely because its SHA appears here.

At the implementation checkpoint, the verifier change touched only:

- `docs/DEVFLOW_SOURCE_OF_TRUTH.md`
- `docs/local-worker-policy.md`
- `src/devflow/loop/execution.py`
- `src/devflow/loop/local_audition_host_gates.py`
- `src/devflow/loop/pipeline_run.py`
- `tests/test_local_audition_host_gates.py`
- `tests/test_loop_execution.py`
- `tests/test_pipeline_run.py`

The verified full suite contained 533 tests: 531 passed and two intentional
live/runtime skips. Imports, CLI help, the deterministic spine fixture, and
`git diff --check` passed.

## What is already complete

### Deterministic V2 product loop

The V2 stage model, adapters, persistence, orientation, planning judge,
builder/judge records, verification receipts, human decision boundary, CLI,
and deterministic end-to-end fixture are active. The fixture reaches
`complete` and persists a final-decision receipt.

### Browser control room and brainstorm

The control room presents active runs, a focused workspace, chronological
activity, source evidence, artifacts, Git identity, and system diagnostics.
Brainstorm sessions share the same filesystem layer as Hermes and create
pipeline runs at the idea stage.

### Bounded builder materialization

A builder packet may touch at most six declared files. Multi-file output must
be a complete unified diff, is checked before application, and is materialized
into an isolated run workspace. The manifest records the workspace,
`changed_files`, `declared_target_files`, and patch path. Judges inspect the
materialized result rather than trusting prose that claims code was built.

### Reliability and receipt integrity

Verification receipts are immutable by receipt ID and receive local SHA-256
attestations. The reliability layer fails closed on receipt tampering,
unexpected routing changes, replayed/concurrent role events, missing actual
model identity, builder/reviewer family overlap, unresolved ownership, and
provider faults beyond the configured threshold.

The attestation boundary detects accidental or single-file modification inside
the local trust boundary. It is not cryptographic proof against an attacker who
can rewrite both a receipt and its attestation.

### Deterministic final-decision classifier

The host, not a final-judge model, decides final acceptance. Typed test, review,
reliability, identity, artifact, authoritative-receipt, mandatory-choice, and
required-product-gate inputs are normalized before global precedence.

The human-approved precedence is frozen:

1. unresolved mandatory human choice -> block;
2. independent uncontradicted failure -> block, even if another gate conflicts;
3. authoritative conflict -> hold;
4. missing mandatory evidence -> hold;
5. every explicit mandatory gate passing -> qualify.

A later model may summarize an already committed host receipt, but that summary
is optional, non-authoritative, and cannot change or delay the decision.

### Deterministic verifier preflight

The latest implementation removes three mechanically decidable facts from
verifier-model authority. Before a verifier model is even resolved, the host
evaluates workspace tests, the current persisted build-judge decision, and
exact materialized manifest scope.

The frozen verifier matrix is:

| Gate | Persisted fact | Host outcome | Model allowed |
| --- | --- | --- | --- |
| Tests | exact nonnegative integers; exit `0`, failed `0`, errors `0` | passed | only if other gates pass |
| Tests | nonzero, negative, Boolean, missing, malformed, failed, or error | failed | no |
| Prior review | `passed` | passed | only if other gates pass |
| Prior review | `failed` or `blocked` | failed | no |
| Prior review | `needs_review`, missing, malformed, or unknown | needs review | no |
| Scope | unique nonempty safe relative paths; normalized sets exactly equal | passed | only if other gates pass |
| Scope | both valid but sets differ in either direction | failed | no |
| Scope | missing/malformed list, duplicate, empty, absolute, traversal, or non-string | needs review | no |

Combination precedence is also frozen:

1. any explicit failure -> verification `failed`;
2. otherwise any missing/malformed/needs-review evidence -> `needs_review`;
3. only three explicit passes -> verifier model may judge remaining Definition
   of Done semantics.

Every bypass receipt uses:

```text
command: verifier (deterministic host gates)
exit_code: 1
```

It records every ordered host finding, names no configured or actual model,
emits no fake verifier model event, persists a receipt and attestation, and
remains at the verification stage. Tests replace both `resolve_role_slot` and
`run_role` with raising stubs on bypass paths, proving neither model resolution
nor dispatch occurs.

Malformed JSON evidence is retained as inspectable raw text by the pipeline
loader so the relevant lifecycle gate can classify it instead of making the
entire run unreadable before fail-closed handling.

## Why the host-gate work was necessary

Small models repeatedly demonstrated that valid JSON is not the same as a safe
decision. The decisive verifier failure occurred after passing tests and a
persisted failed review. Qwythos v2 returned `passed`, reasoning that the test
result overrode the failed independent review. Tests and review are separate
mandatory gates; neither silently supersedes the other.

The correct product response was not another prompt. It was to move review
normalization and scope equality into deterministic host code. This pattern is
central to future work: whenever a fact can be decided from authoritative
structured evidence, prefer host ownership over spending model judgment.

## Model-line chronology and hard stops

### Initial five-iteration dogfood batch

The July 12 batch established that all three local workers could participate in
real DevFlow paths, but it did not qualify a role. Qwythos was verbose and
missed an edge case as builder. Qwen produced two verified builds but needed
revision and frequently emitted forbidden fences. Ornith found real defects but
hit token caps. Only the last run passed the persisted reliability gate.

### Fixed-runtime qualification batch

The 69-call batch used three repetitions per ground-truth case, temperature
`0.0`, and reasoning disabled. Repetitions were byte-identical, which showed
fixed-runtime consistency rather than independent sampling.

No tested model-role qualified:

| Model and role | Result | Main failure |
| --- | --- | --- |
| Qwen planner | 0/9 | invalid packet or target-file relationship |
| Qwen builder | 0/9 | forbidden Markdown fences |
| Ornith planning judge | 9/12 | exact evidence-reference failures |
| Qwythos v1 build judge | 6/15 | false-passed all nine bad cases |
| Qwythos v1 verifier aptitude | 6/12 | missing identity/conflict errors |
| Ornith final-judge aptitude | 6/12 | qualified missing identity; mishandled human choice |

### Iteration 1 and Iteration 2 development screens

Iteration 1 added native JSON-Schema contracts and deterministic gates, but
Qwen builder passed only one of three behavioral cases. An independent audit
found planner defects that the first scorer had missed, plus evaluator wiring
problems. No result transferred capability credit.

The 92-call Iteration 2 prompt screen had clean runtime evidence but no Qwen
builder prompt passed all required behavioral cases. The 24-call correction
also failed its exit gate. Qwen builder prompt-only tuning is stopped; changing
hardware does not reopen that decision.

### Ornith final-judge screens

Ornith often reached the right verdict but selected incompatible fixed human
instructions, mishandled authoritative conflict, held instead of blocking an
unresolved mandatory choice, and false-qualified an explicit failed review.
Prompt/decoder tuning for this line is stopped. The durable response was the
deterministic final-decision classifier.

### Qwythos v2 verifier screens

Four terminal attempts exist. Never splice them into one score or resume an
output directory.

| Attempt | Execution fingerprint | Result | External seal SHA-256 |
| --- | --- | --- | --- |
| Initial real-path | `1a1234e59f8ef6f2dfe265564e831badc294e3a842a92add5b150e247d83bb2f` | preparation rendered wrong repository inventory | `de7a317c997d72db29f268265c10d73297de9af2146b15e7b23bd2d6db179fcc` |
| Corrected inventory | `e7c0674c9f0bff4693f0916e9cf4270ba2fcce6aa53cf230cc8e027a5c1bd0e4` | evaluator ground-truth label defect | `cccf8fbf4e61ce76ebb02548b43e61382fbeb08a7c13ba2682c5605063363d3b` |
| Corrected ground truth | `bc56e32cb0d7cee56d9a951b3b9219d19820f20e9370ebfc04d995977d00bad9` | disk reached 100% during call two | `80907874e4261dc8e95f76b387bdf02b819adf13a6f775a1aa8e322f8ad6ab00` |
| Disk-protected resilient | `b340ca8d743f79f02298dd59504f4b05dd62d5df41f13c64252e813c4a80aada` | four clean calls; critical false accept on failed review | `c341f340e6233bb894e28096ca9d0b8d2adbd68cf787e165ed6809f55d9e86d5` |

The resilient run produced two correct good-case passes, one correct failure for
a missing required regression, and one unsafe pass for a persisted failed
review. That one critical false accept is decisive. Qwythos v2 is not qualified
for verifier. Do not rerun its verifier prompt or decoder line.

### Binding hard stops

- Qwythos v1 is retired, absent, and must not be restored, downloaded, run,
  tuned, benchmarked, or credited.
- Qwen builder prompt-only tuning is stopped.
- Ornith final-judge prompt-only tuning is stopped.
- Qwythos v2 verifier prompt/decoder tuning is stopped.
- No local model has production capability from these screens.
- Host containment does not retroactively qualify a contained model.

Faster hardware justifies broader candidate search, independent repetitions,
and different intervention classes. It does not justify repeating a stopped
line faster.

## Source transfer versus laboratory transfer

A Git clone transfers tracked source, tests, registry, profiles, active docs,
and this handoff. It does not transfer most operational evidence or machine
runtime.

The repository ignores `/.devflow/`. Therefore a clone does not include:

- current pipeline runs and receipts;
- verifier preparation/run directories;
- sealed dogfood evidence;
- the fresh-session handoff under `.devflow/dogfood/`;
- runtime locks;
- local model files;
- the Python virtual environment;
- the external Hermes model-router script;
- authentication, API keys, or shell environment.

One older file,
`.devflow/dogfood/DEVFLOW_LOCAL_MODEL_TUNING_FRESH_SESSION_HANDOFF.md`, is
already tracked despite the ignore rule. Do not infer that the rest of
`.devflow/` is present in Git.

The migration must therefore use two independent channels:

1. GitHub for product source;
2. a byte-preserving archive or `rsync -a` transfer for selected ignored
   evidence and external runtime files.

Do not commit the raw laboratory archive to `main` merely to move machines.

## Preserved evidence to copy byte-for-byte

Copy at least these terminal run directories:

```text
.devflow/dogfood/local-verifier-full-path-qwythos-v2-run/
.devflow/dogfood/local-verifier-full-path-qwythos-v2-corrected-run/
.devflow/dogfood/local-verifier-full-path-qwythos-v2-final-run/
.devflow/dogfood/local-verifier-full-path-qwythos-v2-resilient-run/
.devflow/dogfood/local-tuning-iteration2-correction/
.devflow/dogfood/local-tuning-iteration2-final-judge-rescreen/
.devflow/dogfood/local-tuning-iteration2-final-judge-rescreen-v3/
.devflow/dogfood/local-tuning-iteration2-final-judge-clean/
```

Also copy the four verifier preparation directories:

```text
.devflow/dogfood/local-verifier-full-path-qwythos-v2-prepared-v2/
.devflow/dogfood/local-verifier-full-path-qwythos-v2-prepared-v3/
.devflow/dogfood/local-verifier-full-path-qwythos-v2-prepared-v4/
.devflow/dogfood/local-verifier-full-path-qwythos-v2-prepared-v5/
```

Copy the ignored fresh-session handoff for chronology:

```text
.devflow/dogfood/DEVFLOW_DETERMINISTIC_VERIFIER_GATES_FRESH_SESSION_HANDOFF.md
```

The protected earlier evidence seals are:

| Directory | External seal SHA-256 |
| --- | --- |
| `local-tuning-iteration2-correction` | `59a707d2fa865fc2b928639c58d7fbc3893252b21bafa4ab1fd211d1a465cf17` |
| `local-tuning-iteration2-final-judge-rescreen` | `3d745f3949bc8fc229f5af3314015d8507a633d3b1e811f5b9e022e6c98a654d` |
| `local-tuning-iteration2-final-judge-rescreen-v3` | `8674890f26616849b38dd2110ccb623ea991fcd07487f4acada465753c52f75b` |
| `local-tuning-iteration2-final-judge-clean` | `16d9937cea03f35f90ff9bf0fa5ba74bb94868e0e566a7222973a4659da28df9` |

At handoff preparation, all eight seal-file hashes matched the values above and
the verifier table. Every file named inside every seal matched both expected
byte count and SHA-256 with zero mismatches.

### Safe evidence transfer procedure

Stop all DevFlow writers before copying. Prefer a byte-preserving archive or
`rsync -a`. Do not copy a live output directory while an experiment is running.

After transfer, first verify the eight external seal hashes. Then verify every
file named inside each seal. A compatible zsh verification shape is:

```bash
for seal in .devflow/dogfood/*/evidence-seal.json; do
  dir=${seal:h}
  count=0
  bad=0
  while IFS=$'\t' read -r expected_hash expected_bytes name; do
    count=$((count + 1))
    file_path="$dir/$name"
    actual_hash=$(shasum -a 256 "$file_path" | awk '{print $1}')
    actual_bytes=$(stat -f %z "$file_path")
    if [[ "$actual_hash" != "$expected_hash" || "$actual_bytes" != "$expected_bytes" ]]; then
      bad=$((bad + 1))
    fi
  done < <(jq -r '.files | to_entries[] | [.value.sha256, (.value.bytes|tostring), .key] | @tsv' "$seal")
  printf '%s files=%d mismatches=%d\n' "$dir" "$count" "$bad"
done
```

Do not use `path` as a zsh loop variable; zsh treats `path` as the tied array
for `PATH`, which can make commands disappear during the verification shell.

If any seal, byte count, or content hash differs, stop. Do not repair,
regenerate, or reseal the directory. Preserve the received bytes and determine
whether the transfer or source archive was wrong.

## Current Mac mini runtime fingerprint

This information is comparison evidence, not a requirement that the M4 match
the old machine exactly.

| Item | Current Mac mini value |
| --- | --- |
| Hardware | Apple Silicon M1 Mac mini, 16 GiB unified memory |
| OS | macOS 26.5.1, build `25F80` |
| Kernel | Darwin `25.5.0`, arm64 |
| Python | `3.14.5` |
| llama.cpp server | `/opt/homebrew/bin/llama-server` |
| llama.cpp version | `9810 (2f18fe13c)` |
| Router | `~/.hermes/scripts/model-router` |
| Router SHA-256 | `9c1fd277de7d224ce688fea353f5d273139c1887f91b1f06f9925f40036032b9` |
| Shared endpoint | `http://127.0.0.1:8088` |
| Context | `8192` |
| llama parallel slots | `1` |
| GPU layers | `99` |
| Cache RAM | `512 MiB` |
| Startup timeout | `180 seconds` |

The old machine had approximately 7.2 GiB free on `/` at final inventory.
Disk free space varied materially under APFS and previously reached 100% during
a verifier run. Always run a fresh disk preflight; never rely on the handoff's
free-space observation.

At handoff preparation:

- model router reported stopped;
- port 8088 had no listener;
- no `llama-server` process existed;
- Ollama had no resident model;
- `.devflow/runtime/locks/local-model/global.lock` was absent.

No model server was started to prepare this handoff.

## Local model artifacts

The active small-model files on the Mac mini were:

| Registry model | Local file | Bytes | SHA-256 | Status |
| --- | --- | ---: | --- | --- |
| Qwen 2.5 Coder 7B Q4_K_M | `~/models/qwen2.5-coder-7b-q4_k_m.gguf` | 4,683,074,048 | `60e05f2100071479f596b964f89f510f057ce397ea22f2833a0cfe029bfc2463` | provisional; builder prompt-only line stopped |
| Qwythos-9B v2 Q4_K_M | `~/models/qwythos-9b-v2-q4_k_m.gguf` | 5,736,063,744 | `c0a588704f422b713eca29b2c1f192ae6f69aea3f9e7cb64f9ecdb76ff7a85f4` | structured-output audition only; verifier line stopped |
| Ornith 1.0 9B Q4_K_M | `~/models/ornith-9b-q4_k_m.gguf` | 5,629,108,704 | `5720d1f671b4996481274fffe01868c3c36e87c135cc8538471cc7bd6087b106` | provisional review use; final-judge line stopped |

Downloading fresh copies on the M4 is acceptable only when the files match the
intended model/version and the new artifact hashes are recorded. If a fresh
download does not match the old hash, it is a different runtime artifact. Do
not call it an exact reproduction; bind it into a new fingerprint.

Do not download Qwythos v1. Its historical registry entry is retired and
unavailable by design.

## Router behavior and portability

The router is not in Git. It is an external Hermes script and must be copied or
recreated deliberately. The current script:

- supports only port `8088`;
- starts exactly one `llama-server` with `--parallel 1`;
- swaps models by environment-selected path and alias;
- validates health and `/v1/models` identity;
- refuses an unowned or unhealthy port;
- refuses to start while an Ollama model or another `llama-server` is resident;
- records its PID and log under `~/.hermes/runtime/local-models/8088/`;
- refuses automatic SIGKILL when graceful shutdown exceeds 30 seconds.

The environment variables used by the router include:

```text
DEVFLOW_MODEL_RUNTIME_DIR
LLAMA_SERVER_BIN
MINI_MODEL_DIR
MINI_QWEN_MODEL_PATH
MINI_MODEL_ALIAS
MINI_MODEL_CONTEXT
MINI_MODEL_CACHE_RAM_MIB
MODEL_START_TIMEOUT_SECONDS
```

`MINI_QWEN_MODEL_PATH` is a historical variable name; it currently selects any
of the small local model files, including Qwythos v2 or Ornith.

The in-repository runtime also holds one global lock at:

```text
.devflow/runtime/locks/local-model/global.lock
```

That lock intentionally serializes every local model role in one checkout. A
faster M4 does not automatically create parallel model lanes.

## Clean M4 source bootstrap

Clone and verify source before installing or starting models:

```bash
git clone https://github.com/870DudeMcgee/dev-flow.git
cd dev-flow
git switch main
git pull --ff-only origin main
git status -sb
git log --oneline -5
```

Create an isolated environment. Python 3.11 or newer is supported; record the
exact interpreter used in future experiment fingerprints.

```bash
python3 -m venv .venv
.venv/bin/python -m pip install --upgrade pip
.venv/bin/python -m pip install -e '.[dev]'
```

Before any model setup, run:

```bash
PYTHONPATH=src .venv/bin/python -m pytest -q
PYTHONPATH=src .venv/bin/python -c 'import devflow.loop.execution, devflow.loop.local_audition_contracts, devflow.loop.local_audition_host_gates; print("imports-ok")'
PYTHONPATH=src .venv/bin/python -m devflow.cli --help
PYTHONPATH=src .venv/bin/python -m devflow.cli loop spine-fixture --json
git diff --check
git status -sb
```

Expected deterministic result at this handoff is 533 collected, 531 passed,
and two intentional skips. A different Python or browser environment may alter
which live/runtime tests skip, but any failure must be understood before model
work begins.

Known non-failing warnings at handoff:

- one `datetime.utcnow()` deprecation warning in
  `tests/test_loop_builder_judge.py`;
- Pydantic serializer warnings in `tests/test_v2_brainstorm.py`.

Do not turn those warnings into migration scope creep.

## Deployment profiles and machine-specific configuration

The model registry describes targets; it never grants a role. Role assignment
comes from role capability requirements, deployment profiles, and explicit
audition overrides.

Important environment variables:

```text
DEVFLOW_PROFILE
DEVFLOW_MODELS_YAML
DEVFLOW_PROFILES_YAML
DEVFLOW_AUDITION_OVERRIDES
DEVFLOW_AUDITION_DISABLE_THINKING
DEVFLOW_AUDITION_DISABLE_THINKING_ROLES
DEVFLOW_AUDITION_ROLE_TOKEN_BUDGETS
```

The current `mini-baseline` profile uses Qwen locally for bounded building,
Ornith locally for build review, and subscription models for planning,
verification, final judgment, and brainstorm. Auditions may explicitly route an
unqualified model to a role for a frozen test; this does not grant capability
or change production routing.

For machine-specific endpoints, prefer an external registry through
`DEVFLOW_MODELS_YAML` rather than editing tracked production truth merely to
match one workstation. Record the exact external registry bytes in every new
experiment fingerprint.

Never put credentials in the registry, profile, handoff, Git, or evidence
archive. Hermes OAuth and any OpenRouter key must be configured through the
approved local credential mechanism.

## Standard working workflow

The primary agent should work in this order:

1. Read `AGENTS.md` and the source of truth.
2. Inspect current Git status and preserve unrelated work.
3. Read the exact source and focused tests that own the requested behavior.
4. Check current process, router, lock, and disk state before any live model
   operation.
5. State assumptions and a bounded plan to the human.
6. Use `rg` or `rg --files` for source discovery.
7. Use `apply_patch` for intentional file edits.
8. Run focused tests first.
9. Inspect the diff and run `git diff --check`.
10. Run the full relevant proof, including imports, CLI help, and the spine
    fixture before declaring completion.
11. Recheck runtime cleanliness and Git state.
12. Do not commit, push, publish, promote, open a PR, or change routing without
    explicit human approval.

Commentary updates should keep the human informed during tool-heavy work. The
final report must be self-contained and include changed files, behavioral
result, real command evidence, runtime state, Git state, and the smallest next
human decision.

Diagnose requests are read-only unless the human also asks for a fix. Change or
build requests authorize bounded implementation and proportionate verification,
not unrelated infrastructure changes.

## Sub-agent operating model

No sub-agent was used for the deterministic verifier-gate implementation. The
task was bounded to one owner and overlapping edits would have increased
integration risk. Do not claim that a sub-agent or a particular model was used
when it was not.

Use sub-agents only when the human or applicable repository/skill instructions
authorize delegation and the slice is concrete, bounded, and independently
useful. The primary agent always owns integration and proof.

Good delegated slices include:

- read-only audit of one sealed evidence directory;
- independent verification of expected hashes or call-set transitions;
- focused review of one source module against one frozen contract;
- one non-overlapping test file or implementation slice;
- stale-context scan of active documentation;
- independent ground-truth review before a new experiment is bound;
- runtime inventory that does not start, stop, or mutate a service.

Poor delegated slices include:

- “understand the whole repo”;
- multiple agents editing the same source owner;
- letting one agent change ground truth while another scores calls;
- letting a builder judge its own output;
- letting an agent start a model blindly;
- delegating final integration or the completion claim;
- delegating required reading of a selected skill's `SKILL.md` from the primary
  agent.

All agents share one filesystem in the current Codex collaboration model. An
edit made by one agent becomes immediately visible to every other agent.
Therefore:

1. assign non-overlapping files or read-only work;
2. tell each agent the exact evidence and acceptance criteria;
3. avoid simultaneous formatters or bulk rewrites;
4. require the agent to report commands, findings, and files touched;
5. inspect every returned diff locally;
6. run integrated tests from the primary agent;
7. keep the primary responsible for user-facing conclusions.

When the orchestration surface exposes model or cost selection, prefer the
cheapest capable worker. If the surface does not expose that control, do not
imply a model was deliberately selected.

The current Codex environment may expose four concurrency slots including the
primary agent, but the M4 session must inspect its own available concurrency.
Agent concurrency is separate from local-model runtime concurrency: four
software agents do not mean four GGUF servers may safely run.

## Skills and specialized workflows

When a task matches an available skill or names one explicitly, the primary
agent must read that skill's complete `SKILL.md` before acting, announce why it
is being used, and follow its workflow. Relevant examples include GitHub
publishing, OpenAI documentation, data analysis, documents, browser control,
and product design.

For GitHub publishing, inspect scope, stage explicit intended files, verify the
diff, commit intentionally, and push only with human authorization. Direct
pushes to `main` are allowed only when the human explicitly requests them. Do
not silently sweep ignored evidence, models, credentials, or unrelated changes
into a commit.

## Experiment workflow

Every future model experiment must be ground-truth-first and fingerprinted
before the first call.

1. Freeze the objective and whether the run is development, aptitude, or
   production-path qualification.
2. Freeze case IDs, exact ground truth, required evidence, call order, repeat
   count, token budgets, decoder settings, reasoning settings, stop rule, and
   output directory.
3. Audit the ground truth independently before binding the run.
4. Fingerprint the harness, scorer, tests, manifest, prompts, schemas, runtime
   source, model artifact, llama binary, router, external registry/profile,
   Python, and platform.
5. Persist binding intent and run binding atomically before the first call.
6. Preflight disk, memory, process ownership, ports, locks, router health, and
   served identity.
7. Persist actual request, requested model, served model, pre/post runtime
   snapshots, usage, output, and protocol/semantic result for every call.
8. Hard-stop on runtime drift, request mismatch, identity mismatch, scorer or
   ground-truth defect, infrastructure failure, or the frozen critical
   false-accept rule.
9. Never rerun a semantic miss under the same fingerprint.
10. Independently audit exact call sets, transitions, hashes, requests,
    identity, totals, and shutdown.
11. Write the audit before sealing.
12. Seal the terminal directory and record the seal-file hash outside the
    directory.

Do not reconstruct missing output. A start without a terminal event is partial
evidence, not permission to infer what the model would have returned.

Do not compare or combine results across fingerprints as if they were one run.
Do not grant production capability from one score, one good case, self-judged
output, a run with reliability breaches, or a model that is merely contained by
host gates.

## Safe M4 model-runtime bring-up

After deterministic source verification and evidence transfer:

1. Install or build llama.cpp and record the exact binary path, version, and
   SHA-256.
2. Copy or recreate the router and compare its bytes to the old router only if
   exact reproduction is intended.
3. Install one model first, not all models plus a new scheduler at once.
4. Verify the GGUF hash and byte count.
5. Confirm no port listener, Ollama resident model, llama process, or DevFlow
   lock exists.
6. Start the one approved model through the router.
7. Verify `/health` and `/v1/models` report the expected alias.
8. Run a non-semantic infrastructure smoke test only if the human has
   authorized a model call.
9. Stop the router and prove port/process/Ollama/lock cleanup.
10. Repeat for other model artifacts.

Approved read-only preflight shape:

```bash
~/.hermes/scripts/model-router status 8088
lsof -nP -iTCP:8088 -sTCP:LISTEN
ps ax -o pid=,command= | awk '/[l]lama-server/ {print}'
ollama ps
ls -l .devflow/runtime/locks/local-model/global.lock
/bin/df -h /
```

Expected clean outputs are stopped router, no listener, no llama process, no
resident Ollama model, and absent lock. `lsof` and `ls` commonly exit nonzero
when the expected resource is absent; interpret their actual output rather than
mistaking an expected absence for a product failure.

## Parallel local-model lanes: current boundary

The existing runtime is intentionally single-flight:

```text
all local roles
      -> one repository-global lock
      -> one external router
      -> port 8088
      -> one resident llama-server with --parallel 1
```

The current external router rejects every port except 8088 and refuses to run
while any other llama-server or Ollama model is resident. The repository lock
also serializes local roles even if additional ports are started manually.

Do not create parallelism by starting unowned servers, using separate clones to
evade the lock, or deleting the lock while an owner is active. Those approaches
destroy the ownership and evidence guarantees that the qualification workflow
depends on.

## Recommended parallel-lane architecture on M4

Parallel lanes are a justified future optimization, but they are a separate
runtime implementation with its own tests and human approval.

A safe target shape is:

```text
Qwen lane       -> explicit port -> owned process group -> lane lock
Ornith lane     -> explicit port -> owned process group -> lane lock
Candidate lane  -> explicit port -> owned process group -> lane lock
                                         |
                              experiment coordinator
                                         |
                   isolated call journals and output directories
```

Required design properties:

- explicit lane identifiers and ports;
- one authoritative owner per lane;
- per-lane lock plus a machine-level capacity/admission check;
- exact requested/served identity per call;
- PID/process-group ownership and bounded cancellation;
- no shared output directory between parallel workers;
- no concurrent mutation of one pipeline run unless persistence is explicitly
  made concurrency-safe and tested;
- independent append-only start/terminal journals;
- deterministic aggregation after all assigned calls finish;
- disk and unified-memory headroom thresholds;
- builder/reviewer family separation across lanes;
- no shared model judging its own build;
- runtime snapshots that show every simultaneously resident model;
- tests for port collision, stale owner, cancellation, partial failure, replay,
  identity drift, and shutdown cleanup.

The M4 memory size is not recorded in this handoff. Do not infer safe capacity
from GGUF byte sizes alone. Measure weights, KV cache, prompt context, process
overhead, and APFS headroom. Begin with serial reproduction, then two lanes,
then consider a third only after observed memory and thermal behavior are safe.

The best first parallel workload is independent read-only aptitude calls with
separate output directories. Do not begin with multiple builders writing one
workspace or a parallel production-path run.

## Suggested M4 sequence

Phase 1: source reproduction

1. Clone `main`.
2. Read authority and this handoff.
3. Create `.venv` and install `.[dev]`.
4. Run all deterministic verification.
5. Confirm a clean Git worktree.

Phase 2: evidence migration

1. Copy selected ignored evidence separately.
2. Verify all external seal hashes.
3. Verify every sealed file's byte count and SHA-256.
4. Keep terminal directories immutable.

Phase 3: serial runtime reproduction

1. Install llama.cpp and fingerprint it.
2. Install/copy router and fingerprint it.
3. Install one approved model artifact and verify it.
4. Reproduce clean start, identity, one authorized infrastructure call, stop,
   and cleanup.
5. Repeat one model at a time.

Phase 4: establish M4 performance baseline

1. Use new output directories and fingerprints.
2. Measure load time, prompt evaluation, generation, peak memory, disk writes,
   and shutdown.
3. Do not grant semantic capability from performance measurements.

Phase 5: parallel-runtime implementation, only after human approval

1. Write a bounded design against the required properties above.
2. Add mocked runtime and ownership tests before real servers.
3. Implement per-lane resources without weakening final safety gates.
4. Run two-lane infrastructure-only verification.
5. Recheck reliability reporting and evidence aggregation.

Phase 6: new candidate screen

1. Human chooses candidate and role.
2. Freeze a new casebook and fingerprint.
3. Prefer a different candidate or intervention class over stopped tuning
   lines.
4. Run a small development screen before any production-path claim.

## Stop and ask the human before

- making any model call not already authorized;
- screening a verifier or final-judge candidate;
- changing production profiles or default routing;
- changing verifier or final-decision precedence;
- treating a failed review as superseded without explicit lineage;
- changing from single-flight to parallel local runtime;
- selecting ports, concurrency, or memory thresholds for parallel lanes;
- fine-tuning a model;
- changing intervention class for a stopped builder line;
- recovering historical code or artifacts;
- mutating or resealing terminal evidence;
- committing, pushing, publishing, promoting, or opening a PR.

Do not stop merely because implementation is difficult. Exhaust bounded
read-only inspection, deterministic tests, pure helpers, mocked transports, and
safe alternatives first.

## Prohibitions

- Do not revive Qwythos v1.
- Do not rerun Qwythos v2 verifier prompt/decoder experiments automatically.
- Do not resume Qwen builder or Ornith final-judge prompt-only tuning.
- Do not claim a model is qualified because host gates contain it.
- Do not let passing tests override failed review.
- Do not let a model decide exact manifest list equality.
- Do not label host-only receipts with a model that never ran.
- Do not silently treat missing or malformed evidence as passing.
- Do not splice results across fingerprints.
- Do not reconstruct interrupted output.
- Do not mutate sealed evidence.
- Do not start local servers blindly.
- Do not bypass ownership locks to manufacture concurrency.
- Do not commit models, secrets, `.venv`, or the raw dogfood archive to Git.
- Do not push without explicit human authorization.

## Definition of successful M4 migration

The migration is complete only when:

- current `origin/main` is checked out with no unexplained local changes;
- the full deterministic suite passes;
- imports, CLI help, and spine fixture pass;
- copied sealed evidence has zero hash/byte mismatches;
- llama binary, router, Python, OS, registry/profile, and model artifacts are
  fingerprinted;
- router/port/process/Ollama/lock state can be proven clean;
- at least one authorized serial lane can start, report exact served identity,
  stop, and clean up;
- no stopped model line was resumed;
- no model capability or production routing was silently changed;
- the human is given the next explicit decision before semantic screening or
  parallel-runtime work begins.

## Required report from the first M4 session

Report:

- checked-out commit and Git status;
- OS, architecture, memory, disk, Python, llama, and router fingerprints;
- exact model files installed, byte counts, and SHA-256 values;
- deterministic focused/full test results;
- imports, CLI help, spine fixture, and `git diff --check` results;
- evidence directories copied and seal verification totals;
- router, ports, processes, Ollama, and lock state;
- whether any real model call occurred;
- whether any source or evidence file changed;
- any mismatch from this handoff;
- the smallest next human decision.

## Smallest next human decision

After serial M4 reproduction succeeds, ask the human to choose one of:

1. keep verifier assignment unqualified and implement/test the parallel-lane
   runtime first; or
2. keep the runtime single-flight and authorize a separately fingerprinted
   development screen of a different verifier candidate.

Do not automatically rerun Qwythos v2. Do not treat the M4 migration itself as
model qualification.
