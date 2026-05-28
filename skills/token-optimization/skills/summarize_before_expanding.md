# Subskill: Summarize Before Expanding

This subskill governs how to consume high-level task state and events before inspecting large raw code structures.

## Guidelines

1. **Lightweight Files First**: When assessing the status of a task, always read the smallest state files first:
   - `task.yaml`: Primary metadata, status (`created`, `running`, `verified`, etc.), and title.
   - `summary.json`: Latest computed dashboard metrics and state projections.
   - `events.jsonl`: Chronological append-only events showing transitions and worker actions.
2. **Log Tailing**: If a shell worker or verification failed, read only the last 20–50 lines of `worker.log` or `verify.log` to get the error message and traceback. Avoid reading the complete log file unless it is very short.
3. **Symbol Maps & Directories**: List directories (using `list_dir` or the nearest folder listing tools) to get their shape before deep-diving into individual file structures.
4. **Step-by-Step Traversal**: Do not load neighboring files unless import errors, compilation issues, or test trackbacks specifically indicate a dependency connection.
