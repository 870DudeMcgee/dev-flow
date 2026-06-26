from __future__ import annotations

import subprocess
import hashlib
import json
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

from devflow.control_room.persistence import atomic_write_text, get_task, utc_now
from devflow.control_room.paths import task_dir
from devflow.control_room.estimator import estimate_task_fit, save_task_fit
from devflow.control_room.agent_registry import load_agent_registry
from devflow.control_room.task_packet import build_agent_packet, render_task_packet_text


@dataclass(frozen=True)
class ContextPack:
    schema_version: int
    task_id: str
    agent_id: str
    role: str
    permission_mode: str
    source_packet_path: str
    included_sources: list[str]
    excluded_sources: list[str]
    estimated_chars: int
    estimated_tokens: int
    truncation_notes: list[str] = field(default_factory=list)
    created_at: str = ""


@dataclass(frozen=True)
class WrittenContextPack:
    pack: ContextPack
    json_path: Path
    markdown_path: Path
    packet_path: Path


def _get_authority(path_rel: str) -> str:
    """Return the authority taxonomy rating of a file path."""
    path_lower = path_rel.lower()
    if "archive" in path_lower or "quarantine" in path_lower or "_legacy" in path_lower:
        return "archive"
    if "rejected" in path_lower:
        return "rejected"
    if path_rel.startswith(".devflow/project/") or path_rel == "PRODUCT_NORTH_STAR.md":
        return "canonical"
    if path_rel.startswith("src/"):
        return "canonical"
    if path_rel.startswith("tests/"):
        return "canonical"
    if path_rel.startswith(".devflow/layers/"):
        return "experimental"
    if path_rel.startswith(".devflow/tasks/") or path_rel.startswith(".devflow/workspaces/"):
        return "derived"
    return "active"


def _get_sha256(path: Path) -> str:
    """Compute truncated SHA256 hash of a file's content."""
    try:
        if not path.exists():
            return "null"
        content = path.read_bytes()
        return hashlib.sha256(content).hexdigest()[:12]
    except Exception:
        return "null"


def build_context_pack(
    root: Path,
    task_id: str,
    role: str | None = None,
    *,
    agent_id: str | None = None,
    persist_task_fit: bool = True,
) -> ContextPack | dict[str, Any]:
    if agent_id is not None:
        if role is None:
            raise ValueError("role is required when building an agent context pack")
        return _build_agent_context_pack(root, task_id, agent_id=agent_id, role=role)
    if role is None:
        raise ValueError("role is required")
    return _build_legacy_context_pack(root, task_id, role, persist_task_fit=persist_task_fit)


def write_context_pack(root: Path, task_id: str, *, agent_id: str, role: str) -> WrittenContextPack:
    pack = _build_agent_context_pack(root, task_id, agent_id=agent_id, role=role)
    agent = load_agent_registry(root).require_agent(agent_id)
    packet = build_agent_packet(task_id, agent, root=root)
    base = root / ".devflow" / "tasks" / task_id / "context-packs"
    json_path = base / f"{role}-{agent_id}.json"
    markdown_path = base / f"{role}-{agent_id}.md"
    packet_path = base / f"{role}-{agent_id}.packet.json"

    atomic_write_text(json_path, json.dumps(asdict(pack), indent=2, sort_keys=True) + "\n")
    atomic_write_text(markdown_path, _render_markdown(pack))
    atomic_write_text(packet_path, json.dumps(packet.model_dump(mode="json"), indent=2, sort_keys=True) + "\n")
    return WrittenContextPack(pack=pack, json_path=json_path, markdown_path=markdown_path, packet_path=packet_path)


