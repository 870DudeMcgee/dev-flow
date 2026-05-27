import datetime
import json
import os
import re
from typing import Dict, List


SECTION_KEYS = {
    "1": "objective",
    "2": "allowed_files",
    "3": "do_not_touch",
    "4": "required_context",
    "5": "implementation_instructions",
    "6": "patch_protocol",
    "7": "verification_commands",
    "8": "failure_handling",
    "9": "execution_results",
    "10": "final_report",
}


def _parse_list_block(section_text: str) -> List[str]:
    items: List[str] = []
    for line in section_text.splitlines():
        stripped = line.strip()
        if stripped.startswith("- "):
            value = stripped[2:].strip().strip("`")
            if value:
                items.append(value)
    return items


def _clean_list_item(line: str) -> str:
    return line.strip()[2:].strip().strip("`")


def _metadata_insert_index(lines: List[str]) -> int:
    for index, line in enumerate(lines):
        if line.startswith("## "):
            return index
    return len(lines)


def replace_status(task_content: str, new_status: str) -> str:
    if re.search(r"^Status:\s*.*$", task_content, flags=re.MULTILINE):
        return re.sub(r"^Status:\s*.*$", f"Status: {new_status}", task_content, count=1, flags=re.MULTILINE)
    return task_content


def upsert_header(content: str, key: str, value: str) -> str:
    lines = content.splitlines()
    end = _metadata_insert_index(lines)
    pattern = re.compile(rf"^{re.escape(key)}:\s*.*$")
    for index in range(end):
        if pattern.match(lines[index]):
            lines[index] = f"{key}: {value}"
            return "\n".join(lines) + ("\n" if content.endswith("\n") else "")

    insert_at = 1 if lines and lines[0].startswith("# ") else end
    lines.insert(insert_at, f"{key}: {value}")
    return "\n".join(lines) + ("\n" if content.endswith("\n") else "")


def upsert_header_list(content: str, key: str, values: List[str]) -> str:
    lines = content.splitlines()
    end = _metadata_insert_index(lines)
    key_pattern = re.compile(rf"^{re.escape(key)}:\s*.*$")
    new_block = [f"{key}:"] + [f"- {value}" for value in values]

    for index in range(end):
        if not key_pattern.match(lines[index]):
            continue
        remove_end = index + 1
        while remove_end < end and lines[remove_end].strip().startswith("- "):
            remove_end += 1
        lines[index:remove_end] = new_block
        return "\n".join(lines) + ("\n" if content.endswith("\n") else "")

    insert_at = end
    lines[insert_at:insert_at] = new_block
    return "\n".join(lines) + ("\n" if content.endswith("\n") else "")


def _list_block(values: List[str], fallback: str = "- ") -> str:
    if not values:
        return fallback
    return "\n".join(f"- {value}" for value in values)


def build_task_template(
    task_id: str,
    title: str,
    goal: str = "",
    plan: str = "",
    agent: str = "",
    risk: str = "LOW",
    branch: str = "",
    allowed_files: List[str] | None = None,
    touched_files: List[str] | None = None,
    verification_commands: List[str] | None = None,
    skills: List[str] | None = None,
) -> str:
    allowed_files = allowed_files or []
    touched_files = touched_files or []
    verification_commands = verification_commands or []
    skills = skills or []
    branch = branch or f"devflow/task-{task_id}-{agent}" if agent else f"devflow/task-{task_id}"
    skills_block = _list_block(skills) if skills else ""

    return f"""# Task: {task_id} - {title}
Status: PENDING
Goal: {goal}
Plan: {plan}
Assigned Agent: {agent}
Owner Lock:
Risk: {risk}
Branch: {branch}
Touched Files:
{_list_block(touched_files)}
Skills:
{skills_block}

## 1. Objective

Describe the concrete outcome for this task.

## 2. Allowed Files

{_list_block(allowed_files)}

## 3. Do Not Touch

- .env
- production secrets
- unrelated files outside Allowed Files

## 4. Required Context

Add relevant architecture notes, file excerpts, or decisions.

## 5. Implementation Instructions

Describe the implementation steps for the owning orchestrator.

## 6. Patch Protocol

Unified diff only.

## 7. Verification Commands

{_list_block(verification_commands, '- true')}

## 8. Failure Handling

- Patch apply failure: stop and report
- Protected file touched: stop immediately
- Verification failure: rollback and report

## 9. Execution Results

```diff
# Add unified diff here.
```

## 10. Final Report

Pending.
"""


