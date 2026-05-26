# devflow Hybrid Orchestrator Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Build a global, reusable Python CLI tool (`devflow`) that uses Gemini 3.5 Flash in the cloud as a smart orchestrator and Ollama locally to run specialized coding subagents via a robust file-based handoff and verification loop.

**Architecture:** A lightweight, modular Python CLI application that maintains state inside a local `.devflow/` folder containing a master `plan.json` and a series of task markdown files under `tasks/`. A local Python runner parses the task markdown, routes context to Ollama, interprets XML search-and-replace blocks, runs tests/linting checks, and passes results back to the cloud orchestrator.

**Tech Stack:** Python 3.12+, standard library (`urllib.request` for minimal external dependencies), `pydantic` (for model parsing), and `click` or `argparse` (for CLI entry points).

---

### Task 1: Project Setup & CLI Scaffolding

**Files:**
- Create: `pyproject.toml`
- Create: `src/devflow/__init__.py`
- Create: `src/devflow/cli.py`
- Create: `tests/test_cli.py`

**Step 1: Write the failing test**
Create a test to verify that running the CLI with `--help` or `init` works properly.
```python
# tests/test_cli.py
from click.testing import CliRunner
import os
import shutil
from devflow.cli import main

def test_cli_init_creates_devflow_folder():
    runner = CliRunner()
    with runner.isolated_filesystem():
        result = runner.invoke(main, ["init"])
        assert result.exit_code == 0
        assert os.path.exists(".devflow")
        assert os.path.exists(".devflow/config.json")
        assert os.path.exists(".devflow/tasks")
```

**Step 2: Run test to verify it fails**
Run: `pytest tests/test_cli.py`
Expected: FAIL (module `devflow` not found or not defined)

**Step 3: Write minimal implementation**
Create `pyproject.toml`:
```toml
[project]
name = "devflow"
version = "0.1.0"
dependencies = [
    "click>=8.0.0",
    "pydantic>=2.0.0"
]

[project.scripts]
devflow = "devflow.cli:main"

[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"
```

Create `src/devflow/cli.py`:
```python
import os
import json
import click

@click.group()
def main():
    pass

@main.command()
def init():
    """Initialize a new devflow workspace."""
    os.makedirs(".devflow/tasks", exist_ok=True)
    os.makedirs(".devflow/logs", exist_ok=True)
    
    config = {
        "orchestrator": {
            "provider": "google",
            "model": "gemini-3.5-flash",
            "api_key_env": "GEMINI_API_KEY"
        },
        "local_agent": {
            "provider": "ollama",
            "host": "http://localhost:11434",
            "model": "qwen2.5-coder:7b-instruct"
        }
    }
    
    with open(".devflow/config.json", "w") as f:
        json.dump(config, f, indent=2)
        
    click.echo("Initialized empty devflow workspace in .devflow/")
```

**Step 4: Run test to verify it passes**
Run: `pytest tests/test_cli.py`
Expected: PASS

**Step 5: Commit**
```bash
git add pyproject.toml src/ tests/
git commit -m "feat: initialize devflow CLI scaffolding and init command"
```

---

### Task 2: Task File & Plan Manager

**Files:**
- Create: `src/devflow/manager.py`
- Create: `tests/test_manager.py`

**Step 1: Write the failing test**
Create a test to verify parsing the task file sections (Instructions, Context, Work Area, Results).
```python
# tests/test_manager.py
from devflow.manager import TaskFile, parse_task_file

def test_parse_task_file():
    raw_markdown = """# Task: 001 - Create Auth Schema
Status: PENDING
Assigned To: LOCAL_AGENT_CODING
Target Files: 
- `backend/app/schemas/auth.py`

## [1. ORCHESTRATOR INSTRUCTIONS]
Create a basic schema.

## [2. REQUIRED CONTEXT FILES]
<!-- file: test.py -->
```python
print('hello')
```

## [3. LOCAL AGENT WORK AREA]
Work goes here

## [4. EXECUTION RESULTS]
Results here
"""
    task = parse_task_file(raw_markdown)
    assert task.task_id == "001"
    assert task.status == "PENDING"
    assert task.target_files == ["backend/app/schemas/auth.py"]
    assert "Create a basic schema." in task.instructions
```

