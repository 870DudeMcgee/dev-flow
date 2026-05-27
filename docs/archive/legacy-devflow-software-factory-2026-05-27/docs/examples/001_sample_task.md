# Task: 001 - Update Sample Text
Status: PENDING
Goal: sample_devflow_goal
Plan: 001_sample.plan.json
Assigned Agent: codex
Owner Lock: 
Risk: LOW
Branch: devflow/task-001-codex
Touched Files:
- sample.txt

## 1. Objective

Update `sample.txt` from `hello` to `hello world`.

## 2. Allowed Files

- sample.txt

## 3. Do Not Touch

- .env
- production secrets
- unrelated files outside Allowed Files

## 4. Required Context

`sample.txt` currently contains:

```text
hello
```

## 5. Implementation Instructions

Apply the embedded unified diff.

## 6. Patch Protocol

Unified diff only.

## 7. Verification Commands

- true

## 8. Failure Handling

- Patch apply failure: stop and report
- Protected file touched: stop immediately
- Verification failure: rollback and report

## 9. Execution Results

```diff
diff --git a/sample.txt b/sample.txt
--- a/sample.txt
+++ b/sample.txt
@@ -1 +1 @@
-hello
+hello world
```

## 10. Final Report

Pending.
