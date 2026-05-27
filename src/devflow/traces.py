import os
import json
import uuid
import time
import datetime
import threading
from typing import Dict, List, Any, Optional

# Thread-local storage for active tracing context
_local_context = threading.local()
_write_lock = threading.Lock()

class Span:
    LOG_DIR = os.path.join(".devflow", "logs", "traces")

    def __init__(self, name: str, attributes: Optional[Dict[str, Any]] = None):
        self.name = name
        self.attributes = dict(attributes) if attributes else {}
        self.span_id = uuid.uuid4().hex
        self.parent_span_id: Optional[str] = None
        self.trace_id: Optional[str] = None
        self.start_time: Optional[float] = None
        self.end_time: Optional[float] = None
        self.status = "SUCCESS"
        self.error_message: Optional[str] = None

    def __enter__(self):
        self.start_time = time.time()
        
        # Get or create thread-local context
        if not getattr(_local_context, "active_trace_id", None):
            _local_context.active_trace_id = uuid.uuid4().hex
        if not getattr(_local_context, "span_stack", None):
            _local_context.span_stack = []

        self.trace_id = _local_context.active_trace_id

        # Set parent reference if there is an active span in the stack
        if _local_context.span_stack:
            self.parent_span_id = _local_context.span_stack[-1].span_id

        _local_context.span_stack.append(self)
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.end_time = time.time()
        duration_ms = (self.end_time - self.start_time) * 1000

        # Handle exception tracking
        if exc_type is not None:
            self.status = "ERROR"
            self.error_message = f"{exc_type.__name__}: {str(exc_val)}"

        # Pop from stack
        if getattr(_local_context, "span_stack", None):
            _local_context.span_stack.pop()

        # Build trace record
        record = {
            "name": self.name,
            "span_id": self.span_id,
            "parent_span_id": self.parent_span_id,
            "trace_id": self.trace_id,
            "start_time": datetime.datetime.fromtimestamp(self.start_time).isoformat(),
            "end_time": datetime.datetime.fromtimestamp(self.end_time).isoformat(),
            "duration_ms": duration_ms,
            "attributes": self.attributes,
            "status": self.status,
            "error_message": self.error_message
        }

        # Thread-safe writing to the trace JSON file
        os.makedirs(self.LOG_DIR, exist_ok=True)
        trace_file = os.path.join(self.LOG_DIR, f"{self.trace_id}.json")
        
        with _write_lock:
            spans = []
            if os.path.exists(trace_file):
                try:
                    with open(trace_file, "r", encoding="utf-8") as f:
                        spans = json.load(f)
                except Exception:
                    pass
            spans.append(record)
            with open(trace_file, "w", encoding="utf-8") as f:
                json.dump(spans, f, indent=2)

        # Clear active trace context on thread local if stack is empty
        if not _local_context.span_stack:
            _local_context.active_trace_id = None

        return False  # Do not suppress exceptions

    def set_attribute(self, key: str, value: Any) -> None:
        self.attributes[key] = value

    def record_exception(self, e: Exception) -> None:
        self.status = "ERROR"
        self.error_message = f"{type(e).__name__}: {str(e)}"

def start_span(name: str, attributes: Optional[Dict[str, Any]] = None) -> Span:
    return Span(name, attributes)

def get_active_trace_id() -> Optional[str]:
    return getattr(_local_context, "active_trace_id", None)
