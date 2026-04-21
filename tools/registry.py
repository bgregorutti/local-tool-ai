"""Central registry: aggregates tool schemas and dispatches calls by name."""

from __future__ import annotations

import json
import logging
import os
import re
import sys
from pathlib import Path

from tools import git, list_folder, read_docx, read_file, read_pdf, run_bash, search_files

# Audit logger — writes to agent_audit.log
_audit_logger = logging.getLogger("agent_audit")
_audit_logger.setLevel(logging.INFO)
_audit_handler = logging.FileHandler("agent_audit.log")
_audit_handler.setFormatter(
    logging.Formatter("%(asctime)s %(message)s", datefmt="%Y-%m-%dT%H:%M:%S")
)
_audit_logger.addHandler(_audit_handler)
_audit_logger.propagate = False

# Tool tier classification
READONLY_TOOLS: frozenset[str] = frozenset({
    "search_files", "list_folder", "read_file", "read_pdf", "read_docx",
    "git_status", "git_log", "git_tags", "git_show", "git_diff"
})

DESTRUCTIVE_TOOLS: frozenset[str] = frozenset(
    {"write_file", "move_file", "delete_file", "run_bash"}
)

_DEFAULT_BASH_ALLOWLIST: frozenset[str] = frozenset({
    "ls", "cat", "head", "tail", "grep", "find", "wc", "pwd",
    "date", "uname", "which", "file", "stat", "du", "df",
    "python", "python3", "sort", "uniq", "cut", "awk",
    "sed", "jq", "tar", "zip", "unzip", "touch",
    "mkdir", "cp", "mv", "diff"
})

# Dangerous flag patterns still blocked even for allowed commands
BASH_DANGEROUS_PATTERNS: list[str] = [
    r"rm\s+-rf\s+/",
    r"rm\s+-r\s+-f\s+/",
    r"rm\s+--recursive\s+--force\s+/",
    r":\s*\(\)\s*\{.*\}",      # fork bomb
    r"curl.*\|\s*(sh|bash)",    # remote code execution
    r"wget.*\|\s*(sh|bash)",
    r">\s*/dev/sd",
    r"mkfs\.",
    r"dd\s+if=",
]


def _get_bash_allowlist() -> frozenset[str]:
    """Return the bash command allowlist, configurable via BASH_ALLOWLIST env var."""
    custom = os.environ.get("BASH_ALLOWLIST", "").strip()
    if custom:
        return frozenset(c.strip() for c in custom.split(",") if c.strip())
    return _DEFAULT_BASH_ALLOWLIST

# Sensitive paths that are always denied regardless of ALLOWED_ROOT
SENSITIVE_PATHS: list[Path] = [
    Path(p).expanduser().resolve()
    for p in [
        "~/.ssh",
        "~/.gnupg",
        "~/.gpg",
        "~/.aws",
        "~/.config/gh",
        "~/.config/gcloud",
        "~/.azure",
        "~/.kube",
        "~/.docker/config.json",
        "~/.netrc",
        "~/.npmrc",
        "~/.pypirc",
        "~/.gem/credentials",
        "~/.config/git/credentials",
        "~/.git-credentials",
        "~/.zshrc",
        "~/.zsh_history",
        "~/.zsh_sessions",
        "~/.bashrc",
        "~/.bash_profile"
    ]
]

# Maps tool name → the argument that carries a filesystem path
_PATH_ARG: dict[str, str] = {
    "search_files": "root",
    "list_folder": "path",
    "read_file": "path",
    "git_status": "repo_path",
    "git_log": "repo_path",
    "git_tags": "repo_path",
    "git_show": "repo_path",
    "git_diff": "repo_path",
    "read_pdf": "file_path",
    "read_docx": "file_path",
}

READONLY_SCHEMAS: list[dict] = [
    search_files.SCHEMA,
    list_folder.SCHEMA,
    read_file.SCHEMA,
    *git.SCHEMAS,
    read_pdf.SCHEMA,
    read_docx.SCHEMA,
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
    "read_pdf": read_pdf.run,
    "read_docx": read_docx.run,
    "run_bash": run_bash.run,
    "git_status": git.run_status,
    "git_log": git.run_log,
    "git_tags": git.run_tags,
    "git_show": git.run_show,
    "git_diff": git.run_diff
}


def get_schemas(safe_mode: bool = False, bash_enabled: bool = False) -> list[dict]:
    """Return schemas to send to the model.

    safe_mode=True  → read-only tools only (all destructive tools removed)
    bash_enabled=False → run_bash excluded; other destructive tools kept
    """
    if safe_mode:
        return READONLY_SCHEMAS
    if not bash_enabled:
        return [s for s in SCHEMAS if s is not run_bash.SCHEMA]
    return SCHEMAS


