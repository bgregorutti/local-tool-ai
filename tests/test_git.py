"""Tests for tools/git.py — uses a real fixture git repo created in a temp dir."""

from __future__ import annotations

import os
import re
import subprocess
from pathlib import Path

import pytest

from local_tool_ai.tools.git import (
    repo_context,
    run_commit_context,
    run_diff,
    run_log,
    run_range_report,
    run_release_notes_context,
    run_show,
    run_status,
    run_tags,
)
from local_tool_ai.tools.registry import READONLY_TOOLS, dispatch

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture()
def repo(tmp_path: Path) -> Path:
    """Initialise a minimal git repo with one commit."""
    env = {**os.environ, "GIT_AUTHOR_NAME": "Test", "GIT_AUTHOR_EMAIL": "t@t.com",
           "GIT_COMMITTER_NAME": "Test", "GIT_COMMITTER_EMAIL": "t@t.com"}

    def git(*args: str) -> None:
        subprocess.run(["git", *args], cwd=tmp_path, check=True, capture_output=True, env=env)

    git("init")
    git("config", "user.email", "t@t.com")
    git("config", "user.name", "Test")
    git("config", "commit.gpgsign", "false")
    git("config", "tag.gpgsign", "false")
    (tmp_path / "hello.txt").write_text("hello\n")
    git("add", "hello.txt")
    git("commit", "-m", "initial commit")
    return tmp_path


# ---------------------------------------------------------------------------
# git_status
# ---------------------------------------------------------------------------

def test_status_clean_repo(repo: Path) -> None:
    result = run_status(repo_path=str(repo))
    assert "nothing to commit" in result.lower() or "working tree clean" in result.lower()


def test_status_dirty_repo(repo: Path) -> None:
    (repo / "hello.txt").write_text("modified\n")
    result = run_status(repo_path=str(repo))
    assert "modified" in result.lower() or "hello.txt" in result


def test_status_untracked_file(repo: Path) -> None:
    (repo / "new.txt").write_text("new\n")
    result = run_status(repo_path=str(repo))
    assert "new.txt" in result


def test_status_not_a_git_repo(tmp_path: Path) -> None:
    result = run_status(repo_path=str(tmp_path))
    assert "error" in result.lower()


def test_status_nonexistent_path() -> None:
    result = run_status(repo_path="/nonexistent/path/xyz")
    assert "error" in result.lower()


# ---------------------------------------------------------------------------
# git_log
# ---------------------------------------------------------------------------

def test_log_returns_commits(repo: Path) -> None:
    result = run_log(repo_path=str(repo))
    assert "initial commit" in result


def test_log_respects_max_count(repo: Path) -> None:
    env = {**os.environ, "GIT_AUTHOR_NAME": "Test", "GIT_AUTHOR_EMAIL": "t@t.com",
           "GIT_COMMITTER_NAME": "Test", "GIT_COMMITTER_EMAIL": "t@t.com"}

    def git(*args: str) -> None:
        subprocess.run(["git", "-c", "commit.gpgsign=false", *args],
                       cwd=repo, check=True, capture_output=True, env=env)

    for i in range(1, 6):
        (repo / f"file{i}.txt").write_text(f"content {i}\n")
        git("add", f"file{i}.txt")
        git("commit", "-m", f"commit {i}")

    result_all = run_log(repo_path=str(repo), max_count=6)
    result_limited = run_log(repo_path=str(repo), max_count=2)

    assert result_all.count("commit") > result_limited.count("commit")
    assert "commit 5" in result_all
    assert "commit 5" in result_limited
    assert "initial commit" in result_all
    assert "initial commit" not in result_limited


def test_log_not_a_git_repo(tmp_path: Path) -> None:
    result = run_log(repo_path=str(tmp_path))
    assert "error" in result.lower()


# ---------------------------------------------------------------------------
# git_tags
# ---------------------------------------------------------------------------

def test_tags_empty(repo: Path) -> None:
    result = run_tags(repo_path=str(repo))
    assert "no tags" in result.lower() or result.strip() == "(no tags)"


def test_tags_with_tags(repo: Path) -> None:
    subprocess.run(["git", "tag", "v1.0"], cwd=repo, check=True, capture_output=True)
    subprocess.run(["git", "tag", "v2.0"], cwd=repo, check=True, capture_output=True)
    result = run_tags(repo_path=str(repo))
    assert "v1.0" in result
    assert "v2.0" in result


def test_tags_not_a_git_repo(tmp_path: Path) -> None:
    result = run_tags(repo_path=str(tmp_path))
    assert "error" in result.lower()


# ---------------------------------------------------------------------------
# git_show
# ---------------------------------------------------------------------------

def test_show_valid_ref(repo: Path) -> None:
    result = run_show(repo_path=str(repo), ref="HEAD")
    assert "initial commit" in result or "hello.txt" in result


def test_show_tag(repo: Path) -> None:
    subprocess.run(["git", "tag", "v1.0"], cwd=repo, check=True, capture_output=True)
    result = run_show(repo_path=str(repo), ref="v1.0")
    assert "initial commit" in result or "hello.txt" in result


