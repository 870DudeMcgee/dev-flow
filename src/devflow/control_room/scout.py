from __future__ import annotations

import re
import subprocess
from pathlib import Path
from typing import Any

from devflow.control_room.persistence import get_task
from devflow.control_room.paths import task_dir
from devflow.control_room.estimator import estimate_task_fit


def run_scout_report(root: Path, task_id: str, role: str) -> dict[str, Any]:
    """Deterministic scout reports generation engine."""
    allowed_roles = ("repo_scope", "risk", "context", "test", "stale_context")
    if role not in allowed_roles:
        raise ValueError(f"Invalid scout role: '{role}'. Must be one of: {', '.join(allowed_roles)}")

    # Load task details and estimate basic heuristics
    task = get_task(root, task_id)
    fit_data = estimate_task_fit(root, task_id)
    tf = fit_data.get("task_fit", {})
    rs = fit_data.get("repo_scan", {})

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

    # Find changed files via git status
    changed_files: list[str] = []
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
                if not path_part.startswith(".devflow"):
                    changed_files.append(path_part)
    except Exception:
        pass

    # Basic setup for reports
    report: dict[str, Any] = {}

    if role == "repo_scope":
        # 1. Repo scope scout details
        subsystem_roots = []
        # Guess subsystem root from changed/relevant files
        for f in changed_files:
            if f.startswith("src/devflow/control_room/"):
                subsystem_roots.append("src/devflow/control_room/")
            elif f.startswith("src/devflow/agents/"):
                subsystem_roots.append("src/devflow/agents/")
            elif f.startswith("src/devflow/"):
                subsystem_roots.append("src/devflow/")

        # Deduplicate
        subsystem_roots = list(set(subsystem_roots))
        if not subsystem_roots:
            subsystem_roots.append("src/devflow/")

        likely_risks = []
        if len(changed_files) > 5:
            likely_risks.append("large changes spread across multiple files")
        if "routing" in combined_text or "router" in combined_text:
            likely_risks.append("model profile compatibility")
        if "docs" in combined_text or "readme" in combined_text:
            likely_risks.append("stale docs")

        report = {
            "role": "repo_scope_scout",
            "relevant_files": changed_files if changed_files else ["src/devflow/cli.py"],
            "estimated_scope": tf.get("repo_scope", "medium"),
            "subsystem_roots": subsystem_roots,
            "likely_risks": likely_risks if likely_risks else ["general feature alignment"],
            "suggested_planner": tf.get("recommended_planner_tier", "frontier"),
            "suggested_worker": tf.get("recommended_worker_tier", "strong_local"),
            "confidence": tf.get("confidence", 0.85),
        }

    elif role == "risk":
        # 2. Risk scout details
        code_risk = tf.get("code_edit_risk", "medium")
        arch_risk = tf.get("architectural_risk", "medium")
        
        risks_detected = []
        if "schema" in combined_text or "database" in combined_text:
            risks_detected.append("task schema migration risk")
        if "breaking" in combined_text or "compat" in combined_text or "legacy" in combined_text:
            risks_detected.append("backward compatibility breaks")
        if "routing" in combined_text or "router" in combined_text or "selection" in combined_text:
            risks_detected.append("model routing and tier mapping regression")

        if not risks_detected:
            risks_detected.append("low-impact local modification")

        report = {
            "role": "risk_scout",
            "code_edit_risk": code_risk,
            "architectural_risk": arch_risk,
            "verification_complexity": tf.get("verification_complexity", "medium"),
            "risks_detected": risks_detected,
            "requires_human_gate": "true" if code_risk == "critical" or arch_risk == "critical" else "false",
            "suggested_cap_profiles": ["frontier-architecture-high"] if arch_risk in ("high", "critical") else ["qwen3.6-27b-local", "frontier-low"],
        }

    elif role == "context":
        # 3. Context scout details
        missing_indexes = []
        for index_name in ["project_index.yaml", "subsystem_index.yaml", "architecture_index.yaml"]:
            if not (root / ".devflow" / "memory" / index_name).exists():
                missing_indexes.append(index_name)

        report = {
            "role": "context_scout",
            "estimated_tokens_needed": rs.get("total_context_estimate", 12000),
            "context_layer_required": tf.get("context_layer", "L2"),
            "missing_indexes_detected": missing_indexes if missing_indexes else ["none"],
            "suggested_max_ceiling_tokens": 32000 if rs.get("total_context_estimate", 12000) < 16000 else 64000,
            "index_search_confidence": 0.90 if not missing_indexes else 0.70,
        }

    elif role == "test":
        # 4. Test scout details
        test_files = []
        # Find test files matching the modified source files
        for f in changed_files:
            file_name = Path(f).name
            if file_name.endswith(".py") and not file_name.startswith("test_"):
                test_candidate = Path(f).parent / f"test_{file_name}"
                test_candidate2 = root / "tests" / f"test_{file_name}"
                if test_candidate.exists():
                    test_files.append(str(test_candidate))
                if test_candidate2.exists():
                    test_files.append(str(test_candidate2))

        if not test_files:
            test_files.append("tests/test_estimator.py")

        suggested_verification = task.verification_command
        if not suggested_verification:
            suggested_verification = f"PYTHONPATH=. .venv/bin/pytest {test_files[0]}"

        report = {
            "role": "test_scout",
            "likely_affected_test_files": test_files,
            "suggested_verification_command": suggested_verification,
            "verification_complexity": tf.get("verification_complexity", "medium"),
            "requires_full_suite_run": "true" if len(test_files) > 3 or tf.get("architectural_risk") == "high" else "false",
        }

    elif role == "stale_context":
        # 5. Stale context scout details
        legacy_warnings = []
        # Find if there are files in quarantined legacy directories like _legacy
        for f in changed_files:
            if "_legacy" in f:
                legacy_warnings.append(f"modified quarantined legacy file: {f}")
            if f.startswith("src/devflow/") and "/" not in f[12:]:
                legacy_warnings.append(f"modified file outside src/devflow/control_room boundary: {f}")

        # Search for legacy files inside repository to warn if any are modified
        try:
            legacy_dir = root / "src" / "devflow" / "_legacy"
            if legacy_dir.exists() and legacy_dir.is_dir():
                legacy_warnings.append(f"legacy quarantine folder contains {len(list(legacy_dir.glob('**/*.py')))} files")
        except Exception:
            pass

        report = {
            "role": "stale_context_scout",
            "legacy_files_modified_detected": legacy_warnings if legacy_warnings else ["none"],
            "stale_documents_warnings": ["docs contain legacy workflow commands that should be quarantined"],
            "poison_context_risk": "high" if legacy_warnings else "low",
        }

    return {
        "scout_report": report
    }


def save_scout_report(root: Path, task_id: str, role: str, report_data: dict[str, Any]) -> None:
    """Save the scout report data to scout-<role>.yaml inside the task directory."""
    task_directory = task_dir(root, task_id)
    task_directory.mkdir(parents=True, exist_ok=True)
    yaml_file = task_directory / f"scout-{role}.yaml"

    lines = []
    lines.append("scout_report:")
    
    sr = report_data.get("scout_report", {})
    for key in sorted(sr.keys()):
        if key == "role":
            continue
    lines.append(f"  role: {sr.get('role', '')}")

    for key in sorted(sr.keys()):
        if key == "role":
            continue
        val = sr[key]
        if isinstance(val, list):
            lines.append(f"  {key}:")
            for item in val:
                lines.append(f"    - {item}")
        elif isinstance(val, bool):
            val_str = "true" if val else "false"
            lines.append(f"  {key}: {val_str}")
        elif isinstance(val, (int, float)):
            lines.append(f"  {key}: {val}")
        else:
            lines.append(f"  {key}: {val}")

    yaml_file.write_text("\n".join(lines) + "\n", encoding="utf-8")
