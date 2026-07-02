# Task: 027_update_website_for_new_features_workflow_test - Update website for new features (workflow test)
Status: COMPLETED
Goal:
Plan:
Assigned Agent: vscode
Owner Lock: workflow-test
Risk: LOW
Branch: devflow/task-027_update_website_for_new_features_workflow_test-vscode
Touched Files:
- public/index.html
- README.md
-

## 1. Objective

Describe the concrete outcome for this task.

## 2. Allowed Files

- public/index.html
- README.md

## 3. Do Not Touch

- .env
- production secrets
- unrelated files outside Allowed Files

## 4. Required Context

Add relevant architecture notes, file excerpts, or decisions.

## 5. Implementation Instructions

Describe the implementation steps for the owning orchestrator.

## 6. Patch Protocol

Unified diff only.

## 7. Verification Commands

- test -f public/index.html

## 8. Failure Handling

- Patch apply failure: stop and report
- Protected file touched: stop immediately
- Verification failure: rollback and report

## 9. Execution Results

```diff
diff --git a/public/index.html b/public/index.html
--- a/public/index.html
+++ b/public/index.html
@@ -12,3 +12,4 @@
 </head>
 <body>
+    <!-- Workflow Test Update -->
     <header class="header">
```

## 10. Final Report

Pending.
