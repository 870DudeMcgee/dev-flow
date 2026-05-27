import json
import os
import sys
from typing import Any
from devflow.context import build_context_pack
from devflow.artifacts import write_artifact, read_artifact, ArtifactRecord
from devflow.manager import parse_task_file
from devflow.agents.profiles import load_agent_profile
from devflow.agents import ollama
from devflow.agents.schemas import validate_review_result, validate_diff_result, validate_repair_result, repair_and_parse_json
from devflow.safety import scan_diff_for_hazards
from devflow.failures import serialize_failure, retry_budget_for
from devflow.manager import extract_unified_diff
from devflow.runner import (
    create_checkpoint_branch,
    apply_patch,
    run_verification,
    rollback_to_checkpoint,
    discover_verification_commands,
    protected_paths_touched,
    detect_files_from_unified_diff,
    paths_outside_allowed,
)
from devflow.workspace import load_config


def run_implement_agent(task_file: str, profile_name: str = "implementer", cwd: str = ".") -> ArtifactRecord:
    """
    Runs a stateless implementer agent for a task.
    Builds context, invokes Ollama, performs adversarial safety scanner audit,
    validates schema, and writes a diff_result artifact.
    """
    cwd = os.path.abspath(cwd)
    profile = load_agent_profile(profile_name, cwd=cwd)
    
    # 1. Build bounded context pack
    context_record = build_context_pack(task_file, role=profile.role, cwd=cwd)
    _, context_body = read_artifact(os.path.join(cwd, context_record.metadata_path))
    
    # 2. Load task data
    with open(os.path.join(cwd, task_file), "r", encoding="utf-8") as handle:
        raw_task = handle.read()
    task = parse_task_file(raw_task)
    task_id = str(task.get("task_id", "unknown"))

    # 3. Formulate system instruction and prompt
    system_instruction = (
        "You are an expert Software Engineer. Analyze the task contract and context "
        "and provide code modifications (as a unified diff) in strict JSON format. "
        "Do not return markdown, only output raw JSON matching the diff_result schema:\n"
        "{\n"
        "  \"status\": \"ready\" | \"blocked\" | \"failed\",\n"
        "  \"diff\": \"string (unified diff format)\",\n"
        "  \"touched_paths\": [\"string\"],\n"
        "  \"risk\": \"low\" | \"medium\" | \"high\" | \"critical\",\n"
        "  \"confidence\": float (0.0 to 1.0)\n"
        "}"
    )
    
    prompt = f"TASK CONTRACT AND CONTEXT:\n{context_body}\n"
    
    # 4. Invoke local model (with automatic fallback on failure/memory limits)
    models_to_try = [profile.preferred_model] + profile.fallback_models
    last_exc = None
    response_text = None
    successful_model = profile.preferred_model
    
    for model in models_to_try:
        try:
            response_text = ollama.invoke_local_model(
                model=model,
                system_instruction=system_instruction,
                prompt=prompt,
                temperature=profile.temperature,
                json_mode=True
            )
            successful_model = model
            break
        except Exception as exc:
            last_exc = exc
            print(f"Warning: Model {model} failed (e.g. memory pressure). Error: {exc}", file=sys.stderr)
            print(f"Attempting fallback model...", file=sys.stderr)
            
    if response_text is not None:
        try:
            diff_data = repair_and_parse_json(response_text)
            validate_diff_result(diff_data)
            
            diff_text = diff_data.get("diff", "")
            is_clean, findings = scan_diff_for_hazards(diff_text)
            if not is_clean:
                diff_data["status"] = "blocked"
                diff_data["blocked_reason"] = f"Safety scan findings: {'; '.join(findings)}"
        except Exception as exc:
            diff_data = {
                "status": "blocked",
                "diff": "",
                "touched_paths": [],
                "risk": "critical",
                "confidence": 0.0,
                "blocked_reason": f"JSON parsing or validation of agent response failed: {exc}"
            }
    else:
        diff_data = {
            "status": "blocked",
            "diff": "",
            "touched_paths": [],
            "risk": "critical",
            "confidence": 0.0,
            "blocked_reason": f"Implementation execution failed on all model options: {last_exc}"
        }

    body = json.dumps(diff_data, indent=2, sort_keys=True)
    
    # 5. Write Diff Result Artifact
    return write_artifact(
        task_id=task_id,
        artifact_type="diff_result.json",
        body=body,
        role=profile.role,
        input_text=prompt,
        parent_artifacts=[context_record.artifact_id],
        allowed_paths=list(task.get("allowed_files", [])),
        risk=diff_data.get("risk", "low"),
        confidence=diff_data.get("confidence"),
        verification_status="passing",
        apply_status="not_applied",
        model=profile.preferred_model,
        agent_profile=profile_name,
        cwd=cwd
    )


