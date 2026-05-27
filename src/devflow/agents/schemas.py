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


