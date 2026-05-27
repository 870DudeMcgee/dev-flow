import unittest
import tempfile
import os
import shutil
import json
import threading
import time
from devflow.traces import Span, get_active_trace_id, start_span

class TestTraces(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        # Patch local logging directory in Span class to use self.tmpdir
        self.old_log_dir = Span.LOG_DIR
        Span.LOG_DIR = os.path.join(self.tmpdir, ".devflow", "logs", "traces")

    def tearDown(self):
        Span.LOG_DIR = self.old_log_dir
        shutil.rmtree(self.tmpdir)

    def test_single_span_lifecycle(self):
        with Span("single_operation", attributes={"attr1": "val1"}) as span:
            self.assertEqual(span.name, "single_operation")
            self.assertEqual(span.attributes["attr1"], "val1")
            self.assertEqual(span.status, "SUCCESS")
            time.sleep(0.01)
        
        # Verify trace file was written
        trace_id = span.trace_id
        trace_file = os.path.join(Span.LOG_DIR, f"{trace_id}.json")
        self.assertTrue(os.path.exists(trace_file))

        with open(trace_file, "r", encoding="utf-8") as handle:
            spans = json.load(handle)
        
        self.assertEqual(len(spans), 1)
        s_data = spans[0]
        self.assertEqual(s_data["name"], "single_operation")
        self.assertEqual(s_data["attributes"]["attr1"], "val1")
        self.assertEqual(s_data["status"], "SUCCESS")
        self.assertGreater(s_data["duration_ms"], 0)
        self.assertIsNone(s_data["parent_span_id"])

    def test_nested_spans(self):
        with Span("root_operation") as root:
            trace_id = root.trace_id
            self.assertEqual(get_active_trace_id(), trace_id)
            
            with Span("child_operation") as child:
                self.assertEqual(child.trace_id, trace_id)
                self.assertEqual(child.parent_span_id, root.span_id)
                
                with Span("grandchild_operation") as grandchild:
                    self.assertEqual(grandchild.trace_id, trace_id)
                    self.assertEqual(grandchild.parent_span_id, child.span_id)

        # Verify trace file containing all 3 spans
        trace_file = os.path.join(Span.LOG_DIR, f"{trace_id}.json")
        with open(trace_file, "r", encoding="utf-8") as handle:
            spans = json.load(handle)

        # Spans are appended as they finish, so grandchild finishes first, then child, then root
        self.assertEqual(len(spans), 3)
        names = [s["name"] for s in spans]
        self.assertEqual(names, ["grandchild_operation", "child_operation", "root_operation"])
        
        # Verify structural linkages
        root_data = spans[2]
        child_data = spans[1]
        grandchild_data = spans[0]

        self.assertIsNone(root_data["parent_span_id"])
        self.assertEqual(child_data["parent_span_id"], root_data["span_id"])
        self.assertEqual(grandchild_data["parent_span_id"], child_data["span_id"])

    def test_exception_recording(self):
        try:
            with Span("failed_operation") as span:
                trace_id = span.trace_id
                raise ValueError("Something went wrong")
        except ValueError:
            pass

        trace_file = os.path.join(Span.LOG_DIR, f"{trace_id}.json")
        with open(trace_file, "r", encoding="utf-8") as handle:
            spans = json.load(handle)

        self.assertEqual(len(spans), 1)
        s_data = spans[0]
        self.assertEqual(s_data["status"], "ERROR")
        self.assertIn("Something went wrong", s_data["error_message"])

    def test_thread_isolation(self):
        def thread_target(event_start, event_done, results):
            with Span("thread_root") as root:
                results["trace_id"] = root.trace_id
                with Span("thread_child") as child:
                    results["parent_span_id"] = child.parent_span_id
                    results["root_span_id"] = root.span_id
            event_done.set()

        results_1 = {}
        results_2 = {}
        event_done_1 = threading.Event()
        event_done_2 = threading.Event()

        t1 = threading.Thread(target=thread_target, args=(None, event_done_1, results_1))
        t2 = threading.Thread(target=thread_target, args=(None, event_done_2, results_2))

        t1.start()
        t2.start()

        event_done_1.wait()
        event_done_2.wait()

        # Verify threads generated completely unique trace IDs
        self.assertNotEqual(results_1["trace_id"], results_2["trace_id"])
        
        # Verify parent span ID linkage isolated correctly per thread
        self.assertEqual(results_1["parent_span_id"], results_1["root_span_id"])
        self.assertEqual(results_2["parent_span_id"], results_2["root_span_id"])

if __name__ == "__main__":
    unittest.main()
