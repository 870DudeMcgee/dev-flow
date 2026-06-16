from __future__ import annotations

from dataclasses import dataclass, field
import fnmatch
from pathlib import Path
import re


DANGEROUS_EXACT_NAMES = {
    "packet.json",
    "packet.md",
    "prompt.md",
    "response.md",
    "request.json",
    "response.json",
    "run.json",
    "proposal.md",
    "proposal.json",
    "proposal.patch",
    "patch-review.md",
    "patch-review.json",
}

DANGEROUS_PATTERNS = [
    ".git/**",
    ".devflow/workspaces/**",
    ".devflow/tasks/**",
    ".devflow/agent-runs/**",
    ".devflow/artifacts/**",
    "local-model-runs/**",
    "logs/**",
    "__pycache__/**",
    ".pytest_cache/**",
    ".venv/**",
    ".venv-*/**",
    "node_modules/**",
    "dist/**",
    "build/**",
]

HIGH_RISK_PATTERNS = [
    "src/devflow/control_room/patch_applier.py",
    "src/devflow/control_room/verification.py",
    "src/devflow/control_room/persistence.py",
    "src/devflow/control_room/service.py",
    "src/devflow/control_room/worker_adapter.py",
    "src/devflow/control_room/agent_registry.py",
    "src/devflow/control_room/git_worktree.py",
    "src/devflow/cli.py",
    "pyproject.toml",
    ".github/workflows/**",
    ".devflow/project/**",
    "AGENTS.md",
    "README.md",
    "PRODUCT_NORTH_STAR.md",
    "CHANGELOG.md",
    "LICENSE",
]

UNSUPPORTED_APPLY_METADATA_PREFIXES = (
    "Binary files ",
    "old mode ",
    "new mode ",
    "rename from ",
    "rename to ",
    "similarity index ",
    "dissimilarity index ",
    "copy from ",
    "copy to ",
)


class PatchProposalParseError(ValueError):
    """Raised when a patch proposal is not parseable as unified diff text."""


@dataclass
class PatchProposalHunk:
    old_start: int
    old_lines: int
    new_start: int
    new_lines: int
    lines: list[str] = field(default_factory=list)
    original_lines: list[str] = field(default_factory=list)
    patched_lines: list[str] = field(default_factory=list)


@dataclass
class PatchProposalFile:
    old_path: str | None
    new_path: str | None
    hunks: list[PatchProposalHunk] = field(default_factory=list)

    @property
    def source_file(self) -> str:
        return self.old_path or "/dev/null"

    @property
    def target_file(self) -> str:
        return self.new_path or "/dev/null"

    @property
    def is_new_file(self) -> bool:
        return self.old_path is None and self.new_path is not None

    @property
    def is_deletion(self) -> bool:
        return self.new_path is None and self.old_path is not None

    @property
    def target_path(self) -> str | None:
        return self.old_path if self.is_deletion else self.new_path


@dataclass
class PatchProposal:
    raw_text: str
    files: list[PatchProposalFile]

    @property
    def hunk_count(self) -> int:
        return sum(len(file_patch.hunks) for file_patch in self.files)

    @property
    def touched_files(self) -> list[str]:
        paths: list[str] = []
        for file_patch in self.files:
            if file_patch.old_path:
                paths.append(file_patch.old_path)
            if file_patch.new_path:
                paths.append(file_patch.new_path)
        return sorted(dict.fromkeys(paths))


@dataclass(frozen=True)
class PatchProposalInspection:
    files_touched: list[str]
    hunk_count: int
    has_unified_headers: bool
    parse_error: str | None = None

    @property
    def structurally_valid(self) -> bool:
        return bool(self.files_touched and self.hunk_count > 0 and self.has_unified_headers and self.parse_error is None)


