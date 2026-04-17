"""Execute a bash command and return its output."""

from __future__ import annotations

import subprocess

SCHEMA: dict = {
    "type": "function",
    "function": {
        "name": "run_bash",
        "description": (
            "Execute a shell command and return its stdout and stderr. "
            "Use for tasks like running scripts, checking processes, "
            "or any operation requiring a shell."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "command": {
                    "type": "string",
                    "description": "The bash command to execute.",
                },
                "timeout": {
                    "type": "integer",
                    "description": "Timeout in seconds (default: 30).",
                },
                "working_dir": {
                    "type": "string",
                    "description": "Working directory for the command (default: current dir).",
                },
            },
            "required": ["command"],
        },
    },
}

MAX_OUTPUT_CHARS = 8_000
BLOCKED_PATTERNS = [
    "rm -rf /",
    "mkfs",
    ":(){:|:&};:",  # fork bomb
]


def run(command: str, timeout: int = 30, working_dir: str | None = None) -> str:
    for blocked in BLOCKED_PATTERNS:
        if blocked in command:
            return f"Error: command contains a blocked pattern: '{blocked}'."

    try:
        result = subprocess.run(
            command,
            shell=True,
            capture_output=True,
            text=True,
            timeout=timeout,
            cwd=working_dir,
        )
        output = result.stdout
        if result.stderr:
            output += f"\n[stderr]\n{result.stderr}"
        if result.returncode != 0:
            output += f"\n[exit code: {result.returncode}]"

        if len(output) > MAX_OUTPUT_CHARS:
            output = output[:MAX_OUTPUT_CHARS] + f"\n... [truncated at {MAX_OUTPUT_CHARS} chars]"

        return output.strip() or "(no output)"
    except subprocess.TimeoutExpired:
        return f"Error: command timed out after {timeout}s."
    except Exception as exc:
        return f"Error: {exc}"
