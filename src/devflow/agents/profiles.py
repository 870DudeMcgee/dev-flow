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
    
    profile_override = os.environ.get("LOCAL_AI_PROFILE", "").lower().strip()
    profile_models = {
        "studio": "qwen2.5-coder:32b-instruct",
        "mini": "qwen2.5-coder:14b",
        "mini-fast": "qwen2.5-coder:7b-instruct",
        "baseline": "qwen2.5-coder:1.5b"
    }

    preferred = "qwen2.5-coder:14b"
    fallbacks = ["qwen2.5-coder:7b-instruct", "qwen2.5-coder:1.5b"]
    
    if profile_override:
        if profile_override in profile_models:
            preferred = profile_models[profile_override]
        else:
            preferred = os.environ.get("LOCAL_AI_PROFILE")
    else:
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

    # Local Ollama tokens are FREE — be generous. The orchestrator (cloud) stays lean
    # by only writing skill names in the task packet; the local runner loads full skill
    # content at dispatch time. Budgets: (max_input_tokens, max_output_tokens, temperature)
    budgets = {
        "cartographer": (8000, 2000, 0.2),
        "reviewer": (24000, 6000, 0.2),
        "implementer": (32000, 8000, 0.0),
        "test_writer": (24000, 6000, 0.2),
        "repair": (16000, 6000, 0.3),
        "syntax_repair": (16000, 4000, 0.1),
        "import_repair": (16000, 4000, 0.1),
        "test_repair": (24000, 8000, 0.2),
        "lint_repair": (16000, 4000, 0.1),
        "type_repair": (24000, 6000, 0.2),
        "summarizer": (8000, 2000, 0.2)
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
            "emit_diff": role in {"implementer", "repair", "syntax_repair", "import_repair", "test_repair", "lint_repair", "type_repair"},
            "run_commands": False
        }
    )

