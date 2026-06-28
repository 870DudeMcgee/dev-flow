from __future__ import annotations

from pathlib import Path
from typing import Any
import json

import typer

from devflow.control_room.agent_catalog_command import (
    AgentCatalogCommandError,
    build_agent_catalog_command_payload,
    render_agent_catalog_json,
    render_agent_catalog_lines,
)
from devflow.control_room.agent_registry import AgentRegistryError, load_agent_registry
from devflow.control_room.agent_runtime import agent_runtime_contract
from devflow.control_room.paths import relative_path
from devflow.control_room.project_registry import (
    ProjectRootResolution,
    ProjectRegistryError,
    project_task_ref,
    resolve_project_root,
)
from devflow.control_room.task_packet import build_agent_packet


agent_app = typer.Typer(help="Manage and inspect agents")


def _resolve_task_project_root(project: str | None) -> ProjectRootResolution:
    try:
        return resolve_project_root(Path.cwd(), project)
    except ProjectRegistryError as exc:
        typer.echo(f"Error: {exc}", err=True)
        raise typer.Exit(code=1) from exc


def _echo_list(label: str, values: list[str]) -> None:
    typer.echo(f"{label}:")
    if not values:
        typer.echo("  - none")
        return
    for value in values:
        typer.echo(f"  - {value}")


def _runtime_status_line(contract: dict[str, Any], *, include_refusal: bool) -> str:
    parts = [
        f"runtime: {contract['execution_surface']}",
        f"task_run: {'yes' if contract['task_run_allowed'] else 'no'}",
        f"agent_run: {'yes' if contract['agent_run_allowed'] else 'no'}",
        f"packet: {'yes' if contract['packet_allowed'] else 'no'}",
    ]
    if contract.get("next_command"):
        parts.append(f"next: {contract['next_command']}")
    elif include_refusal and contract.get("refusal_reason"):
        parts.append(f"refusal: {contract['refusal_reason']}")
    elif contract.get("refusal_reason"):
        parts.append("refusal: see agent show")
    return "  " + " | ".join(parts)


def _echo_runtime_contract(contract: dict[str, Any]) -> None:
    typer.echo("runtime_contract:")
    typer.echo(f"  execution_surface: {contract['execution_surface']}")
    typer.echo(f"  task_run_allowed: {str(contract['task_run_allowed']).lower()}")
    typer.echo(f"  agent_run_allowed: {str(contract['agent_run_allowed']).lower()}")
    typer.echo(f"  packet_allowed: {str(contract['packet_allowed']).lower()}")
    typer.echo(f"  refusal_reason: {contract.get('refusal_reason') or 'none'}")
    typer.echo(f"  next_command: {contract.get('next_command') or 'none'}")
    evidence = contract.get("evidence_contract") or {}
    _echo_list("  evidence_required_outputs", list(evidence.get("required_outputs") or []))
    _echo_list("  evidence_optional_outputs", list(evidence.get("optional_outputs") or []))
    _echo_list("  evidence_forbidden_outputs", list(evidence.get("forbidden_outputs") or []))


@agent_app.command("catalog")
def agent_catalog(
    json_output: bool = typer.Option(False, "--json", help="Emit machine-readable JSON."),
    provider: str | None = typer.Option(None, "--provider", help="Filter catalog to one provider id."),
) -> None:
    """Show providers, profiles, runtime contracts, env readiness, and local model discovery."""
    try:
        payload = build_agent_catalog_command_payload(Path.cwd(), provider_id=provider)
    except AgentCatalogCommandError as exc:
        typer.echo(f"Error: {exc}", err=True)
        raise typer.Exit(code=1) from exc

    if json_output:
        typer.echo(render_agent_catalog_json(payload))
        return

    for line in render_agent_catalog_lines(payload):
        typer.echo(line)


@agent_app.command("add-provider")
def agent_add_provider(
    provider_id: str,
    adapter: str = typer.Option(..., "--adapter", help="Provider adapter, such as ollama_chat or openai_compatible."),
    base_url: str = typer.Option(..., "--base-url", help="Provider base URL."),
    api_key_env: str | None = typer.Option(None, "--api-key-env", help="Environment variable name for the API key."),
    timeout_seconds: int | None = typer.Option(None, "--timeout-seconds", min=1, help="Default timeout in seconds."),
    dry_run: bool = typer.Option(False, "--dry-run", help="Validate and preview without writing."),
    json_output: bool = typer.Option(False, "--json", help="Emit machine-readable JSON."),
) -> None:
    """Register a provider config under .devflow/providers."""
    from devflow.control_room.agent_onboarding import AgentOnboardingError, add_provider

    try:
        result = add_provider(
            Path.cwd(),
            provider_id,
            adapter=adapter,
            base_url=base_url,
            api_key_env=api_key_env,
            timeout_seconds=timeout_seconds,
            dry_run=dry_run,
        )
    except AgentOnboardingError as exc:
        typer.echo(f"Error: {exc}", err=True)
        raise typer.Exit(code=1) from exc

    payload = result.to_payload(Path.cwd())
    if json_output:
        typer.echo(json.dumps(payload, indent=2, sort_keys=True))
        return
    typer.echo(f"status: {payload['status']}")
    typer.echo(f"provider_id: {payload['provider']['id']}")
    typer.echo(f"adapter: {payload['provider']['adapter']}")
    typer.echo(f"path: {payload['path']}")
    typer.echo(f"dry_run: {str(payload['dry_run']).lower()}")