def parse_task_file(content: str) -> Dict[str, object]:
    lines = content.splitlines()

    task_id = "000"
    title = "Unknown"
    if lines:
        task_match = re.search(r"^#\s*Task:\s*(.+?)\s+-\s+(.+)$", lines[0].strip())
        if task_match:
            task_id = task_match.group(1).strip()
            title = task_match.group(2).strip()

    metadata = {
        "status": "PENDING",
        "goal": "",
        "plan": "",
        "assigned_agent": "",
        "owner_lock": "",
        "risk": "LOW",
        "branch": "",
        "touched_files": [],
        "skills": [],
        "transitions": [],
    }

    current_header_list = ""
    for line in lines:
        if line.startswith("## "):
            break
        stripped = line.strip()
        if current_header_list and stripped.startswith("- "):
            value = _clean_list_item(stripped)
            if value:
                metadata[current_header_list].append(value)
            continue
        if stripped:
            current_header_list = ""
        if ":" not in line:
            continue
        key, value = line.split(":", 1)
        normalized = key.strip().lower()
        value = value.strip()
        if normalized == "status":
            metadata["status"] = value
        elif normalized == "goal":
            metadata["goal"] = value
        elif normalized == "plan":
            metadata["plan"] = value
        elif normalized == "assigned agent":
            metadata["assigned_agent"] = value
        elif normalized == "owner lock":
            metadata["owner_lock"] = value
        elif normalized == "risk":
            metadata["risk"] = value
        elif normalized == "branch":
            metadata["branch"] = value
        elif normalized == "touched files":
            current_header_list = "touched_files"
            if value:
                metadata["touched_files"].append(value.strip("`"))
        elif normalized == "skills":
            current_header_list = "skills"
            if value:
                metadata["skills"].append(value.strip("`"))
        elif normalized == "transitions":
            current_header_list = "transitions"
            if value:
                metadata["transitions"].append(value.strip("`"))

    section_pattern = re.compile(r"^##\s*(\d+)\.\s+(.+)$", re.MULTILINE)
    section_matches = list(section_pattern.finditer(content))

    sections: Dict[str, str] = {v: "" for v in SECTION_KEYS.values()}
    for index, match in enumerate(section_matches):
        section_id = match.group(1)
        key = SECTION_KEYS.get(section_id)
        if not key:
            continue
        start = match.end()
        end = section_matches[index + 1].start() if index + 1 < len(section_matches) else len(content)
        sections[key] = content[start:end].strip()

    allowed_files = _parse_list_block(sections["allowed_files"])
    do_not_touch = _parse_list_block(sections["do_not_touch"])
    verification_commands = _parse_list_block(sections["verification_commands"])

    return {
        "task_id": task_id,
        "title": title,
        **metadata,
        "objective": sections["objective"],
        "allowed_files": allowed_files,
        "do_not_touch": do_not_touch,
        "required_context": sections["required_context"],
        "implementation_instructions": sections["implementation_instructions"],
        "patch_protocol": sections["patch_protocol"],
        "verification_commands": verification_commands,
        "failure_handling": sections["failure_handling"],
        "execution_results": sections["execution_results"],
        "final_report": sections["final_report"],
        # skills is already in metadata; surface it at the top level for convenience
        "skills": metadata.get("skills", []),
    }


