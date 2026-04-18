"""Search for files matching a glob or substring pattern under a root directory."""

from __future__ import annotations

import fnmatch
from pathlib import Path

SCHEMA: dict = {
    "type": "function",
    "function": {
        "name": "search_files",
        "description": (
            "Recursively search for files whose names match a glob pattern "
            "under a given directory. "
            "USE THIS instead of run_bash when the goal is to find or locate files. "
            "Do NOT use run_bash (e.g. find, locate, ls -R) for this purpose. "
            "Returns a newline-separated list of matching absolute paths, "
            "or a message when nothing is found."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "root": {
                    "type": "string",
                    "description": "Directory to search in (default: current working directory).",
                },
                "pattern": {
                    "type": "string",
                    "description": "Glob pattern to match filenames, e.g. '*.py' or 'README*'.",
                },
                "max_results": {
                    "type": "integer",
                    "description": "Maximum number of results to return (default: 50).",
                },
            },
            "required": ["pattern"],
        },
    },
}


def run(pattern: str, root: str = ".", max_results: int = 50) -> str:
    try:
        root_path = Path(root).expanduser().resolve()
        if not root_path.is_dir():
            return f"Error: '{root}' is not a directory."

        matches: list[str] = []
        for path in root_path.rglob("*"):
            if path.is_file() and fnmatch.fnmatch(path.name, pattern):
                matches.append(str(path))
                if len(matches) >= max_results:
                    break

        if not matches:
            return f"No files matching '{pattern}' found under '{root_path}'."
        return "\n".join(matches)
    except Exception as exc:
        return f"Error: {exc}"