@agent_app.command("add-model")
def agent_add_model(
    provider_id: str = typer.Option(..., "--provider", help="Existing provider id."),
    model_id: str = typer.Option(..., "--model", help="Model slug or local Ollama model id."),
    authority: str = typer.Option(..., "--authority", help="read-only, advisory, patch-proposer, or disabled."),
    role: str = typer.Option(..., "--role", help="Registered role id for this profile."),
    profile_id: str | None = typer.Option(None, "--profile-id", help="Optional safe explicit profile id."),
    dry_run: bool = typer.Option(False, "--dry-run", help="Validate and preview without writing."),
    json_output: bool = typer.Option(False, "--json", help="Emit machine-readable JSON."),
) -> None:
    """Register or upsert a safe model profile under .devflow/agents/registry.yaml."""
    from devflow.control_room.agent_onboarding import AgentOnboardingError, add_model

    try:
        result = add_model(
            Path.cwd(),
            provider_id=provider_id,
            model_id=model_id,
            authority=authority,
            role=role,
            profile_id=profile_id,
            dry_run=dry_run,
        )
    except (AgentRegistryError, AgentOnboardingError) as exc:
        typer.echo(f"Error: {exc}", err=True)
        raise typer.Exit(code=1) from exc

    payload = result.to_payload(Path.cwd())
    if json_output:
        typer.echo(json.dumps(payload, indent=2, sort_keys=True))
        return
    typer.echo(f"status: {payload['status']}")
    typer.echo(f"profile_id: {payload['profile_id']}")
    typer.echo(f"provider: {payload['agent']['provider']}")
    typer.echo(f"model: {payload['agent']['model']}")
    typer.echo(f"runtime: {payload['runtime_contract']['execution_surface']}")
    typer.echo(f"path: {payload['path']}")
    typer.echo(f"dry_run: {str(payload['dry_run']).lower()}")


@agent_app.command("list")
def agent_list(
    json_output: bool = typer.Option(False, "--json", help="Emit machine-readable JSON."),
) -> None:
    """List loaded agents from the registry."""
    try:
        registry = load_agent_registry(Path.cwd())
    except AgentRegistryError as exc:
        typer.echo(f"Error loading agent registry: {exc}", err=True)
        raise typer.Exit(code=1) from exc

    if json_output:
        from devflow.control_room.local_model_worker_pool import registry_json_payload

        typer.echo(json.dumps(registry_json_payload(Path.cwd()), indent=2, sort_keys=True))
        return

    agents = registry.agents
    if not agents:
        typer.echo("No agents defined in registry.")
        return

    typer.echo(f"{'Agent':<42} {'Provider':<10} {'Model':<34} {'Role':<30} {'Mode':<14} {'Hermes':<8} {'Enabled':<8}")
    typer.echo("-" * 155)
    for agent_id in sorted(agents.keys()):
        agent = agents[agent_id]
        enabled_str = "yes" if agent.enabled else "no"
        hermes_str = "yes" if agent.hermes_delegable else "no"
        contract = agent_runtime_contract(Path.cwd(), agent)
        typer.echo(
            f"{agent.id:<42} {agent.provider:<10} {agent.model:<34} {agent.role:<30} {agent.default_mode:<14} {hermes_str:<8} {enabled_str:<8}"
        )
        typer.echo(_runtime_status_line(contract, include_refusal=False))


@agent_app.command("show")
def agent_show(
    agent_id: str,
    json_output: bool = typer.Option(False, "--json", help="Emit machine-readable JSON."),
) -> None:
    """Show details for a specific agent."""
    try:
        registry = load_agent_registry(Path.cwd())
    except AgentRegistryError as exc:
        typer.echo(f"Error loading agent registry: {exc}", err=True)
        raise typer.Exit(code=1) from exc

    try:
        agent = registry.require_agent(agent_id)
    except KeyError as exc:
        typer.echo(str(exc), err=True)
        raise typer.Exit(code=1) from exc

    if json_output:
        from devflow.control_room.local_model_worker_pool import agent_json_payload

        typer.echo(json.dumps(agent_json_payload(Path.cwd(), agent_id), indent=2, sort_keys=True))
        return

    typer.echo(f"agent: {agent.id}")
    typer.echo(f"provider: {agent.provider}")
    typer.echo(f"model: {agent.model}")
    typer.echo(f"adapter: {agent.adapter}")
    typer.echo(f"role: {agent.role}")
    typer.echo(f"tier: {agent.tier}")
    typer.echo(f"default_mode: {agent.default_mode}")
    typer.echo(f"execution_mode: {agent.execution_mode}")
    typer.echo(f"purpose: {agent.purpose or ''}")
    typer.echo(f"workspace: {agent.workspace}")
    typer.echo(f"can_see: {', '.join(agent.can_see) if agent.can_see else 'none'}")
    typer.echo(f"can_touch: {', '.join(agent.can_touch) if agent.can_touch else 'none'}")
    typer.echo(f"cannot_touch: {', '.join(agent.cannot_touch) if agent.cannot_touch else 'none'}")
    _echo_list("allowed_reads", agent.allowed_reads)
    _echo_list("allowed_writes", agent.allowed_writes)
    _echo_list("forbidden_writes", agent.forbidden_writes)
    _echo_list("required_outputs", agent.required_outputs)
    _echo_list("completion_rules", agent.completion_rules)
    typer.echo(f"can_run_shell: {str(agent.can_run_shell).lower()}")
    typer.echo(f"can_use_network: {str(agent.can_use_network).lower()}")
    typer.echo(f"can_promote: {str(agent.can_promote).lower()}")
    typer.echo(f"hermes_delegable: {str(agent.hermes_delegable).lower()}")
    typer.echo(f"enabled: {str(agent.enabled).lower()}")
    _echo_runtime_contract(agent_runtime_contract(Path.cwd(), agent))


