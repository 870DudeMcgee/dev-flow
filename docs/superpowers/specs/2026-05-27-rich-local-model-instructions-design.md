# Design: Rich Local Model Instructions for Bounded Agent Work

**Date:** 2026-05-27  
**Author:** Antigravity (Google DeepMind team)  
**Status:** APPROVED  
**Goal:** Improve output quality of local worker models (e.g., Qwen) inside the Devflow control plane by providing highly detailed role-based system instructions focusing on visual aesthetics, code correctness, and unified diff precision.

---

## 1. Problem Statement
Local model workers (like `qwen2.5-coder`) run state-less tasks (implementation, review, and repair) delegated by orchestrators in the Devflow architecture. The current system instructions in `src/devflow/agents/runner.py` are extremely basic, focusing almost entirely on schema adherence. 

As a result:
1. **Low Visual & Styling Quality:** The local models output default HTML alerts with inline CSS styles and standard colors (e.g., `#e6f7ff`), completely violating the premium dark-mode, glassmorphism theme defined in `public/styles.css`.
2. **Structural "Tag-Soup" Violations:** Small models make layout logic mistakes, leaving tags unclosed or inserting duplicate/malformed tags (e.g. `</nav></header>` closing tags without matching starts).
3. **Sloppy Diffs:** Modifying HTML/CSS blocks sometimes results in malformed unified diff range headers (`@@`) or mismatched surrounding context lines, causing apply failures.

---

## 2. Proposed Solution (Option 1)
Inject rich, Web-First Quality and Git Unified Diff precision protocols directly into the Python orchestrator's inline system prompts. 

Specifically, we upgrade the following three agent prompts inside `src/devflow/agents/runner.py`:
1. `run_implement_agent()` (Implementer role)
2. `_query_repair_model()` (Repair role)
3. `run_review_agent()` (Reviewer role)

---

## 3. Detailed Prompt Specs

### 3.1. Implementer Prompts
We extend the system instruction for the implementer to include the following guidelines:
*   **Web App Aesthetics:** Prioritize premium visual designs (dark modes, glassmorphism, harmonious HSL palettes). Adhere to existing `:root` variables in `styles.css`. Never use basic, unstyled plain components or inline colors.
*   **Structural Cleanliness:** Absolutely prohibit unclosed elements or broken tag blocks (no tag soup).
*   **Unified Diff Protocols:** Strict git header matching, exact character-for-character surrounding context lines, and zero chunk/block truncation.

### 3.2. Repair Agent Prompts
We upgrade the repair agent prompt to focus on:
*   **Root Cause Identification:** Instruct the model to parse the failure taxonomy (e.g., `SYNTAX_ERROR`, `TEST_FAILURE`) to find the precise bug.
*   **Design & Visual Preservation:** Repair bugs while maintaining theme variables, tag closures, and premium CSS.
*   **Clean Diff Application:** Ensure repaired diffs apply cleanly without offset or rejects.

### 3.3. Reviewer Agent Prompts
We upgrade the reviewer agent prompt to enforce:
*   **Quality Gates:** Reviewers must mark any unclosed HTML tags, basic styling, inline colors, or dummy placeholders as `blocking` changes.
*   **Scope & Diff Audits:** Enforce path boundaries (allowed files only) and diff validity.

---

## 4. Verification & Testing
We will verify this change by:
1. Running our full local unit test suite to ensure the JSON parsed schemas, CLI, and mock model generation still work perfectly:
   `PYTHONPATH=src python3 -m unittest discover tests`
2. Conducting a manual verification check on the website code state.