def run_review_agent(task_file: str, profile_name: str = "reviewer", cwd: str = ".") -> ArtifactRecord:
    """
    Runs a stateless review agent for a task.
    Builds context, invokes Ollama, validates schema, and writes a review artifact.
    """
    cwd = os.path.abspath(cwd)
    profile = load_agent_profile(profile_name, cwd=cwd)
    
    # 1. Build bounded context pack
    context_record = build_context_pack(task_file, role=profile.role, cwd=cwd)
    _, context_body = read_artifact(os.path.join(cwd, context_record.metadata_path))
    
    # 2. Load task data
    with open(os.path.join(cwd, task_file), "r", encoding="utf-8") as handle:
        raw_task = handle.read()
    task = parse_task_file(raw_task)
    task_id = str(task.get("task_id", "unknown"))

    # 3. Formulate system instruction and prompt
    system_instruction = (
        "You are an expert Staff Code Reviewer. Analyze the task contract and context "
        "and provide a structured review in strict JSON format. Do not return markdown, "
        "only output raw JSON matching the review_result schema:\n"
        "{\n"
        "  \"status\": \"approved\" | \"changes_requested\" | \"blocked\",\n"
        "  \"summary\": \"string (minLength: 5)\",\n"
        "  \"findings\": [\n"
        "    {\n"
        "      \"severity\": \"blocking\" | \"non_blocking\",\n"
        "      \"category\": \"string\",\n"
        "      \"file\": \"string\",\n"
        "      \"line\": integer,\n"
        "      \"message\": \"string\",\n"
        "      \"suggested_fix\": \"string\"\n"
        "    }\n"
        "  ],\n"
        "  \"required_actions\": [\"string\"],\n"
        "  \"confidence\": float (0.0 to 1.0)\n"
        "}"
    )
    
    prompt = f"TASK CONTRACT AND CONTEXT:\n{context_body}\n"
    
    # 4. Invoke local model (with automatic fallback on failure/memory limits)
    models_to_try = [profile.preferred_model] + profile.fallback_models
    last_exc = None
    response_text = None
    successful_model = profile.preferred_model
    
    for model in models_to_try:
        try:
            response_text = ollama.invoke_local_model(
                model=model,
                system_instruction=system_instruction,
                prompt=prompt,
                temperature=profile.temperature,
                json_mode=True
            )
            successful_model = model
            break
        except Exception as exc:
            last_exc = exc
            print(f"Warning: Model {model} failed. Error: {exc}", file=sys.stderr)
            print(f"Attempting fallback model...", file=sys.stderr)
            
    if response_text is not None:
        try:
            review_data = repair_and_parse_json(response_text)
            validate_review_result(review_data)
        except Exception as exc:
            review_data = {
                "status": "blocked",
                "summary": f"JSON parsing or validation of agent response failed: {exc}",
                "findings": [],
                "required_actions": [],
                "confidence": 0.0,
                "blocked_reason": str(exc)
            }
    else:
        review_data = {
            "status": "blocked",
            "summary": f"Review execution failed on all model options: {last_exc}",
            "findings": [],
            "required_actions": [],
            "confidence": 0.0,
            "blocked_reason": str(last_exc)
        }

    body = json.dumps(review_data, indent=2, sort_keys=True)
    
    # 5. Write Review Artifact
    return write_artifact(
        task_id=task_id,
        artifact_type="review.json",
        body=body,
        role=profile.role,
        input_text=prompt,
        parent_artifacts=[context_record.artifact_id],
        allowed_paths=list(task.get("allowed_files", [])),
        risk="low",
        confidence=review_data.get("confidence"),
        verification_status="passing",
        apply_status="not_applied",
        model=profile.preferred_model,
        agent_profile=profile_name,
        cwd=cwd
    )


