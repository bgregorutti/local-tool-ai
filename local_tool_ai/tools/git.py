"""Read-only Git tools.

Low-level: git_status, git_log, git_tags, git_show, git_diff.
Task-shaped (one call returns everything a small model needs):
git_commit_context, git_range_report, git_release_notes_context.
Also exposes repo_context() for injecting a repo snapshot into the system prompt.
"""

from __future__ import annotations

import fnmatch
import os
import re
import subprocess
from pathlib import Path

MAX_OUTPUT_CHARS = 8_000


def _context_max_chars() -> int:
    """Budget for task-shaped tools, which return richer, pre-structured output."""
    return int(os.environ.get("GIT_CONTEXT_MAX_CHARS", "20000"))


# Reject refs containing shell metacharacters (defence-in-depth; subprocess arg list already prevents injection)
_SHELL_METACHAR_RE = re.compile(r'[;&|`$<>()\\\n\r]')

# Files whose diffs are noise for commit messages / release notes
_NOISE_PATTERNS: tuple[str, ...] = (
    "*.lock", "package-lock.json", "pnpm-lock.yaml", "npm-shrinkwrap.json",
    "*.min.js", "*.min.css", "*.map", "*.svg", "*.ipynb",
)

# Conventional Commits types, in release-notes order
_COMMIT_TYPES: tuple[tuple[str, str], ...] = (
    ("feat", "Features"),
    ("fix", "Bug fixes"),
    ("perf", "Performance"),
    ("refactor", "Refactoring"),
    ("docs", "Documentation"),
    ("test", "Tests"),
    ("build", "Build"),
    ("ci", "CI"),
    ("chore", "Chores"),
)
_CONVENTIONAL_RE = re.compile(r"^(\w+)(\([^)]*\))?(!)?:\s*(.+)$")
_PR_RE = re.compile(r"#(\d+)")

_REPO_PATH_PROP: dict = {
    "type": "string",
    "description": (
        "Path to the Git repository. Optional — omit it to use the current "
        "working directory (recommended)."
    ),
}

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
            "properties": {"repo_path": _REPO_PATH_PROP},
            "required": [],
        },
    },
}

SCHEMA_DIFF: dict = {
    "type": "function",
    "function": {
        "name": "git_diff",
        "description": (
            "Show file changes. Without base/head: unstaged working-tree changes "
            "(or staged changes with staged=true). With base (and optionally head): "
            "changes between two refs, e.g. base='3.0.0', head='3.0.1'. "
            "Output starts with a per-file summary; large diffs are trimmed per file. "
            "For writing a commit message prefer git_commit_context. "
            "Do NOT use run_bash (e.g. git diff) for this purpose. Read-only."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "repo_path": _REPO_PATH_PROP,
                "staged": {
                    "type": "boolean",
                    "description": "Show staged (indexed) changes instead of unstaged ones.",
                    "default": False,
                },
                "base": {
                    "type": "string",
                    "description": "Base ref (commit, tag or branch) to compare from.",
                },
                "head": {
                    "type": "string",
                    "description": "Ref to compare to. Defaults to the working tree.",
                },
                "paths": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Limit the diff to these files or directories.",
                },
                "stat_only": {
                    "type": "boolean",
                    "description": "Only return the per-file summary (files changed, +/- lines).",
                    "default": False,
                },
            },
            "required": [],
        },
    },
}

SCHEMA_LOG: dict = {
    "type": "function",
    "function": {
        "name": "git_log",
        "description": (
            "Return the commit history (hash, date, author, subject, body). "
            "Use revision_range to restrict to a range, e.g. '3.0.0..3.0.1' = commits "
            "after 3.0.0 up to and including 3.0.1. "
            "For release notes between tags prefer git_range_report. "
            "Do NOT use run_bash (e.g. git log) for this purpose. Read-only."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "repo_path": _REPO_PATH_PROP,
                "max_count": {
                    "type": "integer",
                    "description": (
                        "Maximum number of commits to return. Defaults to 20 "
                        "(200 when revision_range is set)."
                    ),
                },
                "revision_range": {
                    "type": "string",
                    "description": (
                        "Range such as 'v1.0..v1.1', 'main..feature' or 'HEAD~10..HEAD'."
                    ),
                },
                "paths": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Only commits touching these files or directories.",
                },
                "no_merges": {
                    "type": "boolean",
                    "description": "Exclude merge commits.",
                    "default": False,
                },
                "with_stat": {
                    "type": "boolean",
                    "description": "Include the list of files changed by each commit.",
                    "default": False,
                },
            },
            "required": [],
        },
    },
}

