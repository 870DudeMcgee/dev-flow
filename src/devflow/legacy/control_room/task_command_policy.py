from __future__ import annotations

import os
from collections.abc import Mapping


EXPERIMENTAL_ENV_VAR = "DEVFLOW_EXPERIMENTAL"
EXPERIMENTAL_ENABLED_VALUE = "1"


def experimental_command_enabled(env: Mapping[str, str] | None = None) -> bool:
    source = os.environ if env is None else env
    return source.get(EXPERIMENTAL_ENV_VAR) == EXPERIMENTAL_ENABLED_VALUE


def experimental_command_hidden(env: Mapping[str, str] | None = None) -> bool:
    return not experimental_command_enabled(env)


def experimental_refusal_lines(command_name: str) -> list[str]:
    return [
        f"Error: Command '{command_name}' is experimental and restricted to transition planning aids.",
        f"To run this command, please set the environment variable {EXPERIMENTAL_ENV_VAR}=1.",
    ]
