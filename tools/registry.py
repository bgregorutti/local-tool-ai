"""Central registry: aggregates tool schemas and dispatches calls by name."""

from __future__ import annotations

import json

from tools import list_folder, read_file, run_bash, search_files

# All tool schemas in the format expected by the OpenAI /chat/completions API
SCHEMAS: list[dict] = [
    search_files.SCHEMA,
    list_folder.SCHEMA,
    read_file.SCHEMA,
    run_bash.SCHEMA,
]

_HANDLERS: dict[str, callable] = {
    "search_files": search_files.run,
    "list_folder": list_folder.run,
    "read_file": read_file.run,
    "run_bash": run_bash.run,
}


def dispatch(tool_name: str, tool_args: dict | str) -> str:
    """Call the tool identified by *tool_name* with *tool_args*.

    *tool_args* may arrive as a JSON string (model sometimes serialises it).
    Always returns a string suitable for the tool-result message.
    """
    if isinstance(tool_args, str):
        try:
            tool_args = json.loads(tool_args)
        except json.JSONDecodeError as exc:
            return f"Error: could not parse tool arguments as JSON: {exc}"

    handler = _HANDLERS.get(tool_name)
    if handler is None:
        available = ", ".join(_HANDLERS)
        return f"Error: unknown tool '{tool_name}'. Available: {available}."

    try:
        return handler(**tool_args)
    except TypeError as exc:
        return f"Error: bad arguments for '{tool_name}': {exc}"
