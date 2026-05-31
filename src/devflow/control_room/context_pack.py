from __future__ import annotations

import re
import subprocess
from pathlib import Path
from typing import Any

from devflow.control_room.persistence import get_task
from devflow.control_room.paths import task_dir
from devflow.control_room.estimator import estimate_task_fit, save_task_fit


def build_context_pack(root: Path, task_id: str, role: str) -> dict[str, Any]:
    """Deterministic role-based context pack builder manifest generator."""
    allowed_roles = ("planner", "worker", "reviewer")
    if role not in allowed_roles:
        raise ValueError(f"Invalid role: '{role}'. Must be one of: {', '.join(allowed_roles)}")

    # Ensure task-fit exists or compute it
    task_fit_file = task_dir(root, task_id) / "task-fit.yaml"
    if not task_fit_file.exists():
        fit_data = estimate_task_fit(root, task_id)
        save_task_fit(root, task_id, fit_data)
    else:
        # Re-compute to ensure we have the latest repository and workspace state
        fit_data = estimate_task_fit(root, task_id)

    task = get_task(root, task_id)
    tf = fit_data.get("task_fit", {})
    rs = fit_data.get("repo_scan", {})
    context_layer = tf.get("context_layer", "L1")

    # Find files in repo to build packs
    title = task.title
    description = ""
    task_yaml_path = task_dir(root, task_id) / "task.yaml"
    if task_yaml_path.exists():
        try:
            content = task_yaml_path.read_text(encoding="utf-8")
            desc_match = re.search(r"^description:\s*(.+)$", content, re.MULTILINE)
            if desc_match:
                description = desc_match.group(1).strip().strip('"\'')
        except Exception:
            pass

    combined_text = f"{title}\n{description}".lower()

    # Find changed files via git
    changed_files: list[Path] = []
    try:
        status_proc = subprocess.run(
            ["git", "status", "--porcelain"],
            cwd=root,
            capture_output=True,
            text=True,
            timeout=5,
        )
        if status_proc.returncode == 0:
            for line in status_proc.stdout.splitlines():
                stripped = line.strip()
                if not stripped:
                    continue
                path_part = stripped[3:].strip() if len(stripped) > 3 else stripped
                if path_part.startswith(".devflow") or path_part.startswith('".devflow'):
                    continue
                file_path = root / path_part
                if file_path.exists() and file_path.is_file():
                    changed_files.append(file_path)
    except Exception:
        pass

    # Extract referenced files
    file_pattern = re.compile(r"\b[a-zA-Z0-9_\-./]+\.[a-zA-Z0-9]+\b")
    referenced_matches = file_pattern.findall(title + " " + description)
    referenced_files: list[Path] = []
    for match in referenced_matches:
        if match.startswith(".devflow"):
            continue
        candidate = root / match
        if candidate.exists() and candidate.is_file():
            if candidate not in referenced_files:
                referenced_files.append(candidate)
        else:
            try:
                for p in root.glob(f"**/{match}"):
                    if p.is_file() and not any(part.startswith('.') for part in p.relative_to(root).parts):
                        if p not in referenced_files:
                            referenced_files.append(p)
                            break
            except Exception:
                pass

    relevant_files = list(set(changed_files + referenced_files))

    # Test files
    test_files: list[Path] = []
    for f in relevant_files:
        if "test" in f.name.lower() or f.parent.name == "tests":
            if f not in test_files:
                test_files.append(f)
            continue
        if f.suffix == ".py":
            t1 = root / "tests" / f"test_{f.name}"
            t2 = f.parent / f"test_{f.name}"
            if t1.exists() and t1.is_file() and t1 not in test_files:
                test_files.append(t1)
            if t2.exists() and t2.is_file() and t2 not in test_files:
                test_files.append(t2)

    # Strategy/Vision files
    strategic_files: list[Path] = []
    for doc_name in ["PRODUCT_NORTH_STAR.md", "docs/control-room-mvp.md", "docs/architecture/agent-registry-and-adapter-runtime.md"]:
        p = root / doc_name
        if p.exists() and p.is_file():
            strategic_files.append(p)

    # Project directories/plans
    project_docs: list[Path] = []
    try:
        project_dir = root / ".devflow" / "project"
        if project_dir.exists() and project_dir.is_dir():
            for p in project_dir.glob("*.md"):
                if p.is_file():
                    project_docs.append(p)
        layers_dir = root / ".devflow" / "layers"
        if layers_dir.exists() and layers_dir.is_dir():
            for p in layers_dir.glob("**/*.md"):
                if p.is_file():
                    project_docs.append(p)
    except Exception:
        pass

    includes: list[str] = []
    excludes: list[str] = []
    total_tokens = 4000  # Default overhead

    def _rel(path: Path) -> str:
        try:
            return str(path.resolve().relative_to(root.resolve()))
        except ValueError:
            return str(path)

    def _estimate_tokens(path: Path) -> int:
        try:
            return path.stat().st_size // 4
        except Exception:
            return 0

    if role == "planner":
        # 1. Planner includes high-level specs, repo maps, task history, but EXCLUDES full source code
        # Include task definition
        task_yaml = task_yaml_path
        if task_yaml.exists():
            t_yaml_tokens = _estimate_tokens(task_yaml)
            includes.append(f"{_rel(task_yaml)} ({t_yaml_tokens} tokens)")
            total_tokens += t_yaml_tokens

        # Include strategic vision docs
        for sf in strategic_files:
            sf_tokens = _estimate_tokens(sf)
            includes.append(f"{_rel(sf)} ({sf_tokens} tokens)")
            total_tokens += sf_tokens

        # Include project specific docs (.devflow/project/ etc.)
        for pd in project_docs:
            pd_tokens = _estimate_tokens(pd)
            includes.append(f"{_rel(pd)} ({pd_tokens} tokens)")
            total_tokens += pd_tokens

        # Include events.jsonl
        events_file = task_dir(root, task_id) / "events.jsonl"
        if events_file.exists():
            ev_tokens = _estimate_tokens(events_file)
            includes.append(f"{_rel(events_file)} ({ev_tokens} tokens)")
            total_tokens += ev_tokens

        # Include repo-map index description (mock mapping of filenames, very small token footprint)
        all_src_files = []
        try:
            src_dir = root / "src"
            if src_dir.exists() and src_dir.is_dir():
                for f in src_dir.glob("**/*.py"):
                    if f.is_file():
                        all_src_files.append(_rel(f))
        except Exception:
            pass
        repo_map_tokens = len(all_src_files) * 5
        includes.append(f"repo-map.md (estimated file structure index - {repo_map_tokens} tokens)")
        total_tokens += repo_map_tokens

        # Exclude raw source files/tests from the planner
        for src_file in all_src_files:
            excludes.append(f"{src_file} (raw python implementation)")
        for rf in relevant_files:
            rf_rel = _rel(rf)
            if rf.suffix == ".py" and not any(rf_rel in exc for exc in excludes):
                excludes.append(f"{rf_rel} (raw python implementation)")
        for tf_path in test_files:
            tf_rel = _rel(tf_path)
            if not any(tf_rel in exc for exc in excludes):
                excludes.append(f"{tf_rel} (raw test file content)")

    elif role == "worker":
        # 2. Worker includes full contents of relevant source files, related tests, task definition
        task_yaml = task_yaml_path
        if task_yaml.exists():
            t_yaml_tokens = _estimate_tokens(task_yaml)
            includes.append(f"{_rel(task_yaml)} ({t_yaml_tokens} tokens)")
            total_tokens += t_yaml_tokens

        # Include full relevant source files
        for rf in relevant_files:
            if rf.is_file() and rf.suffix == ".py":
                rf_tokens = _estimate_tokens(rf)
                includes.append(f"{_rel(rf)} ({rf_tokens} tokens)")
                total_tokens += rf_tokens

        # Include test files
        for tf_path in test_files:
            if tf_path.is_file():
                tf_tokens = _estimate_tokens(tf_path)
                includes.append(f"{_rel(tf_path)} ({tf_tokens} tokens)")
                total_tokens += tf_tokens

        # Exclude high-level strategy and vision docs
        for sf in strategic_files:
            excludes.append(f"{_rel(sf)} (strategic project spec)")
        for pd in project_docs:
            excludes.append(f"{_rel(pd)} (strategic layered design)")

    elif role == "reviewer":
        # 3. Reviewer includes task definition, git diff, result logs
        task_yaml = task_yaml_path
        if task_yaml.exists():
            t_yaml_tokens = _estimate_tokens(task_yaml)
            includes.append(f"{_rel(task_yaml)} ({t_yaml_tokens} tokens)")
            total_tokens += t_yaml_tokens

        # Include git diff
        diff_tokens = 0
        try:
            diff_proc = subprocess.run(
                ["git", "diff"],
                cwd=root,
                capture_output=True,
                text=True,
                timeout=5,
            )
            if diff_proc.returncode == 0 and diff_proc.stdout.strip():
                diff_tokens = len(diff_proc.stdout) // 4
                includes.append(f"git-diff.patch (active worktree modifications - {diff_tokens} tokens)")
                total_tokens += diff_tokens
        except Exception:
            pass

        # Include worker logs
        worker_log = task_dir(root, task_id) / "logs" / "worker.log"
        if worker_log.exists():
            wl_tokens = _estimate_tokens(worker_log)
            includes.append(f"{_rel(worker_log)} ({wl_tokens} tokens)")
            total_tokens += wl_tokens

        # Include result.md summary
        result_md = task_dir(root, task_id) / "result.md"
        if result_md.exists():
            rm_tokens = _estimate_tokens(result_md)
            includes.append(f"{_rel(result_md)} ({rm_tokens} tokens)")
            total_tokens += rm_tokens

        # Exclude high-level strategy
        for sf in strategic_files:
            excludes.append(f"{_rel(sf)} (strategic project spec)")

    # Return structured context pack details
    return {
        "context_pack": {
            "role": role,
            "context_layer": context_layer,
            "includes": includes,
            "excludes": excludes,
            "estimated_tokens": total_tokens,
        }
    }


def save_context_pack(root: Path, task_id: str, role: str, pack_data: dict[str, Any]) -> None:
    """Save the context pack data into context-pack-<role>.yaml inside the task directory."""
    task_directory = task_dir(root, task_id)
    task_directory.mkdir(parents=True, exist_ok=True)
    yaml_file = task_directory / f"context-pack-{role}.yaml"

    lines = []
    lines.append("context_pack:")
    
    cp = pack_data.get("context_pack", {})
    lines.append(f"  role: {cp.get('role', '')}")
    lines.append(f"  context_layer: {cp.get('context_layer', '')}")
    lines.append(f"  estimated_tokens: {cp.get('estimated_tokens', 0)}")

    lines.append("  includes:")
    for inc in cp.get("includes", []):
        lines.append(f"    - {inc}")

    lines.append("  excludes:")
    for exc in cp.get("excludes", []):
        lines.append(f"    - {exc}")

    yaml_file.write_text("\n".join(lines) + "\n", encoding="utf-8")
