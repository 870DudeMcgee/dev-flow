# Task DAG and Impact Analysis Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Provide the deterministic Task DAG and Impact Analysis engine in devflow to govern safe coordination, query dependency status, and analyze source code/git history change scopes.

**Architecture:**
- Create `src/devflow/dag.py` to parse task dependencies, detect dependency cycles, query task coordination states, and handle agent queries.
- Create `src/devflow/impact.py` to parse workspace import dependency maps, inspect git commit co-mutations, evaluate risk profiles, and recommend splits.
- Wire into `src/devflow/cli.py` with custom formatting for hierarchical ASCII graphs and impact assessments.

**Tech Stack:** Pure Python 3.12+, standard library, Git.

---

### Task 1: Task DAG and JSON Schema

**Files:**
- Create: `src/devflow/schemas/dag.schema.json`
- Create: `src/devflow/dag.py`
- Create: `tests/test_dag.py`

**Step 1: Write the failing test**
Create `tests/test_dag.py` asserting DAG cycle detection, unblocked ready/next tasks, and graph tree structures.

**Step 2: Run test to verify it fails**
Run: `PYTHONPATH=src .venv/bin/python -m unittest tests.test_dag -v`
Expected: Fail (ModuleNotFoundError / ImportError)

**Step 3: Create schema and write minimal implementation**
- Create `src/devflow/schemas/dag.schema.json`.
- Implement dynamic statuses load by parsing all task markdown files matching the task ID.
- Check dependency trees for cycles using a depth-first search.
- Implement unblocked task selectors and ASCII graph tree generators.

**Step 4: Run test to verify it passes**
Run: `PYTHONPATH=src .venv/bin/python -m unittest tests.test_dag -v`
Expected: PASS

**Step 5: Commit**
```bash
git add src/devflow/schemas/dag.schema.json src/devflow/dag.py tests/test_dag.py
git commit -m "feat: implement Phase 7 Task DAG engine and schema validation"
```

---

### Task 2: Impact Analysis Engine

**Files:**
- Create: `src/devflow/impact.py`
- Create: `tests/test_impact.py`

**Step 1: Write the failing test**
Create `tests/test_impact.py` asserting import scans, git commit co-mutations parsing, and risk calculations.

**Step 2: Run test to verify it fails**
Run: `PYTHONPATH=src .venv/bin/python -m unittest tests.test_impact -v`
Expected: Fail (ImportError)

**Step 3: Write minimal implementation**
- Build `impact.py` with AST/regex scans for import statements matching the allowed/touched files.
- Fetch recent git logs to score co-occurrences of files committed together.
- Extract test targets and calculate risk metrics based on touched counts and public export references.

**Step 4: Run test to verify it passes**
Run: `PYTHONPATH=src .venv/bin/python -m unittest tests.test_impact -v`
Expected: PASS

**Step 5: Commit**
```bash
git add src/devflow/impact.py tests/test_impact.py
git commit -m "feat: implement Phase 7 workspace and git impact analysis engine"
```

---

### Task 3: Plumb CLI Commands

**Files:**
- Modify: `src/devflow/cli.py`
- Modify: `tests/test_cli.py`

**Step 1: Write the failing test**
Add assertions to `tests/test_cli.py` verifying that invoking `devflow task ready`, `devflow task next`, `devflow task graph`, and `devflow impact` works and produces formatted outputs.

**Step 2: Run test to verify it fails**
Run: `PYTHONPATH=src .venv/bin/python -m unittest tests.test_cli -v`
Expected: FAIL (argument parsing errors/missing command routing)

**Step 3: Write minimal implementation**
- Plumb ready, next, graph, and impact subparsers in `main()`.
- Add subcommand handlers and format outputs beautifully.

**Step 4: Run test to verify it passes**
Run: `PYTHONPATH=src .venv/bin/python -m unittest tests.test_cli -v`
Expected: PASS

**Step 5: Commit**
```bash
git add src/devflow/cli.py tests/test_cli.py
git commit -m "feat: plumb task ready, next, graph, and impact commands in CLI"
```