SCHEMA_TAGS: dict = {
    "type": "function",
    "function": {
        "name": "git_tags",
        "description": (
            "List tags, newest version first, with date, commit and subject. "
            "USE THIS instead of run_bash when the goal is to list or inspect tags. "
            "Do NOT use run_bash (e.g. git tag) for this purpose. Read-only."
        ),
        "parameters": {
            "type": "object",
            "properties": {"repo_path": _REPO_PATH_PROP},
            "required": [],
        },
    },
}

SCHEMA_SHOW: dict = {
    "type": "function",
    "function": {
        "name": "git_show",
        "description": (
            "Show ONE commit (or the commit a tag points to): metadata and its diff. "
            "It does NOT show the history between two tags — use git_range_report for that. "
            "Do NOT use run_bash (e.g. git show) for this purpose. Read-only."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "repo_path": _REPO_PATH_PROP,
                "ref": {
                    "type": "string",
                    "description": "Commit hash, tag name, or branch name to inspect.",
                },
            },
            "required": ["ref"],
        },
    },
}

SCHEMA_COMMIT_CONTEXT: dict = {
    "type": "function",
    "function": {
        "name": "git_commit_context",
        "description": (
            "Collect everything needed to write a commit message in ONE call: branch, "
            "staged and unstaged changes (summary + diff), untracked files, and recent "
            "commit subjects to match the repository's message style. "
            "USE THIS when asked to write or suggest a commit message. Read-only."
        ),
        "parameters": {
            "type": "object",
            "properties": {"repo_path": _REPO_PATH_PROP},
            "required": [],
        },
    },
}

SCHEMA_RANGE_REPORT: dict = {
    "type": "function",
    "function": {
        "name": "git_range_report",
        "description": (
            "Structured summary of all changes between two refs (tags, branches, commits): "
            "dates, authors, diffstat, merged PRs, and every commit grouped by type "
            "(features, fixes, ...) with body and files touched. "
            "USE THIS for release notes, changelogs or 'what changed between X and Y'. Read-only."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "repo_path": _REPO_PATH_PROP,
                "from_ref": {
                    "type": "string",
                    "description": "Older ref, excluded (e.g. '3.0.0').",
                },
                "to_ref": {
                    "type": "string",
                    "description": "Newer ref, included (e.g. '3.0.1'). Defaults to HEAD.",
                },
                "include_diff": {
                    "type": "boolean",
                    "description": "Also append the (trimmed) code diff. Usually not needed.",
                    "default": False,
                },
            },
            "required": ["from_ref"],
        },
    },
}

SCHEMA_RELEASE_NOTES_CONTEXT: dict = {
    "type": "function",
    "function": {
        "name": "git_release_notes_context",
        "description": (
            "Collect release-notes material for several consecutive tags in ONE call. "
            "Tags are sorted by version and a git_range_report is produced for each "
            "consecutive pair, e.g. tags ['3.0.0','3.0.1','3.0.2'] gives "
            "3.0.0→3.0.1 and 3.0.1→3.0.2. Without tags, uses the latest `count` tags. "
            "USE THIS when asked for release notes across multiple versions. Read-only."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "repo_path": _REPO_PATH_PROP,
                "tags": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Tag names (at least two), in any order.",
                },
                "count": {
                    "type": "integer",
                    "description": (
                        "When tags is omitted: how many latest tags to use. Defaults to 3."
                    ),
                    "default": 3,
                },
            },
            "required": [],
        },
    },
}

SCHEMAS: list[dict] = [
    SCHEMA_STATUS,
    SCHEMA_LOG,
    SCHEMA_TAGS,
    SCHEMA_SHOW,
    SCHEMA_DIFF,
    SCHEMA_COMMIT_CONTEXT,
    SCHEMA_RANGE_REPORT,
    SCHEMA_RELEASE_NOTES_CONTEXT,
]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def default_repo_path() -> str:
    """Repo used when the model omits repo_path: ALLOWED_ROOT, else cwd."""
    return os.environ.get("ALLOWED_ROOT", "").strip() or str(Path.cwd())


