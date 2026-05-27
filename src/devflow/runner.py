from __future__ import annotations

import datetime
import fnmatch
import os
import re
import shutil
import shlex
import subprocess
from typing import Dict, List, Tuple


from devflow.failures import DEFAULT_TAXONOMY, classify_failure, retry_budget_for




def run_shell(command: str, cwd: str, input_text: str | None = None) -> Tuple[int, str, str]:
    proc = subprocess.run(
        command,
        cwd=cwd,
        shell=True,
        text=True,
        capture_output=True,
        input=input_text,
    )
    return proc.returncode, proc.stdout, proc.stderr


def get_dirty_worktree_files(cwd: str) -> Tuple[bool, List[str], str]:
    code, out, err = run_shell("git status --porcelain", cwd)
    if code != 0:
        return False, [], err.strip()

    files: List[str] = []
    for line in out.splitlines():
        path = line[3:].strip()
        if " -> " in path:
            path = path.split(" -> ", 1)[1].strip()
        if path:
            files.append(path)
    return len(files) == 0, sorted(set(files)), ""


def discover_verification_commands(config: Dict[str, object], cwd: str) -> List[str]:
    configured = config.get("verification", {}) if isinstance(config.get("verification", {}), dict) else {}
    commands: List[str] = []

    for key in ("test_command", "lint_command", "typecheck_command", "format_check_command"):
        value = configured.get(key) if isinstance(configured, dict) else None
        if isinstance(value, str) and value.strip() and value.strip().lower() != "auto":
            commands.append(value.strip())

    if commands:
        return commands

    has_python_sources = False
    has_tests = os.path.isdir(os.path.join(cwd, "tests"))
    for root, _, files in os.walk(cwd):
        if ".devflow" in root or ".git" in root or ".venv" in root:
            continue
        if any(name.endswith(".py") for name in files):
            has_python_sources = True
            break

    if has_tests and shutil.which("pytest"):
        commands.append("pytest")
    if has_python_sources and shutil.which("ruff"):
        commands.append("ruff check .")

    return commands


def detect_files_from_unified_diff(diff_text: str) -> List[str]:
    files: List[str] = []
    pattern = re.compile(r"^\+\+\+\s+b/(.+)$", re.MULTILINE)
    for match in pattern.finditer(diff_text):
        path = match.group(1).strip()
        if path != "/dev/null":
            files.append(path)
    return sorted(set(files))


def protected_paths_touched(paths: List[str], patterns: List[str]) -> List[str]:
    touched: List[str] = []
    for path in paths:
        normalized = path.replace("\\", "/")
        for pattern in patterns:
            if fnmatch.fnmatch(normalized, pattern) or fnmatch.fnmatch(os.path.basename(normalized), pattern):
                touched.append(path)
                break
    return sorted(set(touched))


def _normalize_scope_pattern(pattern: str) -> str:
    normalized = pattern.strip().strip("`").replace("\\", "/")
    if normalized.endswith("/..."):
        return f"{normalized[:-4]}/**"
    if normalized.endswith("..."):
        return f"{normalized[:-3]}**"
    return normalized


def path_matches_scope(path: str, pattern: str) -> bool:
    normalized_path = path.replace("\\", "/")
    normalized_pattern = _normalize_scope_pattern(pattern)
    return normalized_path == normalized_pattern or fnmatch.fnmatch(normalized_path, normalized_pattern)


def paths_outside_allowed(paths: List[str], allowed_patterns: List[str]) -> List[str]:
    outside: List[str] = []
    for path in paths:
        if not any(path_matches_scope(path, pattern) for pattern in allowed_patterns):
            outside.append(path)
    return sorted(set(outside))




def create_checkpoint_branch(cwd: str, task_id: str, branch_prefix: str) -> Tuple[bool, str, str]:
    code, base_branch, err = run_shell("git rev-parse --abbrev-ref HEAD", cwd)
    if code != 0:
        return False, "", err

    checkpoint = f"{branch_prefix}{task_id}".replace(" ", "-")
    code, _, _ = run_shell(f"git rev-parse --verify {checkpoint}", cwd)
    if code == 0:
        checkpoint = f"{checkpoint}-{datetime.datetime.utcnow().strftime('%Y%m%d%H%M%S')}"

    create_code, _, create_err = run_shell(f"git checkout -b {checkpoint}", cwd)
    if create_code != 0:
        return False, "", create_err
    return True, base_branch.strip(), checkpoint


def dry_run_apply(diff_text: str, cwd: str) -> Tuple[bool, str]:
    code, out, err = run_shell("git apply --check --whitespace=nowarn -", cwd, input_text=diff_text)
    return code == 0, (out + err).strip()