def parse_patch_proposal(
    patch_text: str,
    *,
    reject_unsupported_apply_metadata: bool = False,
) -> PatchProposal:
    if not patch_text.strip():
        raise PatchProposalParseError("Empty diff")

    files: list[PatchProposalFile] = []
    current_file: PatchProposalFile | None = None
    current_hunk: PatchProposalHunk | None = None
    saw_hunk = False

    for line in patch_text.splitlines(keepends=True):
        text = line.rstrip("\r\n")

        if reject_unsupported_apply_metadata and any(
            text.startswith(prefix) for prefix in UNSUPPORTED_APPLY_METADATA_PREFIXES
        ):
            raise PatchProposalParseError(f"Unsupported metadata: {text.strip()}")

        if text.startswith("diff --git "):
            _validate_hunk_counts(current_hunk)
            if current_file and current_file.hunks:
                files.append(current_file)
            current_file = _file_from_diff_git(text)
            current_hunk = None
            continue

        if text.startswith("--- "):
            _validate_hunk_counts(current_hunk)
            if current_file and current_file.hunks:
                files.append(current_file)
                current_file = None
            if current_file is None:
                current_file = PatchProposalFile(old_path=None, new_path=None)
            current_file.old_path = header_path(text[4:])
            current_hunk = None
            continue

        if text.startswith("+++ "):
            if current_file is None:
                current_file = PatchProposalFile(old_path=None, new_path=None)
            current_file.new_path = header_path(text[4:])
            current_hunk = None
            continue

        if text.startswith("@@ "):
            if current_file is None:
                raise PatchProposalParseError("Hunk appeared before file headers.")
            _validate_hunk_counts(current_hunk)
            current_hunk = _parse_hunk_header(text)
            current_file.hunks.append(current_hunk)
            saw_hunk = True
            continue

        if current_hunk is not None:
            if text.startswith("\\ No newline at end of file"):
                current_hunk.lines.append(line)
                continue
            if not line:
                prefix = " "
                content = ""
            else:
                prefix = line[0]
                content = line[1:].rstrip("\r\n")
            if prefix == " ":
                current_hunk.lines.append(line)
                current_hunk.original_lines.append(content)
                current_hunk.patched_lines.append(content)
            elif prefix == "-":
                current_hunk.lines.append(line)
                current_hunk.original_lines.append(content)
            elif prefix == "+":
                current_hunk.lines.append(line)
                current_hunk.patched_lines.append(content)
            else:
                raise PatchProposalParseError(f"Malformed hunk line: {text.strip() or '<blank line>'}")

    _validate_hunk_counts(current_hunk)
    if current_file and current_file.hunks:
        files.append(current_file)

    if not saw_hunk:
        raise PatchProposalParseError("Patch has no hunks.")
    if not files:
        raise PatchProposalParseError("No valid file patches parsed")
    for file_patch in files:
        if file_patch.target_path is None:
            raise PatchProposalParseError("Patch file has no target path.")
    return PatchProposal(raw_text=patch_text, files=files)


def inspect_patch_proposal(patch_text: str) -> PatchProposalInspection:
    try:
        proposal = parse_patch_proposal(patch_text)
    except PatchProposalParseError as exc:
        return PatchProposalInspection(
            files_touched=extract_touched_files(patch_text),
            hunk_count=len(re.findall(r"^@@", patch_text, flags=re.MULTILINE)),
            has_unified_headers=has_unified_diff_headers(patch_text),
            parse_error=str(exc),
        )
    return PatchProposalInspection(
        files_touched=proposal.touched_files,
        hunk_count=proposal.hunk_count,
        has_unified_headers=has_unified_diff_headers(patch_text),
    )


def extract_touched_files(patch_text: str) -> list[str]:
    files: list[str] = []
    for line in patch_text.splitlines():
        if line.startswith("diff --git "):
            parts = line.split()
            if len(parts) >= 4:
                files.append(strip_patch_prefix(parts[3]))
        elif line.startswith("--- ") or line.startswith("+++ "):
            value = line[4:].split("\t", 1)[0].strip()
            if value != "/dev/null":
                files.append(strip_patch_prefix(value))
    return sorted(dict.fromkeys(path for path in files if path))


