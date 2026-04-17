"""List the contents of a directory."""

from __future__ import annotations

from pathlib import Path

SCHEMA: dict = {
    "type": "function",
    "function": {
        "name": "list_folder",
        "description": (
            "List files and subdirectories inside a folder. "
            "Returns a formatted tree-like listing with file sizes."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "path": {
                    "type": "string",
                    "description": "Path of the folder to list (default: current working directory).",
                },
                "show_hidden": {
                    "type": "boolean",
                    "description": "Whether to include hidden files/dirs (starting with '.'). Default false.",
                },
            },
            "required": [],
        },
    },
}


def run(path: str = ".", show_hidden: bool = False) -> str:
    try:
        folder = Path(path).expanduser().resolve()
        if not folder.exists():
            return f"Error: '{path}' does not exist."
        if not folder.is_dir():
            return f"Error: '{path}' is not a directory."

        entries = sorted(folder.iterdir(), key=lambda p: (p.is_file(), p.name.lower()))
        lines: list[str] = [f"{folder}/"]
        for entry in entries:
            if not show_hidden and entry.name.startswith("."):
                continue
            if entry.is_dir():
                lines.append(f"  {entry.name}/")
            else:
                size = entry.stat().st_size
                lines.append(f"  {entry.name}  ({_human_size(size)})")

        return "\n".join(lines) if lines else f"'{folder}' is empty."
    except Exception as exc:
        return f"Error: {exc}"


def _human_size(n: int) -> str:
    for unit in ("B", "KB", "MB", "GB"):
        if n < 1024:
            return f"{n:.0f} {unit}"
        n /= 1024  # type: ignore[assignment]
    return f"{n:.1f} TB"
