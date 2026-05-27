import json
import os

def validate_review_result(review_data: dict) -> None:
    """
    Validate the review result data structure against our canonical schema.
    Provides fast, dependency-free structural parsing.
    """
    schema_path = os.path.abspath(
        os.path.join(os.path.dirname(__file__), "..", "schemas", "review_result.schema.json")
    )
    if not os.path.exists(schema_path):
        # Fallback quick structural check
        for key in ("status", "summary", "findings", "required_actions", "confidence"):
            if key not in review_data:
                raise ValueError(f"Review schema error: missing required key: {key}")
        return

    with open(schema_path, "r", encoding="utf-8") as handle:
        schema = json.load(handle)

    # Perform structural validation to satisfy strategic specs without third-party dependencies
    for key in schema.get("required", []):
        if key not in review_data:
            raise ValueError(f"Schema validation failure: missing required field: {key}")
            
    status = review_data.get("status")
    allowed_statuses = schema["properties"]["status"]["enum"]
    if status not in allowed_statuses:
        raise ValueError(f"Schema validation failure: status '{status}' must be one of {allowed_statuses}")
        
    confidence = review_data.get("confidence")
    if not isinstance(confidence, (int, float)) or not (0 <= confidence <= 1):
        raise ValueError(f"Schema validation failure: confidence '{confidence}' must be a float between 0.0 and 1.0")
        
    findings = review_data.get("findings")
    if not isinstance(findings, list):
        raise ValueError("Schema validation failure: findings must be a list")
    
    for index, finding in enumerate(findings):
        if not isinstance(finding, dict):
            raise ValueError(f"Schema validation failure: finding at index {index} must be an object")
        for req_field in ["severity", "category", "file", "message"]:
            if req_field not in finding:
                raise ValueError(f"Schema validation failure: finding at index {index} is missing required field: {req_field}")
        severity = finding.get("severity")
        if severity not in ["blocking", "non_blocking"]:
            raise ValueError(f"Schema validation failure: finding at index {index} has invalid severity: {severity}")
            
    required_actions = review_data.get("required_actions")
    if not isinstance(required_actions, list):
        raise ValueError("Schema validation failure: required_actions must be a list")


def validate_diff_result(diff_data: dict) -> None:
    """
    Validate the diff result data structure against our canonical schema.
    Provides fast, dependency-free structural parsing.
    """
    schema_path = os.path.abspath(
        os.path.join(os.path.dirname(__file__), "..", "schemas", "diff_result.schema.json")
    )
    if not os.path.exists(schema_path):
        # Fallback quick structural check
        for key in ("status", "diff", "touched_paths", "risk", "confidence"):
            if key not in diff_data:
                raise ValueError(f"Diff schema error: missing required key: {key}")
        return

    with open(schema_path, "r", encoding="utf-8") as handle:
        schema = json.load(handle)

    # Perform structural validation to satisfy strategic specs without third-party dependencies
    for key in schema.get("required", []):
        if key not in diff_data:
            raise ValueError(f"Schema validation failure: missing required field: {key}")
            
    status = diff_data.get("status")
    allowed_statuses = schema["properties"]["status"]["enum"]
    if status not in allowed_statuses:
        raise ValueError(f"Schema validation failure: status '{status}' must be one of {allowed_statuses}")
        
    confidence = diff_data.get("confidence")
    if not isinstance(confidence, (int, float)) or not (0 <= confidence <= 1):
        raise ValueError(f"Schema validation failure: confidence '{confidence}' must be a float between 0.0 and 1.0")
        
    touched_paths = diff_data.get("touched_paths")
    if not isinstance(touched_paths, list):
        raise ValueError("Schema validation failure: touched_paths must be a list")
    
    diff_val = diff_data.get("diff")
    if not isinstance(diff_val, str):
        raise ValueError("Schema validation failure: diff must be a string")
        
    risk = diff_data.get("risk")
    allowed_risks = schema["properties"]["risk"]["enum"]
    if risk not in allowed_risks:
        raise ValueError(f"Schema validation failure: risk '{risk}' must be one of {allowed_risks}")