@agent_app.command("policy")
def agent_policy(
    json_output: bool = typer.Option(False, "--json", help="Emit machine-readable JSON."),
) -> None:
    """Show local worker-pool enforcement policy."""
    from devflow.control_room.local_model_worker_pool import agent_policy_payload

    payload = agent_policy_payload()
    if json_output:
        typer.echo(json.dumps(payload, indent=2, sort_keys=True))
        return
    typer.echo(f"policy_id: {payload['policy_id']}")
    typer.echo(f"source_of_truth: {payload['source_of_truth']}")
    typer.echo(f"worker_outputs_are: {payload['worker_outputs_are']}")
    _echo_list("execution_gates", payload["execution_gates"])
    _echo_list("forbidden", payload["forbidden"])
    _echo_list("allowed_evidence_outputs", payload["allowed_evidence_outputs"])


@agent_app.command("serial-packet")
def agent_serial_packet(
    phase: str = typer.Option(..., "--phase", help="Serial local-agent phase to packetize."),
    provider: str = typer.Option(..., "--provider", help="Local/runtime provider id, such as ollama."),
    model: str = typer.Option(..., "--model", help="Provider model id for the manual worker launch."),
    allowed_files: list[str] | None = typer.Option(
        None,
        "--allowed-file",
        help="Repo-relative file the local worker may edit. Repeat for each allowed file.",
    ),
    verification_commands: list[str] | None = typer.Option(
        None,
        "--verify",
        help="Verification command for the completion verifier. Repeat for each command.",
    ),
    mission: str | None = typer.Option(None, "--mission", help="Optional packet mission text."),
    run_id: str | None = typer.Option(None, "--run-id", help="Optional stable run id."),
    task_id: str | None = typer.Option(None, "--task-id", help="Optional DevFlow task id."),
    worker_id: str | None = typer.Option(None, "--worker-id", help="Optional intended worker id."),
    runtime: str = typer.Option("manual", "--runtime", help="Intended runtime: manual or hermes-profile."),
    hermes_profile: str | None = typer.Option(
        None, "--hermes-profile", help="Hermes profile id when --runtime hermes-profile."
    ),
    toolsets: list[str] | None = typer.Option(
        None, "--toolset", help="Hermes toolset to record for the packet. Repeat for each toolset."
    ),
) -> None:
    """Write a packet-only serial local-agent run directory without launching a worker."""
    from devflow.control_room.serial_local_agent_run import (
        SerialLocalAgentRunError,
        create_serial_local_agent_run,
    )

    root = Path.cwd()
    try:
        result = create_serial_local_agent_run(
            root,
            phase=phase,
            provider=provider,
            model=model,
            allowed_files=allowed_files or [],
            verification_commands=verification_commands or [],
            mission=mission,
            run_id=run_id,
            task_id=task_id,
            worker_id=worker_id,
            runtime_kind=runtime,
            hermes_profile=hermes_profile,
            toolsets=toolsets or [],
        )
    except SerialLocalAgentRunError as exc:
        typer.echo(f"Error: {exc}", err=True)
        raise typer.Exit(code=1) from exc

    run_dir = relative_path(root, result.run_dir)
    artifacts = result.manifest["artifacts"]
    preflight = result.manifest["preflight"]
    runtime_payload = result.manifest.get("runtime") or {}
    typer.echo(f"run_id: {result.run_id}")
    typer.echo(f"run_dir: {run_dir}")
    typer.echo(f"worker_packet: {run_dir}/{artifacts['worker_packet']}")
    typer.echo(f"preflight: {run_dir}/{artifacts['preflight']}")
    typer.echo(f"completion_verifier: {run_dir}/{artifacts['completion_verifier']}")
    typer.echo(f"runtime_preflight_state: {preflight['state']}")
    typer.echo(f"launch_packet_ready: {str(preflight['launch_packet_ready']).lower()}")
    typer.echo(f"runtime: {runtime_payload.get('kind') or 'manual'}")
    if runtime_payload.get("hermes_profile"):
        typer.echo(f"hermes_profile: {runtime_payload['hermes_profile']}")
    if runtime_payload.get("toolsets"):
        typer.echo(f"toolsets: {', '.join(runtime_payload['toolsets'])}")
    typer.echo("model_launch: false")
    typer.echo("worker_ran: no")
    typer.echo("git_mutation: false")
    if runtime_payload.get("kind") == "hermes-profile":
        launch_target = f"Hermes profile {runtime_payload['hermes_profile']} manually outside DevFlow/browser"
    else:
        launch_target = "one single-flight local worker manually"
    typer.echo(
        "next_safe_manual_launch: review "
        f"{run_dir}/{artifacts['preflight']} and {run_dir}/{artifacts['worker_packet']}; "
        f"if launch_packet_ready=true, launch {launch_target}, "
        "then run completion-verifier.py from the packet directory."
    )


@agent_app.command("hermes-run")
def agent_hermes_run(
    run_id: str,
    profile: str = typer.Option(..., "--profile", help="Hermes profile id to use for this packet."),
    dry_run: bool = typer.Option(False, "--dry-run", help="Preview the Hermes command without launching it."),
    json_output: bool = typer.Option(False, "--json", help="Emit machine-readable JSON."),
    force: bool = typer.Option(
        False,
        "--force",
        help="Allow using a Hermes command for a non-Hermes runtime packet.",
    ),
    hermes_bin: str = typer.Option("hermes", "--hermes-bin", help="Hermes executable path."),
    timeout_seconds: int = typer.Option(900, "--timeout-seconds", min=1, help="Hermes launch timeout."),
) -> None:
    """Validate a serial packet and run or preview a Hermes worker command."""
    from devflow.control_room.hermes_worker_runtime import (
        HermesWorkerRuntimeError,
        dry_run_hermes_worker_runtime,
        run_hermes_worker_runtime,
    )

    try:
        if dry_run:
            payload = dry_run_hermes_worker_runtime(
                Path.cwd(),
                run_id=run_id,
                hermes_profile=profile,
                force=force,
                hermes_executable=hermes_bin,
            )
        else:
            payload = run_hermes_worker_runtime(
                Path.cwd(),
                run_id=run_id,
                hermes_profile=profile,
                force=force,
                hermes_executable=hermes_bin,
                timeout_seconds=timeout_seconds,
            )
    except HermesWorkerRuntimeError as exc:
        typer.echo(f"Error: {exc}", err=True)
        raise typer.Exit(code=1) from exc

    if json_output:
        typer.echo(json.dumps(payload, indent=2, sort_keys=True))
    else:
        _echo_hermes_run_payload(payload)

    exit_code = payload.get("exit_code")
    if not dry_run and exit_code not in (None, 0):
        raise typer.Exit(code=int(exit_code) if isinstance(exit_code, int) else 1)


