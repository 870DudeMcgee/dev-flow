import re
from typing import Dict, Any

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
    text = output.lower()
    if stage == "patch":
        return "PATCH_APPLY_FAILURE"
    if "syntaxerror" in text:
        return "SYNTAX_ERROR"
    if "importerror" in text or "modulenotfounderror" in text:
        return "IMPORT_ERROR"
    if "ruff" in text or "lint" in text:
        return "LINT_FAILURE"
    if "mypy" in text or "type error" in text or "typeerror" in text:
        return "TYPE_ERROR"
    if "failed" in text or "error" in text:
        return "TEST_FAILURE"

    return "UNKNOWN_FAILURE"

def serialize_failure(stage: str, output: str, command: str = "") -> dict:
    """Serializes failure details into a structured dictionary."""
    return {
        "stage": stage,
        "classification": classify_failure(stage, output),
        "command": command,
        "output": output
    }
