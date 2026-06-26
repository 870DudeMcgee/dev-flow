from __future__ import annotations

import json
import sys
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from devflow.control_room.agent_registry import (
    load_agent_registry,
    load_provider_registry,
    AgentRegistryError,
)
from devflow.control_room.project_context import build_project_context_packet

def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()

def _timestamp_str() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")

def resolve_and_include_file(repo_root: Path, file_path_str: str) -> str:
    base_path = Path(file_path_str)
    if base_path.is_absolute():
        path = base_path
    else:
        path = repo_root / base_path

    # Reject path traversal
    try:
        resolved_path = path.resolve()
        resolved_root = repo_root.resolve()
        if resolved_root not in resolved_path.parents and resolved_path != resolved_root:
            raise ValueError(f"Path traversal detected or file is outside repository: {file_path_str}")
    except Exception as exc:
        raise ValueError(f"Invalid path or path traversal: {exc}")

    # Reject .git paths
    parts = resolved_path.relative_to(resolved_root).parts
    if ".git" in parts:
        raise ValueError(f"Access to '.git' is prohibited: {file_path_str}")

    # Reject directories
    if resolved_path.is_dir():
        raise ValueError(f"Directories are not supported: {file_path_str}")

    # Verify existence
    if not resolved_path.is_file():
        raise ValueError(f"File not found: {file_path_str}")

    # Read as UTF-8 text
    try:
        return resolved_path.read_text(encoding="utf-8")
    except UnicodeDecodeError as exc:
        raise ValueError(f"File could not be read as text (UnicodeDecodeError): {exc}")
    except Exception as exc:
        raise ValueError(f"Failed to read file: {exc}")

def _looks_like_missing_model(raw_error: str, model: str, status_code: int) -> bool:
    lowered = raw_error.lower()
    return (
        status_code == 404
        or model.lower() in lowered and ("not found" in lowered or "pull" in lowered or "missing" in lowered)
        or "model" in lowered and ("not found" in lowered or "pull" in lowered)
    )

def _http_error_detail(exc: urllib.error.HTTPError) -> str:
    try:
        body = exc.read().decode("utf-8", errors="replace")
    except Exception:
        body = ""
    prefix = f"HTTP {exc.code} {exc.reason}".strip()
    return f"{prefix}: {body}" if body else prefix