def _echo_hermes_run_payload(payload: dict[str, object]) -> None:
    typer.echo(f"will_launch_hermes: {str(payload['will_launch_hermes']).lower()}")
    typer.echo(f"run_id: {payload['run_id']}")
    typer.echo(f"packet_path: {payload['packet_path']}")
    typer.echo(f"hermes_profile: {payload['hermes_profile']}")
    typer.echo(f"preflight_state: {payload['preflight_state']}")
    typer.echo(f"launch_allowed: {str(payload.get('launch_allowed')).lower()}")
    if "launch_status" in payload:
        typer.echo(f"launch_status: {payload['launch_status']}")
        typer.echo(f"exit_code: {payload['exit_code']}")
        typer.echo(f"stdout_path: {payload['stdout_path']}")
        typer.echo(f"stderr_path: {payload['stderr_path']}")
        typer.echo(f"hermes_run_path: {payload['hermes_run_path']}")
        typer.echo(f"next_safe_action: {payload['next_safe_action']}")
    typer.echo("command_preview:")
    command_preview = payload.get("command_preview")
    if not isinstance(command_preview, list):
        command_preview = []
    for index, arg in enumerate(command_preview):
        typer.echo(f"  [{index}] {arg}")


@agent_app.command("packet")
def agent_packet(task_id: str, agent_id: str) -> None:
    """Build and print a task's TaskPacket bounded by the target agent's permissions."""
    try:
        registry = load_agent_registry(Path.cwd())
    except AgentRegistryError as exc:
        typer.echo(f"Error loading agent registry: {exc}", err=True)
        raise typer.Exit(code=1) from exc

    try:
        agent = registry.require_agent(agent_id)
    except KeyError as exc:
        typer.echo(str(exc), err=True)
        raise typer.Exit(code=1) from exc

    try:
        packet = build_agent_packet(task_id, agent, root=Path.cwd())
    except KeyError as exc:
        typer.echo(str(exc), err=True)
        raise typer.Exit(code=1) from exc

    packet_json = json.dumps(packet.model_dump(mode="json"), sort_keys=True, indent=2)
    typer.echo(packet_json)


@agent_app.command("context-pack")
def agent_context_pack(
    task_id: str,
    agent_id: str,
    role: str = typer.Option("implementation_worker", "--role", help="Role label for the context pack."),
    json_output: bool = typer.Option(False, "--json", help="Emit machine-readable JSON."),
    project: str | None = typer.Option(None, "--project", help="Write a context pack from a registered project root."),
) -> None:
    """Write a role-scoped context pack derived from a task packet."""
    scope = _resolve_task_project_root(project)
    root = scope.root
    try:
        from devflow.control_room.context_pack import write_context_pack

        result = write_context_pack(root, task_id, agent_id=agent_id, role=role)
    except (KeyError, ValueError) as exc:
        typer.echo(str(exc), err=True)
        raise typer.Exit(code=1) from exc

    payload = {
        "task_id": result.pack.task_id,
        "agent_id": result.pack.agent_id,
        "role": result.pack.role,
        "permission_mode": result.pack.permission_mode,
        "estimated_chars": result.pack.estimated_chars,
        "estimated_tokens": result.pack.estimated_tokens,
        "json_path": relative_path(root, result.json_path),
        "markdown_path": relative_path(root, result.markdown_path),
        "packet_path": relative_path(root, result.packet_path),
    }
    if json_output:
        typer.echo(json.dumps(payload, indent=2, sort_keys=True))
        return

    typer.echo(f"task_id: {payload['task_id']}")
    typer.echo(f"agent_id: {payload['agent_id']}")
    typer.echo(f"role: {payload['role']}")
    typer.echo(f"permission_mode: {payload['permission_mode']}")
    typer.echo(f"estimated_tokens: {payload['estimated_tokens']}")
    typer.echo(f"json_path: {payload['json_path']}")
    typer.echo(f"markdown_path: {payload['markdown_path']}")
    typer.echo(f"packet_path: {payload['packet_path']}")


@agent_app.command("evidence")
def agent_evidence(
    task_id: str,
    json_output: bool = typer.Option(False, "--json", help="Emit machine-readable JSON."),
) -> None:
    """Show a derived summary of task-local agent evidence."""
    root = Path.cwd()
    try:
        from devflow.control_room.agent_evidence import summarize_agent_evidence

        summary = summarize_agent_evidence(root, task_id)
    except KeyError as exc:
        typer.echo(str(exc), err=True)
        raise typer.Exit(code=1) from exc

    payload = summary.to_dict()
    if json_output:
        typer.echo(json.dumps(payload, indent=2, sort_keys=True))
        return

    typer.echo(f"task_id: {payload['task_id']}")
    typer.echo(f"has_worker_evidence: {str(payload['has_worker_evidence']).lower()}")
    typer.echo(f"local_model_run_count: {len(payload['local_model_runs'])}")
    typer.echo(f"local_patch_agent_count: {len(payload['local_patch_agents'])}")
    typer.echo(f"manual_result_present: {str(payload['manual_result_present']).lower()}")
    typer.echo(f"next_safe_action: {payload['next_safe_action']}")