def has_unified_diff_headers(patch_text: str) -> bool:
    return "diff --git " in patch_text or ("--- " in patch_text and "+++ " in patch_text)


def strip_patch_prefix(path: str) -> str:
    normalized = normalize_patch_path(path)
    if normalized.startswith("a/") or normalized.startswith("b/"):
        return normalized[2:]
    return normalized


def normalize_patch_path(path: str) -> str:
    return path.strip().strip('"').replace("\\", "/")


def header_path(value: str) -> str | None:
    path = value.split("\t", 1)[0].strip()
    if path == "/dev/null":
        return None
    return strip_patch_prefix(path)


def is_dangerous_patch_path(path: str) -> bool:
    normalized = normalize_patch_path(path)
    if Path(normalized).is_absolute():
        return True
    if ".." in Path(normalized).parts:
        return True
    if Path(normalized).name in DANGEROUS_EXACT_NAMES:
        return True
    return any(fnmatch.fnmatch(normalized, pattern) for pattern in DANGEROUS_PATTERNS)


def is_high_risk_patch_path(path: str) -> bool:
    normalized = normalize_patch_path(path)
    return any(fnmatch.fnmatch(normalized, pattern) for pattern in HIGH_RISK_PATTERNS)


def resolve_workspace_patch_target(workspace_root: Path, target_path: str) -> Path:
    workspace = workspace_root.resolve()
    normalized = normalize_patch_path(target_path)
    if Path(normalized).is_absolute():
        raise ValueError(f"Absolute paths are rejected: {target_path}")
    if ".." in Path(normalized).parts:
        raise ValueError(f"Target path escapes workspace boundary (traversal rejected): {target_path}")
    if is_dangerous_patch_path(normalized):
        raise ValueError(f"Dangerous or generated patch path rejected: {target_path}")

    target = (workspace / normalized).resolve()
    try:
        target.relative_to(workspace)
    except ValueError as exc:
        raise ValueError(f"Target path escapes workspace boundary: {target_path}") from exc

    path = target
    while path != workspace:
        if path.is_symlink():
            raise ValueError(f"Writes through symlinks are rejected: {path}")
        path = path.parent
    return target


def _file_from_diff_git(line: str) -> PatchProposalFile:
    parts = line.split()
    old_path = strip_patch_prefix(parts[2]) if len(parts) > 2 else None
    new_path = strip_patch_prefix(parts[3]) if len(parts) > 3 else None
    return PatchProposalFile(old_path=old_path, new_path=new_path)


def _parse_hunk_header(line: str) -> PatchProposalHunk:
    match = re.match(r"^@@ -(\d+)(?:,(\d+))? \+(\d+)(?:,(\d+))? @@", line)
    if not match:
        raise PatchProposalParseError(f"Malformed hunk header: {line.strip()}")
    try:
        return PatchProposalHunk(
            old_start=int(match.group(1)),
            old_lines=int(match.group(2) or "1"),
            new_start=int(match.group(3)),
            new_lines=int(match.group(4) or "1"),
        )
    except ValueError as exc:
        raise PatchProposalParseError(f"Malformed hunk integers: {line.strip()}") from exc


def _validate_hunk_counts(hunk: PatchProposalHunk | None) -> None:
    if hunk is None:
        return
    actual_old_lines = len(hunk.original_lines)
    actual_new_lines = len(hunk.patched_lines)
    if actual_old_lines != hunk.old_lines or actual_new_lines != hunk.new_lines:
        raise PatchProposalParseError(
            "Malformed hunk line counts: "
            f"header expected {hunk.old_lines} old/{hunk.new_lines} new lines, "
            f"body has {actual_old_lines} old/{actual_new_lines} new lines"
        )
