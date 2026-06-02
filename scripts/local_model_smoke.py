#!/usr/bin/env python3
import os
import sys
import json
import urllib.request
import urllib.error


def main():
    base_url = os.environ.get("LOCAL_MODEL_BASE_URL", "http://127.0.0.1:8080/v1")
    model_id = os.environ.get("LOCAL_MODEL_ID")
    timeout_str = os.environ.get("LOCAL_MODEL_TIMEOUT_SECONDS", "120")

    try:
        timeout = float(timeout_str)
    except ValueError:
        timeout = 120.0

    if not model_id:
        print("Error: LOCAL_MODEL_ID environment variable is missing.", file=sys.stderr)
        print("Please set it, e.g.:", file=sys.stderr)
        print("  export LOCAL_MODEL_ID='Jackrong/Qwopus3.6-35B-A3B-v1-GGUF:Q4_K_M'", file=sys.stderr)
        sys.exit(1)

    url = f"{base_url.rstrip('/')}/chat/completions"
    payload = {
        "model": model_id,
        "messages": [
            {"role": "user", "content": "Reply with exactly: local model smoke test ok"}
        ],
        "temperature": 0.0
    }
    
    headers = {
        "Content-Type": "application/json"
    }

    req = urllib.request.Request(
        url,
        data=json.dumps(payload).encode("utf-8"),
        headers=headers,
        method="POST"
    )

    print(f"Sending smoke test request to: {url}")
    print(f"Model ID: {model_id}")

    try:
        with urllib.request.urlopen(req, timeout=timeout) as response:
            res_data = response.read().decode("utf-8")
            response_json = json.loads(res_data)
            
            choices = response_json.get("choices", [])
            if not choices:
                print("Error: No choices returned in completion response.", file=sys.stderr)
                sys.exit(1)
                
            message = choices[0].get("message", {})
            content = message.get("content", "").strip()
            if not content:
                print("Error: Empty assistant content returned.", file=sys.stderr)
                sys.exit(1)
                
            print("Assistant content:")
            print(content)
            
    except urllib.error.URLError as exc:
        print(f"Error: Local model server at {url} is unreachable.", file=sys.stderr)
        print(f"Details: {exc}", file=sys.stderr)
        sys.exit(1)
    except Exception as exc:
        print(f"Error executing smoke test: {exc}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