def validate_repair_result(repair_data: dict) -> None:
    """
    Validate the repair result data structure against our canonical schema.
    Provides fast, dependency-free structural parsing.
    """
    schema_path = os.path.abspath(
        os.path.join(os.path.dirname(__file__), "..", "schemas", "repair_result.schema.json")
    )
    if not os.path.exists(schema_path):
        # Fallback quick structural check
        for key in ("status", "diff", "touched_paths", "risk", "confidence"):
            if key not in repair_data:
                raise ValueError(f"Repair schema error: missing required key: {key}")
        return

    with open(schema_path, "r", encoding="utf-8") as handle:
        schema = json.load(handle)

    # Perform structural validation to satisfy strategic specs without third-party dependencies
    for key in schema.get("required", []):
        if key not in repair_data:
            raise ValueError(f"Schema validation failure: missing required field: {key}")
            
    status = repair_data.get("status")
    allowed_statuses = schema["properties"]["status"]["enum"]
    if status not in allowed_statuses:
        raise ValueError(f"Schema validation failure: status '{status}' must be one of {allowed_statuses}")
        
    confidence = repair_data.get("confidence")
    if not isinstance(confidence, (int, float)) or not (0 <= confidence <= 1):
        raise ValueError(f"Schema validation failure: confidence '{confidence}' must be a float between 0.0 and 1.0")
        
    touched_paths = repair_data.get("touched_paths")
    if not isinstance(touched_paths, list):
        raise ValueError("Schema validation failure: touched_paths must be a list")
    
    diff_val = repair_data.get("diff")
    if not isinstance(diff_val, str):
        raise ValueError("Schema validation failure: diff must be a string")
        
    risk = repair_data.get("risk")
    allowed_risks = schema["properties"]["risk"]["enum"]
    if risk not in allowed_risks:
        raise ValueError(f"Schema validation failure: risk '{risk}' must be one of {allowed_risks}")


import re

def repair_and_parse_json(text: str) -> dict:
    """
    Extracts and parses JSON from text, repairing truncated or slightly malformed
    JSON block responses from LLMs.
    """
    text_clean = text.strip()
    
    # 1. Try direct parse first
    try:
        return json.loads(text_clean)
    except json.JSONDecodeError:
        pass

    # 2. Extract code block content if wrapped in ```json ... ```
    match = re.search(r"```(?:json)?\s*([\s\S]*?)\s*```", text_clean, re.IGNORECASE)
    if match:
        candidate = match.group(1).strip()
        try:
            return json.loads(candidate)
        except json.JSONDecodeError:
            text_clean = candidate

    # 3. Perform a robust character-by-character scan to repair truncated braces/brackets and open quotes
    start_idx = text_clean.find("{")
    if start_idx == -1:
        # Fallback: maybe it's a list?
        start_idx = text_clean.find("[")
        if start_idx == -1:
            raise ValueError("No JSON object or array start found in text")
    
    truncated_candidate = text_clean[start_idx:]
    
    repaired = []
    stack = []  # tracks '{' or '['
    in_string = False
    escaped = False
    
    i = 0
    while i < len(truncated_candidate):
        char = truncated_candidate[i]
        
        if in_string:
            if escaped:
                repaired.append(char)
                escaped = False
            elif char == "\\":
                repaired.append(char)
                escaped = True
            elif char == '"':
                repaired.append(char)
                in_string = False
            elif char == "\n":
                # JSON strings cannot have literal newlines, escape it
                repaired.append("\\n")
            else:
                repaired.append(char)
        else:
            if char == '"':
                repaired.append(char)
                in_string = True
            elif char in ("{", "["):
                repaired.append(char)
                stack.append(char)
            elif char in ("}", "]"):
                if stack:
                    expected = "{" if char == "}" else "["
                    if stack[-1] == expected:
                        stack.pop()
                repaired.append(char)
            elif char == ",":
                repaired.append(char)
            else:
                repaired.append(char)
        i += 1
        
    # Close unclosed string quote if still open
    if in_string:
        if escaped and repaired and repaired[-1] == "\\":
            repaired.pop()
        repaired.append('"')
        
    repaired_str = "".join(repaired).strip()
    
    # Prune trailing commas before closing punctuation
    repaired_str = re.sub(r",\s*([}\]])", r"\1", repaired_str)
    
    # Close any unclosed brackets/braces on stack
    while stack:
        container = stack.pop()
        closing = "}" if container == "{" else "]"
        repaired_str = repaired_str.rstrip()
        if repaired_str.endswith(","):
            repaired_str = repaired_str[:-1].rstrip()
        repaired_str += closing
        
    # Return the parsed repaired JSON
    return json.loads(repaired_str)