MAP_FAILURE_TO_PROFILE = {
    "PATCH_APPLY_FAILURE": "repair",
    "SYNTAX_ERROR": "syntax_repair",
    "IMPORT_ERROR": "import_repair",
    "TEST_FAILURE": "test_repair",
    "LINT_FAILURE": "lint_repair",
    "TYPE_ERROR": "type_repair",
    "UNKNOWN_FAILURE": "repair"
}

def _query_repair_model(task_file: str, diff_text: str, failure_dict: dict, cwd: str) -> str:
    profile_name = MAP_FAILURE_TO_PROFILE.get(failure_dict["classification"], "repair")
    profile = load_agent_profile(profile_name, cwd=cwd)
    
    # Build context pack
    context_record = build_context_pack(task_file, role=profile.role, cwd=cwd)
    _, context_body = read_artifact(os.path.join(cwd, context_record.metadata_path))
    
    system_instruction = (
        "You are an expert Software Engineer specializing in code repair. Analyze the task, the failing diff, "
        "and the verification failure log, and return an improved corrected unified diff in strict JSON format. "
        "Do not return markdown, only output raw JSON matching the repair_result schema:\n"
        "{\n"
        "  \"status\": \"ready\" | \"blocked\" | \"failed\",\n"
        "  \"diff\": \"string (improved unified diff format)\",\n"
        "  \"touched_paths\": [\"string\"],\n"
        "  \"risk\": \"low\" | \"medium\" | \"high\" | \"critical\",\n"
        "  \"confidence\": float (0.0 to 1.0)\n"
        "}"
    )
    
    prompt = (
        f"TASK CONTRACT AND CONTEXT:\n{context_body}\n\n"
        f"FAILING DIFF:\n{diff_text}\n\n"
        f"FAILURE CLASSIFICATION: {failure_dict['classification']}\n"
        f"FAILED COMMAND: {failure_dict['command']}\n"
        f"FAILURE OUTPUT:\n{failure_dict['output']}\n"
    )
    
    models_to_try = [profile.preferred_model] + profile.fallback_models
    response_text = None
    
    for model in models_to_try:
        try:
            response_text = ollama.invoke_local_model(
                model=model,
                system_instruction=system_instruction,
                prompt=prompt,
                temperature=profile.temperature,
                json_mode=True
            )
            break
        except Exception as exc:
            print(f"Warning: Model {model} failed during repair query. Error: {exc}", file=sys.stderr)
            print(f"Attempting fallback model...", file=sys.stderr)
            
    if response_text is not None:
        try:
            repair_data = repair_and_parse_json(response_text)
            validate_repair_result(repair_data)
            return repair_data.get("diff", "")
        except Exception:
            pass
            
    # Gracefully degrade to returning the original diff
    return diff_text


