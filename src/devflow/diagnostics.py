import re
from dataclasses import dataclass
from typing import Optional, List

@dataclass
class DiagnosticPacket:
    """Detailed error diagnostics metadata extracted from raw build/test stdout."""
    classification: str
    file: Optional[str] = None
    line: Optional[int] = None
    code_snippet: Optional[str] = None
    message: str = ""
    suggested_fix: Optional[str] = None

class DiagnosticAdapter:
    """Base adapter interface for tool-specific output parsers."""
    def can_handle(self, command_output: str) -> bool:
        raise NotImplementedError
        
    def parse(self, command_output: str) -> DiagnosticPacket:
        raise NotImplementedError

class PytestAdapter(DiagnosticAdapter):
    """Adapter to parse pytest traceback logs into structured details."""
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
    """Adapter to parse mypy type-checking logs into structured details."""
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
    """Fallback adapter using existing substring classification rules."""
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
        elif "mypy" in text or "type error" in text or "typeerror" in text:
            classification = "TYPE_ERROR"
        elif "failed" in text or "error" in text:
            classification = "TEST_FAILURE"
            
        return DiagnosticPacket(classification=classification, message=command_output)

class DiagnosticAnalyzer:
    """The deep diagnostic engine presenting a simple, high-leverage interface to callers."""
    def __init__(self, adapters: List[DiagnosticAdapter] = None):
        self.adapters = adapters or [PytestAdapter(), MypyAdapter(), FallbackAdapter()]
        
    def analyze(self, command_output: str, stage: str = "verification") -> DiagnosticPacket:
        """Parses raw stdout/stderr logs into a high-locality DiagnosticPacket."""
        if stage == "patch":
            return DiagnosticPacket(classification="PATCH_APPLY_FAILURE", message=command_output)
            
        for adapter in self.adapters:
            if adapter.can_handle(command_output):
                return adapter.parse(command_output)
        return DiagnosticPacket(classification="UNKNOWN_FAILURE", message=command_output)