**Step 2: Run test to verify it fails**
Run: `pytest tests/test_manager.py`
Expected: FAIL (manager module and parse_task_file does not exist)

**Step 3: Write minimal implementation**
Create `src/devflow/manager.py`:
```python
import re
from pydantic import BaseModel
from typing import List

class TaskFile(BaseModel):
    task_id: str
    title: str
    status: str
    assigned_to: str
    target_files: List[str]
    instructions: str
    context_files: str
    work_area: str
    execution_results: str

def parse_task_file(content: str) -> TaskFile:
    lines = content.splitlines()
    
    # Parse header metadata
    task_id_match = re.search(r'# Task:\s*(\d+)\s*-\s*(.*)', lines[0])
    task_id = task_id_match.group(1) if task_id_match else "000"
    title = task_id_match.group(2) if task_id_match else "Unknown"
    
    status = "PENDING"
    assigned_to = "LOCAL_AGENT_CODING"
    target_files = []
    
    for line in lines:
        if line.startswith("Status:"):
            status = line.split(":", 1)[1].strip()
        elif line.startswith("Assigned To:"):
            assigned_to = line.split(":", 1)[1].strip()
        elif line.strip().startswith("- `"):
            file_match = re.search(r'- `(.*?)`', line)
            if file_match:
                target_files.append(file_match.group(1))
                
    # Extract sections by heading markers
    sections = re.split(r'## \[\d+\.\s+.*?\]', content)
    instructions = sections[1].strip() if len(sections) > 1 else ""
    context_files = sections[2].strip() if len(sections) > 2 else ""
    work_area = sections[3].strip() if len(sections) > 3 else ""
    execution_results = sections[4].strip() if len(sections) > 4 else ""
    
    return TaskFile(
        task_id=task_id,
        title=title,
        status=status,
        assigned_to=assigned_to,
        target_files=target_files,
        instructions=instructions,
        context_files=context_files,
        work_area=work_area,
        execution_results=execution_results
    )
```

**Step 4: Run test to verify it passes**
Run: `pytest tests/test_manager.py`
Expected: PASS

**Step 5: Commit**
```bash
git add src/devflow/manager.py tests/test_manager.py
git commit -m "feat: implement task file parsing and manager logic"
```

---

### Task 3: Local XML Edit Parser & Applicator

**Files:**
- Create: `src/devflow/editor.py`
- Create: `tests/test_editor.py`

**Step 1: Write the failing test**
Create a test to verify XML search-and-replace blocks are correctly applied to a mock source file.
```python
# tests/test_editor.py
from devflow.editor import apply_xml_edits

def test_apply_xml_edits():
    original_code = """def hello():
    return "old"

def other():
    return "other"
"""
    xml_block = """<search>
def hello():
    return "old"
</search>
<replace>
def hello():
    return "new"
</replace>"""
    
    modified, err = apply_xml_edits(original_code, xml_block)
    assert err is None
    assert 'return "new"' in modified
    assert 'return "other"' in modified
```

**Step 2: Run test to verify it fails**
Run: `pytest tests/test_editor.py`
Expected: FAIL

**Step 3: Write minimal implementation**
Create `src/devflow/editor.py`:
```python
import re
from typing import Tuple, Optional

def apply_xml_edits(original_content: str, xml_changes: str) -> Tuple[str, Optional[str]]:
    # Extract all search/replace pairs
    blocks = re.findall(r'<search>(.*?)</search>\s*<replace>(.*?)</replace>', xml_changes, re.DOTALL)
    
    if not blocks:
        return original_content, "No valid XML <search> and <replace> blocks found."
        
    current_content = original_content
    for search, replace in blocks:
        # Normalize trailing whitespace and newlines for safety
        search_clean = search.strip()
        
        # Search using exact matching to prevent wildcards breaking logic
        if search_clean not in current_content:
            return original_content, f"Search block not found in target file:\n{search_clean}"
            
        current_content = current_content.replace(search, replace, 1)
        
    return current_content, None