def extract_unified_diff(content: str) -> str:
    # Normalise CRLF to LF before matching so Windows-edited files work
    normalised = content.replace("\r\n", "\n")
    # Allow optional trailing whitespace on the opening ```diff fence line
    diff_match = re.search(r"```diff[ \t]*\n(.*?)```", normalised, re.DOTALL)
    if not diff_match:
        return ""
    return diff_match.group(1).rstrip() + "\n"


def read_task_markdown(task_file: str) -> str:
    if not os.path.exists(task_file):
        raise FileNotFoundError(f"task file does not exist: {task_file}")
    with open(task_file, "r", encoding="utf-8") as handle:
        return handle.read()


def write_task_markdown(task_file: str, content: str) -> None:
    with open(task_file, "w", encoding="utf-8") as handle:
        handle.write(content)


def default_task_branch(task: Dict[str, object], agent: str) -> str:
    task_id = str(task.get("task_id", "000"))
    owner = agent.strip().replace(" ", "-")
    return f"devflow/task-{task_id}-{owner}"


def claim_task_file(
    task_file: str,
    agent: str,
    owner_lock: str,
    touched_files: List[str] | None = None,
    branch: str | None = None,
    force: bool = False,
) -> tuple[bool, str, str]:
    content = read_task_markdown(task_file)
    task = parse_task_file(content)
    status = str(task.get("status", "PENDING"))
    task_id = str(task.get("task_id", "unknown"))
    if status in {"CLAIMED", "RUNNING"} and not force:
        return False, task_id, status

    branch_name = branch or default_task_branch(task, agent)
    updated = replace_status(content, "CLAIMED")
    updated = upsert_header(updated, "Assigned Agent", agent)
    updated = upsert_header(updated, "Owner Lock", owner_lock)
    updated = upsert_header(updated, "Branch", branch_name)
    if touched_files is not None:
        updated = upsert_header_list(updated, "Touched Files", touched_files)
    write_task_markdown(task_file, updated)
    return True, task_id, branch_name


def release_task_file(task_file: str) -> tuple[str, str]:
    content = read_task_markdown(task_file)
    task = parse_task_file(content)
    current_status = str(task.get("status", "PENDING"))
    next_status = "BLOCKED" if current_status == "BLOCKED" else "PENDING"

    updated = replace_status(content, next_status)
    updated = upsert_header(updated, "Assigned Agent", "")
    updated = upsert_header(updated, "Owner Lock", "")
    updated = upsert_header(updated, "Branch", "")
    write_task_markdown(task_file, updated)
    return str(task.get("task_id", "unknown")), next_status


def transition_task_file(task_file: str, to_state: str, reason: str = "", artifact_id: str = "") -> tuple[str, str, str]:
    content = read_task_markdown(task_file)
    task = parse_task_file(content)
    current_status = str(task.get("status", "PENDING")).upper()
    target_status = to_state.upper()

    from devflow.states import validate_transition

    if not validate_transition(current_status, target_status):
        raise ValueError(f"Transition from '{current_status}' to '{target_status}' is invalid.")

    timestamp = datetime.datetime.now().replace(microsecond=0).isoformat()
    if reason and artifact_id:
        transition_line = f"{current_status} -> {target_status}: {reason} (artifact: {artifact_id}) at {timestamp}"
    elif reason:
        transition_line = f"{current_status} -> {target_status}: {reason} at {timestamp}"
    elif artifact_id:
        transition_line = f"{current_status} -> {target_status}: (artifact: {artifact_id}) at {timestamp}"
    else:
        transition_line = f"{current_status} -> {target_status} at {timestamp}"

    transitions = list(task.get("transitions", []))
    transitions.append(transition_line)

    updated = replace_status(content, target_status)
    updated = upsert_header_list(updated, "Transitions", transitions)
    write_task_markdown(task_file, updated)
    return str(task.get("task_id", "unknown")), current_status, target_status


def resolve_plan_path(plan_ref: object) -> str:
    if not isinstance(plan_ref, str) or not plan_ref.strip():
        return ""
    plan_ref = plan_ref.strip()
    if os.path.exists(plan_ref):
        return plan_ref
    return os.path.join(".devflow", "plans", plan_ref)


