import json
import os
from typing import Any
from devflow.context import build_context_pack
from devflow.artifacts import write_artifact, read_artifact, ArtifactRecord
from devflow.manager import parse_task_file
from devflow.agents.profiles import load_agent_profile
from devflow.agents.ollama import invoke_local_model
from devflow.agents.schemas import validate_review_result, validate_diff_result
from devflow.safety import scan_diff_for_hazards

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
    
    # 4. Invoke local model
    try:
        response_text = invoke_local_model(
            model=profile.preferred_model,
            system_instruction=system_instruction,
            prompt=prompt,
            temperature=profile.temperature,
            json_mode=True
        )
        diff_data = json.loads(response_text)
        
        # Validate diff_data first before running scanner
        validate_diff_result(diff_data)
        
        # Call safety scanner to audit unified diff additions for secrets, subprocess, sockets, or exec hazards
        diff_text = diff_data.get("diff", "")
        is_clean, findings = scan_diff_for_hazards(diff_text)
        if not is_clean:
            diff_data["status"] = "blocked"
            diff_data["blocked_reason"] = f"Safety scan findings: {'; '.join(findings)}"
            
    except Exception as exc:
        # Gracefully degrade to BLOCKED/FAILED on failure to satisfy Strategic Rule #7
        diff_data = {
            "status": "blocked",
            "diff": "",
            "touched_paths": [],
            "risk": "critical",
            "confidence": 0.0,
            "blocked_reason": f"Implementation execution failed or produced invalid JSON: {exc}"
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
    
    # 4. Invoke local model
    try:
        response_text = invoke_local_model(
            model=profile.preferred_model,
            system_instruction=system_instruction,
            prompt=prompt,
            temperature=profile.temperature,
            json_mode=True
        )
        review_data = json.loads(response_text)
        validate_review_result(review_data)
    except Exception as exc:
        # Gracefully degrade to BLOCKED on failure to satisfy Strategic Rule #7
        review_data = {
            "status": "blocked",
            "summary": f"Review execution failed or produced invalid JSON: {exc}",
            "findings": [],
            "required_actions": [],
            "confidence": 0.0,
            "blocked_reason": str(exc)
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