def _resolve_repo(repo_path: str | None) -> Path:
    return Path(repo_path or default_repo_path()).expanduser().resolve()


def _validate_ref(ref: str, name: str = "ref") -> str | None:
    """Return an error string if *ref* is unsafe. Leading '-' would be parsed as an option."""
    if not ref or _SHELL_METACHAR_RE.search(ref) or ref.startswith("-"):
        return f"Error: '{name}' contains invalid characters."
    return None


def _as_list(value: list[str] | str | None) -> list[str]:
    """Models sometimes send a comma-separated string instead of an array."""
    if value is None:
        return []
    if isinstance(value, str):
        return [v for v in re.split(r"[,\s]+", value) if v]
    return [str(v) for v in value if str(v)]


def _git(args: list[str], repo_path: str | None) -> tuple[bool, str]:
    """Run git and return (ok, stdout-or-error) without truncation."""
    path = _resolve_repo(repo_path)
    if not path.is_dir():
        return False, f"Error: '{repo_path}' is not a directory."
    try:
        result = subprocess.run(
            ["git", "-c", "core.quotepath=off", *args],
            cwd=str(path),
            capture_output=True,
            text=True,
            errors="replace",
        )
    except Exception as exc:
        return False, f"Error: {exc}"
    if result.returncode != 0:
        return False, f"Error: {result.stderr.strip()}"
    return True, result.stdout


def _clip_lines(text: str, width: int = 120) -> str:
    """Shorten each line; some repos put whole paragraphs in commit subjects."""
    return "\n".join(
        line if len(line) <= width else line[: width - 1] + "…"
        for line in text.strip().splitlines()
    )


def _truncate(output: str, max_chars: int = MAX_OUTPUT_CHARS) -> str:
    if len(output) > max_chars:
        output = output[:max_chars] + f"\n... [truncated at {max_chars} chars]"
    return output.strip() or "(no output)"


def _run_git(args: list[str], repo_path: str | None) -> str:
    ok, output = _git(args, repo_path)
    return _truncate(output) if ok else output