def apply_patch(diff_text: str, cwd: str) -> Tuple[bool, str]:
    code, out, err = run_shell("git apply --whitespace=nowarn -", cwd, input_text=diff_text)
    return code == 0, (out + err).strip()


def rollback_to_checkpoint(cwd: str, files_changed: List[str]) -> Tuple[bool, str]:
    reset_code, reset_out, reset_err = run_shell("git reset --hard HEAD", cwd)
    if reset_code != 0:
        return False, (reset_out + reset_err).strip()

    removed: List[str] = []
    for path in files_changed:
        normalized = path.replace("\\", "/")
        if os.path.isabs(normalized) or normalized.startswith("../") or "/../" in normalized:
            continue

        code, out, _ = run_shell(f"git ls-files --others --exclude-standard -- {shlex.quote(normalized)}", cwd)
        untracked = {line.strip() for line in out.splitlines() if line.strip()} if code == 0 else set()
        if normalized not in untracked:
            continue

        full_path = os.path.abspath(os.path.join(cwd, normalized))
        if not full_path.startswith(os.path.abspath(cwd) + os.sep):
            continue
        if os.path.isdir(full_path):
            shutil.rmtree(full_path)
            removed.append(normalized)
        elif os.path.exists(full_path):
            os.remove(full_path)
            removed.append(normalized)

    if removed:
        return True, f"checkpoint_reset; removed untracked files: {', '.join(sorted(removed))}"
    return True, "checkpoint_reset"


def run_verification(commands: List[str], cwd: str) -> Tuple[bool, List[Dict[str, object]]]:
    results: List[Dict[str, object]] = []
    overall_success = True
    for cmd in commands:
        code, out, err = run_shell(cmd, cwd)
        result = {
            "command": cmd,
            "exit_code": code,
            "stdout": out,
            "stderr": err,
            "success": code == 0,
        }
        results.append(result)
        if code != 0:
            overall_success = False
            break
    return overall_success, results


def write_task_report(report_path: str, payload: Dict[str, object]) -> None:
    lines = [
        f"# Task Report: {payload.get('task_id', 'unknown')}",
        "",
        f"- Status: {payload.get('status', 'UNKNOWN')}",
        f"- Assigned Agent: {payload.get('assigned_agent', '')}",
        f"- Owner Lock: {payload.get('owner_lock', '')}",
        f"- Touched Files: {', '.join(payload.get('touched_files', []))}",
        f"- Checkpoint Branch: {payload.get('checkpoint_branch', '')}",
        f"- Base Branch: {payload.get('base_branch', '')}",
        f"- Files Changed: {', '.join(payload.get('files_changed', []))}",
        f"- Protected Files Detected: {', '.join(payload.get('protected_files', []))}",
        f"- Patch Apply Result: {payload.get('patch_result', '')}",
        f"- Failure Classification: {payload.get('failure_classification', '')}",
        f"- Rollback Status: {payload.get('rollback_status', '')}",
        f"- Final Outcome: {payload.get('final_outcome', '')}",
        "",
    ]

    verification = payload.get("verification", [])
    lines.extend(["", "## Verification Commands"])
    if isinstance(verification, list) and verification:
        for item in verification:
            lines.append(f"- {item.get('command', '')}: exit {item.get('exit_code', '')}")
    else:
        lines.append("- No verification commands were available.")

    transitions = payload.get("status_transitions", [])
    if isinstance(transitions, list) and transitions:
        lines.extend(["", "## Status Transitions"])
        for transition in transitions:
            lines.append(f"- {transition}")

    lines.extend(
        [
            "",
            "## Safety Decisions",
            f"- Dirty Worktree: {payload.get('dirty_worktree_decision', '')}",
            f"- Protected Paths: {payload.get('protected_paths_decision', '')}",
            f"- Allowed Files: {payload.get('allowed_files_decision', '')}",
        ]
    )

    if isinstance(verification, list) and verification:
        lines.extend(["", "## Verification Output"])
        for item in verification:
            command = item.get("command", "")
            stdout = str(item.get("stdout", "")).strip()
            stderr = str(item.get("stderr", "")).strip()
            lines.append(f"### {command}")
            if stdout:
                lines.extend(["", "stdout:", "```text", stdout[:2000], "```"])
            if stderr:
                lines.extend(["", "stderr:", "```text", stderr[:2000], "```"])

    warnings = payload.get("warnings", [])
    if isinstance(warnings, list) and warnings:
        lines.extend(["", "## Warnings"])
        for warning in warnings:
            lines.append(f"- {warning}")

    os.makedirs(os.path.dirname(report_path), exist_ok=True)
    with open(report_path, "w", encoding="utf-8") as handle:
        handle.write("\n".join(lines).strip() + "\n")
