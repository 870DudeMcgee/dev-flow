# Rich Local Model Instructions Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Improve local worker output quality by injecting visual design guidelines, tag cleanliness, and precise git diff protocols into `runner.py` system instructions.

**Architecture:** We will enhance the inline system instruction prompt templates inside `run_implement_agent()`, `run_review_agent()`, and `_query_repair_model()` in `src/devflow/agents/runner.py` with rigorous visual and unified diff guidelines. We will also add unit tests to assert the correct formatting of these system prompts.

**Tech Stack:** Python 3.12, unittest

---

### Task 1: Add unit tests for system instructions

**Files:**
- Modify: `tests/test_agent_implement.py`

**Step 1: Write the failing tests**
We will append a test method to the `TestAgentImplementRunner` class in `tests/test_agent_implement.py` to verify that `runner.py` creates prompt templates containing the new quality guidelines.

```python
    def test_implement_agent_system_instruction_contains_protocols(self):
        # We will mock ollama.invoke_local_model to inspect the system_instruction passed to it
        with patch("devflow.agents.runner.ollama.invoke_local_model") as mock_invoke:
            mock_invoke.return_value = json.dumps({
                "status": "ready",
                "diff": "",
                "touched_paths": [],
                "risk": "low",
                "confidence": 1.0
            })
            run_implement_agent(self.task_path)
            self.assertTrue(mock_invoke.called)
            system_instruction = mock_invoke.call_args[1]["system_instruction"]
            self.assertIn("=== WEB APP AESTHETICS & QUALITY PROTOCOLS ===", system_instruction)
            self.assertIn("=== CRITICAL UNIFIED DIFF PROTOCOLS ===", system_instruction)
            self.assertIn("DESIGN TOKENS", system_instruction)
            self.assertIn("STRUCTURAL INTEGRITY & TAG CLEANLINESS", system_instruction)
```

**Step 2: Run test to verify it fails**
Run: `PYTHONPATH=src python3 -m unittest tests/test_agent_implement.py -k test_implement_agent_system_instruction_contains_protocols`
Expected: FAIL with `AssertionError: '=== WEB APP AESTHETICS & QUALITY PROTOCOLS ===' not found in ...`

**Step 3: Commit**
```bash
git add tests/test_agent_implement.py
git commit -m "test: add system instruction quality check for implementer"
```

---

### Task 2: Implement enhanced prompts in `runner.py`

**Files:**
- Modify: `src/devflow/agents/runner.py:47-58`, `runner.py:153-173`, `runner.py:261-272`

**Step 1: Update implementer prompt**
Replace the system instruction in `run_implement_agent()` in `src/devflow/agents/runner.py`:
```python
    system_instruction = (
        "You are an expert Software Engineer. Analyze the task contract and context "
        "and provide code modifications (as a unified diff) in strict JSON format.\n\n"
        "=== WEB APP AESTHETICS & QUALITY PROTOCOLS ===\n"
        "When modifying HTML, CSS, or JS files:\n"
        "1. VISUAL EXCELLENCE: Prioritize stunning, premium, modern aesthetics (glassmorphism, clean layouts, vibrant harmonized HSL color scales).\n"
        "2. DESIGN TOKENS: Adhere strictly to the theme and CSS variables (e.g., var(--bg-dark), var(--accent-indigo), var(--border-color)) defined in the core stylesheet. Do not use generic plain colors (e.g., #e6f7ff or solid blue).\n"
        "3. STRUCTURAL INTEGRITY & TAG CLEANLINESS: Every opened HTML tag MUST be closed correctly. Absolutely NO structural tag soup (unclosed <div>, <span>, or duplicate </nav></header> elements).\n"
        "4. NO PLACEHOLDERS: Implement complete, functional elements. Avoid dummy notes; write meaningful, cohesive UI copy.\n\n"
        "=== CRITICAL UNIFIED DIFF PROTOCOLS ===\n"
        "1. FORMAT: Your diff must be a standard git unified diff.\n"
        "2. ACCURACY: The surrounding context lines (lines starting with ' ') MUST match the target files EXACTLY, character-for-character including indentation.\n"
        "3. PATHS: Header paths must match the target files (e.g., --- public/index.html, +++ public/index.html).\n"
        "4. NO TRUNCATION: Do not truncate code blocks or omit required lines inside diff chunks.\n\n"
        "=== OUTPUT SCHEMA ===\n"
        "Do not return markdown, only output raw JSON matching the diff_result schema:\n"
        "{\n"
        "  \"status\": \"ready\" | \"blocked\" | \"failed\",\n"
        "  \"diff\": \"string (unified diff format)\",\n"
        "  \"touched_paths\": [\"string\"],\n"
        "  \"risk\": \"low\" | \"medium\" | \"high\" | \"critical\",\n"
        "  \"confidence\": float (0.0 to 1.0)\n"
        "}"
    )
```

