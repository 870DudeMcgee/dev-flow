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
    endpoint: str = "http://127.0.0.1:11434",
    timeout: int = 300
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
        "stream": True,
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
        with urllib.request.urlopen(req, timeout=timeout) as response:
            full_response = []
            is_tty = sys.stderr.isatty()
            for line in response:
                if line:
                    chunk = json.loads(line.decode("utf-8"))
                    token = chunk.get("response", "")
                    full_response.append(token)
                    if is_tty:
                        sys.stderr.write(".")
                        sys.stderr.flush()
            if is_tty:
                sys.stderr.write("\n")
                sys.stderr.flush()
            return "".join(full_response).strip()
    except urllib.error.URLError as e:
        raise ConnectionError(f"Could not connect to Ollama on {endpoint}: {e}")
