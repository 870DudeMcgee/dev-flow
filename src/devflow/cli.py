import argparse
import json
import os
import sys
import datetime

from devflow.admin_commands import (
    doctor_command_impl,
    init_adapters_command_impl,
)
from devflow.lifecycle_commands import (
    impact_command_impl,
    init_workspace_command,
    status_workspace_command,
)
from devflow.resource_commands import (
    artifact_inspect_command,
    artifact_list_command,
    context_build_command,
    context_inspect_command,
    context_list_command,
    context_refresh_command,
    memory_add_command,
    memory_inspect_command,
    memory_list_command,
)
from devflow.task_commands import (
    task_claim_command,
    task_graph_command,
    task_next_command,
    task_new_command,
    task_ready_command,
    task_release_command,
    task_status_command,
    task_transition_command,
)
from devflow.worktree_commands import (
    worktree_create_command,
    worktree_remove_command,
    worktree_status_command,
)
from devflow.trace_eval_commands import (
    eval_compare_command,
    eval_run_command,
    trace_inspect_command,
    trace_list_command,
)
from devflow.workspace import default_config
from devflow.runner import (
    run_task_workflow,
)


def _default_config() -> dict:
    return default_config()


def _default_constitution() -> str:
    return """# devflow Constitution (MVP)\n\n- Files and git are the source of truth.\n- Unified diffs are the only supported patch protocol for MVP.\n- Protected file changes require human approval before apply.\n- Verification should run from task commands, config commands, or auto-detection.\n- Reports are mandatory for every task run.\n- devflow run previews by default; --yes is required to apply patches.\n- devflow run must stop before mutation when the git worktree is dirty.\n- Model/provider routing is post-MVP.\n"""

def new_task(
    task_id: str,
    title: str,
    goal: str = "",
    plan: str = "",
    agent: str = "",
    risk: str = "LOW",
    allowed_files: list[str] | None = None,
    touched_files: list[str] | None = None,
    verification_commands: list[str] | None = None,
    output: str | None = None,
    force: bool = False,
) -> str:
    """Create a canonical task markdown file."""
    return task_new_command(
        task_id=task_id,
        title=title,
        goal=goal,
        plan=plan,
        agent=agent,
        risk=risk,
        allowed_files=allowed_files,
        touched_files=touched_files,
        verification_commands=verification_commands,
        output=output,
        force=force,
    )


def claim_task(
    task_file: str,
    agent: str,
    owner_lock: str,
    touched_files: list[str] | None = None,
    branch: str | None = None,
    force: bool = False,
) -> bool:
    """Claim a task for one peer orchestrator."""
    return task_claim_command(
        task_file=task_file,
        agent=agent,
        owner_lock=owner_lock,
        touched_files=touched_files,
        branch=branch,
        force=force,
    )


def release_task(task_file: str) -> bool:
    """Release an owned task back to the shared queue."""
    return task_release_command(task_file)


def status_task(task_file: str) -> None:
    """Print task ownership and coordination status."""
    task_status_command(task_file)


def transition_task(task_file: str, to_state: str, reason: str = "", artifact_id: str = "") -> None:
    """Transition a task between canonical TDD states with validation."""
    task_transition_command(task_file=task_file, to_state=to_state, reason=reason, artifact_id=artifact_id)


def task_ready(json_output: bool = False, root_dir: str = ".") -> None:
    task_ready_command(json_output=json_output, root_dir=root_dir)


def task_next(agent: str, root_dir: str = ".") -> None:
    task_next_command(agent=agent, root_dir=root_dir)


def task_graph(root_dir: str = ".") -> None:
    task_graph_command(root_dir=root_dir)


def impact_command(task_file: str) -> None:
    impact_command_impl(task_file=task_file, cwd=os.getcwd())


def trace_list() -> None:
    trace_list_command()


def trace_inspect(trace_id: str) -> None:
    trace_inspect_command(trace_id=trace_id)


def eval_run(role: str) -> None:
    eval_run_command(role=role)


def eval_compare(prompt_a: str, prompt_b: str) -> None:
    eval_compare_command(prompt_a=prompt_a, prompt_b=prompt_b)


def worktree_create(task_file: str, agent: str) -> None:
    worktree_create_command(task_file=task_file, agent=agent)


def worktree_status() -> None:
    worktree_status_command()


def worktree_remove(task_file: str, keep_artifacts: bool = False) -> None:
    worktree_remove_command(task_file=task_file, keep_artifacts=keep_artifacts)


# ── Adapter file registry for doctor / init-adapters ─────────────────────