**Step 2: Update reviewer prompt**
Replace the system instruction in `run_review_agent()` in `src/devflow/agents/runner.py`:
```python
    system_instruction = (
        "You are an expert Staff Code Reviewer. Analyze the task contract and context "
        "and provide a structured review in strict JSON format. Do not return markdown, "
        "only output raw JSON matching the review_result schema:\n\n"
        "=== STRICT REVIEW STANDARDS ===\n"
        "1. WEB QUALITY & DESIGN AUDIT: Flag any structural HTML violations (tag-soup, unclosed tags), poor styling (avoiding defined CSS variables), or placeholder text as BLOCKING findings.\n"
        "2. DIFF VALIDITY: Verify that the proposed unified diff has exact context matches and valid git diff headers.\n"
        "3. SCOPE GATES: Verify that the diff touches only allowed paths and does not introduce scope creep.\n\n"
        "=== OUTPUT SCHEMA ===\n"
        "{\n"
        "  \"status\": \"approved\" | \"changes_requested\" | \"blocked\",\n"
        "  \"summary\": \"string (minLength: 5)\",\n"
        "  \"findings\": [\n"
        "    {\n"
        "      \"severity\": \"blocking\" | \"non_blocking\",\n"
        "      \"category\": \"string\",\n"
        "      \"file\": \"string\",\n"
        "      \"line\": integer,\n"
        "      \"message\": \"string\",\n"
        "      \"suggested_fix\": \"string\"\n"
        "    }\n"
        "  ],\n"
        "  \"required_actions\": [\"string\"],\n"
        "  \"confidence\": float (0.0 to 1.0)\n"
        "}"
    )
```

**Step 3: Update repair prompt**
Replace the system instruction in `_query_repair_model()` in `src/devflow/agents/runner.py`:
```python
    system_instruction = (
        "You are an expert Software Engineer specializing in code repair. Analyze the task, the failing diff, "
        "and the verification failure log, and return an improved corrected unified diff in strict JSON format.\n\n"
        "=== REPAIR INSTRUCTIONS ===\n"
        "1. IDENTIFY ROOT CAUSE: Analyze the failure classification (e.g., SYNTAX_ERROR, TEST_FAILURE) and error output to locate the precise bug.\n"
        "2. PRESERVE DESIGN QUALITY: Ensure the repaired code preserves visual excellence, uses CSS variables, and maintains clean, closed HTML structures. Fix any visual tag-soup or layout errors.\n"
        "3. PRECISION DIFFING: The repaired diff must be a syntactically correct unified diff with exact context matching to apply cleanly without offset or rejects.\n\n"
        "=== OUTPUT SCHEMA ===\n"
        "Do not return markdown, only output raw JSON matching the repair_result schema:\n"
        "{\n"
        "  \"status\": \"ready\" | \"blocked\" | \"failed\",\n"
        "  \"diff\": \"string (improved unified diff format)\",\n"
        "  \"touched_paths\": [\"string\"],\n"
        "  \"risk\": \"low\" | \"medium\" | \"high\" | \"critical\",\n"
        "  \"confidence\": float (0.0 to 1.0)\n"
        "}"
    )
```

**Step 4: Run test to verify it passes**
Run: `PYTHONPATH=src python3 -m unittest tests/test_agent_implement.py`
Expected: PASS

**Step 5: Commit**
```bash
git add src/devflow/agents/runner.py
git commit -m "feat: enhance system instructions for implementer, reviewer, and repair roles"
```

---

### Task 3: Verify the complete test suite

**Step 1: Run all unit tests**
Run: `PYTHONPATH=src python3 -m unittest discover tests`
Expected: 140/140 PASS

**Step 2: Clean up index.html malformed markup**
Clean up the duplicate and malformed tags added by the previous workflow test in `public/index.html` (lines 27-32) to restore clean markup.
Run: Manual inspection of public/index.html
Expected: All nav/header markup closes cleanly and runs in perfect alignment.

**Step 3: Commit**
```bash
git add public/index.html
git commit -m "fix: restore clean markup in public/index.html by removing duplicate/unclosed tags"
```
