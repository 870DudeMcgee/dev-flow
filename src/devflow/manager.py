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


def parse_task_file(content: str) -> Dict[str, object]:
    lines = content.splitlines()

    task_id = "000"
    title = "Unknown"
    if lines:
        task_match = re.search(r"^#\s*Task:\s*([^\s-]+)\s*-\s*(.+)$", lines[0].strip())
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
    }


def extract_unified_diff(content: str) -> str:
    diff_match = re.search(r"```diff\n(.*?)```", content, re.DOTALL)
    if not diff_match:
        return ""
    return diff_match.group(1).rstrip() + "\n"
