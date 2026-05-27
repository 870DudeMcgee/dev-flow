import datetime
import re
import shutil
import subprocess
from typing import Dict, List, Tuple, Any

TDD_STATES = {"PENDING", "RED", "GREEN", "REFACTOR", "REPORT"}

ALLOWED_TRANSITIONS = {
    "PENDING": {"RED", "GREEN", "BLOCKED", "FAILED"},
    "RED": {"GREEN", "BLOCKED", "FAILED"},
    "GREEN": {"REFACTOR", "REPORT", "BLOCKED", "FAILED"},
    "REFACTOR": {"REPORT", "BLOCKED", "FAILED"},
    "REPORT": set(),
    "BLOCKED": {"PENDING", "RED", "GREEN", "REFACTOR"},
    "FAILED": {"PENDING", "RED", "GREEN", "REFACTOR"},
}

def validate_transition(from_state: str, to_state: str) -> bool:
    """Validates if a TDD state transition is canonically allowed."""
    # Convert states to uppercase for robust matching
    fs = from_state.upper() if from_state else "PENDING"
    ts = to_state.upper() if to_state else "PENDING"
    return ts in ALLOWED_TRANSITIONS.get(fs, set())

def execute_recipe(recipe: dict, cwd: str) -> dict:
    """
    Executes a single structured verification recipe:
    {
       "command": "...",
       "expected": "pass" | "fail",
       "failure_must_contain": "...",
       "optional_if_missing": bool
    }
    """
    cmd = recipe.get("command", "")
    expected = recipe.get("expected", "pass")
    must_contain = recipe.get("failure_must_contain", "")
    optional = recipe.get("optional_if_missing", False)

    # Handle optional if missing
    cmd_base = cmd.split()[0] if cmd else ""
    if optional and not shutil.which(cmd_base):
        return {
            "command": cmd,
            "exit_code": 0,
            "stdout": "",
            "stderr": "",
            "success": True,
            "message": "Command skipped (optional and missing)"
        }

    proc = subprocess.run(
        cmd,
        cwd=cwd,
        shell=True,
        text=True,
        capture_output=True
    )

    exit_code = proc.returncode
    stdout = proc.stdout
    stderr = proc.stderr
    combined = stdout + "\n" + stderr

    success = False
    msg = ""
    if expected == "fail":
        if exit_code != 0:
            if must_contain:
                if re.search(must_contain, combined):
                    success = True
                else:
                    msg = f"Expected failure message regex '{must_contain}' not found"
            else:
                success = True
        else:
            msg = "Expected command to fail, but it exited with 0"
    else:  # expected == "pass"
        if exit_code == 0:
            success = True
        else:
            msg = f"Command failed unexpectedly with code {exit_code}"

    return {
        "command": cmd,
        "exit_code": exit_code,
        "stdout": stdout,
        "stderr": stderr,
        "success": success,
        "message": msg
    }
