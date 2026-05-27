# Codebase Architecture Deepening Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Refactor and deepen the three shallow components (Safety Scanning, Failure Diagnostics, and Model Orchestration) into robust, polymorphic modules with well-defined seams and adapters to improve testability and maintainability.

**Architecture:** We will replace the procedural, shallow logic inside `safety.py`, `failures.py`, and `orchestrator.py` with deep manager objects (e.g., `SafetyGate`, `DiagnosticAnalyzer`, `ModelGateway`) utilizing polymorphic adapters and strict interface boundaries. Callers will use these clean seams, and backward-compatible wrappers will preserve existing API contracts.

**Tech Stack:** Python 3.12+ (Standard library, `unittest`, `urllib`, `re`, `json`, `ast`).

---

### Task 1: Deepen the Safety Auditing System (`src/devflow/safety_gate.py`)

**Files:**
- Create: `src/devflow/safety_gate.py`
- Modify: `src/devflow/safety.py`
- Test: `tests/test_safety.py`

**Step 1: Write the failing test**

In `tests/test_safety.py`, we add a unit test that expects a polymorphic `SafetyGate` and custom `AstSafetyRule` to detect `eval` dynamically even when formatted with complex spacing that simple regex fails to match.

```python
import unittest
from devflow.safety_gate import SafetyGate, AstSafetyRule, RegexSafetyRule

class TestSafetyGate(unittest.TestCase):
    def test_ast_safety_rule_detects_eval(self):
        rule = AstSafetyRule()
        # Complex multi-line or spaced eval call that simple regexes struggle with
        code = "x = \\n  eval  \\n  (  '1 + 1'  )"
        is_clean, findings = rule.validate(code)
        self.assertFalse(is_clean)
        self.assertTrue(any("eval" in f.lower() for f in findings))
```

**Step 2: Run test to verify it fails**

Run: `PYTHONPATH=src python3 -m unittest tests/test_safety.py -k TestSafetyGate`
Expected: `ImportError: cannot import name 'SafetyGate'` (FAIL)

**Step 3: Write minimal implementation**

Create `src/devflow/safety_gate.py`:
```python
import ast
import re
from typing import Tuple, List

class SafetyRule:
    def validate(self, code_text: str) -> Tuple[bool, List[str]]:
        raise NotImplementedError

class RegexSafetyRule(SafetyRule):
    def __init__(self, pattern: re.Pattern, hazard_name: str):
        self.pattern = pattern
        self.hazard_name = hazard_name
        
    def validate(self, code_text: str) -> Tuple[bool, List[str]]:
        findings = []
        if self.pattern.search(code_text):
            findings.append(f"{self.hazard_name} hazard: {code_text.strip()}")
        return len(findings) == 0, findings

class AstSafetyRule(SafetyRule):
    def validate(self, code_text: str) -> Tuple[bool, List[str]]:
        findings = []
        try:
            tree = ast.parse(code_text)
            for node in ast.walk(tree):
                if isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
                    if node.func.id in {"eval", "exec"}:
                        findings.append(f"Eval/Exec hazard in AST: {node.func.id}")
        except Exception:
            # Fallback to regex or skip syntax errors in incomplete hunks
            pass
        return len(findings) == 0, findings

class SafetyGate:
    def __init__(self, rules: List[SafetyRule] = None):
        self.rules = rules or [
            RegexSafetyRule(re.compile(r"(?i)(key|secret|token|password|credential)\s*=\s*['\"][^'\"]+['\"]"), "Hardcoded secret"),
            RegexSafetyRule(re.compile(r"shell\s*=\s*True"), "Subprocess shell=True"),
            RegexSafetyRule(re.compile(r"\bsocket\s*\.\s*(socket|bind|connect)\b"), "Socket binding/connection"),
            AstSafetyRule()
        ]
        
    def audit(self, patch_text: str) -> Tuple[bool, List[str]]:
        findings = []
        for line in patch_text.splitlines():
            if not line.startswith("+") or line.startswith("+++"):
                continue
            addition = line[1:].strip()
            for rule in self.rules:
                ok, rule_findings = rule.validate(addition)
                if not ok:
                    findings.extend(rule_findings)
        return len(findings) == 0, findings
```

Update `src/devflow/safety.py` to retain backward compatibility:
```python
from typing import Tuple, List
from devflow.safety_gate import SafetyGate

def scan_diff_for_hazards(diff_text: str) -> Tuple[bool, List[str]]:
    """Backward compatible wrapper delegating to deep SafetyGate module."""
    gate = SafetyGate()
    return gate.audit(diff_text)
```