def _budget_diff(diff: str, budget: int) -> str:
    """Fit a unified diff into *budget* chars, sharing space fairly between files.

    Lock/generated files are skipped; whatever does not fit is listed by name so
    the model can request it explicitly with git_diff(paths=[...]).
    """
    chunks = [c for c in re.split(r"(?m)^(?=diff --git )", diff) if c.strip()]
    kept: list[str] = []
    skipped_noise: list[str] = []
    omitted: list[str] = []
    remaining = budget
    for i, chunk in enumerate(chunks):
        header = chunk.split("\n", 1)[0]
        m = re.match(r"diff --git a/(.+?) b/(.+)$", header)
        path = m.group(2) if m else header
        if any(fnmatch.fnmatch(Path(path).name, p) for p in _NOISE_PATTERNS):
            skipped_noise.append(path)
            continue
        if remaining < 300:
            omitted.append(path)
            continue
        share = max(800, remaining // (len(chunks) - i))
        if len(chunk) > share:
            cut = chunk[:share].rsplit("\n", 1)[0]
            hidden = chunk[len(cut):].count("\n")
            chunk = cut + f"\n... [{path}: {hidden} more diff lines not shown]\n"
        kept.append(chunk)
        remaining -= len(chunk)
    out = "".join(kept).rstrip()
    if skipped_noise:
        out += "\n[skipped lock/generated files: " + ", ".join(skipped_noise) + "]"
    if omitted:
        out += (
            "\n[diff omitted for lack of space: " + ", ".join(omitted)
            + " — call git_diff with paths=[...] to see them]"
        )
    return out.strip()


# ---------------------------------------------------------------------------
# Low-level tools
# ---------------------------------------------------------------------------

def run_status(repo_path: str | None = None) -> str:
    return _run_git(["status"], repo_path)


def run_diff(
    repo_path: str | None = None,
    staged: bool = False,
    base: str | None = None,
    head: str | None = None,
    paths: list[str] | str | None = None,
    stat_only: bool = False,
) -> str:
    if head and not base:
        return "Error: 'head' requires 'base'."
    refs = [r for r in (base, head) if r]
    for name, ref in (("base", base), ("head", head)):
        if ref and (err := _validate_ref(ref, name)):
            return err
    args = ["diff"]
    if staged and not refs:
        args.append("--cached")
    pathspec = ["--", *_as_list(paths)]

    ok, stat = _git([*args, "--stat=120", "--end-of-options", *refs, *pathspec], repo_path)
    if not ok:
        return stat
    if not stat.strip():
        return "(no changes)"
    if stat_only:
        return _truncate(stat)
    ok, diff = _git([*args, "--end-of-options", *refs, *pathspec], repo_path)
    if not ok:
        return diff
    return stat.rstrip() + "\n\n" + _budget_diff(diff, MAX_OUTPUT_CHARS - len(stat))


def run_log(
    repo_path: str | None = None,
    max_count: int | None = None,
    revision_range: str | None = None,
    paths: list[str] | str | None = None,
    no_merges: bool = False,
    with_stat: bool = False,
) -> str:
    if revision_range and (err := _validate_ref(revision_range, "revision_range")):
        return err
    if max_count is None:
        max_count = 200 if revision_range else 20
    args = [
        "log",
        f"--max-count={max_count}",
        "--date=short",
        "--format=commit %h | %ad | %an%n%s%n%b",
    ]
    if no_merges:
        args.append("--no-merges")
    if with_stat:
        args.append("--stat=120")
    args.append("--end-of-options")
    if revision_range:
        args.append(revision_range)
    args += ["--", *_as_list(paths)]
    return _run_git(args, repo_path)


def run_tags(repo_path: str | None = None) -> str:
    result = _run_git(
        [
            "for-each-ref",
            "refs/tags",
            "--sort=-v:refname",
            "--format=%(refname:short)  %(creatordate:short)  "
            "%(if)%(*objectname)%(then)%(*objectname:short)%(else)%(objectname:short)%(end)  "
            "%(subject)",
        ],
        repo_path,
    )
    if result == "(no output)":
        return "(no tags)"
    return result


def run_show(repo_path: str | None = None, ref: str = "HEAD") -> str:
    if err := _validate_ref(ref):
        return err
    ok, meta = _git(["show", "--stat=120", "--format=fuller", "--end-of-options", ref], repo_path)
    if not ok:
        return meta
    ok, diff = _git(["show", "--format=", "--end-of-options", ref], repo_path)
    if not ok:
        return diff
    return meta.rstrip() + "\n\n" + _budget_diff(diff, MAX_OUTPUT_CHARS - len(meta))


# ---------------------------------------------------------------------------
# Task-shaped tools
# ---------------------------------------------------------------------------

def run_commit_context(repo_path: str | None = None) -> str:
    budget = _context_max_chars()
    ok, branch = _git(["rev-parse", "--abbrev-ref", "HEAD"], repo_path)
    if not ok and "not a git repository" in branch.lower():
        return branch
    branch = branch.strip() if ok else "(no commits yet)"

    _, staged_stat = _git(["diff", "--cached", "--stat=120"], repo_path)
    _, unstaged_stat = _git(["diff", "--stat=120"], repo_path)
    _, untracked = _git(["ls-files", "--others", "--exclude-standard"], repo_path)
    _, recent = _git(["log", "-10", "--format=%s"], repo_path)
    untracked_files = untracked.split()

    sections = [f"Branch: {branch}"]
    if staged_stat.strip():
        sections.append(
            "NOTE: there are staged changes — a commit will include ONLY the staged "
            "changes. Unstaged changes are shown for reference."
        )
    else:
        sections.append(
            "NOTE: nothing is staged — describe the unstaged changes and untracked files."
        )
    if recent.strip():
        sections.append("## Recent commit subjects (match this style)\n" + _clip_lines(recent))
    sections.append("## Staged changes (summary)\n" + (staged_stat.strip() or "(none)"))
    sections.append("## Unstaged changes (summary)\n" + (unstaged_stat.strip() or "(none)"))
    sections.append(
        "## Untracked files\n" + ("\n".join(untracked_files[:50]) or "(none)")
        + (f"\n... and {len(untracked_files) - 50} more" if len(untracked_files) > 50 else "")
    )
    header = "\n\n".join(sections)

    remaining = budget - len(header)
    diffs: list[str] = []
    wanted = [("Staged diff", ["diff", "--cached"])] if staged_stat.strip() else []
    if unstaged_stat.strip():
        wanted.append(("Unstaged diff", ["diff"]))
    for i, (title, args) in enumerate(wanted):
        _, diff = _git(args, repo_path)
        part = _budget_diff(diff, remaining // (len(wanted) - i))
        diffs.append(f"## {title}\n{part}")
        remaining -= len(part)

    # Show the start of small untracked text files: they are new code to describe
    root = _resolve_repo(repo_path)
    previews: list[str] = []
    for name in untracked_files[:10]:
        if remaining < 500:
            break
        f = root / name
        try:
            if f.stat().st_size > 20_000:
                continue
            text = f.read_text()
        except (OSError, UnicodeDecodeError):
            continue
        preview = "\n".join(text.splitlines()[:40])[: min(2_000, remaining - 200)]
        previews.append(f"--- {name} (new file, first lines)\n{preview}")
        remaining -= len(previews[-1])
    if previews:
        diffs.append("## New file previews\n" + "\n\n".join(previews))

    return (header + "\n\n" + "\n\n".join(diffs)).strip()


def _parse_commits(raw: str) -> list[dict]:
    commits = []
    for record in raw.split("\x1e"):
        if not record.strip():
            continue
        head, _, files = record.partition("\x1d")
        fields = head.split("\x1f")
        if len(fields) < 5:
            continue
        sha, date, author, subject, body = (f.strip() for f in fields[:5])
        commits.append({
            "sha": sha,
            "date": date,
            "author": author,
            "subject": subject,
            "body": body,
            "files": [f for f in files.strip().splitlines() if f.strip()],
        })
    return commits


def _classify(subject: str, body: str) -> tuple[str, bool, str]:
    """Return (type, breaking, description) for a commit subject."""
    m = _CONVENTIONAL_RE.match(subject)
    breaking = "BREAKING CHANGE" in body
    if not m:
        return "other", breaking, subject
    ctype = m.group(1).lower()
    if ctype not in dict(_COMMIT_TYPES):
        ctype = "other"
    scope = m.group(2) or ""
    return ctype, breaking or bool(m.group(3)), f"{scope + ': ' if scope else ''}{m.group(4)}"


def _render_commit(c: dict, detail: int) -> str:
    _, breaking, desc = _classify(c["subject"], c["body"])
    line = f"- {c['sha']} {c['date']} {c['author']}: {desc}" + (" [BREAKING]" if breaking else "")
    if detail >= 2 and c["body"]:
        body = "\n".join(c["body"].splitlines()[:8])[:400]
        line += "\n" + "\n".join("    " + b for b in body.splitlines() if b.strip())
    if detail >= 1 and c["files"]:
        files = c["files"][:8]
        more = f" (+{len(c['files']) - 8} more)" if len(c["files"]) > 8 else ""
        line += "\n    files: " + ", ".join(files) + more
    return line


def _range_report(
    repo_path: str | None,
    from_ref: str,
    to_ref: str,
    include_diff: bool,
    budget: int,
) -> str:
    for name, ref in (("from_ref", from_ref), ("to_ref", to_ref)):
        if err := _validate_ref(ref, name):
            return err
    rng = f"{from_ref}..{to_ref}"
    ok, raw = _git(
        [
            "log", "--no-merges", "--date=short", "--name-only",
            "--format=%x1e%h%x1f%ad%x1f%an%x1f%s%x1f%b%x1d",
            "--end-of-options", rng,
        ],
        repo_path,
    )
    if not ok:
        return raw
    commits = _parse_commits(raw)
    _, merges = _git(["log", "--merges", "--format=%s", "--end-of-options", rng], repo_path)
    _, shortstat = _git(["diff", "--shortstat", "--end-of-options", from_ref, to_ref], repo_path)
    dates = []
    for ref in (from_ref, to_ref):
        _, d = _git(
            ["log", "-1", "--date=short", "--format=%ad", "--end-of-options", ref], repo_path
        )
        dates.append(d.strip() or "?")

    subjects = [c["subject"] for c in commits] + merges.splitlines()
    prs = sorted({int(n) for s in subjects for n in _PR_RE.findall(s)})
    authors = sorted({c["author"] for c in commits})
    head = [
        f"# Changes {from_ref} → {to_ref} ({dates[0]} → {dates[1]})",
        f"Commits: {len(commits)} (merge commits excluded)",
        f"Authors: {', '.join(authors) or '(none)'}",
        f"Diffstat: {shortstat.strip() or '(no file changes)'}",
    ]
    if prs:
        head.append("Merged PRs: " + ", ".join(f"#{n}" for n in prs))
    if not commits:
        return "\n".join(head + ["", "(no commits in this range)"])

    groups: dict[str, list[dict]] = {}
    for c in commits:
        groups.setdefault(_classify(c["subject"], c["body"])[0], []).append(c)
    titles = [*_COMMIT_TYPES, ("other", "Other changes")]

    # Degrade detail (bodies, then file lists) until the report fits the budget
    for detail in (2, 1, 0):
        parts = ["\n".join(head)]
        for key, title in titles:
            if key in groups:
                lines = "\n".join(_render_commit(c, detail) for c in groups[key])
                parts.append(f"## {title}\n{lines}")
        report = "\n\n".join(parts)
        if len(report) <= budget:
            break
    report = _truncate(report, budget)

    if include_diff and budget - len(report) > 1_000:
        _, diff = _git(["diff", "-U1", "--end-of-options", from_ref, to_ref], repo_path)
        report += "\n\n## Code diff (trimmed)\n" + _budget_diff(diff, budget - len(report))
    return report


def run_range_report(
    repo_path: str | None = None,
    from_ref: str = "",
    to_ref: str | None = None,
    include_diff: bool = False,
) -> str:
    return _range_report(repo_path, from_ref, to_ref or "HEAD", include_diff, _context_max_chars())


def run_release_notes_context(
    repo_path: str | None = None,
    tags: list[str] | str | None = None,
    count: int = 3,
) -> str:
    ok, raw = _git(["tag", "--list", "--sort=v:refname"], repo_path)
    if not ok:
        return raw
    all_tags = raw.split()
    wanted = _as_list(tags)
    if wanted:
        missing = [t for t in wanted if t not in all_tags]
        if missing:
            latest = ", ".join(reversed(all_tags[-20:])) or "(none)"
            return f"Error: unknown tag(s): {', '.join(missing)}. Latest tags: {latest}"
        ordered = sorted(set(wanted), key=all_tags.index)
    else:
        ordered = all_tags[-max(count, 2):]
    if len(ordered) < 2:
        return "Error: need at least two tags to build release-notes ranges."

    pairs = list(zip(ordered, ordered[1:]))
    budget = _context_max_chars() // len(pairs)
    reports = [_range_report(repo_path, a, b, False, budget) for a, b in pairs]
    intro = (
        f"Release ranges (oldest first): {', '.join(f'{a} → {b}' for a, b in pairs)}.\n"
        "Write one release-notes section per range."
    )
    return intro + "\n\n" + "\n\n".join(reports)


# ---------------------------------------------------------------------------
# System-prompt snapshot
# ---------------------------------------------------------------------------

def repo_context(repo_path: str | None = None) -> str:
    """Compact repo snapshot for the system prompt, or '' when not inside a repo."""
    ok, top = _git(["rev-parse", "--show-toplevel"], repo_path)
    if not ok:
        return ""
    _, status = _git(["status", "--short", "--branch"], repo_path)
    _, log = _git(["log", "-10", "--date=short", "--format=%h %ad %s"], repo_path)
    _, tags = _git(
        [
            "for-each-ref", "refs/tags", "--sort=-v:refname", "--count=15",
            "--format=%(refname:short) %(creatordate:short)",
        ],
        repo_path,
    )
    status_lines = status.strip().splitlines()
    if len(status_lines) > 40:
        status_lines = status_lines[:40] + [f"... and {len(status_lines) - 40} more"]
    return "\n".join([
        "## Git repository (auto-collected at the start of this turn — no need to re-query)",
        f"Repository root: {top.strip()}",
        "Git tools default to this repository: omit repo_path.",
        "Status (git status --short --branch):",
        "\n".join(status_lines) or "(clean)",
        "Recent commits:",
        _clip_lines(log) or "(no commits)",
        "Tags (newest first, max 15):",
        tags.strip() or "(no tags)",
    ])