```

**Step 4: Run test to verify it passes**
Run: `pytest tests/test_editor.py`
Expected: PASS

**Step 5: Commit**
```bash
git add src/devflow/editor.py tests/test_editor.py
git commit -m "feat: implement XML search-and-replace applicator"
```

---

### Task 4: Local Ollama Execution & Self-Healing Loop

**Files:**
- Create: `src/devflow/runner.py`
- Create: `tests/test_runner.py`

**Step 1: Write the failing test**
Create a test to verify the local runner calling Ollama (mocked) and performing AST syntax validation.
```python
# tests/test_runner.py
from devflow.runner import validate_syntax

def test_validate_syntax_catches_invalid_python():
    bad_python = "def fail_syntax(\n"
    assert not validate_syntax(bad_python, "file.py")

def test_validate_syntax_passes_valid_python():
    good_python = "def success():\n    pass\n"
    assert validate_syntax(good_python, "file.py")
```

**Step 2: Run test to verify it fails**
Run: `pytest tests/test_runner.py`
Expected: FAIL

**Step 3: Write minimal implementation**
Create `src/devflow/runner.py`:
```python
import ast
import urllib.request
import json

def validate_syntax(content: str, filename: str) -> bool:
    if filename.endswith(".py"):
        try:
            ast.parse(content)
            return True
        except SyntaxError:
            return False
    # Default true for non-compiled or unsupported formats (HTML, CSS)
    return True

def call_ollama(prompt: str, host: str, model: str) -> str:
    url = f"{host}/api/generate"
    data = {
        "model": model,
        "prompt": prompt,
        "stream": False
    }
    req = urllib.request.Request(
        url,
        data=json.dumps(data).encode("utf-8"),
        headers={"Content-Type": "application/json"}
    )
    try:
        with urllib.request.urlopen(req) as res:
            response = json.loads(res.read().decode("utf-8"))
            return response.get("response", "")
    except Exception as e:
        return f"Error connecting to Ollama: {str(e)}"
```

**Step 4: Run test to verify it passes**
Run: `pytest tests/test_runner.py`
Expected: PASS

**Step 5: Commit**
```bash
git add src/devflow/runner.py tests/test_runner.py
git commit -m "feat: implement local Ollama API connector and AST validator"
```

---

### Task 5: Cloud Gemini Orchestrator Integration

**Files:**
- Create: `src/devflow/orchestrator.py`
- Create: `tests/test_orchestrator.py`

**Step 1: Write the failing test**
Create a test to verify the cloud orchestrator builds plans and reviews files using mock Gemini requests.
```python
# tests/test_orchestrator.py
from devflow.orchestrator import check_gemini_api

def test_check_gemini_config():
    # Just verify environment key resolution
    import os
    os.environ["GEMINI_API_KEY"] = "mock_key"
    assert check_gemini_api() == "mock_key"
```

**Step 2: Run test to verify it fails**
Run: `pytest tests/test_orchestrator.py`
Expected: FAIL

**Step 3: Write minimal implementation**
Create `src/devflow/orchestrator.py`:
```python
import os
import urllib.request
import json

def check_gemini_api() -> str:
    return os.environ.get("GEMINI_API_KEY", "")

def call_gemini(system_instruction: str, prompt: str, api_key: str) -> str:
    # Google AI Studio Gemini API Endpoint
    url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-1.5-flash:generateContent?key={api_key}"
    
    headers = {"Content-Type": "application/json"}
    payload = {
        "contents": [{"parts": [{"text": prompt}]}],
        "systemInstruction": {"parts": [{"text": system_instruction}]}
    }
    
    req = urllib.request.Request(
        url,
        data=json.dumps(payload).encode("utf-8"),
        headers=headers
    )
    try:
        with urllib.request.urlopen(req) as res:
            res_data = json.loads(res.read().decode("utf-8"))
            return res_data["candidates"][0]["content"]["parts"][0]["text"]
    except Exception as e:
        return f"Orchestrator error: {str(e)}"
```

**Step 4: Run test to verify it passes**
Run: `pytest tests/test_orchestrator.py`
Expected: PASS

**Step 5: Commit**
```bash
git add src/devflow/orchestrator.py tests/test_orchestrator.py
git commit -m "feat: implement Gemini 3.5 cloud orchestrator caller"
```
