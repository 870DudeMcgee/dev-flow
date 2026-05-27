import json
import urllib.request
import urllib.error
import sys

def invoke_local_model(
    model: str,
    system_instruction: str,
    prompt: str,
    temperature: float = 0.2,
    json_mode: bool = False,
    endpoint: str = "http://127.0.0.1:11434"
) -> str:
    """
    Invokes the local model via Ollama generate API (zero external dependencies).
    """
    url = f"{endpoint.rstrip('/')}/api/generate"
    options = {
        "temperature": temperature
    }
    data = {
        "model": model,
        "prompt": prompt,
        "system": system_instruction,
        "stream": False,
        "options": options
    }
    if json_mode:
        data["format"] = "json"

    req = urllib.request.Request(
        url,
        data=json.dumps(data).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST"
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as response:
            res = json.loads(response.read().decode("utf-8"))
            return res.get("response", "").strip()
    except urllib.error.URLError as e:
        raise ConnectionError(f"Could not connect to Ollama on {endpoint}: {e}")
