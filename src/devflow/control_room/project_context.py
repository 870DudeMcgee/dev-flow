from __future__ import annotations

import subprocess
from datetime import datetime
from pathlib import Path
import yaml

def build_project_context_packet(repo_root: Path, max_chars: int = 50000) -> str:
    """Builds a curated, safe, and compact project context packet."""
    repo_root = repo_root.resolve()

    # 1. Gather git branch and status
    branch = "unknown"
    try:
        res = subprocess.run(
            ["git", "branch", "--show-current"],
            capture_output=True,
            text=True,
            timeout=2,
            cwd=str(repo_root)
        )
        if res.returncode == 0:
            val = res.stdout.strip()
            if val:
                branch = val
    except Exception:
        pass

    git_status = "unavailable"
    try:
        res = subprocess.run(
            ["git", "status", "--short"],
            capture_output=True,
            text=True,
            timeout=2,
            cwd=str(repo_root)
        )
        if res.returncode == 0:
            val = res.stdout.strip()
            git_status = val if val else "clean"
    except Exception:
        pass

    # Build first section: metadata
    metadata_section = (
        "---\n"
        "Project context: DevFlow repository\n"
        "---\n\n"
        f"Repo root: {repo_root}\n"
        f"Branch: {branch}\n"
        "Git status:\n"
        f"{git_status}\n"
    )

    packet = ""
    truncated = False

    def append_with_truncation(current: str, section: str) -> tuple[str, bool]:
        trunc_msg = "\n[Project context truncated]"
        if len(current) >= max_chars:
            return current[:max_chars - len(trunc_msg)] + trunc_msg, True
        
        if len(current) + len(section) > max_chars:
            allowed_len = max_chars - len(current) - len(trunc_msg)
            if allowed_len > 0:
                return current + section[:allowed_len] + trunc_msg, True
            else:
                return current[:max_chars - len(trunc_msg)] + trunc_msg, True
        return current + section, False

    packet, truncated = append_with_truncation(packet, metadata_section)
    if truncated:
        return packet

    # 2. Add canonical files in order
    canonical_files = [
        "README.md",
        "PRODUCT_NORTH_STAR.md",
        "docs/control-room-mvp.md",
        "docs/mvp-contract.md",
        "docs/architecture/agent-registry-and-adapter-runtime.md",
        ".devflow/agents/registry.yaml",
        ".devflow/providers/ollama.yaml",
    ]

    forbidden_parts = {".git", ".venv", ".venv-1", "node_modules", "build", "dist", "workspaces"}

    for rel_path_str in canonical_files:
        try:
            target_path = (repo_root / rel_path_str).resolve()
            # Traversal check:
            if repo_root not in target_path.parents and target_path != repo_root:
                continue
            # Forbidden parts check:
            if any(part in forbidden_parts for part in target_path.parts):
                continue
            if not target_path.exists() or not target_path.is_file():
                continue

            # Read file contents
            try:
                content = target_path.read_text(encoding="utf-8")
            except UnicodeDecodeError:
                content = f"[Skipped unreadable text file: {rel_path_str}]"
            except Exception:
                continue

            file_section = (
                "\n---\n"
                f"File: {rel_path_str}\n"
                "---\n\n"
                f"{content}\n"
            )
            packet, truncated = append_with_truncation(packet, file_section)
            if truncated:
                return packet
        except Exception:
            continue

    # 3. Add tasks section (up to 5 most recently updated tasks)
    tasks_dir = repo_root / ".devflow" / "tasks"
    tasks = []
    if tasks_dir.exists() and tasks_dir.is_dir():
        try:
            for child in tasks_dir.iterdir():
                if child.is_dir():
                    task_yaml_path = child / "task.yaml"
                    try:
                        resolved_task_yaml = task_yaml_path.resolve()
                        # Traversal & safety checks
                        if repo_root not in resolved_task_yaml.parents:
                            continue
                        if any(part in forbidden_parts for part in resolved_task_yaml.parts):
                            continue
                        if resolved_task_yaml.exists() and resolved_task_yaml.is_file():
                            content = resolved_task_yaml.read_text(encoding="utf-8")
                            data = yaml.safe_load(content)
                            if isinstance(data, dict):
                                task_id = data.get("id") or child.name
                                status = data.get("status") or "unknown"
                                title = data.get("title") or ""
                                updated_at_str = data.get("updated_at")

                                updated_at = None
                                if updated_at_str:
                                    try:
                                        updated_at = datetime.fromisoformat(str(updated_at_str))
                                    except Exception:
                                        pass
                                
                                tasks.append({
                                    "id": task_id,
                                    "status": status,
                                    "title": title,
                                    "updated_at": updated_at,
                                })
                    except Exception:
                        pass
        except Exception:
            pass

    if tasks:
        # Sort recently updated first, None values placed last
        tasks.sort(key=lambda t: (t["updated_at"] is not None, t["updated_at"] or datetime.min), reverse=True)
        recent_tasks = tasks[:5]

        tasks_lines = []
        for t in recent_tasks:
            tasks_lines.append(f"- {t['id']} {t['status']}: {t['title']}")

        tasks_section = (
            "\n---\n"
            "Recent Dev-Flow tasks\n"
            "---\n\n"
            + "\n".join(tasks_lines) + "\n"
        )
        packet, truncated = append_with_truncation(packet, tasks_section)

    return packet
