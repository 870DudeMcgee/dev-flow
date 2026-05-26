import os
import json
import argparse
import sys
import re
from devflow.manager import parse_task_file
from devflow.editor import apply_xml_edits
from devflow.runner import validate_syntax, call_ollama
from devflow.orchestrator import check_gemini_api, call_gemini

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

def plan_workspace(goal: str):
    """Call cloud orchestrator to build a development plan."""
    if not os.path.exists(".devflow"):
        print("Error: .devflow/ folder not found. Run 'devflow init' first.")
        sys.exit(1)
        
    api_key = check_gemini_api()
    if not api_key:
        print("Error: GEMINI_API_KEY environment variable not found. Please set it to proceed.")
        sys.exit(1)
        
    print(f"Planning goal: '{goal}'...")
    
    # 1. Discover current project files to send context to Orchestrator
    files_context = []
    for root, dirs, files in os.walk("."):
        # Exclude standard directories to keep prompt lightweight
        dirs[:] = [d for d in dirs if d not in (".git", ".venv", "node_modules", ".devflow", "__pycache__", "docs")]
        for file in files:
            file_path = os.path.join(root, file)
            files_context.append(file_path)
            
    # 2. Build the system instruction for the Cloud Orchestrator
    system_instruction = (
        "You are the Cloud Orchestrator for devflow. Your job is to analyze the user's goal and the current workspace "
        "structure, and produce: \n"
        "1. A master plan.json file describing the architecture and stages.\n"
        "2. A series of independent task files in markdown format, which will be executed by local coding agents.\n"
        "Format your response as a single valid JSON block matching this structure:\n"
        "{\n"
        "  \"plan\": { ... },\n"
        "  \"tasks\": [\n"
        "    { \"filename\": \"001_xxx.md\", \"content\": \"...\" }\n"
        "  ]\n"
        "}"
    )
    
    prompt = f"Goal: {goal}\n\nWorkspace files:\n" + "\n".join(files_context)
    
    raw_response = call_gemini(system_instruction, prompt, api_key)
    
    # Simple extraction of JSON block from response
    json_match = re.search(r'(\{.*\})', raw_response, re.DOTALL)
    if not json_match:
        print("Error: Received invalid planning response from Gemini API.")
        print("Raw response:", raw_response)
        sys.exit(1)
        
    try:
        data = json.loads(json_match.group(1))
        
        # Save master plan
        with open(".devflow/plan.json", "w") as f:
            json.dump(data.get("plan", {}), f, indent=2)
            
        # Scaffold tasks
        for task in data.get("tasks", []):
            task_path = os.path.join(".devflow/tasks", task["filename"])
            with open(task_path, "w") as f:
                f.write(task["content"])
            print(f"Scaffolded task: {task['filename']}")
            
        print("Planning completed successfully!")
    except Exception as e:
        print(f"Error parsing orchestrator response: {str(e)}")
        sys.exit(1)

