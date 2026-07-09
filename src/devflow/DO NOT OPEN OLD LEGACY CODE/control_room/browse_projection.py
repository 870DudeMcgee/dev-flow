from __future__ import annotations

from pathlib import Path


class BrowsePathError(ValueError):
    pass


def build_browse_payload(
    raw_path: str | None,
    *,
    max_file_bytes: int,
    max_directory_entries: int,
) -> dict[str, object]:
    browse_path = _resolve_browse_path(raw_path)
    if browse_path.is_file():
        return _build_file_payload(browse_path, max_file_bytes=max_file_bytes)
    if not browse_path.is_dir():
        raise BrowsePathError(f"Not a directory: {browse_path}")
    return _build_directory_payload(browse_path, max_directory_entries=max_directory_entries)


def _resolve_browse_path(raw_path: str | None) -> Path:
    if raw_path is None or raw_path == "~":
        return Path.home()
    return Path(raw_path).expanduser().resolve()


def _build_file_payload(path: Path, *, max_file_bytes: int) -> dict[str, object]:
    file_size = path.stat().st_size
    file_bytes, truncated = _read_file_bytes_with_limit(path, max_file_bytes)
    try:
        content = _decode_browse_file_content(file_bytes, truncated=truncated)
    except UnicodeDecodeError:
        content = "(binary file)"
    return {
        "path": str(path),
        "content": content,
        "is_file": True,
        "content_truncated": truncated,
        "content_limit": max_file_bytes,
        "content_size": file_size,
        "returned_bytes": len(file_bytes),
    }


def _build_directory_payload(path: Path, *, max_directory_entries: int) -> dict[str, object]:
    visible_entries: list[Path] = []
    entries_truncated = False
    for entry in path.iterdir():
        if entry.name.startswith("."):
            continue
        visible_entries.append(entry)
        if len(visible_entries) > max_directory_entries:
            entries_truncated = True
            break

    sorted_entries = sorted(
        visible_entries[:max_directory_entries],
        key=lambda entry: (not entry.is_dir(), entry.name.lower()),
    )
    entries = []
    for entry in sorted_entries:
        is_dir = entry.is_dir()
        entries.append({
            "name": entry.name,
            "path": str(entry),
            "is_dir": is_dir,
            "has_devflow": is_dir and (entry / ".devflow").is_dir(),
        })

    return {
        "current_path": str(path),
        "parent_path": str(path.parent) if path != path.parent else None,
        "entries": entries,
        "entries_truncated": entries_truncated,
        "entry_limit": max_directory_entries,
    }


def _read_file_bytes_with_limit(path: Path, max_bytes: int) -> tuple[bytes, bool]:
    with path.open("rb") as handle:
        data = handle.read(max_bytes + 1)
    return data[:max_bytes], len(data) > max_bytes


def _decode_browse_file_content(data: bytes, *, truncated: bool) -> str:
    try:
        return data.decode("utf-8")
    except UnicodeDecodeError:
        if not truncated:
            raise
    for trim_count in range(1, min(4, len(data) + 1)):
        try:
            return data[:-trim_count].decode("utf-8")
        except UnicodeDecodeError:
            continue
    raise UnicodeDecodeError("utf-8", data, 0, 1, "invalid truncated utf-8")