def run_repair_agent(task_file: str, max_loops: int = 3, profile_name: str = "repair", cwd: str = ".") -> ArtifactRecord:
    """
    Runs a test-driven automated repair loop on a task file.
    Runs inside a safe git checkpoint branch.
    Rolls back any changes before final completion to ensure repair output remains unapplied.
    """
    cwd = os.path.abspath(cwd)
    
    # Check clean worktree
    from devflow.runner import get_dirty_worktree_files
    clean, _, _ = get_dirty_worktree_files(cwd)
    if not clean:
        raise ValueError("Git worktree is dirty. Commit or stash changes before running repair.")
        
    with open(os.path.join(cwd, task_file), "r", encoding="utf-8") as handle:
        raw_markdown = handle.read()
    task = parse_task_file(raw_markdown)
    task_id = str(task.get("task_id", "unknown"))
    
    # Load initial diff
    diff_text = extract_unified_diff(raw_markdown)
    if not diff_text.strip():
        # Call implementer first to get an initial diff
        implement_record = run_implement_agent(task_file, cwd=cwd)
        _, implement_body = read_artifact(os.path.join(cwd, implement_record.metadata_path))
        try:
            implement_data = json.loads(implement_body)
            diff_text = implement_data.get("diff", "")
        except Exception:
            pass
            
    # Load config and commands
    config = load_config()
    commands = task.get("verification_commands") or discover_verification_commands(config, cwd)
    
    # Create checkpoint branch
    ok, base_branch, checkpoint = create_checkpoint_branch(
        cwd=cwd,
        task_id=task_id,
        branch_prefix=config.get("git", {}).get("branch_prefix", "devflow/task-"),
    )
    if not ok:
        raise ValueError(f"Error creating checkpoint branch: {checkpoint}")
        
    # Start repair loop
    final_artifact_record = None
    for loop_idx in range(max_loops):
        files_changed = detect_files_from_unified_diff(diff_text)
        
        # Enforce protected paths
        protected_patterns = config.get("risk", {}).get("protected_paths", [])
        protected = protected_paths_touched(files_changed, protected_patterns)
        if protected:
            rollback_to_checkpoint(cwd, files_changed)
            final_artifact_record = write_artifact(
                task_id=task_id,
                artifact_type="repair_result.json",
                body=json.dumps({
                    "status": "blocked",
                    "diff": diff_text,
                    "touched_paths": files_changed,
                    "risk": "critical",
                    "confidence": 0.0,
                    "blocked_reason": f"Protected paths touched: {', '.join(protected)}"
                }, indent=2, sort_keys=True),
                role="repair",
                input_text="",
                parent_artifacts=[],
                allowed_paths=list(task.get("allowed_files", [])),
                risk="critical",
                confidence=0.0,
                verification_status="blocked",
                apply_status="not_applied",
                cwd=cwd
            )
            break
            
        # Enforce allowed files
        allowed = task.get("allowed_files", [])
        if isinstance(allowed, list) and allowed:
            outside_allowed = paths_outside_allowed(files_changed, allowed)
            if outside_allowed:
                rollback_to_checkpoint(cwd, files_changed)
                final_artifact_record = write_artifact(
                    task_id=task_id,
                    artifact_type="repair_result.json",
                    body=json.dumps({
                        "status": "blocked",
                        "diff": diff_text,
                        "touched_paths": files_changed,
                        "risk": "critical",
                        "confidence": 0.0,
                        "blocked_reason": f"Modifies files outside allowed: {', '.join(outside_allowed)}"
                    }, indent=2, sort_keys=True),
                    role="repair",
                    input_text="",
                    parent_artifacts=[],
                    allowed_paths=list(task.get("allowed_files", [])),
                    risk="critical",
                    confidence=0.0,
                    verification_status="blocked",
                    apply_status="not_applied",
                    cwd=cwd
                )
                break
                
        # Apply patch temporarily
        apply_ok, apply_output = apply_patch(diff_text, cwd)
        if not apply_ok:
            failure_dict = serialize_failure("patch", apply_output)

            failure_record = write_artifact(
                task_id=task_id,
                artifact_type="failure_result.json",
                body=json.dumps(failure_dict, indent=2, sort_keys=True),
                role="repair",
                input_text=apply_output,
                parent_artifacts=[],
                allowed_paths=list(task.get("allowed_files", [])),
                risk="low",
                confidence=1.0,
                verification_status="failing",
                apply_status="not_applied",
                cwd=cwd
            )
            diff_text = _query_repair_model(task_file, diff_text, failure_dict, cwd)
            rollback_to_checkpoint(cwd, files_changed)
            continue
            
        # Run verification
        verify_ok, verify_results = run_verification(commands, cwd)
        if verify_ok:

            rollback_to_checkpoint(cwd, files_changed)
            final_artifact_record = write_artifact(
                task_id=task_id,
                artifact_type="repair_result.json",
                body=json.dumps({
                    "status": "ready",
                    "diff": diff_text,
                    "touched_paths": files_changed,
                    "risk": "low",
                    "confidence": 1.0
                }, indent=2, sort_keys=True),
                role="repair",
                input_text="",
                parent_artifacts=[],
                allowed_paths=list(task.get("allowed_files", [])),
                risk="low",
                confidence=1.0,
                verification_status="passing",
                apply_status="not_applied",
                cwd=cwd
            )
            break
            
        # Find failed command output
        failed_cmd = ""
        failed_output = ""
        for res in verify_results:
            if not res.get("success", False):
                failed_cmd = str(res.get("command", ""))
                failed_output = f"STDOUT:\n{res.get('stdout', '')}\nSTDERR:\n{res.get('stderr', '')}"
                break
                
        failure_dict = serialize_failure("verification", failed_output, failed_cmd)
        failure_record = write_artifact(
            task_id=task_id,
            artifact_type="failure_result.json",
            body=json.dumps(failure_dict, indent=2, sort_keys=True),
            role="repair",
            input_text=failed_output,
            parent_artifacts=[],
            allowed_paths=list(task.get("allowed_files", [])),
            risk="low",
            confidence=1.0,
            verification_status="failing",
            apply_status="not_applied",
            cwd=cwd
        )
        
        # Enforce failure retry budget
        budget = retry_budget_for(failure_dict["classification"])
        if budget <= 0:
            rollback_to_checkpoint(cwd, files_changed)
            final_artifact_record = write_artifact(
                task_id=task_id,
                artifact_type="repair_result.json",
                body=json.dumps({
                    "status": "failed",
                    "diff": diff_text,
                    "touched_paths": files_changed,
                    "risk": "high",
                    "confidence": 0.0,
                    "blocked_reason": f"Non-retryable failure classified: {failure_dict['classification']}"
                }, indent=2, sort_keys=True),
                role="repair",
                input_text="",
                parent_artifacts=[failure_record.artifact_id],
                allowed_paths=list(task.get("allowed_files", [])),
                risk="high",
                confidence=0.0,
                verification_status="failing",
                apply_status="not_applied",
                cwd=cwd
            )
            break
            
        # Call repair agent
        diff_text = _query_repair_model(task_file, diff_text, failure_dict, cwd)
        
        # Enforce safety scanner on newly repaired diff
        is_clean, findings = scan_diff_for_hazards(diff_text)
        if not is_clean:
            rollback_to_checkpoint(cwd, files_changed)
            final_artifact_record = write_artifact(
                task_id=task_id,
                artifact_type="repair_result.json",
                body=json.dumps({
                    "status": "blocked",
                    "diff": diff_text,
                    "touched_paths": files_changed,
                    "risk": "critical",
                    "confidence": 0.0,
                    "blocked_reason": f"Safety hazards detected in repaired diff: {'; '.join(findings)}"
                }, indent=2, sort_keys=True),
                role="repair",
                input_text="",
                parent_artifacts=[failure_record.artifact_id],
                allowed_paths=list(task.get("allowed_files", [])),
                risk="critical",
                confidence=0.0,
                verification_status="blocked",
                apply_status="not_applied",
                cwd=cwd
            )
            break
            
        rollback_to_checkpoint(cwd, files_changed)
        
    if final_artifact_record is None:
        # Budget exhausted!
        final_artifact_record = write_artifact(
            task_id=task_id,
            artifact_type="repair_result.json",
            body=json.dumps({
                "status": "blocked",
                "diff": diff_text,
                "touched_paths": [],
                "risk": "high",
                "confidence": 0.0,
                "blocked_reason": f"Repair budget exhausted after {max_loops} loops."
            }, indent=2, sort_keys=True),
            role="repair",
            input_text="",
            parent_artifacts=[],
            allowed_paths=list(task.get("allowed_files", [])),
            risk="high",
            confidence=0.0,
            verification_status="failing",
            apply_status="not_applied",
            cwd=cwd
        )
        
    return final_artifact_record

