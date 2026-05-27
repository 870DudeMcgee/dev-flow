# Traces and Evals Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Establish a deterministic, evidence-driven tracing and evaluations framework in devflow to record execution traces, query inner span details, and evaluate role prompt harnesses without live model calls.

**Architecture:**
- Create `src/devflow/traces.py` implementing thread-safe hierarchical span recording.
- Create `src/devflow/evals.py` implementing mock-intercept evaluation runners and fixtures testing.
- Wire into `src/devflow/cli.py` with visual nested span graphs and evaluation metrics reports.

**Tech Stack:** Pure Python 3.12+, standard library, Git.

---

### Task 1: obs-tracing Observability Engine

**Files:**
- Create: `src/devflow/traces.py`
- Create: `tests/test_traces.py`

**Step 1: Write the failing test**
Create `tests/test_traces.py` asserting trace start/finish operations, duration calculations, attribute storage, and thread-local parent-child span nesting.

**Step 2: Run test to verify it fails**
Run: `PYTHONPATH=src .venv/bin/python -m unittest tests.test_traces -v`
Expected: Fail (ModuleNotFoundError / ImportError)

**Step 3: Write minimal implementation**
- Build `traces.py` with `Span` context managers tracking nesting on a thread-local stack.
- Save structured spans to `.devflow/logs/traces/{trace_id}.json`.

**Step 4: Run test to verify it passes**
Run: `PYTHONPATH=src .venv/bin/python -m unittest tests.test_traces -v`
Expected: PASS

**Step 5: Commit**
```bash
git add src/devflow/traces.py tests/test_traces.py
git commit -m "feat: implement Phase 8 nested tracing span engine"
```

---

### Task 2: Deterministic Evals Engine and Seed Fixtures

**Files:**
- Create: `src/devflow/evals.py`
- Create: `tests/test_evals.py`
- Create: `.devflow/evals/README.md`
- Create: `.devflow/evals/fixtures/implementer_paths.json`
- Create: `.devflow/evals/fixtures/reviewer_scope.json`
- Create: `.devflow/evals/fixtures/repair_minimality.json`

**Step 1: Write the failing test**
Create `tests/test_evals.py` asserting loading JSON fixtures, mocking urllib calls to return mock LLM responses, running evaluators, and validating assertions.

**Step 2: Run test to verify it fails**
Run: `PYTHONPATH=src .venv/bin/python -m unittest tests.test_evals -v`
Expected: Fail (ImportError)

**Step 3: Create README, seed files, and write minimal implementation**
- Create README and fixtures under `.devflow/evals/`.
- Build `evals.py` implementing `run_role_eval(role)` which mocks `devflow.agents.ollama.invoke_local_model` dynamically to simulate LLM responses.
- Verify status, touches, and error outcomes.

**Step 4: Run test to verify it passes**
Run: `PYTHONPATH=src .venv/bin/python -m unittest tests.test_evals -v`
Expected: PASS

**Step 5: Commit**
```bash
git add src/devflow/evals.py tests/test_evals.py .devflow/evals/
git commit -m "feat: implement Phase 8 mock-driven evals engine and seed fixtures"
```

---

### Task 3: Plumb Observability CLI

**Files:**
- Modify: `src/devflow/cli.py`
- Modify: `tests/test_cli.py`

**Step 1: Write the failing test**
Add assertions to `tests/test_cli.py` verifying that `devflow trace list`, `devflow trace inspect`, `devflow eval run`, and `devflow eval compare` run and print structured outputs.

**Step 2: Run test to verify it fails**
Run: `PYTHONPATH=src .venv/bin/python -m unittest tests.test_cli -v`
Expected: FAIL (missing command routing)

**Step 3: Write minimal implementation**
- Plumb `trace` and `eval` subparsers in `main()`.
- Add command handlers printing hierarchical span graphs and comparative prompt statistics.

**Step 4: Run test to verify it passes**
Run: `PYTHONPATH=src .venv/bin/python -m unittest tests.test_cli -v`
Expected: PASS

**Step 5: Commit**
```bash
git add src/devflow/cli.py tests/test_cli.py
git commit -m "feat: plumb trace and eval commands in CLI"
```
