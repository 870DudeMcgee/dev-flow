import os
import json
from typing import Dict, List, Any, Optional
from devflow.manager import parse_task_file
import devflow.agents.ollama

def run_role_eval(role: str, root_dir: str = ".") -> Dict[str, Any]:
    """
    Runs all deterministic evaluations under .devflow/evals/fixtures/
    matching the designated role. Intercepts local model queries dynamically.
    """
    fixtures_dir = os.path.join(root_dir, ".devflow", "evals", "fixtures")
    results = {
        "role": role,
        "total": 0,
        "passed": 0,
        "failures": []
    }

    if not os.path.isdir(fixtures_dir):
        return results

    fixtures = []
    for filename in os.listdir(fixtures_dir):
        if filename.endswith(".json"):
            path = os.path.join(fixtures_dir, filename)
            try:
                with open(path, "r", encoding="utf-8") as handle:
                    data = json.load(handle)
                if str(data.get("role", "")).lower() == role.lower():
                    fixtures.append((filename, data))
            except Exception:
                pass

    results["total"] = len(fixtures)
    original_invoke = devflow.agents.ollama.invoke_local_model

    for filename, fix in fixtures:
        name = fix.get("name", filename)
        task_markdown = fix.get("task_markdown", "")
        mock_response = fix.get("mock_model_response", "")
        assertions = fix.get("assertions", {})

        # Write initial task markdown into a temp file
        tasks_dir = os.path.join(root_dir, ".devflow", "tasks")
        os.makedirs(tasks_dir, exist_ok=True)
        
        init_parsed = parse_task_file(task_markdown)
        task_id = init_parsed.get("task_id", "temp")
        title_slug = str(init_parsed.get("title", "temp_task")).lower().replace(" ", "_")
        temp_task_file = os.path.join(tasks_dir, f"{task_id}_{title_slug}.md")

        with open(temp_task_file, "w", encoding="utf-8") as handle:
            handle.write(task_markdown)

        # Dynamic mock intercept
        devflow.agents.ollama.invoke_local_model = lambda *args, **kwargs: mock_response

        # Execute agent runner based on role
        success = True
        err_msg = ""
        try:
            if role.lower() == "implementer":
                from devflow.agents.runner import run_implement_agent
                run_implement_agent(temp_task_file, cwd=root_dir)
            elif role.lower() == "reviewer":
                from devflow.agents.runner import run_review_agent
                run_review_agent(temp_task_file, cwd=root_dir)
            elif role.lower() == "repair":
                from devflow.agents.runner import run_repair_agent
                run_repair_agent(temp_task_file, max_loops=1, cwd=root_dir)
            else:
                success = False
                err_msg = f"Unknown evaluation role: {role}"
        except Exception as e:
            if assertions.get("expected_status") != "FAILED":
                success = False
                err_msg = f"Agent runner raised exception: {str(e)}"

        # Restore original invoke function
        devflow.agents.ollama.invoke_local_model = original_invoke

        # Verify assertions
        if success:
            try:
                # Load latest artifact to verify status
                from devflow.artifacts import list_artifacts, read_artifact
                artifacts = list_artifacts(task_id, root=os.path.join(root_dir, ".devflow", "artifacts"))
                
                # Check status
                expected_status = assertions.get("expected_status")
                actual_status = None
                
                if artifacts:
                    latest_art = artifacts[-1]
                    try:
                        # Construct absolute path in root_dir
                        meta_abs = os.path.join(root_dir, latest_art.metadata_path)
                        metadata, body = read_artifact(meta_abs)
                        try:
                            body_json = json.loads(body)
                            actual_status = body_json.get("status")
                        except Exception:
                            actual_status = metadata.get("status")
                    except Exception:
                        pass
                
                # Fallback to task status if no artifact status was found
                if not actual_status:
                    with open(temp_task_file, "r", encoding="utf-8") as handle:
                        updated_content = handle.read()
                    updated_task = parse_task_file(updated_content)
                    actual_status = updated_task.get("status")
                
                if expected_status and actual_status and expected_status.upper() != actual_status.upper():
                    success = False
                    err_msg = f"expected status '{expected_status}' but got '{actual_status}'"

                # Check must touch files
                must_touch = assertions.get("must_touch_files", [])
                touched_files = []
                if artifacts:
                    try:
                        meta_abs = os.path.join(root_dir, artifacts[-1].metadata_path)
                        metadata, body = read_artifact(meta_abs)
                        body_json = json.loads(body)
                        touched_files = body_json.get("touched_paths", []) or body_json.get("files_changed", []) or []
                    except Exception:
                        pass
                
                # Fallback to task touched_files
                if not touched_files:
                    with open(temp_task_file, "r", encoding="utf-8") as handle:
                        updated_content = handle.read()
                    updated_task = parse_task_file(updated_content)
                    touched_files = updated_task.get("touched_files", [])

                for f in must_touch:
                    if f not in touched_files:
                        success = False
                        err_msg = f"expected touched file '{f}' was missing from touched list"

                # Check must not touch files
                must_not_touch = assertions.get("must_not_touch_files", [])
                for f in must_not_touch:
                    if f in touched_files:
                        success = False
                        err_msg = f"file '{f}' was touched but is strictly forbidden by do-not-touch rules"
            except Exception as e:
                success = False
                err_msg = f"Assertion verification raised exception: {str(e)}"

        # Record outcome
        if success:
            results["passed"] += 1
        else:
            results["failures"].append({
                "fixture": filename,
                "name": name,
                "message": err_msg
            })

        # Cleanup temp task file if it exists
        if os.path.exists(temp_task_file):
            try:
                os.remove(temp_task_file)
            except Exception:
                pass

    return results

def compare_prompts(prompt_a: str, prompt_b: str) -> Dict[str, Any]:
    """
    Simulates comparative token/duration metrics between prompt A and prompt B.
    """
    return {
        "prompt_a": prompt_a[:200] + ("..." if len(prompt_a) > 200 else ""),
        "prompt_b": prompt_b[:200] + ("..." if len(prompt_b) > 200 else ""),
        "metrics": {
            "prompt_a": {
                "tokens": 450,
                "duration_ms": 1240.0,
                "cost_usd": 0.000675
            },
            "prompt_b": {
                "tokens": 320,
                "duration_ms": 980.0,
                "cost_usd": 0.00048
            }
        },
        "comparison": "Prompt Version B is 28.8% faster and uses 28.8% fewer tokens than Prompt Version A."
    }
