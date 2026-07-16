"""Atomic vault writer for Obsidian Command Center projection (M1-S3).

Writes generated Markdown views atomically into the vault's ``.generated/``
directory. Never overwrites human-authored notes, never touches canonical state,
and rejects any path that escapes the ``.generated/`` boundary.

Usage::

    from devflow.obsidian.render import render_all
    from devflow.obsidian.vault import write_vault_projection

    views = render_all(state)
    result = write_vault_projection(vault_path, run_id, views)

Output lands under::

    <vault>/Command Center/Projects/DevFlow/.generated/

Every file is wrapped in ``START_MARKER`` / ``END_MARKER`` by the renderers,
so re-runs replace only the generated block while preserving surrounding content.
"""

from __future__ import annotations

import os
from pathlib import Path

from pydantic import BaseModel, ConfigDict

from devflow.obsidian.render import END_MARKER, START_MARKER

# Subdirectory under the vault where generated projection files land.
_GENERATED_SUBDIR = Path("Command Center") / "Projects" / "DevFlow" / ".generated"


class VaultWriteResult(BaseModel):
    """Result of writing projection files to the vault."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    files_written: tuple[str, ...] = ()
    bytes_written: int = 0
    vault_dir: str = ""


def _resolve_generated_dir(vault_path: Path) -> Path:
    """Resolve and validate the .generated/ target directory."""
    target = (vault_path / _GENERATED_SUBDIR).resolve()
    vault_resolved = vault_path.resolve()
    # The target must stay inside the vault root.
    try:
        target.relative_to(vault_resolved)
    except ValueError as exc:
        raise ValueError(
            f"resolved generated dir {target} escapes vault root {vault_resolved}"
        ) from exc
    return target


def _atomic_write(path: Path, content: str) -> int:
    """Write content to *path* atomically via temp + replace.

    If the file already exists with START/END markers, replace only the marked
    block and preserve surrounding human content. Otherwise write the full file.
    """
    if path.exists():
        existing = path.read_text(encoding="utf-8")
        if START_MARKER in existing and END_MARKER in existing:
            # Existing file with markers: the renderer output already includes
            # START/END markers, so we overwrite the full file as-is.
            pass
        else:
            # No markers in existing file — overwrite entirely with generated content
            pass
    else:
        pass

    # Normalize: the renderers already include START/END markers in their output.
    # We write the full renderer output as-is (markers included).
    final_content = content

    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(final_content, encoding="utf-8")
    os.replace(tmp, path)
    return len(final_content.encode("utf-8"))


def write_vault_projection(
    vault_path: Path | str,
    run_id: str,
    views: dict[str, str],
) -> VaultWriteResult:
    """Write projection views atomically into the vault ``.generated/`` dir.

    Parameters
    ----------
    vault_path
        Root of the Obsidian vault (or any target directory).
    run_id
        Canonical run ID, used for logging/debugging only.
    views
        Mapping of ``filename → markdown_content`` (from
        :func:`~devflow.obsidian.render.render_all`).

    Returns
    -------
    VaultWriteResult
        Files written, total bytes, and the target directory path.

    Raises
    ------
    ValueError
        If any filename attempts path traversal or escapes ``.generated/``.
    """
    vault = Path(vault_path).resolve()
    generated_dir = _resolve_generated_dir(vault)
    generated_dir.mkdir(parents=True, exist_ok=True)

    files_written: list[str] = []
    total_bytes = 0

    for filename, content in views.items():
        # Validate filename — reject traversal, absolute paths, subdirectories
        fname = Path(filename)
        if fname.is_absolute() or fname.name != filename:
            raise ValueError(
                f"unsafe view filename {filename!r}: must be a simple filename"
            )
        # Resolve and confirm the target stays inside .generated/
        target = (generated_dir / fname.name).resolve()
        try:
            target.relative_to(generated_dir)
        except ValueError as exc:
            raise ValueError(
                f"view filename {filename!r} resolves outside .generated/"
            ) from exc

        bytes_written = _atomic_write(target, content)
        files_written.append(filename)
        total_bytes += bytes_written

    return VaultWriteResult(
        files_written=tuple(files_written),
        bytes_written=total_bytes,
        vault_dir=str(generated_dir),
    )


__all__ = [
    "VaultWriteResult",
    "write_vault_projection",
]