@agent_app.command("discover-local")
def agent_discover_local(
    json_output: bool = typer.Option(False, "--json", help="Emit machine-readable JSON."),
) -> None:
    """Discover installed local Ollama models and classify their capabilities."""
    try:
        from devflow.control_room.local_agent_discovery import discover_local_ollama_models

        report = discover_local_ollama_models()
    except Exception as exc:
        typer.echo(f"Error: {exc}", err=True)
        raise typer.Exit(code=1) from exc

    payload = report.to_dict()
    if json_output:
        typer.echo(json.dumps(payload, indent=2, sort_keys=True))
        return

    typer.echo(f"provider: {payload['provider']}")
    typer.echo(f"installed_model_count: {len(payload['installed_models'])}")
    for model in payload["installed_models"]:
        typer.echo(f"- {model['name']} ({model['size']})")
    if payload["errors"]:
        typer.echo("errors:")
        for error in payload["errors"]:
            typer.echo(f"- {error['model']}: {error['error']}")


@agent_app.command("select-local")
def agent_select_local(
    task_id: str,
    role: str = typer.Option("implementation_worker", "--role", help="Role to select a local agent for."),
    json_output: bool = typer.Option(False, "--json", help="Emit machine-readable JSON."),
    project: str | None = typer.Option(None, "--project", help="Write selection evidence under a registered project root."),
) -> None:
    """Rank installed local agents for a role and write selection evidence."""
    scope = _resolve_task_project_root(project)
    root = scope.root
    try:
        from devflow.control_room.local_agent_discovery import (
            discover_local_ollama_models,
            rank_local_agent_candidates,
            selection_payload_with_path,
            write_selected_agent_evidence,
        )

        report = discover_local_ollama_models()
        registry = load_agent_registry(root)
        selection = rank_local_agent_candidates(registry, report.installed_models, role=role)
        selection_path = write_selected_agent_evidence(root, task_id, selection, project_id=scope.project_id)
        payload = selection_payload_with_path(root, task_id, selection, selection_path, project_id=scope.project_id)
    except (AgentRegistryError, FileNotFoundError, ValueError) as exc:
        typer.echo(f"Error: {exc}", err=True)
        raise typer.Exit(code=1) from exc

    if json_output:
        typer.echo(json.dumps(payload, indent=2, sort_keys=True))
    else:
        typer.echo(f"task_id: {project_task_ref(task_id, scope.project_id)}")
        if scope.project_id:
            typer.echo(f"project_root: {root}")
        typer.echo(f"role: {payload['role']}")
        typer.echo(f"status: {payload['status']}")
        typer.echo(f"selected_agent_id: {payload['selected_agent_id'] or 'none'}")
        typer.echo(f"selected_model: {payload['selected_model'] or 'none'}")
        typer.echo(f"selection_path: {payload['selection_path']}")
        if payload["next_command"]:
            typer.echo(f"next: {payload['next_command']}")

    if payload["status"] != "selected":
        raise typer.Exit(code=1)


@agent_app.command("audition")
def agent_audition(
    task_id: str,
    job: str = typer.Option(..., "--job", help="Audition job type, such as review-debug or summary-status."),
    dry_run: bool = typer.Option(False, "--dry-run", help="Plan an audition without calling models."),
    execute: bool = typer.Option(False, "--execute", help="Run selected candidates sequentially through local worker-pool evidence."),
    json_output: bool = typer.Option(False, "--json", help="Emit machine-readable JSON."),
    project: str | None = typer.Option(None, "--project", help="Write audition evidence under a registered project root."),
) -> None:
    """Plan a read-only local model audition for a task."""
    from devflow.control_room.model_audition import (
        ModelAuditionError,
        execute_model_audition,
        write_model_audition_dry_run_plan,
    )

    if dry_run == execute:
        typer.echo("Error: Provide exactly one of --dry-run or --execute.", err=True)
        raise typer.Exit(code=1)

    scope = _resolve_task_project_root(project)
    try:
        payload = (
            execute_model_audition(scope.root, task_id, job, project_id=scope.project_id)
            if execute
            else write_model_audition_dry_run_plan(
                scope.root,
                task_id,
                job,
                project_id=scope.project_id,
            )
        )
    except ModelAuditionError as exc:
        typer.echo(f"Error: {exc}", err=True)
        raise typer.Exit(code=1) from exc

    if json_output:
        typer.echo(json.dumps(payload, indent=2, sort_keys=True))
        return

    typer.echo(f"task_id: {project_task_ref(task_id, scope.project_id)}")
    typer.echo(f"job_type: {payload['job_type']}")
    typer.echo(f"status: {payload['status']}")
    typer.echo(f"audition_id: {payload['audition_id']}")
    typer.echo(f"plan_path: {payload['plan_path']}")
    if payload["dry_run"]:
        typer.echo(f"selected_candidate_count: {len(payload['selected_candidates'])}")
        for candidate in payload["selected_candidates"]:
            typer.echo(f"- {candidate['candidate_alias']}: {candidate['profile_id']} ({candidate['model']})")
        typer.echo("will_call_models: no")
    else:
        typer.echo(f"run_count: {payload['run_count']}")
        typer.echo(f"runs_path: {payload['runs_path']}")
        typer.echo(f"scorecard_path: {payload['scorecard_path']}")
        typer.echo(f"report_path: {payload['report_path']}")
        typer.echo("will_call_models: yes")


