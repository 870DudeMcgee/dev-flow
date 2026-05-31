from __future__ import annotations

import os
import json
import subprocess
import urllib.request
import urllib.error
from pathlib import Path

from devflow.control_room.models import WorkerInput, WorkerResult
from devflow.control_room.log_sanitizer import latest_visible_log_line
from devflow.control_room.agent_registry import load_agent_registry, load_provider_registry
from devflow.control_room.context_pack import build_context_pack
from devflow._legacy.agents.schemas import repair_and_parse_json


class OpenAICompatibleWorkerAdapter:
    name = "openai_compatible"

    def run(self, worker_input: WorkerInput) -> WorkerResult:
        worker_input.workspace_path.mkdir(parents=True, exist_ok=True)
        worker_input.log_file.parent.mkdir(parents=True, exist_ok=True)

        # Write header to logs
        with worker_input.log_file.open("w", encoding="utf-8") as log:
            log.write(f"=== OpenAI-Compatible Worker Execution for Task {worker_input.task_id} ===\n")
            log.flush()

        # 1. Resolve agent profile & connections
        agent_id = worker_input.env.get("DEVFLOW_AGENT_ID")
        model = "gpt-4o"
        base_url = "https://api.openai.com/v1"
        timeout = worker_input.timeout_seconds or 300
        api_key = "mock-key"

        if agent_id:
            try:
                registry = load_agent_registry(worker_input.repo_root)
                agent = registry.require_agent(agent_id)
                model = agent.model
                
                providers = load_provider_registry(worker_input.repo_root)
                provider_def = providers.require_provider(agent.provider)
                if provider_def.base_url:
                    base_url = provider_def.base_url
                if provider_def.default_timeout_seconds:
                    timeout = provider_def.default_timeout_seconds
                if provider_def.api_key_env:
                    api_key = os.environ.get(provider_def.api_key_env, "mock-key")
            except Exception as exc:
                with worker_input.log_file.open("a", encoding="utf-8") as log:
                    log.write(f"Warning resolving agent/provider registry: {exc}\n")
                    log.flush()

        # Fallback to default OPENAI_API_KEY environment variable if not resolved/set
        if api_key == "mock-key" or not api_key:
            api_key = os.environ.get("OPENAI_API_KEY", "mock-key")

        # 2. Build or load Context Pack for 'worker' role
        try:
            # Build context pack to get source code contexts
            pack_data = build_context_pack(worker_input.repo_root, worker_input.task_id, "worker")
            context_pack = pack_data.get("context_pack", {})
        except Exception as exc:
            context_pack = {}
            with worker_input.log_file.open("a", encoding="utf-8") as log:
                log.write(f"Warning generating context pack: {exc}\n")
                log.flush()

        # 3. Formulate prompts (System + Prompt)
        # Fetch design tokens & prohibited patterns verbatim to guarantee premium dark glassmorphism styling
        CSS_DESIGN_TOKENS = """\
ACTIVE SITE DESIGN SYSTEM (public/styles.css)
==============================================
:root {
    --bg-dark: #030712;
    --bg-card: rgba(15, 19, 26, 0.4);
    --border-color: rgba(255, 255, 255, 0.08);
    --text-primary: #f8fafc;
    --text-secondary: #94a3b8;
    --accent-indigo: #6366f1;
    --accent-purple: hsl(263, 85%, 65%);
    --accent-indigo-glow: hsl(217, 91%, 60%);
    --accent-green: #10b981;
    --accent-red: #ef4444;
    --font-sans: 'Inter', sans-serif;
    --font-heading: 'Outfit', sans-serif;
    --font-mono: 'JetBrains Mono', monospace;
}
Theme: Dark glassmorphism. Background is near-black (#030712). Cards use
rgba(15,19,26,0.4) with backdrop-filter:blur(20px) and border
rgba(255,255,255,0.08). Primary accent is indigo (#6366f1)."""

        ANTI_PATTERNS = """\
PROHIBITED PATTERNS (automatic BLOCKING finding if any appear in your output):
  ✗ background: #e6f7ff          — light blue, violates dark theme
  ✗ background: white            — violates dark theme
  ✗ background: #fff             — violates dark theme
  ✗ background-color: white      — violates dark theme
  ✗ color: #222                  — dark text on light bg, violates dark theme
  ✗ color: #333                  — same violation
  ✗ border-left: ... solid blue  — unthemed border colour
  ✗ border-left: 4px solid #1890ff — exact violation from previous run
  ✗ <style> tags injected inline  — no inline <style> blocks, use classes
  ✗ style="background:..."        — no inline style attributes for colour
  ✗ style="color:..."             — no inline style attributes for colour
  ✗ Orphaned </div> closing tags  — every <div> must have a matching opener
  ✗ Inter, Roboto, or Arial fonts — use --font-heading / --font-sans / --font-mono
  ✗ Generic SaaS gradients (purple→blue on white) — already have a dark theme"""

        system_instruction = (
            "You are an expert Software Engineer and Frontend Designer. Analyze the task "
            "contract and context and provide code modifications (as a unified diff) in "
            "strict JSON format.\n\n"
            "=== ACTIVE SITE DESIGN SYSTEM ===\n"
            + CSS_DESIGN_TOKENS
            + "\n\n=== WEB APP AESTHETICS & QUALITY PROTOCOLS ===\n"
            "When modifying HTML, CSS, or JS files:\n"
            "1. VISUAL EXCELLENCE: Prioritize stunning, premium dark-mode glassmorphism aesthetics. "
            "Use the design token variables above — never invent raw hex colours or inline styles.\n"
            "2. DESIGN TOKENS: ALL colours MUST use var(--...) CSS variables from the :root block above. "
            "Do NOT use any hardcoded colour values (#e6f7ff, #1890ff, white, #222, etc.).\n"
            "3. STRUCTURAL INTEGRITY & TAG CLEANLINESS: Every opened HTML tag MUST be closed correctly "
            "in the same diff chunk. NO orphaned closing tags, NO tag soup, NO unclosed <div>/<span>.\n"
            "4. NO INLINE STYLES FOR THEME: Do not inject <style> blocks or style=\"...\" attributes "
            "for colours. Use existing CSS classes (.glass, .card, .btn-primary, etc.).\n"
            "5. NO PLACEHOLDERS: Implement complete, functional elements with real UI copy.\n\n"
            "=== ANTI-PATTERN BLACKLIST ===\n"
            + ANTI_PATTERNS
            + "\n\n=== CRITICAL UNIFIED DIFF PROTOCOLS ===\n"
            "1. FORMAT: Your diff must be a standard git unified diff.\n"
            "2. ACCURACY: The surrounding context lines (lines starting with ' ') MUST match "
            "the target files EXACTLY, character-for-character including indentation.\n"
            "3. PATHS: Header paths must match the target files (e.g., --- public/index.html, "
            "+++ public/index.html).\n"
            "4. NO TRUNCATION: Do not truncate code blocks or omit required lines inside diff chunks.\n\n"
            "=== OUTPUT SCHEMA ===\n"
            "Do not return markdown, only output raw JSON matching the diff_result schema:\n"
            "{\n"
            "  \"status\": \"ready\" | \"blocked\" | \"failed\",\n"
            "  \"diff\": \"string (unified diff format)\",\n"
            "  \"touched_paths\": [\"string\"],\n"
            "  \"risk\": \"low\" | \"medium\" | \"high\" | \"critical\",\n"
            "  \"confidence\": float (0.0 to 1.0)\n"
            "}"
        )

        # Build prompt using context pack details
        prompt_lines = [
            f"TASK ID: {worker_input.task_id}",
            f"WORKSPACE: {worker_input.workspace_path.name}",
            "",
            "CONTEXT SOURCES:"
        ]
        
        for item in context_pack.get("sources_metadata", []):
            if item.get("mode") == "full":
                prompt_lines.append(f"--- File: {item['path']} ---")
                prompt_lines.append(item.get("content", ""))
                prompt_lines.append("")

        prompt = "\n".join(prompt_lines)

        # 4. Invoke OpenAI-Compatible API
        url = f"{base_url.rstrip('/')}/chat/completions"
        data = {
            "model": model,
            "messages": [
                {"role": "system", "content": system_instruction},
                {"role": "user", "content": prompt}
            ],
            "temperature": 0.2,
            "response_format": {"type": "json_object"}
        }

        with worker_input.log_file.open("a", encoding="utf-8") as log:
            log.write(f"Connecting to OpenAI-compatible API on {url} (model: {model}, timeout: {timeout}s)...\n")
            log.flush()

        req = urllib.request.Request(
            url,
            data=json.dumps(data).encode("utf-8"),
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {api_key}"
            },
            method="POST"
        )

        try:
            with urllib.request.urlopen(req, timeout=timeout) as response:
                res_body = json.loads(response.read().decode("utf-8"))
                choices = res_body.get("choices", [])
                if not choices:
                    raise ValueError("No choices returned from OpenAI-compatible completion API")
                response_text = choices[0].get("message", {}).get("content", "")
        except urllib.error.URLError as e:
            err_msg = f"Error connecting to OpenAI-compatible agent: {e}"
            with worker_input.log_file.open("a", encoding="utf-8") as log:
                log.write(f"{err_msg}\n")
                log.flush()
            return WorkerResult(
                status="worker_failed",
                summary=err_msg,
                exit_code=1,
                latest_log_line=latest_visible_log_line(worker_input.log_file),
                result_file=worker_input.result_file,
                log_file=worker_input.log_file,
            )
        except Exception as e:
            err_msg = f"OpenAI-compatible execution encountered an exception: {e}"
            with worker_input.log_file.open("a", encoding="utf-8") as log:
                log.write(f"{err_msg}\n")
                log.flush()
            return WorkerResult(
                status="worker_failed",
                summary=err_msg,
                exit_code=1,
                latest_log_line=latest_visible_log_line(worker_input.log_file),
                result_file=worker_input.result_file,
                log_file=worker_input.log_file,
            )

        # 5. Parse and apply patch
        try:
            diff_data = repair_and_parse_json(response_text)
        except Exception as exc:
            err_msg = f"JSON parsing of agent response failed: {exc}"
            with worker_input.log_file.open("a", encoding="utf-8") as log:
                log.write(f"{err_msg}\n")
                log.write(f"Raw Response: {response_text}\n")
                log.flush()
            return WorkerResult(
                status="worker_failed",
                summary=err_msg,
                exit_code=1,
                latest_log_line=latest_visible_log_line(worker_input.log_file),
                result_file=worker_input.result_file,
                log_file=worker_input.log_file,
            )

        status = diff_data.get("status", "failed")
        if status != "ready":
            blocked_reason = diff_data.get("blocked_reason", "Worker indicated blocked/failed state")
            with worker_input.log_file.open("a", encoding="utf-8") as log:
                log.write(f"Worker did not complete successfully. Status: {status}. Reason: {blocked_reason}\n")
                log.flush()
            return WorkerResult(
                status="blocked" if status == "blocked" else "worker_failed",
                summary=blocked_reason,
                exit_code=1,
                latest_log_line=latest_visible_log_line(worker_input.log_file),
                result_file=worker_input.result_file,
                log_file=worker_input.log_file,
            )

        diff_text = diff_data.get("diff", "")
        if not diff_text.strip():
            with worker_input.log_file.open("a", encoding="utf-8") as log:
                log.write("Worker output completed but returned an empty diff.\n")
                log.flush()
            return WorkerResult(
                status="complete",
                summary="Worker completed with empty diff",
                exit_code=0,
                latest_log_line=latest_visible_log_line(worker_input.log_file),
                result_file=worker_input.result_file,
                log_file=worker_input.log_file,
            )

        # Apply patch inside workspace using relative directory from repo root
        rel_workspace = os.path.relpath(worker_input.workspace_path, worker_input.repo_root)
        
        with worker_input.log_file.open("a", encoding="utf-8") as log:
            log.write(f"Applying unified patch inside workspace {rel_workspace}...\n")
            log.flush()

        proc = subprocess.Popen(
            ["git", "apply", f"--directory={rel_workspace}", "--whitespace=nowarn", "-"],
            cwd=worker_input.repo_root,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True
        )
        stdout, stderr = proc.communicate(input=diff_text)

        if proc.returncode != 0:
            err_msg = f"Patch application failed with exit code {proc.returncode}"
            with worker_input.log_file.open("a", encoding="utf-8") as log:
                log.write(f"{err_msg}\n")
                log.write(f"stdout:\n{stdout}\n")
                log.write(f"stderr:\n{stderr}\n")
                log.flush()
            return WorkerResult(
                status="worker_failed",
                summary=err_msg,
                exit_code=proc.returncode,
                latest_log_line=latest_visible_log_line(worker_input.log_file),
                result_file=worker_input.result_file,
                log_file=worker_input.log_file,
            )

        with worker_input.log_file.open("a", encoding="utf-8") as log:
            log.write("Patch applied successfully!\n")
            log.write("Worker completed successfully.\n")
            log.flush()

        return WorkerResult(
            status="complete",
            summary="Worker completed successfully",
            exit_code=0,
            latest_log_line=latest_visible_log_line(worker_input.log_file),
            result_file=worker_input.result_file,
            log_file=worker_input.log_file,
        )
