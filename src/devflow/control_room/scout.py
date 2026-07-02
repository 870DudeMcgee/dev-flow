from __future__ import annotations

import re
import subprocess
from pathlib import Path
from typing import Any

from devflow.control_room.persistence import get_task
from devflow.control_room.paths import task_dir
from devflow.control_room.estimator import estimate_task_fit


SCOUT_ROLES = ("repo_scope", "risk", "context", "test", "stale_context")


class RepoScout:
    """Consolidated repository and task workspace scanning engine."""

    def __init__(self, root: Path) -> None:
        self.root = root.resolve()
        self._changed_files: list[str] | None = None
        self._raw_status: list[str] | None = None
        self._relevant_files_cache: dict[tuple[str, str], list[Path]] = {}
        self._test_files_cache: dict[str, list[Path]] = {}

    def get_git_status(self) -> list[str]:
        """Fetch raw git status porcelain lines."""
        if self._raw_status is not None:
            return self._raw_status
        lines = []
        try:
            status_proc = subprocess.run(
                ["git", "status", "--porcelain"],
                cwd=self.root,
                capture_output=True,
                text=True,
                timeout=5,
            )
            if status_proc.returncode == 0:
                lines = [line for line in status_proc.stdout.splitlines() if line.strip()]
        except Exception:
            pass
        self._raw_status = lines
        return lines

    def get_changed_files(self) -> list[str]:
        """Fetch changed files relative to repo root using Git status."""
        if self._changed_files is not None:
            return self._changed_files

        changed = []
        for line in self.get_git_status():
            path_part = line[3:].strip() if len(line) > 3 else line
            if path_part.startswith('"') and path_part.endswith('"'):
                path_part = path_part[1:-1]
            if path_part.startswith(".devflow") or path_part.startswith('".devflow'):
                continue
            changed.append(path_part)

        self._changed_files = changed
        return changed

    def get_referenced_files(self, title: str, description: str) -> list[Path]:
        """Scan title and description to extract referenced codebase file paths."""
        file_pattern = re.compile(r"\b[a-zA-Z0-9_\-./]+\.[a-zA-Z0-9]+\b")
        referenced_matches = file_pattern.findall(f"{title} {description}")
        
        referenced_files = []
        for match in referenced_matches:
            if match.startswith(".devflow"):
                continue
            
            candidate = self.root / match
            if candidate.exists() and candidate.is_file():
                if candidate not in referenced_files:
                    referenced_files.append(candidate)
            else:
                try:
                    for p in self.root.glob(f"**/{match}"):
                        if p.is_file() and not any(part.startswith('.') for part in p.relative_to(self.root).parts):
                            if p not in referenced_files:
                                referenced_files.append(p)
                                break
                except Exception:
                    pass
        return referenced_files

    def get_relevant_files(self, title: str, description: str) -> list[Path]:
        """Resolve a combined deduplicated list of Git-changed and text-referenced files."""
        cache_key = (title, description)
        if cache_key in self._relevant_files_cache:
            return self._relevant_files_cache[cache_key]

        changed_paths = [self.root / f for f in self.get_changed_files()]
        # Filter existing files
        changed_paths = [p for p in changed_paths if p.exists() and p.is_file()]
        
        referenced = self.get_referenced_files(title, description)
        relevant = list(set(changed_paths + referenced))
        
        self._relevant_files_cache[cache_key] = relevant
        return relevant

    def get_test_files(self, relevant_files: list[Path]) -> list[Path]:
        """Find matching test coverage files for a list of relevant files."""
        test_files = []
        for f in relevant_files:
            if "test" in f.name.lower() or f.parent.name == "tests":
                if f not in test_files:
                    test_files.append(f)
                continue
            
            if f.suffix == ".py":
                t1 = self.root / "tests" / f"test_{f.name}"
                t2 = f.parent / f"test_{f.name}"
                if t1.exists() and t1.is_file() and t1 not in test_files:
                    test_files.append(t1)
                if t2.exists() and t2.is_file() and t2 not in test_files:
                    test_files.append(t2)
        return test_files

    def get_strategic_files(self) -> list[Path]:
        """Fetch primary strategic product guidance and architecture maps."""
        docs = []
        for doc_name in ["PRODUCT_NORTH_STAR.md", "docs/control-room-mvp.md", "docs/architecture/agent-registry-and-adapter-runtime.md"]:
            doc_path = self.root / doc_name
            if doc_path.exists() and doc_path.is_file():
                docs.append(doc_path)
        return docs

    def get_project_docs(self) -> list[Path]:
        """Fetch project markdown files under layers and roadmap definitions."""
        project_docs = []
        try:
            project_dir = self.root / ".devflow" / "project"
            if project_dir.exists() and project_dir.is_dir():
                for p in project_dir.glob("*.md"):
                    if p.is_file():
                        project_docs.append(p)
            
            layers_dir = self.root / ".devflow" / "layers"
            if layers_dir.exists() and layers_dir.is_dir():
                for p in layers_dir.glob("**/*.md"):
                    if p.is_file():
                        project_docs.append(p)
        except Exception:
            pass
        return project_docs

    def get_task_description(self, task_id: str) -> str:
        """Extract a task's full description from task.yaml configuration."""
        task_yaml_path = task_dir(self.root, task_id) / "task.yaml"
        if task_yaml_path.exists():
            try:
                content = task_yaml_path.read_text(encoding="utf-8")
                desc_match = re.search(r"^description:\s*(.+)$", content, re.MULTILINE)
                if desc_match:
                    return desc_match.group(1).strip().strip('"\'')
            except Exception:
                pass
        return ""


