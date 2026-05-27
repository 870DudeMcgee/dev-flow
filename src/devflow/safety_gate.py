import ast
import re
from typing import Tuple, List

class SafetyRule:
    """Base safety rule interface."""
    def validate(self, code_text: str) -> Tuple[bool, List[str]]:
        raise NotImplementedError

class RegexSafetyRule(SafetyRule):
    """Safety rule checking for raw patterns using regular expressions."""
    def __init__(self, pattern: re.Pattern, hazard_name: str):
        self.pattern = pattern
        self.hazard_name = hazard_name
        
    def validate(self, code_text: str) -> Tuple[bool, List[str]]:
        findings = []
        if self.pattern.search(code_text):
            findings.append(f"{self.hazard_name} hazard: {code_text.strip()}")
        return len(findings) == 0, findings

class AstSafetyRule(SafetyRule):
    """Advanced safety rule that parses python code to detect structural hazards recursively."""
    def validate(self, code_text: str) -> Tuple[bool, List[str]]:
        findings = []
        try:
            tree = ast.parse(code_text)
            for node in ast.walk(tree):
                if isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
                    if node.func.id in {"eval", "exec"}:
                        findings.append(f"Eval/Exec hazard in AST: {node.func.id}")
        except Exception:
            # Fall back or skip syntax errors in partial/non-python diff hunks
            pass
        return len(findings) == 0, findings

class SafetyGate:
    """The deep safety engine presenting a simple, high-leverage interface to callers."""
    def __init__(self, rules: List[SafetyRule] = None):
        self.rules = rules or [
            RegexSafetyRule(re.compile(r"(?i)(key|secret|token|password|credential)\s*=\s*['\"][^'\"]+['\"]"), "Hardcoded secret"),
            RegexSafetyRule(re.compile(r"shell\s*=\s*True"), "Subprocess shell=True"),
            RegexSafetyRule(re.compile(r"\bsocket\s*\.\s*(socket|bind|connect)\b"), "Socket binding/connection"),
            AstSafetyRule()
        ]
        
    def audit(self, patch_text: str) -> Tuple[bool, List[str]]:
        """Scans the additions in a unified diff and validates them against the rules list."""
        findings = []
        for line in patch_text.splitlines():
            # Only audit code additions (starting with '+' and not being a file header '+++')
            if not line.startswith("+") or line.startswith("+++"):
                continue
            addition = line[1:].strip()
            for rule in self.rules:
                ok, rule_findings = rule.validate(addition)
                if not ok:
                    findings.extend(rule_findings)
        return len(findings) == 0, findings