def _allowed_root_is_explicit() -> bool:
    """Return True if the user explicitly set ALLOWED_ROOT."""
    return bool(os.environ.get("ALLOWED_ROOT", "").strip())


def _get_allowed_root() -> Path:
    """Return the allowed root directory.

    Falls back to cwd if ALLOWED_ROOT is not explicitly set.
    """
    val = os.environ.get("ALLOWED_ROOT", "").strip()
    if not val:
        return Path.cwd()
    return Path(val).expanduser().resolve()


def _check_path_allowlist(tool_name: str, tool_args: dict) -> str | None:
    """Return an error string if the tool's path argument is outside ALLOWED_ROOT."""
    allowed_root = _get_allowed_root()

    path_arg = _PATH_ARG.get(tool_name)
    if path_arg is None:
        return None

    raw_path = tool_args.get(path_arg, ".")
    target = Path(raw_path).expanduser().resolve()

    # Always deny sensitive paths
    for sensitive in SENSITIVE_PATHS:
        if target == sensitive or target.is_relative_to(sensitive):
            return "Error: access to sensitive path is denied."

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


def _check_bash_command(command: str) -> str | None:
    """Return an error string if the command is not allowed.

    Two layers:
    1. Allowlist: extract the first token (base command) and check against permitted commands.
    2. Dangerous patterns: block known-dangerous flag combinations even on allowed commands.
    """
    # Extract first token (the base command), stripping env var assignments
    stripped = command.strip()
    # Skip leading env assignments like VAR=val
    tokens = stripped.split()
    base_cmd = None
    for token in tokens:
        if "=" in token and not token.startswith("-"):
            continue
        base_cmd = token
        break

    if base_cmd is None:
        return "Error: could not determine command to execute."

    # Resolve to basename (handle /usr/bin/ls etc.)
    base_cmd = os.path.basename(base_cmd)

    allowlist = _get_bash_allowlist()
    if base_cmd not in allowlist:
        return f"Error: command '{base_cmd}' is not in the allowed commands list."

    # Second layer: dangerous patterns
    for pattern in BASH_DANGEROUS_PATTERNS:
        if re.search(pattern, command):
            return "Error: command matches a dangerous pattern and was blocked."

    return None


def dispatch(
    tool_name: str,
    tool_args: dict | str,
    *,
    skip_confirmation: bool = False,
    bash_enabled: bool = False,
) -> str:
    """Call the tool identified by *tool_name* with *tool_args*.

    *tool_args* may arrive as a JSON string (model sometimes serialises it).
    Always returns a string suitable for the tool-result message.

    *bash_enabled* must be True for run_bash to execute; otherwise it is
    hard-blocked before any confirmation prompt is shown.

    *skip_confirmation* lets callers that have already obtained user consent
    (e.g. the web UI via an async confirmation flow) bypass the stdin prompt
    while still enforcing the bash blacklist and path allowlist.
    """
    if isinstance(tool_args, str):
        try:
            tool_args = json.loads(tool_args)
        except json.JSONDecodeError as exc:
            return f"Error: could not parse tool arguments as JSON: {exc}"

    # 1. Bash gate — hard block, no prompt, no exception
    if tool_name == "run_bash" and not bash_enabled:
        return "run_bash is disabled. Use a specific tool instead."

    handler = _HANDLERS.get(tool_name)
    if handler is None:
        available = ", ".join(_HANDLERS)
        return f"Error: unknown tool '{tool_name}'. Available: {available}."

    # Path allowlist check for all filesystem tools
    path_error = _check_path_allowlist(tool_name, tool_args)
    if path_error:
        return path_error

    # 2. Human-in-the-loop confirmation for destructive tools (only reached if bash is enabled)
    if tool_name in DESTRUCTIVE_TOOLS:
        if not skip_confirmation and not _confirm_destructive(tool_name, tool_args):
            return "Action cancelled by user."

        # Bash-specific allowlist + dangerous pattern check (always enforced)
        if tool_name == "run_bash":
            command = tool_args.get("command", "")
            bash_error = _check_bash_command(command)
            if bash_error:
                return bash_error

    # 3. Execute
    args_summary = json.dumps(tool_args, default=str)
    if len(args_summary) > 200:
        args_summary = args_summary[:200] + "…"
    _audit_logger.info("DISPATCH tool=%s args=%s", tool_name, args_summary)
    try:
        result = handler(**tool_args)
        _audit_logger.info(
            "RESULT tool=%s status=ok length=%d", tool_name, len(result)
        )
        return result
    except TypeError as exc:
        _audit_logger.info("RESULT tool=%s status=error error=%s", tool_name, exc)
        return f"Error: bad arguments for '{tool_name}': {exc}"