def doctor_command() -> None:
    doctor_command_impl()


def init_adapters_command(targets: list[str] | None = None, force: bool = False) -> None:
    init_adapters_command_impl(targets=targets, force=force)


def init_workspace():
    """Initialize the canonical .devflow protocol tree."""
    init_workspace_command(default_config=_default_config(), constitution_text=_default_constitution())

def status_workspace():
    """Print a summary of goal/plan/task state from .devflow."""
    status_workspace_command()


def artifact_list(task_id: str) -> None:
    """Print artifact metadata for one task."""
    artifact_list_command(task_id=task_id)


def artifact_inspect(identifier: str) -> None:
    """Print metadata and body location for one artifact."""
    artifact_inspect_command(identifier=identifier)


def context_refresh() -> None:
    """Refresh deterministic repository maps under .devflow/context."""
    context_refresh_command()


def context_build(task_file: str, role: str, budget: int | None = None) -> None:
    """Build and store a context pack artifact for one task and role."""
    context_build_command(task_file=task_file, role=role, budget=budget)


def context_inspect(identifier: str) -> None:
    """Print a context pack summary by artifact id or path."""
    context_inspect_command(identifier=identifier)


def context_list(task_id: str) -> None:
    """List context-pack artifacts for one task."""
    context_list_command(task_id=task_id)


def memory_add(memory_type: str, statement: str, evidence: str, invalidate_on: list[str]) -> None:
    memory_add_command(
        memory_type=memory_type,
        statement=statement,
        evidence=evidence,
        invalidate_on=invalidate_on,
    )


def memory_list() -> None:
    memory_list_command()


def memory_inspect(memory_id: str) -> None:
    memory_inspect_command(memory_id=memory_id)


def run_task(task_file: str, yes: bool = False):
    """Run a single canonical task file with unified-diff safe-edit workflow."""
    run_task_workflow(task_file=task_file, yes=yes)

