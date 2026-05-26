import os
import json
import argparse
import sys

def init_workspace():
    """Initialize the .devflow/ environment in the current directory."""
    os.makedirs(".devflow/tasks", exist_ok=True)
    os.makedirs(".devflow/logs", exist_ok=True)
    
    config = {
        "orchestrator": {
            "provider": "google",
            "model": "gemini-3.5-flash",
            "api_key_env": "GEMINI_API_KEY"
        },
        "local_agent": {
            "provider": "ollama",
            "host": "http://localhost:11434",
            "model_map": {
                "work_m4_max_64gb": "qwen2.5-coder:32b-instruct",
                "home_m1_16gb": "qwen2.5-coder:7b-instruct"
            },
            "active_profile": "work_m4_max_64gb"
        },
        "verification": {
            "run_tests_command": "/usr/bin/python3 -m unittest",
            "run_lint_command": ""
        }
    }
    
    config_path = os.path.join(".devflow", "config.json")
    with open(config_path, "w") as f:
        json.dump(config, f, indent=2)
    print("Initialized empty devflow workspace in .devflow/")

def main():
    parser = argparse.ArgumentParser(description="devflow - Hybrid AI Developer Setup")
    subparsers = parser.add_subparsers(dest="command")
    
    # init command
    subparsers.add_parser("init", help="Initialize a new devflow workspace")
    
    args = parser.parse_args()
    
    if args.command == "init":
        init_workspace()
    else:
        parser.print_help()

if __name__ == "__main__":
    main()
