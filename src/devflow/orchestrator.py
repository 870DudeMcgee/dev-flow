import os
import urllib.request
import json
from typing import Optional

def check_gemini_api() -> str:
    """
    Checks for the presence of GEMINI_API_KEY in the environment.
    """
    return os.environ.get("GEMINI_API_KEY", "")

def call_gemini(system_instruction: str, prompt: str, api_key: str) -> str:
    """
    Calls the Google Gemini generateContent API via urllib (zero external dependencies).
    """
    if not api_key:
        return "Orchestrator error: API key missing. Please set the GEMINI_API_KEY environment variable."
        
    # Standard Google Gemini API endpoint (we use gemini-1.5-flash as default orchestrator endpoint)
    # Note: gemini-3.5-flash is available, so we support the standard endpoint structure.
    url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-1.5-flash:generateContent?key={api_key}"
    
    headers = {"Content-Type": "application/json"}
    payload = {
        "contents": [{"parts": [{"text": prompt}]}],
        "systemInstruction": {"parts": [{"text": system_instruction}]}
    }
    
    req = urllib.request.Request(
        url,
        data=json.dumps(payload).encode("utf-8"),
        headers=headers
    )
    
    try:
        # 10 second timeout for API responses
        with urllib.request.urlopen(req, timeout=10) as res:
            res_data = json.loads(res.read().decode("utf-8"))
            
            # Navigate standard Gemini API response structure
            candidates = res_data.get("candidates", [])
            if candidates:
                content = candidates[0].get("content", {})
                parts = content.get("parts", [])
                if parts:
                    return parts[0].get("text", "")
            return "Orchestrator error: Received empty response structure from Gemini API."
    except Exception as e:
        return f"Orchestrator error: {str(e)}"