@agent_app.command("hyperplane", hidden=True)
def agent_hyperplane(
    task_id: str,
    suite: str = typer.Option(..., "--suite", help="Hyperplane suite id, such as worker-safety."),
    target: str = typer.Option(..., "--target", help="Target under test: control-room or a local model profile id."),
    judge: str = typer.Option(..., "--judge", help="Local model profile used as the Hyperplane judge."),
    dry_run: bool = typer.Option(False, "--dry-run", help="Write a no-model Hyperplane plan."),
    execute: bool = typer.Option(False, "--execute", help="Run Hyperplane sequentially and write task-local evidence."),
    json_output: bool = typer.Option(False, "--json", help="Emit machine-readable JSON."),
    project: str | None = typer.Option(None, "--project", help="Write Hyperplane evidence under a registered project root."),
    depth: int = typer.Option(12, "--depth", min=1, help="Hyperplane depth budget."),
    breadth: int = typer.Option(2, "--breadth", min=1, help="Hyperplane breadth budget."),
    timeout_seconds: int | None = typer.Option(None, "--timeout-seconds", min=1, help="Override local judge timeout."),
    output_budget_tokens: int | None = typer.Option(None, "--output-budget-tokens", min=1, help="Override local judge output budget."),
    allow_self_grading: bool = typer.Option(
        False,
        "--allow-self-grading",
        help="Explicitly allow target and judge to be the same local model profile.",
    ),
) -> None:
    """Quarantined experimental Hyperplane evidence runner."""
    from devflow.control_room.hyperplane_harness import (
        HyperplaneHarnessError,
        execute_hyperplane_run,
        write_hyperplane_dry_run_plan,
    )

    if dry_run == execute:
        typer.echo("Error: Provide exactly one of --dry-run or --execute.", err=True)
        raise typer.Exit(code=1)

    scope = _resolve_task_project_root(project)
    try:
        payload = (
            execute_hyperplane_run(
                scope.root,
                task_id,
                suite,
                target,
                judge,
                project_id=scope.project_id,
                depth=depth,
                breadth=breadth,
                timeout_seconds=timeout_seconds,
                output_budget_tokens=output_budget_tokens,
                allow_self_grading=allow_self_grading,
            )
            if execute
            else write_hyperplane_dry_run_plan(
                scope.root,
                task_id,
                suite,
                target,
                judge,
                project_id=scope.project_id,
                depth=depth,
                breadth=breadth,
                timeout_seconds=timeout_seconds,
                output_budget_tokens=output_budget_tokens,
                allow_self_grading=allow_self_grading,
            )
        )
    except HyperplaneHarnessError as exc:
        typer.echo(f"Error: {exc}", err=True)
        raise typer.Exit(code=1) from exc

    if json_output:
        typer.echo(json.dumps(payload, indent=2, sort_keys=True))
        return

    typer.echo(f"task_id: {project_task_ref(task_id, scope.project_id)}")
    typer.echo(f"suite: {payload['suite']}")
    typer.echo(f"target: {payload['target']}")
    typer.echo(f"judge: {payload['judge']}")
    typer.echo(f"status: {payload['status']}")
    typer.echo(f"run_id: {payload['run_id']}")
    typer.echo(f"run_dir: {payload['run_dir']}")
    typer.echo(f"plan_path: {payload['plan_path']}")
    typer.echo(f"will_call_hyperplane: {str(payload['will_call_hyperplane']).lower()}")
    typer.echo(f"will_call_models: {str(payload['will_call_models']).lower()}")
    if payload.get("summary_path"):
        typer.echo(f"summary_path: {payload['summary_path']}")
    if payload.get("findings_path"):
        typer.echo(f"findings_path: {payload['findings_path']}")
    if payload.get("report_path"):
        typer.echo(f"report_path: {payload['report_path']}")


@agent_app.command("hyperplane-list", hidden=True)
def agent_hyperplane_list(
    task_id: str,
    json_output: bool = typer.Option(False, "--json", help="Emit machine-readable JSON."),
    project: str | None = typer.Option(None, "--project", help="Read Hyperplane evidence from a registered project root."),
) -> None:
    """List task-local Hyperplane evidence runs."""
    from devflow.control_room.hyperplane_harness import list_hyperplane_runs

    scope = _resolve_task_project_root(project)
    payload = list_hyperplane_runs(scope.root, task_id)
    if json_output:
        typer.echo(json.dumps(payload, indent=2, sort_keys=True))
        return
    typer.echo(f"task_id: {project_task_ref(task_id, scope.project_id)}")
    for run in payload["runs"]:
        typer.echo(f"- {run['run_id']}: {run.get('status', 'unknown')} ({run.get('suite') or 'unknown-suite'})")


@agent_app.command("hyperplane-show", hidden=True)
def agent_hyperplane_show(
    task_id: str,
    run_id: str,
    json_output: bool = typer.Option(False, "--json", help="Emit machine-readable JSON."),
    project: str | None = typer.Option(None, "--project", help="Read Hyperplane evidence from a registered project root."),
) -> None:
    """Show a task-local Hyperplane evidence run."""
    from devflow.control_room.hyperplane_harness import HyperplaneHarnessError, show_hyperplane_run

    scope = _resolve_task_project_root(project)
    try:
        payload = show_hyperplane_run(scope.root, task_id, run_id)
    except HyperplaneHarnessError as exc:
        typer.echo(f"Error: {exc}", err=True)
        raise typer.Exit(code=1) from exc
    if json_output:
        typer.echo(json.dumps(payload, indent=2, sort_keys=True))
        return
    summary = payload.get("summary") or {}
    typer.echo(f"task_id: {project_task_ref(task_id, scope.project_id)}")
    typer.echo(f"run_id: {run_id}")
    typer.echo(f"status: {summary.get('status', 'unknown')}")
    typer.echo(f"run_dir: {payload['run_dir']}")
    if payload["missing_files"]:
        typer.echo("missing_files:")
        for item in payload["missing_files"]:
            typer.echo(f"- {item}")



