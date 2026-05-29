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
