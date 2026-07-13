"""Typed authoritative execution plan for new canonical product-build runs."""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path, PurePosixPath
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from devflow.loop.pipeline_run import load_pipeline_run, update_pipeline_run_record


_ALLOWED_EXECUTABLES = {
    "python",
    "python3",
    "pytest",
    "ruff",
    "mypy",
    "node",
    "npm",
    "npx",
    "pnpm",
    "yarn",
    "go",
    "cargo",
}
_ALLOWED_EVIDENCE = {
    "exit-code",
    "output",
    "stdout",
    "stderr",
    "pytest-exit-code",
    "pytest-output",
}


def _relative_path(value: str, *, allow_dot: bool = False) -> str:
    if not isinstance(value, str) or not value.strip() or "\\" in value:
        raise ValueError("path must be a nonblank POSIX-style relative path")
    path = PurePosixPath(value)
    if path.is_absolute() or ".." in path.parts:
        raise ValueError(f"path must remain inside the selected working tree: {value!r}")
    if not allow_dot and path == PurePosixPath("."):
        raise ValueError("target path cannot be the working-tree root")
    return value


class ExecutionPacket(BaseModel):
    """One deterministic packet in the approved dependency graph."""

    model_config = ConfigDict(extra="forbid")

    id: str = Field(min_length=1, pattern=r"^[A-Za-z0-9][A-Za-z0-9._-]*$")
    target_files: list[str] = Field(min_length=1)
    depends_on: list[str] = Field(default_factory=list)

    @field_validator("target_files")
    @classmethod
    def validate_target_files(cls, values: list[str]) -> list[str]:
        checked = [_relative_path(value) for value in values]
        if len(checked) != len(set(checked)):
            raise ValueError("packet target_files must be unique")
        return checked

    @field_validator("depends_on")
    @classmethod
    def validate_dependencies(cls, values: list[str]) -> list[str]:
        if len(values) != len(set(values)):
            raise ValueError("packet dependencies must be unique")
        return values

    @model_validator(mode="after")
    def reject_self_dependency(self) -> "ExecutionPacket":
        if self.id in self.depends_on:
            raise ValueError("packet cannot depend on itself")
        return self


class ExecutionValidator(BaseModel):
    """Allowlisted argv validator; never a planner-authored shell string."""

    model_config = ConfigDict(extra="forbid")

    id: str = Field(min_length=1, pattern=r"^[A-Za-z0-9][A-Za-z0-9._-]*$")
    kind: Literal["command"] = "command"
    argv: list[str] = Field(min_length=1)
    cwd: str = "."
    timeout_seconds: int = Field(default=300, gt=0, le=3600)
    network: Literal["forbid", "allow"] = "forbid"
    permissions: list[str] = Field(default_factory=list)
    evidence: list[str] = Field(min_length=1)

    @field_validator("argv", mode="before")
    @classmethod
    def reject_shell_string(cls, value: object) -> object:
        if isinstance(value, str):
            raise ValueError("argv must be a list, never a shell command string")
        return value

    @field_validator("argv")
    @classmethod
    def validate_argv(cls, values: list[str]) -> list[str]:
        if any(not isinstance(value, str) or not value for value in values):
            raise ValueError("argv entries must be nonblank strings")
        return values

    @field_validator("cwd")
    @classmethod
    def validate_cwd(cls, value: str) -> str:
        return _relative_path(value, allow_dot=True)

    @model_validator(mode="after")
    def enforce_phase_one_allowlist(self) -> "ExecutionValidator":
        executable = Path(self.argv[0]).name
        if executable not in _ALLOWED_EXECUTABLES:
            raise ValueError(f"executable {executable!r} is not allowlisted")
        if self.network != "forbid":
            raise ValueError("Phase 1 validators require network=forbid")
        if self.permissions:
            raise ValueError("Phase 1 validators do not grant extra permissions")
        unknown_evidence = set(self.evidence) - _ALLOWED_EVIDENCE
        if unknown_evidence:
            raise ValueError(f"validator evidence is not allowlisted: {sorted(unknown_evidence)!r}")
        return self


class ExecutionValidatorReceipt(BaseModel):
    """Immutable deterministic receipt for one typed validator attempt."""

    model_config = ConfigDict(extra="forbid")

    validator_id: str
    argv: list[str]
    cwd: str
    exit_code: int | None = None
    passed: bool
    stdout: str = ""
    stderr: str = ""
    timed_out: bool = False