def main():
    parser = argparse.ArgumentParser(description="devflow - Safe unified-diff MVP runner")
    subparsers = parser.add_subparsers(dest="command")

    subparsers.add_parser("init", help="Initialize a new devflow workspace")
    subparsers.add_parser("status", help="Show goal, plan, and task state")
    subparsers.add_parser("doctor", help="Check that all adapter and workflow files are present")

    adapters_parser = subparsers.add_parser("init-adapters", help="Generate adapter files from canonical workflow")
    adapters_parser.add_argument("--target", action="append", default=[], help="Target: vscode, antigravity, codex, universal, or all (may be repeated)")
    adapters_parser.add_argument("--all", action="store_true", dest="all_targets", help="Generate adapters for all targets")
    adapters_parser.add_argument("--force", action="store_true", help="Overwrite existing adapter files")

    task_parser = subparsers.add_parser("task", help="Manage task ownership and status")
    task_subparsers = task_parser.add_subparsers(dest="task_command")

    new_parser = task_subparsers.add_parser("new", help="Create a canonical task markdown file")
    new_parser.add_argument("task_id", type=str, help="Task id, e.g. 001")
    new_parser.add_argument("title", type=str, help="Task title")
    new_parser.add_argument("--goal", default="", help="Goal id/reference")
    new_parser.add_argument("--plan", default="", help="Plan JSON filename or path")
    new_parser.add_argument("--agent", default="", help="Initial assigned orchestrator")
    new_parser.add_argument("--risk", default="LOW", help="Risk level")
    new_parser.add_argument("--allowed", action="append", default=[], help="Allowed file path/glob; may be repeated")
    new_parser.add_argument("--touch", action="append", default=[], help="Expected touched file/glob; may be repeated")
    new_parser.add_argument("--verify", action="append", default=[], help="Verification command; may be repeated")
    new_parser.add_argument("--output", help="Output task path")
    new_parser.add_argument("--force", action="store_true", help="Overwrite existing task file")

    claim_parser = task_subparsers.add_parser("claim", help="Claim a task for an orchestrator")
    claim_parser.add_argument("task_file", type=str, help="Path to canonical task markdown file")
    claim_parser.add_argument("--agent", required=True, help="Owning orchestrator: codex, vscode, or antigravity")
    claim_parser.add_argument("--lock", required=True, help="Session/team lock identifier")
    claim_parser.add_argument("--branch", help="Branch name to write into the task header")
    claim_parser.add_argument("--touch", action="append", default=[], help="Expected touched file or glob; may be repeated")
    claim_parser.add_argument("--force", action="store_true", help="Override an existing CLAIMED/RUNNING task")

    release_parser = task_subparsers.add_parser("release", help="Release a claimed task")
    release_parser.add_argument("task_file", type=str, help="Path to canonical task markdown file")

    task_status_parser = task_subparsers.add_parser("status", help="Show one task's coordination status")
    task_status_parser.add_argument("task_file", type=str, help="Path to canonical task markdown file")

    transition_parser = task_subparsers.add_parser("transition", help="Transition a task between TDD states")
    transition_parser.add_argument("task_file", type=str, help="Path to canonical task markdown file")
    transition_parser.add_argument("--to", required=True, help="Target state, e.g. RED, GREEN, REFACTOR, REPORT")
    transition_parser.add_argument("--reason", default="", help="Reason for the transition")
    transition_parser.add_argument("--artifact", default="", help="Artifact ID associated with this transition")

    ready_parser = task_subparsers.add_parser("ready", help="List unblocked dependency-ready tasks")
    ready_parser.add_argument("--json", action="store_true", help="Format output as JSON list")

    next_parser = task_subparsers.add_parser("next", help="Get next task to execute for an agent")
    next_parser.add_argument("--agent", required=True, help="Agent name")

    graph_parser = task_subparsers.add_parser("graph", help="Show the hierarchical task dependency graph")

    run_parser = subparsers.add_parser("run", help="Run a single task markdown file")
    run_parser.add_argument("task_file", type=str, help="Path to canonical task markdown file")
    run_parser.add_argument("--yes", action="store_true", help="Apply the patch after validation")

    impact_parser = subparsers.add_parser("impact", help="Analyze task allowed/touched files change impact")
    impact_parser.add_argument("task_file", type=str, help="Path to canonical task markdown file")

    artifact_parser = subparsers.add_parser("artifact", help="Inspect and list task artifacts")
    artifact_subparsers = artifact_parser.add_subparsers(dest="artifact_command")

    artifact_list_parser = artifact_subparsers.add_parser("list", help="List artifacts for a task")
    artifact_list_parser.add_argument("task_id", type=str, help="Task id, e.g. T-042")

    artifact_inspect_parser = artifact_subparsers.add_parser("inspect", help="Inspect one artifact")
    artifact_inspect_parser.add_argument("identifier", type=str, help="Artifact id, metadata path, or body path")

    context_parser = subparsers.add_parser("context", help="Build and inspect bounded context packs")
    context_subparsers = context_parser.add_subparsers(dest="context_command")

    context_subparsers.add_parser("refresh", help="Refresh repository maps under .devflow/context")

    context_build_parser = context_subparsers.add_parser("build", help="Build a context pack artifact")
    context_build_parser.add_argument("task_file", type=str, help="Path to canonical task markdown file")
    context_build_parser.add_argument("--role", required=True, help="Worker role, e.g. reviewer or implementer")
    context_build_parser.add_argument("--budget", type=int, help="Token budget override")

    context_inspect_parser = context_subparsers.add_parser("inspect", help="Inspect a context pack")
    context_inspect_parser.add_argument("identifier", type=str, help="Context artifact id, metadata path, or body path")

    context_list_parser = context_subparsers.add_parser("list", help="List context packs for a task")
    context_list_parser.add_argument("task_id", type=str, help="Task id, e.g. T-042")

    memory_parser = subparsers.add_parser("memory", help="Manage architectural memory records")
    memory_subparsers = memory_parser.add_subparsers(dest="memory_command")

    memory_subparsers.add_parser("list", help="List architectural memory records")

    memory_add_parser = memory_subparsers.add_parser("add", help="Add an architectural memory record")
    memory_add_parser.add_argument("--type", required=True, help="Memory type, e.g. architecture")
    memory_add_parser.add_argument("--statement", required=True, help="Memory statement")
    memory_add_parser.add_argument("--evidence", required=True, help="Evidence supporting the memory")
    memory_add_parser.add_argument("--invalidate-on", action="append", required=True, help="Path or glob that stales this memory; may be repeated")

    memory_inspect_parser = memory_subparsers.add_parser("inspect", help="Inspect one memory record")
    memory_inspect_parser.add_argument("memory_id", type=str, help="Memory id, e.g. mem_abc123")

    agent_parser = subparsers.add_parser("agent", help="Stateless model agent commands")
    agent_subparsers = agent_parser.add_subparsers(dest="agent_command")

    agent_review_parser = agent_subparsers.add_parser("review", help="Run stateless code review agent")
    agent_review_parser.add_argument("task_file", type=str, help="Path to task file")
    agent_review_parser.add_argument("--profile", default="reviewer", help="Agent profile to use")

    agent_implement_parser = agent_subparsers.add_parser("implement", help="Run stateless code implementer agent")
    agent_implement_parser.add_argument("task_file", type=str, help="Path to task file")
    agent_implement_parser.add_argument("--profile", default="implementer", help="Agent profile to use")
    agent_implement_parser.add_argument("--emit-diff", action="store_true", help="Emit proposed diff immediately after execution")

    agent_repair_parser = agent_subparsers.add_parser("repair", help="Run automated test-driven repair loop agent")
    agent_repair_parser.add_argument("task_file", type=str, help="Path to task file")
    agent_repair_parser.add_argument("--profile", default="repair", help="Agent profile to use")
    agent_repair_parser.add_argument("--max-loops", type=int, default=3, help="Maximum repair loop limit")



    guard_parser = subparsers.add_parser("guard", help="Deterministic guard commands")
    guard_subparsers = guard_parser.add_subparsers(dest="guard_command")

    guard_scan_diff_parser = guard_subparsers.add_parser("scan-diff", help="Deterministic static hazard scan of a diff")
    guard_scan_diff_parser.add_argument("identifier", type=str, help="Artifact ID, file path, or sequence pattern")

    trace_parser = subparsers.add_parser("trace", help="Observability trace span commands")
    trace_subparsers = trace_parser.add_subparsers(dest="trace_command")
    trace_subparsers.add_parser("list", help="List all executed traces")
    trace_inspect_parser = trace_subparsers.add_parser("inspect", help="Inspect a trace execution nested span tree")
    trace_inspect_parser.add_argument("trace_id", type=str, help="Trace unique ID")

    eval_parser = subparsers.add_parser("eval", help="Role prompt harness evaluation commands")
    eval_subparsers = eval_parser.add_subparsers(dest="eval_command")
    eval_run_parser = eval_subparsers.add_parser("run", help="Run deterministic evaluations for a role")
    eval_run_parser.add_argument("--role", required=True, help="Agent role, e.g. implementer | reviewer | repair")
    eval_compare_parser = eval_subparsers.add_parser("compare", help="Compare two prompt versions and display metrics")
    eval_compare_parser.add_argument("prompt_a", type=str, help="First prompt version or path")
    eval_compare_parser.add_argument("prompt_b", type=str, help="Second prompt version or path")

    worktree_parser = subparsers.add_parser("worktree", help="Manage explicit task git worktrees")
    worktree_subparsers = worktree_parser.add_subparsers(dest="worktree_command")

    worktree_create_parser = worktree_subparsers.add_parser("create", help="Create an isolated worktree for a task")
    worktree_create_parser.add_argument("task_file", type=str, help="Path to canonical task markdown file")
    worktree_create_parser.add_argument("--agent", required=True, help="Owning orchestrator for this worktree")

    worktree_subparsers.add_parser("status", help="List recorded task worktrees")

    worktree_remove_parser = worktree_subparsers.add_parser("remove", help="Remove a task worktree")
    worktree_remove_parser.add_argument("task_file", type=str, help="Path to canonical task markdown file")
    worktree_remove_parser.add_argument("--keep-artifacts", action="store_true", help="Preserve task artifacts under .devflow/artifacts/")

    args = parser.parse_args()

    if args.command == "init":
        init_workspace()
    elif args.command == "status":
        status_workspace()
    elif args.command == "doctor":
        doctor_command()
    elif args.command == "init-adapters":
        targets = args.target if args.target else None
        if args.all_targets:
            targets = ["all"]
        init_adapters_command(targets=targets, force=args.force)
    elif args.command == "task":
        if args.task_command == "new":
            try:
                new_task(
                    args.task_id,
                    args.title,
                    goal=args.goal,
                    plan=args.plan,
                    agent=args.agent,
                    risk=args.risk,
                    allowed_files=args.allowed,
                    touched_files=args.touch,
                    verification_commands=args.verify,
                    output=args.output,
                    force=args.force,
                )
            except FileExistsError as exc:
                print(f"Error: {exc}")
                sys.exit(1)
        elif args.task_command == "claim":
            claim_task(
                args.task_file,
                agent=args.agent,
                owner_lock=args.lock,
                touched_files=args.touch or None,
                branch=args.branch,
                force=args.force,
            )
        elif args.task_command == "release":
            release_task(args.task_file)
        elif args.task_command == "status":
            status_task(args.task_file)
        elif args.task_command == "transition":
            transition_task(
                args.task_file,
                to_state=args.to,
                reason=args.reason,
                artifact_id=args.artifact
            )
        elif args.task_command == "ready":
            task_ready(json_output=args.json)
        elif args.task_command == "next":
            task_next(agent=args.agent)
        elif args.task_command == "graph":
            task_graph()
        else:
            task_parser.print_help()
    elif args.command == "run":
        run_task(args.task_file, yes=args.yes)
    elif args.command == "impact":
        impact_command(args.task_file)
    elif args.command == "artifact":
        if args.artifact_command == "list":
            artifact_list(args.task_id)
        elif args.artifact_command == "inspect":
            artifact_inspect(args.identifier)
        else:
            artifact_parser.print_help()
    elif args.command == "context":
        if args.context_command == "refresh":
            context_refresh()
        elif args.context_command == "build":
            context_build(args.task_file, role=args.role, budget=args.budget)
        elif args.context_command == "inspect":
            context_inspect(args.identifier)
        elif args.context_command == "list":
            context_list(args.task_id)
        else:
            context_parser.print_help()
    elif args.command == "memory":
        if args.memory_command == "list":
            memory_list()
        elif args.memory_command == "add":
            memory_add(args.type, args.statement, args.evidence, args.invalidate_on)
        elif args.memory_command == "inspect":
            memory_inspect(args.memory_id)
        else:
            memory_parser.print_help()
    elif args.command == "agent":
        if args.agent_command == "review":
            from devflow.agents.runner import run_review_agent
            record = run_review_agent(args.task_file, profile_name=args.profile)
            print(f"Agent review completed. Artifact created: {record.artifact_id}")
            print(f"Path: {record.body_path}")
        elif args.agent_command == "implement":
            from devflow.agents.runner import run_implement_agent
            record = run_implement_agent(args.task_file, profile_name=args.profile)
            print(f"Agent implementation completed. Artifact created: {record.artifact_id}")
            print(f"Path: {record.body_path}")
            if args.emit_diff:
                # Read artifact and print the diff
                from devflow.artifacts import read_artifact
                _, body = read_artifact(record.body_path)
                try:
                    diff_data = json.loads(body)
                    print("\n--- PROPOSED DIFF ---")
                    print(diff_data.get("diff", ""))
                    print("---------------------")
                except Exception:
                    pass
        elif args.agent_command == "repair":
            from devflow.agents.runner import run_repair_agent
            record = run_repair_agent(args.task_file, max_loops=args.max_loops, profile_name=args.profile)
            print(f"Agent repair completed. Artifact created: {record.artifact_id}")
            print(f"Path: {record.body_path}")
        else:
            agent_parser.print_help()

    elif args.command == "guard":
        if args.guard_command == "scan-diff":
            from devflow.safety import scan_diff_for_hazards
            from devflow.artifacts import find_artifact, read_artifact
            
            diff_text = ""
            try:
                # First try finding as an artifact
                record = find_artifact(args.identifier)
                _, body = read_artifact(record.metadata_path)
                try:
                    data = json.loads(body)
                    diff_text = data.get("diff", "")
                except Exception:
                    diff_text = body
            except Exception:
                # Fall back to checking if it's a file
                if os.path.exists(args.identifier):
                    with open(args.identifier, "r", encoding="utf-8") as f:
                        content = f.read()
                    try:
                        data = json.loads(content)
                        diff_text = data.get("diff", "")
                    except Exception:
                        diff_text = content
                else:
                    print(f"Error: could not resolve identifier as an artifact or file path: {args.identifier}")
                    sys.exit(1)
            
            is_clean, findings = scan_diff_for_hazards(diff_text)
            if not is_clean:
                print("Adversarial hazards detected in proposed diff:")
                for finding in findings:
                    print(f"- {finding}")
                sys.exit(1)
            else:
                print("Safety scan completed: no adversarial hazards detected.")
                sys.exit(0)
        else:
            guard_parser.print_help()
    elif args.command == "trace":
        if args.trace_command == "list":
            trace_list()
        elif args.trace_command == "inspect":
            trace_inspect(args.trace_id)
        else:
            trace_parser.print_help()
    elif args.command == "eval":
        if args.eval_command == "run":
            eval_run(args.role)
        elif args.eval_command == "compare":
            eval_compare(args.prompt_a, args.prompt_b)
        else:
            eval_parser.print_help()
    elif args.command == "worktree":
        if args.worktree_command == "create":
            worktree_create(args.task_file, agent=args.agent)
        elif args.worktree_command == "status":
            worktree_status()
        elif args.worktree_command == "remove":
            worktree_remove(args.task_file, keep_artifacts=args.keep_artifacts)
        else:
            worktree_parser.print_help()
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
