#!/usr/bin/env python3
"""Local-only Mini model benchmark with raw evidence capture.

Calls exactly one localhost endpoint. It has no cloud/provider fallback path.
"""
from __future__ import annotations

import argparse
import json
import platform
import subprocess
import sys
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_ENDPOINT = "http://127.0.0.1:8088"
DEFAULT_MODEL = "qwen3.5-9b-mini"


def get_json(url: str, timeout: int = 10) -> tuple[int, dict[str, Any]]:
    req = urllib.request.Request(url, method="GET")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as response:
            return response.status, json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        try:
            payload = json.loads(body)
        except json.JSONDecodeError:
            payload = {"body": body}
        return exc.code, payload


def post_json(url: str, payload: dict[str, Any], timeout: int = 300) -> tuple[int, dict[str, Any], float]:
    req = urllib.request.Request(
        url,
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    started = time.perf_counter()
    try:
        with urllib.request.urlopen(req, timeout=timeout) as response:
            body = response.read().decode("utf-8")
            return response.status, json.loads(body), time.perf_counter() - started
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        try:
            parsed = json.loads(body)
        except json.JSONDecodeError:
            parsed = {"body": body}
        return exc.code, parsed, time.perf_counter() - started


def command_output(command: list[str]) -> str:
    proc = subprocess.run(command, capture_output=True, text=True, timeout=30)
    return (proc.stdout + proc.stderr).strip()


def memory_snapshot() -> dict[str, Any]:
    top = command_output(["top", "-l", "1", "-n", "0"])
    phys = next((line for line in top.splitlines() if line.startswith("PhysMem:")), "")
    vm = next((line for line in top.splitlines() if line.startswith("VM:")), "")
    swap = command_output(["sysctl", "vm.swapusage"])
    pressure = command_output(["memory_pressure"])
    free_line = next((line for line in pressure.splitlines() if "System-wide memory free percentage" in line), "")
    return {"physmem": phys, "vm": vm, "swap": swap, "memory_free_percentage": free_line}


def repository_packet() -> str:
    files = [ROOT / "AGENTS.md", ROOT / "src/devflow/loop/model_router.py"]
    chunks: list[str] = []
    remaining = 9000
    for path in files:
        text = path.read_text(encoding="utf-8")
        excerpt = text[:remaining]
        chunks.append(f"FILE: {path.relative_to(ROOT)}\n{excerpt}")
        remaining -= len(excerpt)
        if remaining <= 0:
            break
    return "\n\n".join(chunks)


def completion_payload(model: str, prompt: str, max_tokens: int, *, json_only: bool = False) -> dict[str, Any]:
    system = "You are a bounded local coding worker. Follow the requested output shape exactly."
    if json_only:
        system += " Return valid JSON only, without Markdown fences or commentary."
    return {
        "model": model,
        "messages": [{"role": "system", "content": system}, {"role": "user", "content": prompt}],
        "temperature": 0.0,
        "max_tokens": max_tokens,
        "chat_template_kwargs": {"enable_thinking": False},
    }


def extract_metrics(response: dict[str, Any], elapsed: float) -> dict[str, Any]:
    raw_usage = response.get("usage")
    usage: dict[str, Any] = raw_usage if isinstance(raw_usage, dict) else {}
    raw_timings = response.get("timings")
    timings: dict[str, Any] = raw_timings if isinstance(raw_timings, dict) else {}
    raw_choices = response.get("choices")
    choice: dict[str, Any] = raw_choices[0] if isinstance(raw_choices, list) and raw_choices and isinstance(raw_choices[0], dict) else {}
    raw_message = choice.get("message")
    message: dict[str, Any] = raw_message if isinstance(raw_message, dict) else {}
    return {
        "elapsed_seconds": round(elapsed, 4),
        "input_tokens": usage.get("prompt_tokens"),
        "output_tokens": usage.get("completion_tokens"),
        "prompt_tokens_per_second": timings.get("prompt_per_second"),
        "generation_tokens_per_second": timings.get("predicted_per_second"),
        "finish_reason": choice.get("finish_reason"),
        "content": message.get("content", ""),
    }


def run_completion(endpoint: str, model: str, prompt: str, max_tokens: int, *, json_only: bool = False) -> dict[str, Any]:
    status, response, elapsed = post_json(
        f"{endpoint}/v1/chat/completions",
        completion_payload(model, prompt, max_tokens, json_only=json_only),
    )
    metrics = extract_metrics(response, elapsed)
    metrics.update({"http_status": status, "memory": memory_snapshot(), "raw_response": response})
    return metrics


def run_devflow_client(endpoint: str, prompt: str) -> dict[str, Any]:
    sys.path.insert(0, str(ROOT / "src"))
    from devflow.loop.execution import LocalModelClient

    started = time.perf_counter()
    client = LocalModelClient(endpoint, timeout=300, model_name=DEFAULT_MODEL)
    content, usage = client.chat(
        messages=[
            {"role": "system", "content": "Reply exactly as requested."},
            {"role": "user", "content": prompt},
        ],
        max_tokens=512,
        temperature=0.0,
    )
    return {
        "elapsed_seconds": round(time.perf_counter() - started, 4),
        "content": content,
        "usage": usage,
        "memory": memory_snapshot(),
    }


def valid_json_content(record: dict[str, Any]) -> bool:
    try:
        parsed = json.loads(record.get("content", ""))
    except (json.JSONDecodeError, TypeError):
        return False
    return isinstance(parsed, dict) and set(parsed) == {"status", "files", "risk"} and parsed["status"] == "ok"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--endpoint", default=DEFAULT_ENDPOINT)
    parser.add_argument("--model", default=DEFAULT_MODEL)
    parser.add_argument("--context", type=int, default=8192)
    parser.add_argument("--idle-seconds", type=int, default=300)
    parser.add_argument("--cache-ram-mib", type=int, default=512)
    parser.add_argument("--output-dir")
    args = parser.parse_args()

    if not args.endpoint.startswith(("http://127.0.0.1:", "http://localhost:")):
        raise SystemExit("Refusing non-local endpoint")

    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    output_dir = Path(args.output_dir) if args.output_dir else ROOT / ".devflow" / "evidence" / "local-model-benchmarks" / stamp
    output_dir.mkdir(parents=True, exist_ok=False)

    evidence: dict[str, Any] = {
        "started_at": datetime.now(timezone.utc).isoformat(),
        "machine": {"platform": platform.platform(), "processor": platform.processor()},
        "endpoint": args.endpoint,
        "model": args.model,
        "context": args.context,
        "parallel": 1,
        "cache_ram_mib": args.cache_ram_mib,
        "initial_memory": memory_snapshot(),
        "tests": {},
    }
    output_path = output_dir / "raw-results.json"

    def persist() -> None:
        output_path.write_text(
            json.dumps(evidence, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )

    persist()

    for test_name, path in (("health", "/health"), ("models", "/v1/models")):
        evidence["tests"][test_name] = []
        for repetition in range(1, 4):
            started = time.perf_counter()
            status, response = get_json(args.endpoint + path)
            evidence["tests"][test_name].append({
                "repetition": repetition,
                "http_status": status,
                "elapsed_seconds": round(time.perf_counter() - started, 4),
                "response": response,
                "memory": memory_snapshot(),
            })
            persist()

    tasks = {
        "tiny_completion": ("Reply with exactly: MINI_BASELINE_OK", 512, False),
        "repository_summary": (
            "Summarize the repository packet below for a supervising engineer. Return four headings: Purpose, Runtime invariant, Risks, Verification. Stay under 450 words.\n\n" + repository_packet(),
            1024,
            False,
        ),
        "json_only": (
            'Return exactly one JSON object with keys "status", "files", and "risk". Set status to "ok", files to ["src/devflow/loop/model_router.py"], and risk to "single-flight".',
            512,
            True,
        ),
    }
    for test_name, (prompt, max_tokens, json_only) in tasks.items():
        evidence["tests"][test_name] = []
        for repetition in range(1, 4):
            record = run_completion(args.endpoint, args.model, prompt, max_tokens, json_only=json_only)
            record["repetition"] = repetition
            if test_name == "json_only":
                record["valid_expected_json"] = valid_json_content(record)
            evidence["tests"][test_name].append(record)
            persist()

    evidence["tests"]["devflow_client"] = []
    for repetition in range(1, 4):
        record = run_devflow_client(args.endpoint, "Reply with exactly: DEVFLOW_CLIENT_OK")
        record["repetition"] = repetition
        evidence["tests"]["devflow_client"].append(record)
        persist()

    evidence["idle_started_at"] = datetime.now(timezone.utc).isoformat()
    evidence["idle_seconds"] = args.idle_seconds
    persist()
    time.sleep(args.idle_seconds)
    evidence["tests"]["post_idle_completion"] = []
    for repetition in range(1, 4):
        record = run_completion(args.endpoint, args.model, "Reply with exactly: MINI_IDLE_OK", 512)
        record["repetition"] = repetition
        evidence["tests"]["post_idle_completion"].append(record)
        persist()

    evidence["finished_at"] = datetime.now(timezone.utc).isoformat()
    evidence["final_memory"] = memory_snapshot()
    persist()
    print(output_path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