def _build_agent_context_pack(root: Path, task_id: str, *, agent_id: str, role: str) -> ContextPack:
    agent = load_agent_registry(root).require_agent(agent_id)
    packet = build_agent_packet(task_id, agent, root=root)
    text = render_task_packet_text(packet)
    source_packet_path = f".devflow/tasks/{task_id}/context-packs/{role}-{agent_id}.packet.json"
    included_sources = sorted(
        {
            *packet.allowed_artifacts,
            packet.logs["worker"].path,
            packet.logs["verify"].path,
            "<task>/task.yaml",
        }
    )
    excluded_sources = sorted(
        {
            *agent.forbidden_writes,
            *agent.cannot_touch,
            ".env",
            ".env*",
            ".git/**",
            "<main_checkout>/**",
        }
    )
    estimated_chars = len(text)
    return ContextPack(
        schema_version=1,
        task_id=task_id,
        agent_id=agent_id,
        role=role,
        permission_mode=agent.default_mode,
        source_packet_path=source_packet_path,
        included_sources=included_sources,
        excluded_sources=excluded_sources,
        estimated_chars=estimated_chars,
        estimated_tokens=max(1, estimated_chars // 4),
        truncation_notes=list(packet.truncation_notes),
        created_at=utc_now().isoformat(),
    )


def _render_markdown(pack: ContextPack) -> str:
    included = "\n".join(f"- {source}" for source in pack.included_sources)
    excluded = "\n".join(f"- {source}" for source in pack.excluded_sources)
    return (
        f"# Context Pack: {pack.task_id} / {pack.agent_id}\n\n"
        f"Role: {pack.role}\n"
        f"Permission mode: {pack.permission_mode}\n"
        f"Source packet: {pack.source_packet_path}\n"
        f"Estimated tokens: {pack.estimated_tokens}\n\n"
        "## Included Sources\n"
        f"{included}\n\n"
        "## Excluded Sources\n"
        f"{excluded}\n"
    )


def _build_legacy_context_pack(root: Path, task_id: str, role: str, *, persist_task_fit: bool = True) -> dict[str, Any]:
    """Deterministic role-based context pack builder and physical packet generator."""
    from devflow.control_room.scout import RepoScout

    allowed_roles = ("planner", "worker", "reviewer")
    if role not in allowed_roles:
        raise ValueError(f"Invalid role: '{role}'. Must be one of: {', '.join(allowed_roles)}")

    # Ensure task-fit exists or compute it
    task_fit_file = task_dir(root, task_id) / "task-fit.yaml"
    if not task_fit_file.exists():
        fit_data = estimate_task_fit(root, task_id)
        if persist_task_fit:
            save_task_fit(root, task_id, fit_data)
    else:
        fit_data = estimate_task_fit(root, task_id)

    task = get_task(root, task_id)
    tf = fit_data.get("task_fit", {})
    context_layer = tf.get("context_layer", "L1")

    scout = RepoScout(root)
    task_yaml_path = task_dir(root, task_id) / "task.yaml"

    # Find files in repo to build packs
    title = task.title
    description = scout.get_task_description(task_id)

    # Find changed files via git
    changed_files = [root / f for f in scout.get_changed_files()]
    changed_files = [p for p in changed_files if p.exists() and p.is_file()]

    # Extract referenced files
    referenced_files = scout.get_referenced_files(title, description)

    relevant_files = list(set(changed_files + referenced_files))

    # Test files
    test_files = scout.get_test_files(relevant_files)

    # Strategy/Vision files
    strategic_files = scout.get_strategic_files()

    # Project directories/plans
    project_docs = scout.get_project_docs()

    includes: list[str] = []
    excludes: list[str] = []
    sources_metadata: list[dict[str, Any]] = []
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

    def _add_include(path: Path, reason: str) -> None:
        path_rel = _rel(path)
        auth = _get_authority(path_rel)
        if auth in ("archive", "rejected"):
            _add_exclude(path, f"excluded due to {auth} authority level")
            return

        # Resolve path inside the task workspace if it exists
        from devflow.control_room.paths import absolute_path
        workspace = absolute_path(root, task.workspace).resolve()
        target_path = path
        if workspace.is_dir() and path_rel:
            ws_path = workspace / path_rel
            if ws_path.is_file():
                target_path = ws_path

        tokens = _estimate_tokens(target_path)
        sha = _get_sha256(target_path)
        content = ""
        try:
            content = target_path.read_text(encoding="utf-8")
        except Exception:
            pass

        includes.append(f"{path_rel} [authority: {auth}] ({tokens} tokens)")
        sources_metadata.append({
            "path": path_rel,
            "authority": auth,
            "mode": "full",
            "token_estimate": tokens,
            "sha_or_mtime": sha,
            "reason_included": reason,
            "reason_excluded": None,
            "content": content
        })
        nonlocal total_tokens
        total_tokens += tokens

    def _add_exclude(path: Path, reason: str) -> None:
        path_rel = _rel(path)
        auth = _get_authority(path_rel)
        tokens = _estimate_tokens(path)
        excludes.append(f"{path_rel} [authority: {auth}] ({reason})")
        sources_metadata.append({
            "path": path_rel,
            "authority": auth,
            "mode": "omitted",
            "token_estimate": tokens,
            "sha_or_mtime": None,
            "reason_included": None,
            "reason_excluded": reason,
            "content": ""
        })

    if role == "planner":
        # 1. Planner includes high-level specs, repo maps, task history, but EXCLUDES full source code
        if task_yaml_path.exists():
            _add_include(task_yaml_path, "canonical task definition")

        for sf in strategic_files:
            _add_include(sf, "strategic vision document")

        for pd in project_docs:
            _add_include(pd, "project roadmap/plan doc")

        events_file = task_dir(root, task_id) / "events.jsonl"
        if events_file.exists():
            _add_include(events_file, "task run events log history")

        # Exclude raw source files/tests from the planner
        all_src_files = []
        try:
            src_dir = root / "src"
            if src_dir.exists() and src_dir.is_dir():
                for f in src_dir.glob("**/*.py"):
                    if f.is_file():
                        all_src_files.append(f)
        except Exception:
            pass

        for sf in all_src_files:
            _add_exclude(sf, "excluded from planner to prevent raw code context leak")
        for rf in relevant_files:
            if rf.suffix == ".py" and rf not in all_src_files:
                _add_exclude(rf, "excluded from planner to prevent raw code context leak")
        for tf_path in test_files:
            _add_exclude(tf_path, "excluded raw test file from planner")

    elif role == "worker":
        # 2. Worker includes full contents of relevant source files, related tests, task definition
        if task_yaml_path.exists():
            _add_include(task_yaml_path, "canonical task definition")

        is_docs_polish = any(
            term in (title + " " + description).lower()
            for term in ["doc", "polish", "readme", "documentation"]
        )

        for rf in relevant_files:
            if rf.is_file():
                if rf.suffix == ".py":
                    _add_include(rf, "active source file to edit")
                elif is_docs_polish and rf.suffix in {".md", ".txt", ".json", ".rst"}:
                    _add_include(rf, "relevant docs/polish file to edit")

        for tf_path in test_files:
            if tf_path.is_file():
                _add_include(tf_path, "related test coverage")

        for sf in strategic_files:
            _add_exclude(sf, "excluded high-level strategy specs from worker")
        for pd in project_docs:
            _add_exclude(pd, "excluded strategic layered design from worker")

    elif role == "reviewer":
        # 3. Reviewer includes task definition, git diff, result logs
        if task_yaml_path.exists():
            _add_include(task_yaml_path, "canonical task definition")

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
                diff_path = task_dir(root, task_id) / "git-diff.patch"
                diff_path.write_text(diff_proc.stdout, encoding="utf-8")
                _add_include(diff_path, "git diff of changes to review")
        except Exception:
            pass

        worker_log = task_dir(root, task_id) / "logs" / "worker.log"
        if worker_log.exists():
            _add_include(worker_log, "worker output log")

        result_md = task_dir(root, task_id) / "result.md"
        if result_md.exists():
            _add_include(result_md, "result summary markdown")

        for sf in strategic_files:
            _add_exclude(sf, "excluded high-level strategy from reviewer")

    return {
        "context_pack": {
            "role": role,
            "context_layer": context_layer,
            "includes": includes,
            "excludes": excludes,
            "estimated_tokens": total_tokens,
            "sources_metadata": sources_metadata,
        }
    }


def save_context_pack(root: Path, task_id: str, role: str, pack_data: dict[str, Any]) -> None:
    """Save context pack details into YAML, human-readable MD, and machine-readable JSON packets."""
    task_directory = task_dir(root, task_id)
    task_directory.mkdir(parents=True, exist_ok=True)
    cp = pack_data.get("context_pack", {})

    # 1. Save .yaml manifest
    yaml_file = task_directory / f"context-pack-{role}.yaml"
    lines = []
    lines.append("context_pack:")
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

    # 2. Save .json complete packet
    json_file = task_directory / f"context-pack-{role}.json"
    json_file.write_text(json.dumps(pack_data, indent=2) + "\n", encoding="utf-8")

    # 3. Save .md physical packet
    md_file = task_directory / f"context-pack-{role}.md"
    md_lines = []
    md_lines.append(f"# Context Pack for Task: {task_id}")
    md_lines.append(f"- **Role**: {cp.get('role', '').upper()}")
    md_lines.append(f"- **Context Layer**: {cp.get('context_layer', 'L1')}")
    md_lines.append(f"- **Estimated Token Size**: {cp.get('estimated_tokens', 0)}")
    md_lines.append("\n---\n")

    md_lines.append("## Included Sources\n")
    metadata = cp.get("sources_metadata", [])
    included_entries = [m for m in metadata if m.get("mode") == "full"]
    if not included_entries:
        md_lines.append("None included.\n")
    else:
        for item in included_entries:
            md_lines.append(f"### File: `{item['path']}`")
            md_lines.append(f"- **Authority Level**: `{item['authority']}`")
            md_lines.append(f"- **Mode**: `{item['mode']}`")
            md_lines.append(f"- **Token Estimate**: {item['token_estimate']}")
            md_lines.append(f"- **SHA256 Hash**: `{item['sha_or_mtime']}`")
            md_lines.append(f"- **Reason Included**: {item['reason_included']}")
            md_lines.append("\n#### Content:\n")
            md_lines.append("```python" if item["path"].endswith(".py") else "```markdown")
            md_lines.append(item["content"])
            md_lines.append("```\n")

    md_lines.append("---\n")
    md_lines.append("## Excluded Sources\n")
    excluded_entries = [m for m in metadata if m.get("mode") == "omitted"]
    if not excluded_entries:
        md_lines.append("None excluded.\n")
    else:
        for item in excluded_entries:
            md_lines.append(f"- **File**: `{item['path']}`")
            md_lines.append(f"  - **Authority Level**: `{item['authority']}`")
            md_lines.append(f"  - **Reason Excluded**: {item['reason_excluded']}")
            md_lines.append(f"  - **Token Estimate**: {item['token_estimate']}\n")

    md_file.write_text("\n".join(md_lines) + "\n", encoding="utf-8")