@agent_app.command("advise")
def agent_advise(
    profile_id: str = typer.Option(..., "--profile", help="Remote advisory profile id."),
    task_id: str | None = typer.Option(None, "--task", help="Optional Dev-Flow task id for task-scoped advice."),
    job: str = typer.Option(..., "--job", help="Advisory job: gap-analysis, review, or status."),
    dry_run: bool = typer.Option(False, "--dry-run", help="Build the bounded prompt plan without calling OpenRouter."),
    json_output: bool = typer.Option(False, "--json", help="Emit machine-readable JSON."),
    max_prompt_chars: int = typer.Option(200_000, "--max-prompt-chars", min=1),
) -> None:
    """Write bounded remote advisory evidence through an OpenRouter profile."""
    from devflow.control_room.openrouter_agent import (
        OpenRouterAgentError,
        dry_run_advice,
        run_advice,
    )

    try:
        payload = (
            dry_run_advice(
                root=Path.cwd(),
                profile_id=profile_id,
                task_id=task_id,
                job=job,
                max_prompt_chars=max_prompt_chars,
            )
            if dry_run
            else run_advice(
                root=Path.cwd(),
                profile_id=profile_id,
                task_id=task_id,
                job=job,
                max_prompt_chars=max_prompt_chars,
            )
        )
    except OpenRouterAgentError as exc:
        typer.echo(f"Error: {exc}", err=True)
        raise typer.Exit(code=1) from exc

    if json_output:
        typer.echo(json.dumps(payload, indent=2, sort_keys=True))
    else:
        typer.echo(f"status: {payload['status']}")
        typer.echo(f"profile_id: {payload['profile_id']}")
        typer.echo(f"job: {payload['job']}")
        typer.echo(f"provider: {payload['provider']}")
        typer.echo(f"model: {payload['model']}")
        typer.echo(f"dry_run: {str(payload['dry_run']).lower()}")
        typer.echo(f"evidence_dir: {payload['evidence_dir']}")
        typer.echo(f"will_call_provider: {str(payload['will_call_provider']).lower()}")
        if payload.get("recommendations"):
            typer.echo("recommendations:")
            for recommendation in payload["recommendations"]:
                typer.echo(f"- {recommendation['next_safe_action']}")
        if payload.get("error"):
            typer.echo(f"error: {payload['error']}")
    if payload.get("status") == "failed":
        raise typer.Exit(code=1)


@agent_app.command("propose-patch")
def agent_propose_patch(
    task_id: str = typer.Option(..., "--task", help="Dev-Flow task id for explicit patch proposal evidence."),
    profile_id: str = typer.Option(..., "--profile", help="Patch-proposal profile id."),
    json_output: bool = typer.Option(False, "--json", help="Emit machine-readable JSON."),
    max_prompt_chars: int = typer.Option(200_000, "--max-prompt-chars", min=1),
) -> None:
    """Write explicit remote patch proposal evidence without applying it."""
    from devflow.control_room.openrouter_agent import OpenRouterAgentError, run_patch_proposal

    try:
        payload = run_patch_proposal(
            root=Path.cwd(),
            task_id=task_id,
            profile_id=profile_id,
            max_prompt_chars=max_prompt_chars,
        )
    except OpenRouterAgentError as exc:
        typer.echo(f"Error: {exc}", err=True)
        raise typer.Exit(code=1) from exc

    if json_output:
        typer.echo(json.dumps(payload, indent=2, sort_keys=True))
    else:
        typer.echo(f"status: {payload['status']}")
        typer.echo(f"task_id: {payload['task_id']}")
        typer.echo(f"profile_id: {payload['profile_id']}")
        typer.echo(f"prompt_mode: {payload.get('prompt_mode', 'standard')}")
        typer.echo(f"prompt_chars: {payload.get('prompt_chars', 0)}")
        typer.echo(f"proposal_patch_path: {payload['proposal_patch_path'] or 'none'}")
        typer.echo(f"run_metadata_path: {payload['run_metadata_path']}")
        typer.echo(f"result_path: {payload['result_path']}")
        typer.echo(f"next_safe_action: {payload['next_safe_action']}")
        if payload.get("error"):
            typer.echo(f"error: {payload['error']}")
    if payload.get("status") != "success":
        raise typer.Exit(code=1)


@agent_app.command("ask")
def agent_ask(
    agent_id: str = typer.Argument(..., help="The local agent name."),
    prompt: list[str] = typer.Argument(None, help="The prompt to send."),
    file: str | None = typer.Option(None, "--file", help="File to include."),
    show_paths: bool = typer.Option(False, "--show-paths"),
    no_save: bool = typer.Option(False, "--no-save"),
    allow_disabled: bool = typer.Option(False, "--allow-disabled"),
) -> None:
    """[LEGACY] Ask a local agent a prompt directly."""
    if not prompt:
        typer.echo(
            "Error: prompt is required.\n\n"
            "Try:\n"
            "  df ask \"your prompt\"\n"
            "  qwopus \"your prompt\"\n"
            "  qwopus chat\n"
            "  df quick",
            err=True,
        )
        raise typer.Exit(code=1)
    prompt_text = " ".join(prompt)
    from devflow.control_room.agent_terminal import AgentTerminalRunner
    runner = AgentTerminalRunner(repo_root=Path.cwd(), agent_name=agent_id, allow_disabled=allow_disabled)
    runner.run_one_shot(
        command="ask",
        prompt=prompt_text,
        file_to_include=file,
        no_save=no_save,
        show_paths=show_paths,
    )


