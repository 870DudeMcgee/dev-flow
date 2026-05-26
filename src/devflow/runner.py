import ast
import urllib.request
import json
from typing import Optional

def validate_syntax(content: str, filename: str) -> bool:
    """
    Validates the syntax of content if it's a Python file by trying to parse its AST.
    """
    if filename.endswith(".py"):
        try:
            ast.parse(content)
            return True
        except SyntaxError:
            return False
    # Return True for other file extensions by default
    return True

def call_ollama(prompt: str, host: str, model: str) -> str:
    """
    Calls the local Ollama generate API endpoint with zero external dependencies.
    """
    url = f"{host}/api/generate"
    data = {
        "model": model,
        "prompt": prompt,
        "stream": False
    }
    
    req = urllib.request.Request(
        url,
        data=json.dumps(data).encode("utf-8"),
        headers={"Content-Type": "application/json"}
    )
    
    try:
        # Set a short timeout of 5 seconds for connection check/non-stream
        with urllib.request.urlopen(req, timeout=5) as res:
            response_bytes = res.read()
            response_json = json.loads(response_bytes.decode("utf-8"))
            return response_json.get("response", "")
    except Exception as e:
        return f"Error connecting to Ollama: {str(e)}"