def run_scout_report(root: Path, task_id: str, role: str) -> dict[str, Any]:
    """Deterministic scout reports generation engine."""
    if role not in SCOUT_ROLES:
        raise ValueError(f"Invalid scout role: '{role}'. Must be one of: {', '.join(SCOUT_ROLES)}")

    scout = RepoScout(root)
    # Load task details and estimate basic heuristics
    task = get_task(root, task_id)
    fit_data = estimate_task_fit(root, task_id)
    tf = fit_data.get("task_fit", {})
    rs = fit_data.get("repo_scan", {})

    title = task.title
    description = scout.get_task_description(task_id)
    combined_text = f"{title}\n{description}".lower()

    changed_files = scout.get_changed_files()

    # Basic setup for reports
    report: dict[str, Any] = {}

    if role == "repo_scope":
        # 1. Repo scope scout details
        subsystem_roots = []
        # Guess subsystem root from changed/relevant files
        for f in changed_files:
            if f.startswith("src/devflow/control_room/"):
                subsystem_roots.append("src/devflow/control_room/")
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
        changed_paths = [scout.root / f for f in changed_files]
        test_paths = scout.get_test_files(changed_paths)
        test_files = [str(Path(t).relative_to(scout.root)) for t in test_paths]

        if not test_files:
            test_files.append("tests/test_estimator.py")

        suggested_verification = task.verification_command
        if not suggested_verification:
            venv_pytest_path = scout.root / ".venv" / "bin" / "pytest"
            suggested_verification = f"PYTHONPATH=. {venv_pytest_path} {test_files[0]}"

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


def run_scout_reports(root: Path, task_id: str, role: str = "all") -> dict[str, dict[str, Any]]:
    """Run one or all deterministic scout roles for a task."""
    if role == "all":
        roles = SCOUT_ROLES
    elif role in SCOUT_ROLES:
        roles = (role,)
    else:
        raise ValueError(f"Invalid scout role: '{role}'. Must be one of: all, {', '.join(SCOUT_ROLES)}")

    return {scout_role: run_scout_report(root, task_id, scout_role) for scout_role in roles}


def save_scout_report(root: Path, task_id: str, role: str, report_data: dict[str, Any]) -> Path:
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
    return yaml_file