**Step 4: Run test to verify it passes**

Run: `PYTHONPATH=src python3 -m unittest tests/test_safety.py -q`
Expected: `Ran 6 tests ... OK`

**Step 5: Commit**

```bash
git add src/devflow/safety_gate.py src/devflow/safety.py tests/test_safety.py
git commit -m "feat: deepen safety scanning into polymorphic SafetyGate seam"
```

---

### Task 2: Deepen Build & Test Diagnostics Classification (`src/devflow/diagnostics.py`)

**Files:**
- Create: `src/devflow/diagnostics.py`
- Modify: `src/devflow/failures.py`
- Test: `tests/test_failures.py`

**Step 1: Write the failing test**

In `tests/test_failures.py`, we add a unit test verifying that the new `DiagnosticAnalyzer` and its custom `PytestAdapter` parse test failures into a structured, highly useful `DiagnosticPacket` with file context, line numbers, and trace details.

```python
import unittest
from devflow.diagnostics import DiagnosticAnalyzer, PytestAdapter

class TestDiagnostics(unittest.TestCase):
    def test_pytest_adapter_extracts_details(self):
        output = (
            "================================== FAILURES ==================================\n"
            "___________________________ test_claim_task_clean ____________________________\n"
            "tests/test_manager.py:290: in test_claim_task_clean\n"
            "    self.assertEqual(status, 'PENDING')\n"
            "E   AssertionError: 'CLAIMED' != 'PENDING'\n"
        )
        adapter = PytestAdapter()
        self.assertTrue(adapter.can_handle(output))
        packet = adapter.parse(output)
        self.assertEqual(packet.classification, "TEST_FAILURE")
        self.assertEqual(packet.file, "tests/test_manager.py")
        self.assertEqual(packet.line, 290)
        self.assertIn("AssertionError", packet.message)
```

**Step 2: Run test to verify it fails**

Run: `PYTHONPATH=src python3 -m unittest tests/test_failures.py -k TestDiagnostics`
Expected: `ImportError: cannot import name 'DiagnosticAnalyzer'` (FAIL)

**Step 3: Write minimal implementation**

Create `src/devflow/diagnostics.py`:
```python
import re
from dataclasses import dataclass
from typing import Optional, List

@dataclass
class DiagnosticPacket:
    classification: str
    file: Optional[str] = None
    line: Optional[int] = None
    code_snippet: Optional[str] = None
    message: str = ""
    suggested_fix: Optional[str] = None

class DiagnosticAdapter:
    def can_handle(self, command_output: str) -> bool:
        raise NotImplementedError
        
    def parse(self, command_output: str) -> DiagnosticPacket:
        raise NotImplementedError

class PytestAdapter(DiagnosticAdapter):
    def can_handle(self, command_output: str) -> bool:
        return "failures =" in command_output or "FAILURES ===" in command_output or "E   AssertionError:" in command_output

    def parse(self, command_output: str) -> DiagnosticPacket:
        file_match = re.search(r"([\w\-/]+\.py):(\d+):", command_output)
        file = file_match.group(1) if file_match else None
        line = int(file_match.group(2)) if file_match else None
        
        msg_match = re.search(r"(E\s+AssertionError:.*)", command_output)
        msg = msg_match.group(1) if msg_match else "Test failed with AssertionError"
        
        return DiagnosticPacket(
            classification="TEST_FAILURE",
            file=file,
            line=line,
            message=msg,
            suggested_fix="Check implementation state; verify expected output matches assertion."
        )

class MypyAdapter(DiagnosticAdapter):
    def can_handle(self, command_output: str) -> bool:
        return "error:" in command_output and ".py:" in command_output

    def parse(self, command_output: str) -> DiagnosticPacket:
        match = re.search(r"([\w\-/]+\.py):(\d+):\s*error:\s*(.*)", command_output)
        if match:
            return DiagnosticPacket(
                classification="TYPE_ERROR",
                file=match.group(1),
                line=int(match.group(2)),
                message=match.group(3),
                suggested_fix="Align type definitions or add appropriate type assertions/annotations."
            )
        return DiagnosticPacket(classification="TYPE_ERROR", message=command_output)

class FallbackAdapter(DiagnosticAdapter):
    def can_handle(self, command_output: str) -> bool:
        return True
        
    def parse(self, command_output: str) -> DiagnosticPacket:
        text = command_output.lower()
        classification = "UNKNOWN_FAILURE"
        
        if "syntaxerror" in text:
            classification = "SYNTAX_ERROR"
        elif "importerror" in text or "modulenotfounderror" in text:
            classification = "IMPORT_ERROR"
        elif "ruff" in text or "lint" in text:
            classification = "LINT_FAILURE"
        elif "failed" in text or "error" in text:
            classification = "TEST_FAILURE"
            
        return DiagnosticPacket(classification=classification, message=command_output)

class DiagnosticAnalyzer:
    def __init__(self, adapters: List[DiagnosticAdapter] = None):
        self.adapters = adapters or [PytestAdapter(), MypyAdapter(), FallbackAdapter()]
        
    def analyze(self, command_output: str, stage: str = "verification") -> DiagnosticPacket:
        if stage == "patch":
            return DiagnosticPacket(classification="PATCH_APPLY_FAILURE", message=command_output)
            
        for adapter in self.adapters:
            if adapter.can_handle(command_output):
                return adapter.parse(command_output)
        return DiagnosticPacket(classification="UNKNOWN_FAILURE", message=command_output)
```

