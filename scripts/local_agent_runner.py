import argparse
import json
import os
import urllib.request
import urllib.error
import sys

PROFILES = {
    "studio": "qwen2.5-coder:32b-instruct",
    "mini": "qwen2.5-coder:14b",
    "mini-fast": "qwen2.5-coder:7b-instruct",
    "baseline": "qwen2.5-coder:1.5b"
}
DEFAULT_PROFILE = "baseline"

def get_selected_model(profile_name: str = None) -> tuple[str, str]:
    """
    Resolves the target model and profile name.
    If profile_name is not provided, reads the LOCAL_AI_PROFILE environment variable.
    If still not set, automatically detects system memory to choose the optimal profile.
    """
    detected = False
    if not profile_name:
        profile_name = os.environ.get("LOCAL_AI_PROFILE", "").lower().strip()
    
    if not profile_name:
        detected = True
        try:
            total_bytes = os.sysconf('SC_PAGE_SIZE') * os.sysconf('SC_PHYS_PAGES')
            # > 32 GB -> studio
            if total_bytes > 32 * 1024 * 1024 * 1024:
                profile_name = "studio"
            # > 8 GB -> mini
            elif total_bytes > 8 * 1024 * 1024 * 1024:
                profile_name = "mini"
            else:
                profile_name = "baseline"
        except Exception:
            profile_name = DEFAULT_PROFILE
    
    if profile_name in PROFILES:
        resolved_profile = f"{profile_name} (auto-detected)" if detected else profile_name
        return PROFILES[profile_name], resolved_profile
    
    # If a specific/custom model is provided that doesn't match predefined profiles, use it directly
    return profile_name, "custom"


def generate_text(prompt: str, profile_name: str = None) -> str:
    """
    Queries the local Ollama agent using the selected model/profile.
    """
    model, resolved_profile = get_selected_model(profile_name)
    # Log model selection to stderr to avoid polluting stdout
    print(f"Using local worker profile: {resolved_profile} (model: {model})", file=sys.stderr)
    
    url = "http://127.0.0.1:11434/api/generate"
    data = {
        "model": model,
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
    parser = argparse.ArgumentParser(description="Local model worker runner utility.")
    parser.add_argument("--profile", type=str, help="Override active local model profile (studio, mini, mini-fast, baseline).")
    parser.add_argument("prompt", nargs="+", help="The prompt to send to the local model.")
    args = parser.parse_args()
    
    prompt_str = " ".join(args.prompt)
    print(generate_text(prompt_str, profile_name=args.profile))
