"""Read the contents of a file."""

from __future__ import annotations

from pathlib import Path

SCHEMA: dict = {
    "type": "function",
    "function": {
        "name": "read_file",
        "description": (
            "Read and return the text content of a file. "
            "USE THIS instead of run_bash when the goal is to read or inspect a file. "
            "Optionally restrict to a line range. "
            "Do NOT use run_bash (e.g. cat, head, tail) for this purpose."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "path": {
                    "type": "string",
                    "description": "Absolute or relative path to the file.",
                },
                "start_line": {
                    "type": "integer",
                    "description": "First line to return, 1-indexed (default: 1).",
                },
                "end_line": {
                    "type": "integer",
                    "description": "Last line to return, inclusive (default: all lines).",
                },
            },
            "required": ["path"],
        },
    },
}

MAX_CHARS = 8_000


def run(path: str, start_line: int = 1, end_line: int | None = None) -> str:
    try:
        file_path = Path(path).expanduser().resolve()
        if not file_path.exists():
            return f"Error: '{path}' does not exist."
        if not file_path.is_file():
            return f"Error: '{path}' is not a file."

        text = file_path.read_text(encoding="utf-8", errors="replace")
        lines = text.splitlines(keepends=True)

        start = max(1, start_line) - 1
        end = len(lines) if end_line is None else min(end_line, len(lines))
        selected = "".join(lines[start:end])

        if len(selected) > MAX_CHARS:
            selected = selected[:MAX_CHARS] + f"\n... [truncated at {MAX_CHARS} chars]"

        return selected or "(empty file)"
    except Exception as exc:
        return f"Error: {exc}"
