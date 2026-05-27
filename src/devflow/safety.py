from typing import Tuple, List
from devflow.safety_gate import SafetyGate

def scan_diff_for_hazards(diff_text: str) -> Tuple[bool, List[str]]:
    """
    Parses a unified diff's added lines and checks them for high-risk safety hazards.
    Backward-compatible wrapper delegating to the deep SafetyGate engine.
    """
    gate = SafetyGate()
    return gate.audit(diff_text)