def test_show_invalid_ref(repo: Path) -> None:
    result = run_show(repo_path=str(repo), ref="nonexistent-ref-xyz")
    assert "error" in result.lower()


def test_show_shell_injection_rejected(repo: Path) -> None:
    result = run_show(repo_path=str(repo), ref="main; rm -rf .")
    assert "error" in result.lower() and "invalid" in result.lower()


def test_show_pipe_injection_rejected(repo: Path) -> None:
    result = run_show(repo_path=str(repo), ref="HEAD | cat /etc/passwd")
    assert "error" in result.lower() and "invalid" in result.lower()


# ---------------------------------------------------------------------------
# ALLOWED_ROOT enforcement (via dispatch)
# ---------------------------------------------------------------------------

def test_dispatch_blocks_path_outside_allowed_root(repo: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ALLOWED_ROOT", str(repo))
    result = dispatch("git_status", {"repo_path": "/tmp"})
    assert "outside" in result.lower() or "allowed" in result.lower()


def test_dispatch_allows_path_inside_allowed_root(repo: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ALLOWED_ROOT", str(repo))
    result = dispatch("git_status", {"repo_path": str(repo)})
    assert "error" not in result.lower() or "outside" not in result.lower()


# ---------------------------------------------------------------------------
# No confirmation prompt for git tools (read-only tier)
# ---------------------------------------------------------------------------

def test_git_tools_are_readonly() -> None:
    for name in (
        "git_status", "git_log", "git_tags", "git_show", "git_diff",
        "git_commit_context", "git_range_report", "git_release_notes_context",
    ):
        assert name in READONLY_TOOLS, f"{name} must be in READONLY_TOOLS"


# ---------------------------------------------------------------------------
# Option injection (refs starting with '-')
# ---------------------------------------------------------------------------

def test_show_option_injection_rejected(repo: Path, tmp_path: Path) -> None:
    target = tmp_path / "pwned.txt"
    result = run_show(repo_path=str(repo), ref=f"--output={target}")
    assert "invalid" in result.lower()
    assert not target.exists()


def test_log_range_option_injection_rejected(repo: Path) -> None:
    result = run_log(repo_path=str(repo), revision_range="--output=x")
    assert "invalid" in result.lower()


def test_diff_base_option_injection_rejected(repo: Path) -> None:
    result = run_diff(repo_path=str(repo), base="--output=x")
    assert "invalid" in result.lower()


# ---------------------------------------------------------------------------
# Release history fixture: tags 3.0.0, 3.0.1, 3.0.2 with conventional commits
# ---------------------------------------------------------------------------

def _git(repo: Path, *args: str) -> None:
    env = {**os.environ, "GIT_AUTHOR_NAME": "Test", "GIT_AUTHOR_EMAIL": "t@t.com",
           "GIT_COMMITTER_NAME": "Test", "GIT_COMMITTER_EMAIL": "t@t.com"}
    subprocess.run(["git", "-c", "commit.gpgsign=false", "-c", "tag.gpgsign=false", *args],
                   cwd=repo, check=True, capture_output=True, env=env)


def _commit(repo: Path, name: str, message: str) -> None:
    (repo / name).write_text(message + "\n")
    _git(repo, "add", name)
    _git(repo, "commit", "-m", message)


@pytest.fixture()
def release_repo(repo: Path) -> Path:
    _git(repo, "tag", "3.0.0")
    _commit(repo, "a.py", "feat(api): add export endpoint (#12)")
    _commit(repo, "b.py", "fix: handle empty input")
    _git(repo, "tag", "-a", "3.0.1", "-m", "release 3.0.1")
    _commit(repo, "c.py", "feat!: drop python 3.10 support")
    _commit(repo, "d.txt", "update readme wording")
    (repo / "uv.lock").write_text("lock\n" * 50)
    _git(repo, "add", "uv.lock")
    _git(repo, "commit", "-m", "chore: bump deps")
    _git(repo, "tag", "3.0.2")
    return repo


def test_tags_sorted_by_version_with_dates(release_repo: Path) -> None:
    lines = run_tags(repo_path=str(release_repo)).splitlines()
    assert [ln.split()[0] for ln in lines] == ["3.0.2", "3.0.1", "3.0.0"]
    assert re.search(r"\d{4}-\d{2}-\d{2}", lines[0])


def test_log_revision_range(release_repo: Path) -> None:
    result = run_log(repo_path=str(release_repo), revision_range="3.0.0..3.0.1")
    assert "add export endpoint" in result
    assert "handle empty input" in result
    assert "drop python" not in result
    assert "initial commit" not in result


def test_log_paths_filter(release_repo: Path) -> None:
    result = run_log(repo_path=str(release_repo), paths=["b.py"])
    assert "handle empty input" in result
    assert "add export endpoint" not in result


def test_diff_between_refs(release_repo: Path) -> None:
    result = run_diff(repo_path=str(release_repo), base="3.0.0", head="3.0.1")
    assert "a.py" in result and "b.py" in result
    assert "c.py" not in result


def test_diff_staged(repo: Path) -> None:
    (repo / "hello.txt").write_text("staged change\n")
    _git(repo, "add", "hello.txt")
    assert run_diff(repo_path=str(repo)) == "(no changes)"
    assert "staged change" in run_diff(repo_path=str(repo), staged=True)


def test_diff_head_requires_base(repo: Path) -> None:
    assert "error" in run_diff(repo_path=str(repo), head="HEAD").lower()


def test_diff_skips_lock_files(release_repo: Path) -> None:
    result = run_diff(repo_path=str(release_repo), base="3.0.1", head="3.0.2")
    assert "skipped lock/generated files: uv.lock" in result
    assert "+lock" not in result


def test_range_report_groups_commits(release_repo: Path) -> None:
    result = run_range_report(repo_path=str(release_repo), from_ref="3.0.0", to_ref="3.0.1")
    assert "3.0.0 → 3.0.1" in result
    assert "Commits: 2" in result
    assert "## Features" in result and "(api): add export endpoint" in result
    assert "## Bug fixes" in result and "handle empty input" in result
    assert "Merged PRs: #12" in result
    assert "files: a.py" in result
    assert "drop python" not in result


def test_range_report_breaking_and_other(release_repo: Path) -> None:
    result = run_range_report(repo_path=str(release_repo), from_ref="3.0.1", to_ref="3.0.2")
    assert "drop python 3.10 support [BREAKING]" in result
    assert "## Other changes" in result and "update readme wording" in result


def test_range_report_defaults_to_head(release_repo: Path) -> None:
    result = run_range_report(repo_path=str(release_repo), from_ref="3.0.1")
    assert "3.0.1 → HEAD" in result


def test_range_report_degrades_to_fit_budget(
    release_repo: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("GIT_CONTEXT_MAX_CHARS", "400")
    result = run_range_report(repo_path=str(release_repo), from_ref="3.0.0", to_ref="3.0.2")
    assert "files:" not in result
    assert len(result) <= 450


def test_range_report_unknown_ref(release_repo: Path) -> None:
    result = run_range_report(repo_path=str(release_repo), from_ref="9.9.9")
    assert "error" in result.lower()


def test_release_notes_context_explicit_tags(release_repo: Path) -> None:
    result = run_release_notes_context(
        repo_path=str(release_repo), tags=["3.0.2", "3.0.0", "3.0.1"]
    )
    assert "3.0.0 → 3.0.1, 3.0.1 → 3.0.2" in result
    first, second = result.split("# Changes 3.0.1 → 3.0.2")
    assert "add export endpoint" in first and "drop python" not in first
    assert "drop python" in second and "add export endpoint" not in second


def test_release_notes_context_comma_string(release_repo: Path) -> None:
    result = run_release_notes_context(repo_path=str(release_repo), tags="3.0.0, 3.0.1")
    assert "# Changes 3.0.0 → 3.0.1" in result


def test_release_notes_context_latest_tags(release_repo: Path) -> None:
    result = run_release_notes_context(repo_path=str(release_repo), count=2)
    assert "# Changes 3.0.1 → 3.0.2" in result
    assert "3.0.0 →" not in result


def test_release_notes_context_unknown_tag(release_repo: Path) -> None:
    result = run_release_notes_context(repo_path=str(release_repo), tags=["3.0.0", "4.0.0"])
    assert "unknown tag(s): 4.0.0" in result


def test_release_notes_context_needs_two_tags(repo: Path) -> None:
    assert "at least two" in run_release_notes_context(repo_path=str(repo))


# ---------------------------------------------------------------------------
# git_commit_context
# ---------------------------------------------------------------------------

def test_commit_context_unstaged_and_untracked(repo: Path) -> None:
    (repo / "hello.txt").write_text("changed\n")
    (repo / "new_module.py").write_text("def answer():\n    return 42\n")
    result = run_commit_context(repo_path=str(repo))
    assert "nothing is staged" in result
    assert "initial commit" in result  # style reference
    assert "+changed" in result
    assert "new_module.py" in result and "return 42" in result


def test_commit_context_staged_only_note(repo: Path) -> None:
    (repo / "hello.txt").write_text("staged\n")
    _git(repo, "add", "hello.txt")
    result = run_commit_context(repo_path=str(repo))
    assert "ONLY the staged" in result
    assert "## Staged diff" in result and "+staged" in result


def test_commit_context_not_a_repo(tmp_path: Path) -> None:
    assert "error" in run_commit_context(repo_path=str(tmp_path)).lower()


# ---------------------------------------------------------------------------
# repo_path default + system-prompt snapshot
# ---------------------------------------------------------------------------

def test_repo_path_defaults_to_allowed_root(
    release_repo: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("ALLOWED_ROOT", str(release_repo))
    assert "3.0.2" in dispatch("git_tags", {})


def test_repo_context_snapshot(release_repo: Path) -> None:
    snapshot = repo_context(str(release_repo))
    assert f"Repository root: {release_repo.resolve()}" in snapshot
    assert "3.0.2" in snapshot and "bump deps" in snapshot


def test_repo_context_outside_repo(tmp_path: Path) -> None:
    assert repo_context(str(tmp_path)) == ""