class AgentTerminalRunner:
    def __init__(
        self,
        repo_root: Path,
        agent_name: str = "qwopus-implementer",
        allow_disabled: bool = False,
    ):
        self.repo_root = repo_root.resolve()
        self.agent_name = agent_name
        self.allow_disabled = allow_disabled

        # Load registries
        try:
            self.registry = load_agent_registry(self.repo_root)
        except AgentRegistryError as exc:
            print(f"Error loading agent registry: {exc}", file=sys.stderr)
            sys.exit(1)

        # Refuse unknown agents
        try:
            self.agent = self.registry.require_agent(self.agent_name)
        except KeyError as exc:
            print(f"Error: {exc}", file=sys.stderr)
            sys.exit(1)

        # Refuse disabled agents by default
        if not self.agent.enabled and not self.allow_disabled:
            print(f"Error: Agent '{self.agent_name}' is disabled.", file=sys.stderr)
            sys.exit(1)

        # Refuse non-Ollama providers
        if self.agent.provider != "ollama":
            print(
                f"Error: Provider '{self.agent.provider}' is not supported by Dev-Flow local commands. "
                "Only local Ollama agents are supported in this mode.",
                file=sys.stderr,
            )
            sys.exit(1)

        # Resolve provider details
        try:
            providers = load_provider_registry(self.repo_root)
            self.provider_def = providers.require_provider(self.agent.provider)
            self.base_url = self.provider_def.base_url or "http://127.0.0.1:11434"
        except Exception:
            self.base_url = "http://127.0.0.1:11434"

        self.model = self.agent.model

    def _call_ollama_api(self, endpoint: str, payload: dict[str, Any]) -> dict[str, Any]:
        url = f"{self.base_url.rstrip('/')}{endpoint}"
        req = urllib.request.Request(
            url,
            data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        # Timeout defaults to 120s for interactive commands unless provider config specifies otherwise
        timeout = 120
        if hasattr(self, "provider_def") and self.provider_def and self.provider_def.default_timeout_seconds:
            timeout = self.provider_def.default_timeout_seconds

        try:
            with urllib.request.urlopen(req, timeout=timeout) as response:
                return json.loads(response.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            raw_error = _http_error_detail(exc)
            if _looks_like_missing_model(raw_error, self.model, exc.code):
                print(f"\nError: Model '{self.model}' is missing.\n", file=sys.stderr)
                print(f"Install it with:\nollama pull {self.model}", file=sys.stderr)
            else:
                print(f"\nError: Ollama HTTP request failed at configured local URL {self.base_url}.", file=sys.stderr)
                print(f"Raw Ollama error: {raw_error}", file=sys.stderr)
            sys.exit(1)
        except urllib.error.URLError:
            print(f"\nError: Ollama could not be reached at {self.base_url}.\n", file=sys.stderr)
            print("Start Ollama and retry:\nollama serve", file=sys.stderr)
            sys.exit(1)
        except Exception as exc:
            print(f"\nError: Ollama execution encountered an exception: {exc}", file=sys.stderr)
            sys.exit(1)

    def run_one_shot(
        self,
        command: str,  # "ask" or "run"
        prompt: str,
        file_to_include: str | None = None,
        no_save: bool = False,
        show_paths: bool = False,
        include_project: bool = False,
    ) -> None:
        started_at = _utc_now_iso()

        # Handle project context
        final_prompt = prompt
        if include_project:
            try:
                packet = build_project_context_packet(self.repo_root)
                header = "---\nProject context: DevFlow repository\n---"
                if packet.startswith("---") and "Project context: DevFlow repository" in packet.splitlines()[:3]:
                    final_prompt = f"{prompt}\n\n{packet}"
                else:
                    final_prompt = f"{prompt}\n\n{header}\n\n{packet}"
            except Exception as exc:
                print(f"Error: could not build project context: {exc}", file=sys.stderr)
                sys.exit(1)

        # Handle file inclusion
        if file_to_include:
            try:
                content = resolve_and_include_file(self.repo_root, file_to_include)
                # Keep file path relative for display in the heading
                try:
                    rel_path = str(Path(file_to_include).resolve().relative_to(self.repo_root))
                except Exception:
                    rel_path = file_to_include

                if include_project:
                    final_prompt = f"{final_prompt}\n\n---\nIncluded file: {rel_path}\n---\n\n{content}"
                else:
                    final_prompt = f"{prompt}\n\n---\n\n## Included file: {rel_path}\n\n{content}"
            except ValueError as exc:
                print(f"Error: {exc}", file=sys.stderr)
                sys.exit(1)

        # Call model
        payload = {
            "model": self.model,
            "prompt": final_prompt,
            "stream": False,
        }
        res = self._call_ollama_api("/api/generate", payload)
        response_text = res.get("response", "")

        completed_at = _utc_now_iso()

        # Print model response by default
        print(response_text)

        # Handle evidence saving
        saved = False
        prompt_rel = None
        response_rel = None
        run_rel = None

        if not no_save:
            timestamp = _timestamp_str()
            run_dir_name = f"{timestamp}-{self.agent_name}"
            run_dir = self.repo_root / ".devflow" / "agent-runs" / run_dir_name
            try:
                run_dir.mkdir(parents=True, exist_ok=True)
                prompt_file = run_dir / "prompt.md"
                response_file = run_dir / "response.md"
                run_file = run_dir / "run.json"

                prompt_file.write_text(final_prompt, encoding="utf-8")
                response_file.write_text(response_text, encoding="utf-8")

                run_meta = {
                    "schema_version": 1,
                    "command": command,
                    "agent_name": self.agent_name,
                    "provider": self.agent.provider,
                    "model": self.model,
                    "adapter": self.agent.adapter,
                    "started_at": started_at,
                    "completed_at": completed_at,
                    "status": "success",
                    "exit_code": 0,
                    "saved": True,
                    "prompt_path": str(prompt_file.relative_to(self.repo_root)),
                    "response_path": str(response_file.relative_to(self.repo_root)),
                    "project_context_included": include_project,
                }
                run_file.write_text(json.dumps(run_meta, indent=2, sort_keys=True) + "\n", encoding="utf-8")
                saved = True

                prompt_rel = f".devflow/agent-runs/{run_dir_name}/prompt.md"
                response_rel = f".devflow/agent-runs/{run_dir_name}/response.md"
                run_rel = f".devflow/agent-runs/{run_dir_name}/run.json"
            except Exception as exc:
                print(f"Warning: Failed to save evidence artifacts: {exc}", file=sys.stderr)

        if show_paths:
            if no_save:
                print("\nSaved: disabled by --no-save")
            elif saved:
                print("\nSaved:")
                print(f"prompt:   {prompt_rel}")
                print(f"response: {response_rel}")
                print(f"run:      {run_rel}")

    def run_chat(self, no_save: bool = False) -> None:
        started_at = _utc_now_iso()

        # Print header
        print("Dev-Flow local agent chat")
        print(f"Agent: {self.agent_name}")
        print(f"Model: {self.model}")
        print("Type /help for commands. Type /exit to quit.\n")

        messages = []
        transcript_lines = []

        transcript_lines.append(f"# Dev-Flow Chat Session with {self.agent_name}")
        transcript_lines.append(f"Model: {self.model}")
        transcript_lines.append(f"Started: {started_at}\n")

        try:
            while True:
                try:
                    user_input = input("you> ")
                except (KeyboardInterrupt, EOFError):
                    print()  # print newline
                    break

                cleaned = user_input.strip()
                if not cleaned:
                    continue

                if cleaned in ("/exit", "/quit"):
                    break
                elif cleaned == "/help":
                    print("Available commands:")
                    print("  /help - Show this help message.")
                    print("  /exit - Quit the chat session.")
                    print("  /quit - Quit the chat session.\n")
                    continue
                elif cleaned.startswith("/"):
                    print(f"Unknown command '{cleaned}'. Type /help for assistance.\n")
                    continue

                # Add to transcript
                transcript_lines.append(f"### you\n\n{user_input}\n")

                # Add user message to conversation history
                messages.append({"role": "user", "content": user_input})

                # Call API
                print()
                print(f"{self.agent_name}> ", end="", flush=True)

                payload = {
                    "model": self.model,
                    "messages": messages,
                    "stream": False,
                }
                res = self._call_ollama_api("/api/chat", payload)
                response_msg = res.get("message", {})
                response_text = response_msg.get("content", "")

                print(response_text)
                print()

                # Add assistant response to history
                messages.append({"role": "assistant", "content": response_text})
                transcript_lines.append(f"### {self.agent_name}\n\n{response_text}\n")
        finally:
            completed_at = _utc_now_iso()
            # Handle transcript saving
            saved = False
            transcript_rel = None
            run_rel = None

            if not no_save and len(messages) > 0:
                timestamp = _timestamp_str()
                run_dir_name = f"{timestamp}-{self.agent_name}-chat"
                run_dir = self.repo_root / ".devflow" / "agent-runs" / run_dir_name
                try:
                    run_dir.mkdir(parents=True, exist_ok=True)
                    transcript_file = run_dir / "transcript.md"
                    run_file = run_dir / "run.json"

                    transcript_file.write_text("\n".join(transcript_lines) + "\n", encoding="utf-8")

                    run_meta = {
                        "schema_version": 1,
                        "command": "chat",
                        "agent_name": self.agent_name,
                        "provider": self.agent.provider,
                        "model": self.model,
                        "adapter": self.agent.adapter,
                        "started_at": started_at,
                        "completed_at": completed_at,
                        "status": "success",
                        "exit_code": 0,
                        "saved": True,
                        "transcript_path": str(transcript_file.relative_to(self.repo_root)),
                        "message_count": len(messages),
                    }
                    run_file.write_text(json.dumps(run_meta, indent=2, sort_keys=True) + "\n", encoding="utf-8")
                    saved = True

                    transcript_rel = f".devflow/agent-runs/{run_dir_name}/transcript.md"
                    run_rel = f".devflow/agent-runs/{run_dir_name}/run.json"
                except Exception as exc:
                    print(f"Warning: Failed to save chat transcript: {exc}", file=sys.stderr)

            if saved:
                print("Saved:")
                print(f"transcript: {transcript_rel}")
                print(f"run:        {run_rel}")
