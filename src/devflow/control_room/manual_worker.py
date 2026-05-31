from __future__ import annotations

import sys
from pathlib import Path

from devflow.control_room.log_sanitizer import latest_visible_log_line
from devflow.control_room.models import WorkerInput, WorkerResult


class ManualWorkerAdapter:
    name = "manual"

    def run(self, worker_input: WorkerInput) -> WorkerResult:
        worker_input.workspace_path.mkdir(parents=True, exist_ok=True)
        worker_input.log_file.parent.mkdir(parents=True, exist_ok=True)

        # Write orienting manual instructions log
        with worker_input.log_file.open("w", encoding="utf-8") as log:
            log.write(f"=== Manual Worker Escalation for Task {worker_input.task_id} ===\n")
            log.write(f"Workspace Path: {worker_input.workspace_path.resolve()}\n")
            log.write(f"Command provided: {' '.join(worker_input.command) if worker_input.command else 'None'}\n\n")
            log.write("Instructions:\n")
            log.write(f"1. Please navigate to the workspace directory: {worker_input.workspace_path.resolve()}\n")
            log.write("2. Apply the necessary changes manually in the workspace.\n")
            log.write(f"3. Document your changes by editing .devflow/tasks/{worker_input.task_id}/result.md.\n")
            log.write("4. Once you have completed the changes, run task verification to test them, e.g.:\n")
            log.write(f"   devflow task verify {worker_input.task_id} -- <verification command>\n\n")
            log.write("Awaiting human manual execution...\n")
            log.flush()

        latest = latest_visible_log_line(worker_input.log_file)

        # Handle interactive terminal vs non-interactive environments
        # We also check a test bypass flag to simplify unit testing of interactive prompts
        is_interactive = sys.stdin.isatty() and not getattr(sys.stdin, "_mocked", False)
        
        if is_interactive:
            print(f"\n[Manual Worker] Escalation active for task '{worker_input.task_id}'.")
            print(f"Workspace path: {worker_input.workspace_path.resolve()}")
            print("Instructions log file has been written.")
            try:
                input(">>> Press [ENTER] once you have completed the manual changes in the workspace...")
            except (KeyboardInterrupt, EOFError):
                print("\n[Manual Worker] Cancelled manual session.")
                return WorkerResult(
                    status="worker_failed",
                    summary="Manual session cancelled by user",
                    exit_code=1,
                    latest_log_line=latest,
                    result_file=worker_input.result_file,
                    log_file=worker_input.log_file,
                )

            return WorkerResult(
                status="complete",
                summary="Manual work completed by user",
                exit_code=0,
                latest_log_line=latest,
                result_file=worker_input.result_file,
                log_file=worker_input.log_file,
            )
        else:
            # Non-interactive / Background runner
            import json
            from devflow.control_room.persistence import timestamp

            event = {
                "timestamp": timestamp(),
                "event": "manual_packet_generated",
                "status": "awaiting_human",
                "summary": "Manual instructions generated. Awaiting human workspace changes.",
            }
            try:
                with worker_input.context_file.open("a", encoding="utf-8") as f:
                    f.write(json.dumps(event) + "\n")
            except Exception:
                pass

            return WorkerResult(
                status="blocked",
                summary="Manual instructions generated. Awaiting human workspace changes.",
                exit_code=0,
                latest_log_line=latest,
                result_file=worker_input.result_file,
                log_file=worker_input.log_file,
            )