def mirror_plan_status(task: Dict[str, object], new_status: str) -> str:
    plan_path = resolve_plan_path(task.get("plan"))
    if not plan_path or not os.path.exists(plan_path):
        return ""

    try:
        with open(plan_path, "r", encoding="utf-8") as handle:
            plan = json.load(handle)
        tasks = plan.get("tasks", [])
        if not isinstance(tasks, list):
            return f"Plan status mirror skipped: {plan_path} has no tasks list."

        task_id = str(task.get("task_id", ""))
        for item in tasks:
            if isinstance(item, dict) and str(item.get("id", "")) == task_id:
                item["status"] = new_status
                with open(plan_path, "w", encoding="utf-8") as handle:
                    json.dump(plan, handle, indent=2)
                    handle.write("\n")
                return ""
        return f"Plan status mirror skipped: task {task_id} not found in {plan_path}."
    except Exception as exc:
        return f"Plan status mirror failed: {exc}"


def write_task_status(task_file: str, new_status: str, task: Dict[str, object], report_payload: Dict[str, object]) -> None:
    latest_task = read_task_markdown(task_file)
    previous_status = report_payload.get("_current_status") or parse_task_file(latest_task).get("status", "")
    write_task_markdown(task_file, replace_status(latest_task, new_status))

    if previous_status and previous_status != new_status:
        transitions = report_payload.setdefault("status_transitions", [])
        if isinstance(transitions, list):
            transitions.append(f"{previous_status} -> {new_status}")
    report_payload["_current_status"] = new_status

    warning = mirror_plan_status(task, new_status)
    if warning:
        warnings = report_payload.setdefault("warnings", [])
        if isinstance(warnings, list):
            warnings.append(warning)


def plan_status_for_task(task: Dict[str, object]) -> str:
    plan_path = resolve_plan_path(task.get("plan"))
    if not plan_path or not os.path.exists(plan_path):
        return ""

    try:
        with open(plan_path, "r", encoding="utf-8") as handle:
            plan = json.load(handle)
    except Exception:
        return ""

    task_id = str(task.get("task_id", ""))
    for item in plan.get("tasks", []):
        if isinstance(item, dict) and str(item.get("id", "")) == task_id:
            return str(item.get("status", ""))
    return ""


def load_all_plan_tasks(root_dir: str = ".") -> List[Dict[str, object]]:
    plans_dir = os.path.join(root_dir, ".devflow", "plans")
    if not os.path.isdir(plans_dir):
        return []

    all_tasks: List[Dict[str, object]] = []
    for filename in os.listdir(plans_dir):
        if not filename.endswith(".plan.json"):
            continue

        path = os.path.join(plans_dir, filename)
        try:
            with open(path, "r", encoding="utf-8") as handle:
                plan_data = json.load(handle)
            tasks = plan_data.get("tasks", [])
            for item in tasks:
                if isinstance(item, dict) and "id" in item:
                    all_tasks.append(item)
        except Exception:
            pass
    return all_tasks


def latest_report_for_task(task: Dict[str, object], root_dir: str = ".") -> str:
    if root_dir in ("", "."):
        report_path = os.path.join(".devflow", "reports", f"{task.get('task_id', 'unknown')}.report.md")
    else:
        report_path = os.path.join(root_dir, ".devflow", "reports", f"{task.get('task_id', 'unknown')}.report.md")
    return report_path if os.path.exists(report_path) else ""


def verification_results_from_report(report_path: str) -> List[str]:
    if not report_path or not os.path.exists(report_path):
        return []

    try:
        with open(report_path, "r", encoding="utf-8") as handle:
            report_content = handle.read()
    except Exception:
        return []

    lines = report_content.splitlines()
    in_verification = False
    verification_lines: List[str] = []
    for line in lines:
        if line.startswith("## Verification Commands"):
            in_verification = True
            continue
        if in_verification:
            if line.startswith("## "):
                break
            if line.strip():
                verification_lines.append(line.strip())
    return verification_lines
