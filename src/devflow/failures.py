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
