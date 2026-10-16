"""Change the agent's working directory."""

from __future__ import annotations

import os
from pathlib import Path

CHANGED_PREFIX = "Working directory changed to: "

SCHEMA: dict = {
    "type": "function",
    "function": {
        "name": "change_directory",
        "description": (
            "Change the current working directory. Relative paths given to other tools "
            "are resolved against it. Must stay inside the allowed root."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "path": {
                    "type": "string",
                    "description": "Directory to switch to (absolute or relative to the current one).",
                },
            },
            "required": ["path"],
        },
    },
}


def run(path: str) -> str:
    try:
        target = Path(path).expanduser().resolve()
        if not target.exists():
            return f"Error: '{path}' does not exist."
        if not target.is_dir():
            return f"Error: '{path}' is not a directory."
        os.chdir(target)
        return f"{CHANGED_PREFIX}{target}"
    except Exception as exc:  # noqa: BLE001
        return f"Error changing directory: {exc}"
