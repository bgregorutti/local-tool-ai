"""Read-only Git tools: git_status, git_log, git_tags, git_show."""

from __future__ import annotations

import re
import subprocess
from pathlib import Path

MAX_OUTPUT_CHARS = 8_000

# Reject refs containing shell metacharacters (defence-in-depth; subprocess arg list already prevents injection)
_SHELL_METACHAR_RE = re.compile(r'[;&|`$<>()\\\n\r]')

SCHEMA_STATUS: dict = {
    "type": "function",
    "function": {
        "name": "git_status",
        "description": (
            "Return the working tree status of a local Git repository. "
            "USE THIS instead of run_bash when the goal is to check the state of a repo. "
            "Do NOT use run_bash (e.g. git status) for this purpose. "
            "Read-only operation — no changes are made to the repository."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "repo_path": {
                    "type": "string",
                    "description": "Absolute path to the Git repository root.",
                },
            },
            "required": ["repo_path"],
        },
    },
}

SCHEMA_DIFF: dict = {
    "type": "function",
    "function": {
        "name": "git_diff",
        "description": (
            "Return changes between the working tree and the index or a tree, changes between the index and a tree, changes between two trees, changes resulting from a merge, changes between two blob objects, or changes between two files on disk. "
            "USE THIS instead of run_bash when the goal is to compare two states of files. "
            "Do NOT use run_bash (e.g. git diff) for this purpose. "
            "Read-only operation — no changes are made to the repository."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "repo_path": {
                    "type": "string",
                    "description": "Absolute path to the Git repository root.",
                },
            },
            "required": ["repo_path"],
        },
    },
}

SCHEMA_LOG: dict = {
    "type": "function",
    "function": {
        "name": "git_log",
        "description": (
            "Return the commit history of a local Git repository. "
            "USE THIS instead of run_bash when the goal is to inspect commits or history. "
            "Do NOT use run_bash (e.g. git log) for this purpose. "
            "Read-only operation — no changes are made to the repository."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "repo_path": {
                    "type": "string",
                    "description": "Absolute path to the Git repository root.",
                },
                "max_count": {
                    "type": "integer",
                    "description": "Maximum number of commits to return. Defaults to 20.",
                    "default": 20,
                },
            },
            "required": ["repo_path"],
        },
    },
}

SCHEMA_TAGS: dict = {
    "type": "function",
    "function": {
        "name": "git_tags",
        "description": (
            "List all tags in a local Git repository. "
            "USE THIS instead of run_bash when the goal is to list or inspect tags. "
            "Do NOT use run_bash (e.g. git tag) for this purpose. "
            "Read-only operation — no changes are made to the repository."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "repo_path": {
                    "type": "string",
                    "description": "Absolute path to the Git repository root.",
                },
            },
            "required": ["repo_path"],
        },
    },
}

SCHEMA_SHOW: dict = {
    "type": "function",
    "function": {
        "name": "git_show",
        "description": (
            "Show the details of a specific Git ref (commit, tag, or branch): metadata and diff. "
            "USE THIS instead of run_bash when the goal is to inspect a specific commit or tag. "
            "Do NOT use run_bash (e.g. git show) for this purpose. "
            "Read-only operation — no changes are made to the repository."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "repo_path": {
                    "type": "string",
                    "description": "Absolute path to the Git repository root.",
                },
                "ref": {
                    "type": "string",
                    "description": "Commit hash, tag name, or branch name to inspect.",
                },
            },
            "required": ["repo_path", "ref"],
        },
    },
}

SCHEMAS: list[dict] = [SCHEMA_STATUS, SCHEMA_LOG, SCHEMA_TAGS, SCHEMA_SHOW, SCHEMA_DIFF]


def _run_git(args: list[str], repo_path: str) -> str:
    path = Path(repo_path).expanduser().resolve()
    if not path.is_dir():
        return f"Error: '{repo_path}' is not a directory."
    try:
        result = subprocess.run(
            ["git", *args],
            cwd=str(path),
            capture_output=True,
            text=True,
        )
        if result.returncode != 0:
            return f"Error: {result.stderr.strip()}"
        output = result.stdout
        if len(output) > MAX_OUTPUT_CHARS:
            output = output[:MAX_OUTPUT_CHARS] + f"\n... [truncated at {MAX_OUTPUT_CHARS} chars]"
        return output.strip() or "(no output)"
    except Exception as exc:
        return f"Error: {exc}"


def run_status(repo_path: str) -> str:
    return _run_git(["status"], repo_path)

def run_diff(repo_path: str) -> str:
    return _run_git(["diff"], repo_path)


def run_log(repo_path: str, max_count: int = 20) -> str:
    return _run_git(["log", f"--max-count={max_count}"], repo_path)


def run_tags(repo_path: str) -> str:
    result = _run_git(["tag", "--list"], repo_path)
    if result == "(no output)":
        return "(no tags)"
    return result


def run_show(repo_path: str, ref: str) -> str:
    if _SHELL_METACHAR_RE.search(ref):
        return "Error: 'ref' contains invalid characters."
    return _run_git(["show", ref], repo_path)
