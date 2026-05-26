import json
import urllib.request
import urllib.error
import sys

def generate_text(prompt: str) -> str:
    url = "http://127.0.0.1:11434/api/generate"
    data = {
        "model": "qwen2.5-coder:1.5b",
        "prompt": prompt,
        "stream": False
    }
    req = urllib.request.Request(
        url,
        data=json.dumps(data).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST"
    )
    try:
        with urllib.request.urlopen(req) as response:
            res = json.loads(response.read().decode("utf-8"))
            return res.get("response", "")
    except urllib.error.URLError as e:
        print(f"Error connecting to local Ollama agent: {e}", file=sys.stderr)
        sys.exit(1)

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python3 scripts/local_agent_runner.py <prompt>")
        sys.exit(1)
    prompt = " ".join(sys.argv[1:])
    print(generate_text(prompt))