Update `src/devflow/failures.py` to preserve compatibility:
```python
from typing import Dict, Any
from devflow.diagnostics import DiagnosticAnalyzer

DEFAULT_TAXONOMY = {
    "PATCH_APPLY_FAILURE": {"retryable": True, "max_retries": 1},
    "SYNTAX_ERROR": {"retryable": True, "max_retries": 1},
    "IMPORT_ERROR": {"retryable": True, "max_retries": 1},
    "TEST_FAILURE": {"retryable": True, "max_retries": 1},
    "LINT_FAILURE": {"retryable": True, "max_retries": 1},
    "TYPE_ERROR": {"retryable": True, "max_retries": 1},
    "PROTECTED_FILE_TOUCHED": {"retryable": False, "max_retries": 0},
    "UNKNOWN_FAILURE": {"retryable": False, "max_retries": 0},
}

def classify_failure(stage: str, output: str) -> str:
    """Classifies a build/test/lint failure output into a formal category."""
    analyzer = DiagnosticAnalyzer()
    packet = analyzer.analyze(output, stage=stage)
    return packet.classification

def serialize_failure(stage: str, output: str, command: str = "") -> dict:
    """Serializes failure details into a structured dictionary."""
    analyzer = DiagnosticAnalyzer()
    packet = analyzer.analyze(output, stage=stage)
    return {
        "stage": stage,
        "classification": packet.classification,
        "command": command,
        "output": output,
        "file": packet.file,
        "line": packet.line,
        "message": packet.message
    }

def retry_budget_for(classification: str, taxonomy: Dict[str, Dict[str, object]] | None = None) -> int:
    """Gets the retry budget/limit for a given failure classification."""
    rules = taxonomy or DEFAULT_TAXONOMY
    if classification not in rules:
        return 0
    value = rules[classification].get("max_retries", 0)
    return int(value) if isinstance(value, int) else 0
```

**Step 4: Run test to verify it passes**

Run: `PYTHONPATH=src python3 -m unittest tests/test_failures.py -q`
Expected: `Ran 9 tests ... OK`

**Step 5: Commit**

```bash
git add src/devflow/diagnostics.py src/devflow/failures.py tests/test_failures.py
git commit -m "feat: deepen build/test diagnostics into a deep DiagnosticAnalyzer module"
```

---

### Task 3: Deepen Model Orchestration (`src/devflow/model_gateway.py`)

**Files:**
- Create: `src/devflow/model_gateway.py`
- Modify: `src/devflow/orchestrator.py`
- Test: `tests/test_orchestrator.py`

**Step 1: Write the failing test**

In `tests/test_orchestrator.py`, we add a unit test verifying that `ModelGateway` supports a seamless `MockClient` for local and networkless unit testing, validating fallback client chain mechanics.

```python
import unittest
from devflow.model_gateway import ModelGateway, PromptRequest, MockClient

class TestModelGateway(unittest.TestCase):
    def test_mock_gateway_fallback_behavior(self):
        failing_client = MockClient(response_text="Error", should_fail=True)
        passing_client = MockClient(response_text="Success Response")
        
        gateway = ModelGateway(primary=failing_client, fallbacks=[passing_client])
        req = PromptRequest(system_instruction="sys", prompt="ping")
        res = gateway.invoke(req)
        
        self.assertTrue(res.success)
        self.assertEqual(res.text, "Success Response")
```

**Step 2: Run test to verify it fails**

