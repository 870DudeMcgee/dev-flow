# Task: 001 - Integrate local agent runner
Status: CLAIMED
Goal: antigravity_integration_spike
Plan: 001_test_project.plan.json
Assigned Agent: antigravity
Owner Lock: antigravity-session-001
Risk: LOW
Branch: devflow/task-001-antigravity
Touched Files:
- scripts/local_agent_runner.py
- tests/test_local_agent.py

## 1. Objective

Integrate a safe, lightweight runner utility `scripts/local_agent_runner.py` that queries the local `qwen2.5-coder:1.5b` model via Ollama HTTP API, along with its mock-based unit tests.

## 2. Allowed Files

- scripts/local_agent_runner.py
- tests/test_local_agent.py

## 3. Do Not Touch

- .env
- production secrets
- unrelated source files

## 4. Required Context

- Ollama is healthy and runs on `http://127.0.0.1:11434`.
- Model `qwen2.5-coder:1.5b` is downloaded.

## 5. Implementation Instructions

Write the implementation and unit test scripts as a standard Python module and run it through devflow.

## 6. Patch Protocol

Unified diff only.

## 7. Verification Commands

- PYTHONPATH=src python3 -m unittest tests/test_local_agent.py

## 8. Failure Handling

- Rollback on failure.

## 9. Execution Results

```diff
diff --git a/scripts/local_agent_runner.py b/scripts/local_agent_runner.py
new file mode 100644
--- /dev/null
+++ b/scripts/local_agent_runner.py
@@ -0,0 +1,30 @@
+import json
+import urllib.request
+import urllib.error
+import sys
+
+def generate_text(prompt: str) -> str:
+    url = "http://127.0.0.1:11434/api/generate"
+    data = {
+        "model": "qwen2.5-coder:1.5b",
+        "prompt": prompt,
+        "stream": False
+    }
+    req = urllib.request.Request(
+        url,
+        data=json.dumps(data).encode("utf-8"),
+        headers={"Content-Type": "application/json"},
+        method="POST"
+    )
+    try:
+        with urllib.request.urlopen(req) as response:
+            res = json.loads(response.read().decode("utf-8"))
+            return res.get("response", "")
+    except urllib.error.URLError as e:
+        print(f"Error connecting to local Ollama agent: {e}", file=sys.stderr)
+        sys.exit(1)
+
+if __name__ == "__main__":
+    if len(sys.argv) < 2:
+        print("Usage: python3 scripts/local_agent_runner.py <prompt>")
+        sys.exit(1)
+    prompt = " ".join(sys.argv[1:])
+    print(generate_text(prompt))
diff --git a/tests/test_local_agent.py b/tests/test_local_agent.py
new file mode 100644
--- /dev/null
+++ b/tests/test_local_agent.py
@@ -0,0 +1,21 @@
+import unittest
+from unittest.mock import patch, MagicMock
+import urllib.error
+from scripts.local_agent_runner import generate_text
+
+class TestLocalAgentRunner(unittest.TestCase):
+    @patch("urllib.request.urlopen")
+    def test_generate_text_success(self, mock_urlopen):
+        mock_response = MagicMock()
+        mock_response.read.return_value = b'{"response": "hello mock world"}'
+        mock_urlopen.return_value.__enter__.return_value = mock_response
+
+        res = generate_text("test prompt")
+        self.assertEqual(res, "hello mock world")
+
+    @patch("urllib.request.urlopen")
+    def test_generate_text_failure(self, mock_urlopen):
+        mock_urlopen.side_effect = urllib.error.URLError("Connection refused")
+        with self.assertRaises(SystemExit):
+            generate_text("test prompt")
```

## 10. Final Report

Pending.
