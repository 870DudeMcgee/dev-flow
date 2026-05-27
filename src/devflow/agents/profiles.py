import os
import re
from dataclasses import dataclass
from typing import List

@dataclass
class AgentProfile:
    role: str
    preferred_model: str
    fallback_models: List[str]
    max_input_tokens: int
    max_output_tokens: int
    temperature: float
    permissions: dict

def load_agent_profile(role: str, cwd: str = ".") -> AgentProfile:
    """
    Load task budgets, permissions, and preferred models based on role.
    Integrates with local model policy config where possible.
    """
    cwd = os.path.abspath(cwd)
    policy_path = os.path.join(cwd, ".devflow", "orchestrators", "local-model-worker-policy.md")
    
    preferred = "qwen2.5-coder:14b"
    fallbacks = ["qwen2.5-coder:7b-instruct", "qwen2.5-coder:1.5b"]
    
    # Try parsing the preferred model from the local-model-worker-policy.md
    if os.path.exists(policy_path):
        try:
            with open(policy_path, "r", encoding="utf-8") as handle:
                text = handle.read()
            match = re.search(r"preferred coding worker for Mac mini.*?: (qwen\S+)", text)
            if match:
                preferred = match.group(1).strip()
        except Exception:
            pass

    budgets = {
        "cartographer": (4000, 1000, 0.2),
        "reviewer": (6000, 2000, 0.2),
        "implementer": (12000, 4000, 0.0),
        "test_writer": (8000, 2500, 0.2),
        "repair": (4000, 2000, 0.3),
        "summarizer": (3000, 1000, 0.2)
    }
    
    max_in, max_out, temp = budgets.get(role, (6000, 2000, 0.2))
    
    return AgentProfile(
        role=role,
        preferred_model=preferred,
        fallback_models=fallbacks,
        max_input_tokens=max_in,
        max_output_tokens=max_out,
        temperature=temp,
        permissions={
            "read_files": True,
            "write_files": False,
            "emit_diff": role == "implementer",
            "run_commands": False
        }
    )
