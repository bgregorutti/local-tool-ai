"""Tests for tools/git.py — uses a real fixture git repo created in a temp dir."""

from __future__ import annotations

import os
import subprocess
from pathlib import Path

import pytest

from tools.git import run_log, run_show, run_status, run_tags
from tools.registry import dispatch, READONLY_TOOLS


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
    for name in ("git_status", "git_log", "git_tags", "git_show"):
        assert name in READONLY_TOOLS, f"{name} must be in READONLY_TOOLS"
