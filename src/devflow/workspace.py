from __future__ import annotations

import json
import os

from devflow.runner import DEFAULT_TAXONOMY


def default_config() -> dict:
    return {
        "version": "0.1.0",
        "git": {
            "require_clean_worktree": True,
            "checkpoint_strategy": "branch",
            "branch_prefix": "devflow/task-",
            "auto_commit_on_success": False,
        },
        "verification": {
            "test_command": "auto",
            "lint_command": "auto",
            "typecheck_command": "auto",
        },
        "risk": {
            "default_mode": "review",
            "auto_apply_low_risk": False,
            "require_approval_for_protected_paths": True,
            "protected_paths": [
                ".env",
                ".env.*",
                "**/.env",
                "**/.env.*",
                "**/secrets/**",
                "**/secret/**",
                "**/auth/**",
                "**/payments/**",
                "**/billing/**",
                "**/migrations/**",
                ".github/workflows/**",
                "package-lock.json",
                "pnpm-lock.yaml",
                "yarn.lock",
                "poetry.lock",
                "requirements*.txt",
                "pyproject.toml",
            ],
        },
        "failure_taxonomy": DEFAULT_TAXONOMY,
    }


def load_config() -> dict:
    config_path = os.path.join(".devflow", "config.json")
    if not os.path.exists(config_path):
        return default_config()
    with open(config_path, "r", encoding="utf-8") as handle:
        return json.load(handle)
