import json
import os
from pathlib import Path
from datetime import datetime, timezone

from devflow.control_room.persistence import get_task
from devflow.control_room.task_packet import build_task_packet, render_task_packet_text
from devflow.control_room.local_model_client import LocalModelClient, LocalModelClientError

def run_local_packet_review(
    task_id: str,
    base_url: str | None = None,
    model: str | None = None,
    timeout_seconds: float | None = None,
    temperature: float | None = None,
    save_prompt: bool = True,
    max_packet_chars: int = 200_000,
    root: Path | None = None,
) -> dict:
    repo_root = (root or Path.cwd()).resolve()
    
    # 1. Load task to verify it exists
    try:
        get_task(repo_root, task_id)
    except KeyError as exc:
        raise ValueError(f"Task '{task_id}' not found.") from exc

    # 2. Build the task packet using existing helper
    packet = build_task_packet(task_id, root=repo_root)

    # 3. Render packet into compact text suitable for model input
    packet_text = render_task_packet_text(packet)
    
    # Check for truncation
    truncation_warning = ""
    if len(packet_text) > max_packet_chars:
        truncation_warning = f"\n\n**[TRUNCATION WARNING]**: The rendered task packet text exceeded the maximum context character limit of {max_packet_chars} and was truncated."
        packet_text = packet_text[:max_packet_chars] + truncation_warning

    # 4. Assemble system and user prompts
    system_prompt = (
        "You are a replaceable local model worker inside DevFlow.\n"
        "DevFlow is the source of truth. You may only use the bounded task packet provided.\n"
        "Do not claim you edited files. Do not claim verification passed.\n"
        "Do not promote. Do not merge. Do not apply patches.\n"
        "If information is missing, ask a clear question instead of guessing.\n"
        "Return concise, structured advisory output for a human or future patch worker."
    )
    
    user_prompt = (
        f"Bounded Task Packet:\n"
        f"```markdown\n"
        f"{packet_text}\n"
        f"```\n\n"
        f"Please provide your local model review in the following requested format:\n"
        f"# Local Model Review\n\n"
        f"## Understanding\n"
        f"...\n\n"
        f"## Proposed Approach\n"
        f"...\n\n"
        f"## Files Likely Affected\n"
        f"- ...\n\n"
        f"## Acceptance Criteria Mapping\n"
        f"- ...\n\n"
        f"## Verification Plan\n"
        f"- ...\n\n"
        f"## Risks / Questions\n"
        f"- ...\n\n"
        f"## Recommended Next DevFlow Command\n"
        f"..."
    )

    # 5. Create deterministic run folder YYYYMMDD-HHMMSS-local
    timestamp_str = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
    run_id = f"{timestamp_str}-{os.urandom(4).hex()}-local"
    
    task_dir = repo_root / ".devflow" / "tasks" / task_id
    runs_dir = task_dir / "local-model-runs" / run_id

    # Initialize client
    client = LocalModelClient(
        base_url=base_url,
        model_id=model,
        timeout_seconds=timeout_seconds,
        temperature=temperature,
    )

    # Validate that LOCAL_MODEL_ID is present before trying to connect
    if not client.model_id:
        raise ValueError(
            "LOCAL_MODEL_ID is missing. Please set the environment variable or pass --model."
        )

    # Create run directory
    runs_dir.mkdir(parents=True, exist_ok=True)

    # Prepare initial status metadata
    run_metadata = {
        "task_id": task_id,
        "run_id": run_id,
        "status": "started",
        "model": client.model_id,
        "base_url": client.base_url,
        "temperature": client.temperature,
        "timeout_seconds": client.timeout,
        "started_at": datetime.now(timezone.utc).isoformat(),
    }

    # Write prompt.md if requested
    if save_prompt:
        prompt_content = f"# System Prompt\n{system_prompt}\n\n# User Prompt\n{user_prompt}\n"
        (runs_dir / "prompt.md").write_text(prompt_content, encoding="utf-8")

    # Write initial request.json
    request_details = {
        "url": client.get_completions_url(),
        "model": client.model_id,
        "temperature": client.temperature,
        "timeout": client.timeout,
        "system_prompt": system_prompt,
        "user_prompt": user_prompt,
    }
    (runs_dir / "request.json").write_text(
        json.dumps(request_details, indent=2, sort_keys=True), encoding="utf-8"
    )

    try:
        # Call the endpoint
        result = client.chat_completion(system_prompt=system_prompt, user_prompt=user_prompt)
        
        # Parse assistant content
        choices = result["response"].get("choices", [])
        if not choices:
            # Empty choice list: write response.json and fail
            (runs_dir / "response.json").write_text(
                json.dumps(result["response"], indent=2, sort_keys=True), encoding="utf-8"
            )
            run_metadata["status"] = "failed"
            run_metadata["error_message"] = "Empty choice list or no completion choices returned."
            run_metadata["finished_at"] = datetime.now(timezone.utc).isoformat()
            (runs_dir / "run.json").write_text(
                json.dumps(run_metadata, indent=2, sort_keys=True), encoding="utf-8"
            )
            (runs_dir / "error.txt").write_text(run_metadata["error_message"], encoding="utf-8")
            raise ValueError(run_metadata["error_message"])

        message = choices[0].get("message", {})
        assistant_content = message.get("content", "").strip()
        
        # Save response.json
        (runs_dir / "response.json").write_text(
            json.dumps(result["response"], indent=2, sort_keys=True), encoding="utf-8"
        )

        if not assistant_content:
            run_metadata["status"] = "failed"
            run_metadata["error_message"] = "Empty assistant content returned."
            run_metadata["finished_at"] = datetime.now(timezone.utc).isoformat()
            (runs_dir / "run.json").write_text(
                json.dumps(run_metadata, indent=2, sort_keys=True), encoding="utf-8"
            )
            (runs_dir / "error.txt").write_text(run_metadata["error_message"], encoding="utf-8")
            raise ValueError(run_metadata["error_message"])

        # Save response.md, proposal.md
        (runs_dir / "response.md").write_text(assistant_content, encoding="utf-8")
        (runs_dir / "proposal.md").write_text(assistant_content, encoding="utf-8")

        # Save success metadata
        run_metadata["status"] = "success"
        run_metadata["finished_at"] = datetime.now(timezone.utc).isoformat()
        (runs_dir / "run.json").write_text(
            json.dumps(run_metadata, indent=2, sort_keys=True), encoding="utf-8"
        )

        return {
            "run_id": run_id,
            "status": "success",
            "evidence_dir": runs_dir,
            "response_path": runs_dir / "response.md",
            "truncation_warning": truncation_warning,
        }

    except LocalModelClientError as exc:
        run_metadata["status"] = "failed"
        run_metadata["error_message"] = str(exc)
        run_metadata["finished_at"] = datetime.now(timezone.utc).isoformat()
        
        # Save error info
        (runs_dir / "run.json").write_text(
            json.dumps(run_metadata, indent=2, sort_keys=True), encoding="utf-8"
        )
        (runs_dir / "error.txt").write_text(run_metadata["error_message"], encoding="utf-8")
        
        if exc.response_body:
            (runs_dir / "response.json").write_text(exc.response_body, encoding="utf-8")

        raise ValueError(run_metadata["error_message"]) from exc
    except Exception as exc:
        run_metadata["status"] = "failed"
        run_metadata["error_message"] = str(exc)
        run_metadata["finished_at"] = datetime.now(timezone.utc).isoformat()
        
        # Save error info
        (runs_dir / "run.json").write_text(
            json.dumps(run_metadata, indent=2, sort_keys=True), encoding="utf-8"
        )
        (runs_dir / "error.txt").write_text(run_metadata["error_message"], encoding="utf-8")
        
        raise ValueError(run_metadata["error_message"]) from exc
