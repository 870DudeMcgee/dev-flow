# Dev-Flow Workflow Preview

Status: conceptual/reference walkthrough. This document is not an implementation contract. Use [mvp-contract.md](mvp-contract.md), [control-room-mvp.md](control-room-mvp.md), and [devflow-operating-model.md](devflow-operating-model.md) for current authority.

## Purpose

This document provides a conceptual walkthrough of the end-to-end developer experience under the redefined Dev-Flow operating model. It illustrates how a human developer coordinates AI-assisted work with absolute safety, visibility, and control.

---

## The Workflow Lifecycle

```text
  [Human Developer] 
         │ 1. Proposes Goal
         ▼
[Main Chat / Control-Room Agent] (Read-Only)
         │ 2. Decomposes & Generates Spec
         ▼
  [Dev-Flow Kernel] 
         │ 3. Prepares Isolated Workspace & Task Packet
         ▼
   [Worker Agent] (Isolated Executor)
         │ 4. Performs Mutating Work
         ▼
  [Verification Gate] (Dev-Flow Kernel)
         │ 5. Executes Tests & Records Evidence
         ▼
[Main Chat / Control-Room Agent] (Read-Only)
         │ 6. Reviews Handoff vs Evidence & Recommends
         ▼
  [Human Developer] 
         │ 7. Approves & Promotes
         ▼
   [Main checkout] (Safe Integration)
```

---

## Detailed Step Walkthrough

### 1. Goal Initiation
The Human Developer has a goal (e.g., "Add user email verification to the auth flow"). Instead of letting an AI agent run free in the repository, the human describes the goal to the **Main Chat / Control-Room Agent**.

### 2. Planning & Specification
Operating in strict **read-only mode**, the Main Chat Agent:
* Analyzes the workspace architecture, dependencies, and requirements.
* Identifies relevant files, potential hazards, and testing parameters.
* Decomposes the goal into discrete, isolated task specs.
* Proposes a task packet containing the goal, scope, allowed files, and a specific verification command (e.g., `pytest tests/test_auth.py`).

### 3. Workspace Preparation
Once the human developer grants human approval for the task spec, the **Dev-Flow Kernel** instantiates the task:
* Generates the canonical `task.yaml` and append-only `events.jsonl` in `.devflow/tasks/<task_id>/`.
* Prepares an isolated, clean copied scratchpad workspace under `.devflow/workspaces/<task_id>/`.
* Passes a read-only `TaskPacket` projection to the designated worker.

### 4. Bounded Implementation
The **Worker Agent** (which may be a cheap shell process wrapping local tools or an external CLI like Claude Code) is spawned inside the sandbox:
* It mutates **only** the files within `.devflow/workspaces/<task_id>/`.
* It cannot touch the main repository branch, stage changes, commit, or merge.
* Any status updates or logs are piped directly into Dev-Flow's append-only `logs/worker.log`.
* If blocked by ambiguity, the worker raises a structured question to `.devflow/tasks/<task_id>/questions.jsonl` and suspends execution, awaiting a human response.

### 5. Authoritative Verification
Upon worker completion, the **Dev-Flow Kernel** asserts control over the verification gate:
* It runs the configured verification command (e.g. tests) inside the isolated workspace.
* It captures the full stderr/stdout in `logs/verify.log`.
* It writes the outcome status (`passed` / `failed`), exit codes, and durations to `verification.json`.
* If tests pass, the task state is marked `verified` and ready for review.

### 6. Read-Only Review
The **Main Chat Agent** takes the stage to inspect the results:
* Compares the stated goal with the actual changed files in the isolated workspace.
* Audits `logs/verify.log` and `verification.json` to verify the tests actually passed.
* Analyzes `logs/worker.log` for hidden warnings, failures, or sloppy code.
* Packages findings into a PR-style handoff report highlighting blockers, non-blockers, and risks.
* Recommends next safe actions to the human developer.

### 7. Human Promotion Approval
The Human Developer reads the Main Chat Agent's review.
* If unsatisfied, the human rejects promotion and instructs the agent to revise, keeping the main checkout pristine.
* If satisfied, the human triggers the promotion gate (via copying back verified files, applying a patch, or merging). The code is integrated safely.

---

## Core Guarantees

* **Pristine Checkout:** No unverified code ever touches your primary workspace.
* **Radical Visibility:** Every command, edit, log line, and test outcome is recorded durably.
* **Recoverable Failure:** If a worker goes into an infinite loop or writes buggy code, simply delete the task's workspace. Your repository is untouched.
* **Deterministic Verification:** The platform, not the worker, holds the keys to the verification results, preventing deceptive "all tests passed" claims.
