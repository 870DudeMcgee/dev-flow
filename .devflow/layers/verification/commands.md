# Verification Commands

Useful checks for this slice:

```bash
git diff --check
.venv/bin/python -m pytest tests/test_control_room_shell.py -q
```

Optional parse checks may validate YAML, JSON, and JSONL files when local parser dependencies are available.