@agent_app.command("chat")
def agent_chat(
    agent_id: str = typer.Argument(..., help="The local agent name."),
    no_save: bool = typer.Option(False, "--no-save"),
    allow_disabled: bool = typer.Option(False, "--allow-disabled"),
) -> None:
    """[LEGACY] Start an interactive chat session with a local agent."""
    from devflow.control_room.agent_terminal import AgentTerminalRunner
    runner = AgentTerminalRunner(repo_root=Path.cwd(), agent_name=agent_id, allow_disabled=allow_disabled)
    runner.run_chat(no_save=no_save)


@agent_app.command("run")
def agent_run(
    agent_id: str | None = typer.Argument(None, help="The local agent name for legacy runs, or profile id when --task is set."),
    task_id: str | None = typer.Option(None, "--task", help="Dev-Flow task id for registry-backed local worker-pool runs."),
    profile_id: str | None = typer.Option(None, "--profile", help="Agent registry profile id for local worker-pool runs."),
    dry_run: bool = typer.Option(False, "--dry-run", help="Preview worker-pool run without calling the model or writing evidence."),
    json_output: bool = typer.Option(False, "--json", help="Emit machine-readable JSON for worker-pool runs."),
    base_url: str | None = typer.Option(None, "--base-url", help="Override local OpenAI-compatible base URL for worker-pool runs."),
    timeout_seconds: int | None = typer.Option(None, "--timeout-seconds", min=1, help="Override local model timeout seconds."),
    temperature: float | None = typer.Option(None, "--temperature", min=0.0, max=2.0, help="Local model temperature."),
    max_packet_chars: int = typer.Option(200_000, "--max-packet-chars", help="Capping size of rendered task packet text."),
    prompt: str | None = typer.Option(None, "--prompt"),
    prompt_file: str | None = typer.Option(None, "--prompt-file"),
    stdin: bool = typer.Option(False, "--stdin"),
    file: str | None = typer.Option(None, "--file"),
    show_paths: bool = typer.Option(False, "--show-paths"),
    no_save: bool = typer.Option(False, "--no-save"),
    allow_disabled: bool = typer.Option(False, "--allow-disabled"),
) -> None:
    """[LEGACY] Run a task-less one-shot prompt with a local agent."""
    if task_id is not None or profile_id is not None:
        from devflow.control_room.local_model_worker_pool import (
            LocalModelWorkerPoolError,
            dry_run_local_model_profile,
            run_local_model_profile,
        )

        resolved_profile = profile_id or agent_id
        if task_id is None or resolved_profile is None:
            typer.echo("Error: --task and --profile are required for local worker-pool runs.", err=True)
            raise typer.Exit(code=1)
        try:
            if dry_run:
                payload = dry_run_local_model_profile(
                    root=Path.cwd(),
                    task_id=task_id,
                    profile_id=resolved_profile,
                    max_packet_chars=max_packet_chars,
                )
            else:
                payload = run_local_model_profile(
                    root=Path.cwd(),
                    task_id=task_id,
                    profile_id=resolved_profile,
                    base_url=base_url,
                    timeout_seconds=timeout_seconds,
                    temperature=temperature,
                    max_packet_chars=max_packet_chars,
                )
        except LocalModelWorkerPoolError as exc:
            typer.echo(f"Error: {exc}", err=True)
            raise typer.Exit(code=1) from exc

        if json_output:
            typer.echo(json.dumps(payload, indent=2, sort_keys=True))
        else:
            typer.echo(f"task_id: {payload['task_id']}")
            typer.echo(f"profile_id: {payload['profile_id']}")
            typer.echo(f"model: {payload['model']}")
            typer.echo(f"adapter: {payload['adapter']}")
            typer.echo(f"adapter_maturity: {payload['adapter_maturity']}")
            typer.echo(f"permission_mode: {payload['permission_mode']}")
            typer.echo(f"hermes_delegable: {str(payload['hermes_delegable']).lower()}")
            typer.echo(f"dry_run: {str(payload['dry_run']).lower()}")
            if payload["dry_run"]:
                typer.echo("will_call_model: false")
                _echo_list("safety_warnings", payload["safety_warnings"])
                _echo_list("expected_evidence_outputs", list(payload["expected_evidence_outputs"].values()))
            else:
                typer.echo(f"status: {payload['status']}")
                typer.echo(f"run_id: {payload['run_id']}")
                typer.echo(f"evidence_dir: {payload['evidence_dir']}")
                typer.echo(f"response_path: {payload['response_path']}")
                typer.echo(f"raw_output_path: {payload['raw_output_path']}")
                if payload.get("error_message"):
                    typer.echo(f"error: {payload['error_message']}")
        if not dry_run and payload.get("status") != "success":
            raise typer.Exit(code=1)
        return

    import sys
    prompt_text = ""
    if stdin:
        prompt_text = sys.stdin.read()
    elif prompt_file:
        try:
            prompt_text = Path(prompt_file).read_text(encoding="utf-8")
        except Exception as exc:
            typer.echo(f"Error: Failed to read prompt-file: {exc}", err=True)
            raise typer.Exit(code=1)
    elif prompt:
        prompt_text = prompt
    else:
        typer.echo("Error: One of --prompt, --prompt-file, or --stdin is required.", err=True)
        raise typer.Exit(code=1)

    from devflow.control_room.agent_terminal import AgentTerminalRunner
    runner = AgentTerminalRunner(repo_root=Path.cwd(), agent_name=agent_id, allow_disabled=allow_disabled)
    runner.run_one_shot(
        command="run",
        prompt=prompt_text,
        file_to_include=file,
        no_save=no_save,
        show_paths=show_paths,
    )
