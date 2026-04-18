"""Central registry: aggregates tool schemas and dispatches calls by name."""

from __future__ import annotations

import json
import os
import re
import sys
from pathlib import Path

from tools import list_folder, read_file, run_bash, search_files

# Tool tier classification
READONLY_TOOLS: frozenset[str] = frozenset({"search_files", "list_folder", "read_file"})
DESTRUCTIVE_TOOLS: frozenset[str] = frozenset(
    {"write_file", "move_file", "delete_file", "run_bash"}
)

BASH_BLACKLIST: list[str] = [
    r"rm\s+-rf",
    r"rm\s+-f",
    r"sudo",
    r"chmod",
    r"chown",
    r"mkfs",
    r"dd\s+if=",
    r":\s*\(\)\s*\{.*\}",  # fork bomb
    r"curl.*\|.*sh",        # remote code execution
    r"wget.*\|.*sh",
    r"> /dev/",
    r"shred",
    r"shutdown",
    r"reboot",
]

# Maps tool name → the argument that carries a filesystem path
_PATH_ARG: dict[str, str] = {
    "search_files": "root",
    "list_folder": "path",
    "read_file": "path",
}

READONLY_SCHEMAS: list[dict] = [
    search_files.SCHEMA,
    list_folder.SCHEMA,
    read_file.SCHEMA,
]

DESTRUCTIVE_SCHEMAS: list[dict] = [
    run_bash.SCHEMA,
]

# All tool schemas in the format expected by the OpenAI /chat/completions API
SCHEMAS: list[dict] = READONLY_SCHEMAS + DESTRUCTIVE_SCHEMAS

_HANDLERS: dict[str, callable] = {
    "search_files": search_files.run,
    "list_folder": list_folder.run,
    "read_file": read_file.run,
    "run_bash": run_bash.run,
}


def get_schemas(safe_mode: bool = False) -> list[dict]:
    """Return schemas to send to the model; omits destructive tools in safe mode."""
    return READONLY_SCHEMAS if safe_mode else SCHEMAS


def _get_allowed_root() -> Path | None:
    val = os.environ.get("ALLOWED_ROOT", "").strip()
    if not val:
        return None
    return Path(val).expanduser().resolve()


def _check_path_allowlist(tool_name: str, tool_args: dict) -> str | None:
    """Return an error string if the tool's path argument is outside ALLOWED_ROOT."""
    allowed_root = _get_allowed_root()
    if allowed_root is None:
        return None

    path_arg = _PATH_ARG.get(tool_name)
    if path_arg is None:
        return None

    raw_path = tool_args.get(path_arg, ".")
    target = Path(raw_path).expanduser().resolve()
    if not target.is_relative_to(allowed_root):
        return "Error: path is outside the allowed working directory."
    return None


def _confirm_destructive(tool_name: str, tool_args: dict) -> bool:
    """Prompt the user for confirmation before running a destructive tool.

    Returns True if the user confirms, False to cancel. Auto-cancels when
    stdin is not a TTY (non-interactive / web mode).
    """
    if not sys.stdin.isatty():
        return False

    args_str = json.dumps(tool_args, indent=2)
    print(f"\nDestructive tool call: {tool_name}")
    print(f"Arguments:\n{args_str}")
    try:
        answer = input("Allow? [y/N] ").strip().lower()
    except EOFError:
        return False
    return answer == "y"


def _check_bash_blacklist(command: str) -> str | None:
    """Return an error string if the command matches a blacklisted pattern."""
    for pattern in BASH_BLACKLIST:
        if re.search(pattern, command):
            return "Error: command matches a blacklisted pattern and was blocked."
    return None


def dispatch(
    tool_name: str,
    tool_args: dict | str,
    *,
    skip_confirmation: bool = False,
) -> str:
    """Call the tool identified by *tool_name* with *tool_args*.

    *tool_args* may arrive as a JSON string (model sometimes serialises it).
    Always returns a string suitable for the tool-result message.

    *skip_confirmation* lets callers that have already obtained user consent
    (e.g. the web UI via an async confirmation flow) bypass the stdin prompt
    while still enforcing the bash blacklist and path allowlist.
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

    # Path allowlist check for all filesystem tools
    path_error = _check_path_allowlist(tool_name, tool_args)
    if path_error:
        return path_error

    # Human-in-the-loop confirmation for destructive tools
    if tool_name in DESTRUCTIVE_TOOLS:
        if not skip_confirmation and not _confirm_destructive(tool_name, tool_args):
            return "Action cancelled by user."

        # Bash-specific blacklist (always enforced, even after confirmation)
        if tool_name == "run_bash":
            command = tool_args.get("command", "")
            blacklist_error = _check_bash_blacklist(command)
            if blacklist_error:
                return blacklist_error

    try:
        return handler(**tool_args)
    except TypeError as exc:
        return f"Error: bad arguments for '{tool_name}': {exc}"