class ExecutionPlan(BaseModel):
    """Immutable contract approved by the planning judge for one new run."""

    model_config = ConfigDict(extra="forbid")

    schema_version: Literal[1] = 1
    workflow_id: Literal["canonical_product_build@1"] = "canonical_product_build@1"
    target_files: list[str] = Field(min_length=1)
    packets: list[ExecutionPacket] = Field(min_length=1)
    validators: list[ExecutionValidator] = Field(min_length=1)

    @field_validator("target_files")
    @classmethod
    def validate_target_files(cls, values: list[str]) -> list[str]:
        checked = [_relative_path(value) for value in values]
        if len(checked) != len(set(checked)):
            raise ValueError("plan target_files must be unique")
        return checked

    @model_validator(mode="after")
    def validate_graph(self) -> "ExecutionPlan":
        packet_ids = [packet.id for packet in self.packets]
        if len(packet_ids) != len(set(packet_ids)):
            raise ValueError("packet ids must be unique")
        validator_ids = [validator.id for validator in self.validators]
        if len(validator_ids) != len(set(validator_ids)):
            raise ValueError("validator ids must be unique")

        known_packets = set(packet_ids)
        assigned: list[str] = []
        graph: dict[str, list[str]] = {}
        for packet in self.packets:
            unknown = set(packet.depends_on) - known_packets
            if unknown:
                raise ValueError(f"unknown packet dependencies: {sorted(unknown)!r}")
            extra_targets = set(packet.target_files) - set(self.target_files)
            if extra_targets:
                raise ValueError(f"packet targets outside plan: {sorted(extra_targets)!r}")
            assigned.extend(packet.target_files)
            graph[packet.id] = packet.depends_on

        if len(assigned) != len(set(assigned)):
            raise ValueError("packet target_files cannot overlap")
        if set(assigned) != set(self.target_files):
            raise ValueError("packets must cover every approved target exactly once")

        visiting: set[str] = set()
        visited: set[str] = set()

        def visit(packet_id: str) -> None:
            if packet_id in visiting:
                raise ValueError("packet dependency graph contains a cycle")
            if packet_id in visited:
                return
            visiting.add(packet_id)
            for dependency in graph[packet_id]:
                visit(dependency)
            visiting.remove(packet_id)
            visited.add(packet_id)

        for packet_id in packet_ids:
            visit(packet_id)
        return self


def render_execution_plan_markdown(plan: ExecutionPlan, narrative: str = "") -> str:
    """Render the human view from the authoritative typed plan."""
    lines = ["# Execution Plan", ""]
    if narrative.strip():
        lines.extend([narrative.strip(), ""])
    lines.extend(["## Targets", *[f"- `{path}`" for path in plan.target_files], ""])
    lines.append("## Packets")
    for packet in plan.packets:
        dependencies = ", ".join(packet.depends_on) or "none"
        lines.append(f"- `{packet.id}`: {', '.join(packet.target_files)}; depends on {dependencies}")
    lines.extend(["", "## Validators"])
    for validator in plan.validators:
        lines.append(f"- `{validator.id}`: `{validator.argv!r}` (cwd `{validator.cwd}`)")
    return "\n".join(lines).rstrip() + "\n"


def save_execution_plan(root: Path | str, run_id: str, plan: ExecutionPlan) -> None:
    update_pipeline_run_record(
        root, run_id, "execution-plan.json", plan.model_dump(mode="json")
    )


def load_execution_plan(root: Path | str, run_id: str) -> ExecutionPlan:
    records = load_pipeline_run(root, run_id)
    if "execution-plan.json" not in records:
        raise ValueError(f"Run {run_id!r} has no authoritative execution-plan.json")
    return ExecutionPlan.model_validate(records["execution-plan.json"])


def run_execution_validators(
    workspace: Path | str,
    validators: list[ExecutionValidator],
) -> list[ExecutionValidatorReceipt]:
    """Run allowlisted argv validators inside one materialized workspace."""
    workspace_root = Path(workspace).resolve()
    receipts: list[ExecutionValidatorReceipt] = []
    for validator in validators:
        cwd = (workspace_root / validator.cwd).resolve()
        try:
            cwd.relative_to(workspace_root)
        except ValueError:
            receipts.append(
                ExecutionValidatorReceipt(
                    validator_id=validator.id,
                    argv=validator.argv,
                    cwd=str(cwd),
                    passed=False,
                    stderr=f"cwd {validator.cwd!r} escapes the build workspace",
                )
            )
            continue
        if not cwd.is_dir():
            receipts.append(
                ExecutionValidatorReceipt(
                    validator_id=validator.id,
                    argv=validator.argv,
                    cwd=str(cwd),
                    passed=False,
                    stderr=f"cwd {validator.cwd!r} does not exist",
                )
            )
            continue
        try:
            env = dict(os.environ)
            env["PATH"] = (
                f"{Path(sys.executable).parent}{os.pathsep}{env.get('PATH', '')}"
            )
            completed = subprocess.run(
                validator.argv,
                shell=False,
                cwd=cwd,
                capture_output=True,
                text=True,
                timeout=validator.timeout_seconds,
                env=env,
            )
            receipts.append(
                ExecutionValidatorReceipt(
                    validator_id=validator.id,
                    argv=validator.argv,
                    cwd=str(cwd),
                    exit_code=completed.returncode,
                    passed=completed.returncode == 0,
                    stdout=completed.stdout,
                    stderr=completed.stderr,
                )
            )
        except subprocess.TimeoutExpired as exc:
            receipts.append(
                ExecutionValidatorReceipt(
                    validator_id=validator.id,
                    argv=validator.argv,
                    cwd=str(cwd),
                    passed=False,
                    stdout=exc.stdout if isinstance(exc.stdout, str) else "",
                    stderr=f"timed out after {validator.timeout_seconds} seconds",
                    timed_out=True,
                )
            )
        except OSError as exc:
            receipts.append(
                ExecutionValidatorReceipt(
                    validator_id=validator.id,
                    argv=validator.argv,
                    cwd=str(cwd),
                    passed=False,
                    stderr=f"could not start validator: {exc}",
                )
            )
    return receipts


__all__ = [
    "ExecutionPacket",
    "ExecutionPlan",
    "ExecutionValidator",
    "ExecutionValidatorReceipt",
    "load_execution_plan",
    "render_execution_plan_markdown",
    "run_execution_validators",
    "save_execution_plan",
]
