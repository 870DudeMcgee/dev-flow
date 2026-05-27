import re
from typing import Tuple, List

SECRET_PATTERN = re.compile(r"(?i)(key|secret|token|password|credential)\s*=\s*['\"][^'\"]+['\"]")
SHELL_PATTERN = re.compile(r"shell\s*=\s*True")
EXEC_PATTERN = re.compile(r"\b(eval|exec)\b\s*\(")
SOCKET_PATTERN = re.compile(r"\bsocket\s*\.\s*(socket|bind|connect)\b")

def scan_diff_for_hazards(diff_text: str) -> Tuple[bool, List[str]]:
    """
    Parses a unified diff's added lines and checks them for high-risk safety hazards.
    Returns (is_clean: bool, findings: List[str]).
    """
    findings = []
    for line in diff_text.splitlines():
        # Only audit code additions (starting with '+' and not being a file header '+++')
        if not line.startswith("+") or line.startswith("+++"):
            continue
        addition = line[1:].strip()
        if SECRET_PATTERN.search(addition):
            findings.append(f"Hardcoded secret hazard: {addition}")
        if SHELL_PATTERN.search(addition):
            findings.append(f"Subprocess shell=True hazard: {addition}")
        if EXEC_PATTERN.search(addition):
            findings.append(f"Eval/Exec hazard: {addition}")
        if SOCKET_PATTERN.search(addition):
            findings.append(f"Socket binding/connection hazard: {addition}")
    return len(findings) == 0, findings
