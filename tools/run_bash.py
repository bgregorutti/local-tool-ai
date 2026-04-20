"""Execute a bash command and return its output."""

from __future__ import annotations

import subprocess

SCHEMA: dict = {
    "type": "function",
    "function": {
        "name": "run_bash",
        "description": (
            "Run an arbitrary shell command. "
            "Only use this when no other specific tool covers the task. "
            "Do NOT use for listing directories, reading files, or searching."
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


def run(command: str, timeout: int = 30, working_dir: str | None = None) -> str:
    # NOTE: command validation (allowlist + dangerous patterns) is enforced
    # in tools/registry.py dispatch() — single enforcement point.
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