Run: `PYTHONPATH=src python3 -m unittest tests/test_orchestrator.py -k TestModelGateway`
Expected: `ImportError: cannot import name 'ModelGateway'` (FAIL)

**Step 3: Write minimal implementation**

Create `src/devflow/model_gateway.py`:
```python
import json
import urllib.request
from dataclasses import dataclass
from typing import List, Optional

@dataclass
class PromptRequest:
    system_instruction: str
    prompt: str
    temperature: float = 0.2
    json_mode: bool = False
    timeout: int = 300

@dataclass
class PromptResponse:
    text: str
    model: str
    success: bool
    error_message: Optional[str] = None

class ModelClient:
    def call(self, request: PromptRequest) -> PromptResponse:
        raise NotImplementedError

class MockClient(ModelClient):
    def __init__(self, response_text: str, should_fail: bool = False):
        self.response_text = response_text
        self.should_fail = should_fail
        
    def call(self, request: PromptRequest) -> PromptResponse:
        if self.should_fail:
            return PromptResponse(text="", model="mock-fail", success=False, error_message="Mock connection error")
        return PromptResponse(text=self.response_text, model="mock-success", success=True)

class GeminiClient(ModelClient):
    def __init__(self, api_key: str, model: str = "gemini-1.5-flash"):
        self.api_key = api_key
        self.model = model
        
    def call(self, request: PromptRequest) -> PromptResponse:
        if not self.api_key:
            return PromptResponse(text="", model=self.model, success=False, error_message="Gemini key missing")
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{self.model}:generateContent?key={self.api_key}"
        headers = {"Content-Type": "application/json"}
        payload = {
            "contents": [{"parts": [{"text": request.prompt}]}],
            "systemInstruction": {"parts": [{"text": request.system_instruction}]}
        }
        req = urllib.request.Request(
            url,
            data=json.dumps(payload).encode("utf-8"),
            headers=headers
        )
        try:
            with urllib.request.urlopen(req, timeout=request.timeout) as res:
                res_data = json.loads(res.read().decode("utf-8"))
                candidates = res_data.get("candidates", [])
                if candidates:
                    content = candidates[0].get("content", {})
                    parts = content.get("parts", [])
                    if parts:
                        return PromptResponse(text=parts[0].get("text", ""), model=self.model, success=True)
                return PromptResponse(text="", model=self.model, success=False, error_message="Empty response candidates")
        except Exception as e:
            return PromptResponse(text="", model=self.model, success=False, error_message=str(e))

class ModelGateway:
    def __init__(self, primary: ModelClient, fallbacks: List[ModelClient] = None):
        self.primary = primary
        self.fallbacks = fallbacks or []
        
    def invoke(self, request: PromptRequest) -> PromptResponse:
        clients = [self.primary] + self.fallbacks
        last_error = "No client configured"
        for client in clients:
            res = client.call(request)
            if res.success:
                return res
            last_error = res.error_message or "Unknown model client failure"
        return PromptResponse(text="", model="unknown", success=False, error_message=last_error)
```

Update `src/devflow/orchestrator.py` to preserve backward compatibility:
```python
import os
from devflow.model_gateway import ModelGateway, GeminiClient, PromptRequest

def check_gemini_api() -> str:
    """Checks for the presence of GEMINI_API_KEY in the environment."""
    return os.environ.get("GEMINI_API_KEY", "")

def call_gemini(system_instruction: str, prompt: str, api_key: str) -> str:
    """Calls Gemini API via the ModelGateway seam."""
    client = GeminiClient(api_key=api_key)
    gateway = ModelGateway(primary=client)
    req = PromptRequest(system_instruction=system_instruction, prompt=prompt)
    res = gateway.invoke(req)
    if res.success:
        return res.text
    return f"Orchestrator error: {res.error_message}"
```

**Step 4: Run test to verify it passes**

Run: `PYTHONPATH=src python3 -m unittest tests/test_orchestrator.py -q`
Expected: `Ran 3 tests ... OK`

**Step 5: Commit**

```bash
git add src/devflow/model_gateway.py src/devflow/orchestrator.py tests/test_orchestrator.py
git commit -m "feat: deepen model orchestration into polymorphic ModelGateway interface"
```

---

## Verification Plan

### Automated Tests
- Run full unit tests to confirm zero regressions:
  `PYTHONPATH=src python3 -m unittest discover -s tests -q`
- Expected output: `OK` (All 134+ tests passing cleanly).

### Manual Verification
- Execute `python3 scripts/generate_architecture_review.py` to re-prove report generation.
