import os
import re
import subprocess
from typing import Dict, List, Set, Tuple, Any
from devflow.manager import parse_task_file

def _get_module_name(filepath: str) -> str:
    """Helper to convert a file path like src/devflow/states.py to devflow.states module name."""
    parts = filepath.replace("\\", "/").split("/")
    if parts and parts[0] == "src":
        parts = parts[1:]
    if parts and parts[-1].endswith(".py"):
        parts[-1] = parts[-1][:-3]
    return ".".join(parts)

def get_imports_for_file(target_file: str, src_dir: str) -> List[str]:
    """Finds all python files under src_dir that import the target_file."""
    target_module = _get_module_name(target_file)
    if not target_module:
        return []

    imported_by = []
    # Build regexes to detect different import styles
    # Style 1: import devflow.states
    # Style 2: from devflow.states import ...
    # Style 3: from devflow import states
    import_pattern = re.compile(rf"\bimport\s+({re.escape(target_module)})\b")
    from_pattern = re.compile(rf"\bfrom\s+({re.escape(target_module)})\s+import\b")
    
    # Also support nested from imports: e.g. from devflow import states
    parent_module = ".".join(target_module.split(".")[:-1])
    sub_module = target_module.split(".")[-1]
    nested_pattern = re.compile(rf"\bfrom\s+({re.escape(parent_module)})\s+import\s+.*\b({re.escape(sub_module)})\b")

    for root, _, files in os.walk(src_dir):
        for filename in files:
            if not filename.endswith(".py"):
                continue
            filepath = os.path.join(root, filename)
            # Avoid self-import checks
            if os.path.abspath(filepath) == os.path.abspath(target_file):
                continue
            try:
                with open(filepath, "r", encoding="utf-8") as handle:
                    content = handle.read()
                if (import_pattern.search(content) or 
                    from_pattern.search(content) or 
                    (parent_module and nested_pattern.search(content))):
                    imported_by.append(filepath)
            except Exception:
                pass
    return sorted(list(set(imported_by)))

def get_co_mutations(target_file: str, cwd: str) -> List[str]:
    """Scans git history (last 50 commits) to find files frequently committed together with target_file."""
    try:
        proc = subprocess.run(
            ["git", "log", "--pretty=format:", "--name-only", "-n", "50"],
            cwd=cwd,
            text=True,
            capture_output=True,
            check=True
        )
        stdout = proc.stdout
    except Exception:
        return []

    # Parse output into commit blocks
    # Git log outputs a list of files per commit separated by blank lines
    blocks = stdout.strip().split("\n\n")
    co_occurrences: Dict[str, int] = {}
    normalized_target = target_file.replace("\\", "/")

    for block in blocks:
        files = [f.strip().replace("\\", "/") for f in block.splitlines() if f.strip()]
        if normalized_target in files:
            for f in files:
                if f != normalized_target:
                    co_occurrences[f] = co_occurrences.get(f, 0) + 1

    # Sort by frequency of occurrence descending
    sorted_co = sorted(co_occurrences.items(), key=lambda item: item[1], reverse=True)
    return [item[0] for item in sorted_co[:5]]

def calculate_risk(allowed_files: List[str], import_count: int, protected_paths: List[str]) -> Tuple[str, int]:
    """Calculates risk level based on file count, import references, and protected path access."""
    score = 0
    score += len(allowed_files) * 2
    score += import_count * 1

    # Protected paths matching (e.g. config.py, .env, setup files)
    normalized_protected = [p.replace("\\", "/").lower() for p in protected_paths]
    for filepath in allowed_files:
        normalized = filepath.replace("\\", "/").lower()
        if any(p in normalized for p in normalized_protected):
            score += 10

    if score <= 4:
        return "LOW", score
    elif score <= 10:
        return "MEDIUM", score
    else:
        return "HIGH", score

def analyze_impact(task_file: str, cwd: str) -> Dict[str, Any]:
    """Generates a comprehensive impact report for a task file."""
    if not os.path.exists(task_file):
        raise FileNotFoundError(f"Task file not found: {task_file}")

    with open(task_file, "r", encoding="utf-8") as handle:
        content = handle.read()

    task = parse_task_file(content)
    allowed_files = task.get("allowed_files", [])
    touched_files = task.get("touched_files", [])
    
    # Union of allowed and touched
    target_files = sorted(list(set(allowed_files + touched_files)))
    
    # 1. Imports Analysis
    src_dir = os.path.join(cwd, "src")
    public_usages: Set[str] = set()
    if os.path.exists(src_dir):
        for filepath in target_files:
            usages = get_imports_for_file(filepath, src_dir)
            for u in usages:
                public_usages.add(os.path.relpath(u, cwd).replace("\\", "/"))

    # 2. Git Co-mutation Analysis
    co_mutations: Set[str] = set()
    for filepath in target_files:
        co = get_co_mutations(filepath, cwd)
        co_mutations.update(co)

    # 3. Verification Targets
    verif_targets: Set[str] = set()
    # Scan task verification commands for test references
    for cmd in task.get("verification_commands", []):
        matches = re.findall(r"\btests/\S+\.py", cmd)
        verif_targets.update(matches)

    # Also automatically match test_*.py matching allowed file basenames
    tests_dir = os.path.join(cwd, "tests")
    if os.path.exists(tests_dir):
        for filepath in target_files:
            base = os.path.basename(filepath)
            if base.endswith(".py"):
                test_name = f"test_{base}"
                potential_test = os.path.join(tests_dir, test_name)
                if os.path.exists(potential_test):
                    verif_targets.add(f"tests/{test_name}")

    # 4. Risk Level Calculation
    config_path = os.path.join(cwd, ".devflow", "config.json")
    protected_paths = ["config", ".env", "security", "constitution.md"]
    if os.path.exists(config_path):
        try:
            import json
            with open(config_path, "r", encoding="utf-8") as f:
                config = json.load(f)
            protected_paths = config.get("risk", {}).get("protected_paths", protected_paths)
        except Exception:
            pass

    risk_level, risk_score = calculate_risk(target_files, len(public_usages), protected_paths)

    # 5. Suggested Splits
    # Suggest splitting if allowed_files > 3 or if they span multiple top-level directories under src/
    suggests_split = False
    split_reason = ""
    if len(allowed_files) > 3:
        suggests_split = True
        split_reason = f"Touches {len(allowed_files)} distinct files. Consider splitting into micro-vertical slices."
    else:
        # Check subdirectories
        subdirs = set()
        for f in allowed_files:
            parts = f.replace("\\", "/").split("/")
            if len(parts) > 2:
                subdirs.add(parts[1])
        if len(subdirs) > 1:
            suggests_split = True
            split_reason = f"Spans multiple distinct module domains: {', '.join(sorted(subdirs))}. Consider splitting task."

    return {
        "task_id": task.get("task_id", "unknown"),
        "title": task.get("title", "Unknown"),
        "risk_level": risk_level,
        "risk_score": risk_score,
        "allowed_files": allowed_files,
        "touched_files": touched_files,
        "public_interface_usages": sorted(list(public_usages)),
        "co_mutations": sorted(list(co_mutations)),
        "verification_targets": sorted(list(verif_targets)),
        "suggests_split": suggests_split,
        "split_reason": split_reason
    }
