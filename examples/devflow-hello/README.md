# Devflow Hello Test Project

This is the smallest runnable project for proving the Devflow workflow from an orchestrator lane.

It is intentionally dependency-free:

```bash
python3 examples/devflow-hello/hello.py
python3 examples/devflow-hello/test_hello.py
```

Use it when checking that an agent can create a task packet, claim ownership, make a tiny behavior change, verify it, and report the result without touching the main package.