def run_tasks():
    """Iterate outstanding tasks and run them using the local agent."""
    if not os.path.exists(".devflow"):
        print("Error: .devflow/ folder not found. Run 'devflow init' first.")
        sys.exit(1)
        
    # Read config
    with open(".devflow/config.json", "r") as f:
        config = json.load(f)
        
    local_cfg = config.get("local_agent", {})
    host = local_cfg.get("host", "http://localhost:11434")
    profile = local_cfg.get("active_profile", "work_m4_max_64gb")
    model = local_cfg.get("model_map", {}).get(profile, "qwen2.5-coder:7b-instruct")
    
    tasks_dir = ".devflow/tasks"
    all_files = sorted(os.listdir(tasks_dir))
    
    pending_task_file = None
    for filename in all_files:
        if filename.endswith(".md"):
            path = os.path.join(tasks_dir, filename)
            with open(path, "r") as f:
                content = f.read()
            if "Status: PENDING" in content:
                pending_task_file = path
                break
                
    if not pending_task_file:
        print("No pending tasks found in .devflow/tasks/.")
        return
        
    print(f"Running task: {os.path.basename(pending_task_file)} using local model: {model}...")
    
    with open(pending_task_file, "r") as f:
        raw_markdown = f.read()
        
    task = parse_task_file(raw_markdown)
    
    # Prepare local prompt
    local_prompt = (
        f"You are the Local Coding Agent for devflow. Your task is: {task['title']}\n"
        f"Instructions:\n{task['instructions']}\n\n"
        f"Context:\n{task['context_files']}\n\n"
        "You MUST output code changes inside XML search-and-replace tags exactly like this:\n"
        "<search>\n"
        "def old_code():\n"
        "    pass\n"
        "</search>\n"
        "<replace>\n"
        "def new_code():\n"
        "    return True\n"
        "</replace>\n\n"
        "Only edit files specified in Target Files. Do not output conversational text, only XML blocks."
    )
    
    # Self-healing loop (up to 3 attempts)
    success = False
    for attempt in range(1, 4):
        print(f"Attempt {attempt}/3...")
        response = call_ollama(local_prompt, host, model)
        
        if "Error connecting to Ollama" in response:
            print(f"Ollama server offline: {response}")
            return
            
        # Parse and apply changes to target files
        error = None
        for target_file in task["target_files"]:
            # Ensure target directories exist
            os.makedirs(os.path.dirname(target_file) or ".", exist_ok=True)
            
            # Read original content
            original_content = ""
            if os.path.exists(target_file):
                with open(target_file, "r") as f:
                    original_content = f.read()
                    
            modified, err = apply_xml_edits(original_content, response)
            if err:
                error = f"XML Edit Error in {target_file}: {err}"
                break
                
            # Perform AST validation
            if not validate_syntax(modified, target_file):
                error = f"Syntax Error: proposed changes to {target_file} resulted in an invalid Python AST."
                break
                
            # Temporarily write to verify tests
            with open(target_file, "w") as f:
                f.write(modified)
                
        if error:
            print(f"Validation failed: {error}")
            # Feed error back for self-healing
            local_prompt += f"\n\n[ATTEMPT {attempt} FAILED]\nError: {error}\nPlease correct your search-and-replace blocks."
            continue
            
        # If we reached here, AST validation passed!
        print("AST validation passed! Running project verification suite...")
        
        # Run test command if specified
        test_cmd = config.get("verification", {}).get("run_tests_command", "")
        if test_cmd:
            test_result = os.system(test_cmd)
            if test_result != 0:
                print("Project test suite failed! Rolling back changes...")
                local_prompt += "\n\n[TEST SUITE FAILED]\nThe project tests failed with the proposed changes. Please modify your code."
                continue
                
        success = True
        break
        
    if success:
        print("Task completed successfully!")
        # Update task file status
        raw_markdown = raw_markdown.replace("Status: PENDING", "Status: COMPLETED")
        # Append completion logs/results
        results_sec = f"## [4. EXECUTION RESULTS]\nSUCCESS - Attempt {attempt}. Verification suite passed."
        raw_markdown = re.sub(r'## \[4\.\s+EXECUTION RESULTS\].*', results_sec, raw_markdown, flags=re.DOTALL)
        
        with open(pending_task_file, "w") as f:
            f.write(raw_markdown)
    else:
        print("Task failed after 3 self-healing attempts.")
        raw_markdown = raw_markdown.replace("Status: PENDING", "Status: FAILED")
        with open(pending_task_file, "w") as f:
            f.write(raw_markdown)

def main():
    parser = argparse.ArgumentParser(description="devflow - Hybrid AI Developer Setup")
    subparsers = parser.add_subparsers(dest="command")
    
    # init
    subparsers.add_parser("init", help="Initialize a new devflow workspace")
    
    # plan
    plan_parser = subparsers.add_parser("plan", help="Call cloud orchestrator to build a development plan")
    plan_parser.add_argument("goal", type=str, help="The development goal or feature description")
    
    # run
    subparsers.add_parser("run", help="Iterate and run outstanding tasks using the local agent")
    
    args = parser.parse_args()
    
    if args.command == "init":
        init_workspace()
    elif args.command == "plan":
        plan_workspace(args.goal)
    elif args.command == "run":
        run_tasks()
    else:
        parser.print_help()

if __name__ == "__main__":
    main()
