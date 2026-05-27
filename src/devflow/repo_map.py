from __future__ import annotations

import ast
import hashlib
import json
import os
import subprocess
from typing import Any


EXCLUDED_DIRS = {".git", ".devflow", ".venv", "venv", "__pycache__", ".pytest_cache", ".mypy_cache"}
MAX_FILE_BYTES = 1_000_000
CONTEXT_DIR = os.path.join(".devflow", "context")


def _repo_head(cwd: str) -> str:
    try:
        proc = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=cwd,
            text=True,
            capture_output=True,
            check=False,
        )
    except OSError:
        return "dev"
    if proc.returncode != 0:
        return "dev"
    return proc.stdout.strip() or "dev"


def _relpath(path: str, cwd: str) -> str:
    return os.path.relpath(path, cwd).replace(os.sep, "/")


def _language_for(path: str) -> str:
    if path.endswith(".py"):
        return "python"
    if path.endswith(".md"):
        return "markdown"
    if path.endswith(".json"):
        return "json"
    if path.endswith(".toml"):
        return "toml"
    if path.endswith((".html", ".css", ".js")):
        return path.rsplit(".", 1)[-1]
    return "text"


def collect_repo_files(cwd: str = ".") -> list[dict[str, Any]]:
    """Collect deterministic metadata for non-ignored repository files."""
    cwd = os.path.abspath(cwd)
    files: list[dict[str, Any]] = []
    for root, dirs, names in os.walk(cwd):
        dirs[:] = sorted(name for name in dirs if name not in EXCLUDED_DIRS)
        for name in sorted(names):
            full_path = os.path.join(root, name)
            rel_path = _relpath(full_path, cwd)
            try:
                size = os.path.getsize(full_path)
            except OSError:
                continue
            if size > MAX_FILE_BYTES:
                continue
            files.append({"path": rel_path, "size": size, "language": _language_for(rel_path)})
    return files


def _first_docstring(node: ast.AST) -> str:
    value = ast.get_docstring(node) or ""
    return value.strip().splitlines()[0] if value.strip() else ""


def _extract_imports(tree: ast.AST) -> list[str]:
    imports: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                imports.add(alias.name.split(".", 1)[0])
        elif isinstance(node, ast.ImportFrom) and node.module:
            imports.add(node.module.split(".", 1)[0])
    return sorted(imports)


def _extract_python_symbols(path: str, cwd: str = ".") -> tuple[list[dict[str, Any]], list[str]]:
    full_path = os.path.join(cwd, path)
    try:
        with open(full_path, "r", encoding="utf-8") as handle:
            source = handle.read()
        tree = ast.parse(source, filename=path)
    except (OSError, SyntaxError, UnicodeDecodeError):
        return [], []

    symbols: list[dict[str, Any]] = []
    imports = _extract_imports(tree)
    for node in tree.body:
        if isinstance(node, ast.ClassDef):
            symbols.append(
                {
                    "name": node.name,
                    "type": "class",
                    "file": path,
                    "line": node.lineno,
                    "docstring": _first_docstring(node),
                }
            )
            for child in node.body:
                if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    symbols.append(
                        {
                            "name": f"{node.name}.{child.name}",
                            "type": "method",
                            "file": path,
                            "line": child.lineno,
                            "docstring": _first_docstring(child),
                        }
                    )
        elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            symbols.append(
                {
                    "name": node.name,
                    "type": "function",
                    "file": path,
                    "line": node.lineno,
                    "docstring": _first_docstring(node),
                }
            )
        elif isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name) and target.id.isupper():
                    symbols.append(
                        {
                            "name": target.id,
                            "type": "constant",
                            "file": path,
                            "line": node.lineno,
                            "docstring": "",
                        }
                    )
    return sorted(symbols, key=lambda item: (item["file"], item["line"], item["name"])), imports


def _tested_by_for(path: str, all_paths: set[str]) -> list[str]:
    if not path.startswith("src/") or not path.endswith(".py"):
        return []
    stem = os.path.splitext(os.path.basename(path))[0]
    candidates = [
        f"tests/test_{stem}.py",
        f"tests/{stem}_test.py",
    ]
    return sorted(candidate for candidate in candidates if candidate in all_paths)


def _stable_hash(value: Any) -> str:
    payload = json.dumps(value, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def build_repo_map_symbols(cwd: str = ".") -> dict[str, Any]:
    """Build a deterministic Python symbol map."""
    files = collect_repo_files(cwd)
    symbols: list[dict[str, Any]] = []
    for item in files:
        if item["path"].endswith(".py"):
            file_symbols, _ = _extract_python_symbols(item["path"], cwd=cwd)
            symbols.extend(file_symbols)
    symbols = sorted(symbols, key=lambda item: (item["file"], item["line"], item["name"]))
    result = {"repo_head": _repo_head(os.path.abspath(cwd)), "symbols": symbols}
    result["map_hash"] = _stable_hash(result)
    return result


def build_repo_map_deps(cwd: str = ".") -> dict[str, Any]:
    """Build a deterministic import and test mapping for repository files."""
    files = collect_repo_files(cwd)
    all_paths = {item["path"] for item in files}
    mapped: dict[str, Any] = {}
    for item in files:
        imports: list[str] = []
        if item["path"].endswith(".py"):
            _, imports = _extract_python_symbols(item["path"], cwd=cwd)
        mapped[item["path"]] = {
            "imports": imports,
            "tested_by": _tested_by_for(item["path"], all_paths),
        }
    result = {"repo_head": _repo_head(os.path.abspath(cwd)), "files": dict(sorted(mapped.items()))}
    result["map_hash"] = _stable_hash(result)
    return result


def build_repo_map_short(cwd: str = ".") -> str:
    """Build a human-readable repository map."""
    files = collect_repo_files(cwd)
    deps = build_repo_map_deps(cwd)
    lines = ["# Repository Map", "", f"Repo Head: {deps['repo_head']}", "", "## Files"]
    for item in files:
        tested_by = deps["files"].get(item["path"], {}).get("tested_by", [])
        suffix = f" (tested by {', '.join(tested_by)})" if tested_by else ""
        lines.append(f"- {item['path']} [{item['language']}, {item['size']} bytes]{suffix}")
    lines.extend(["", "## Python Imports"])
    for path, data in deps["files"].items():
        imports = data.get("imports", [])
        if imports:
            lines.append(f"- {path}: {', '.join(imports)}")
    return "\n".join(lines).rstrip() + "\n"


def refresh_repo_maps(cwd: str = ".") -> dict[str, str]:
    """Regenerate short, symbol, and dependency repo maps under `.devflow/context`."""
    context_dir = os.path.join(cwd, CONTEXT_DIR)
    os.makedirs(context_dir, exist_ok=True)

    short_path = os.path.join(context_dir, "repo-map.short.md")
    symbols_path = os.path.join(context_dir, "repo-map.symbols.json")
    deps_path = os.path.join(context_dir, "repo-map.deps.json")

    with open(short_path, "w", encoding="utf-8") as handle:
        handle.write(build_repo_map_short(cwd))
    with open(symbols_path, "w", encoding="utf-8") as handle:
        json.dump(build_repo_map_symbols(cwd), handle, indent=2, sort_keys=True)
        handle.write("\n")
    with open(deps_path, "w", encoding="utf-8") as handle:
        json.dump(build_repo_map_deps(cwd), handle, indent=2, sort_keys=True)
        handle.write("\n")

    return {"short": short_path, "symbols": symbols_path, "deps": deps_path}
