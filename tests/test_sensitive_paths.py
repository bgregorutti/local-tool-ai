"""Tests for sensitive-path denylist enforcement."""

from pathlib import Path

from local_tool_ai.tools.registry import _check_path_allowlist


def test_ssh_dir_is_denied(monkeypatch):
    monkeypatch.setenv("ALLOWED_ROOT", str(Path.home()))
    result = _check_path_allowlist("read_file", {"path": str(Path.home() / ".ssh" / "id_rsa")})
    assert result is not None
    assert "sensitive" in result.lower()


def test_aws_dir_is_denied(monkeypatch):
    monkeypatch.setenv("ALLOWED_ROOT", str(Path.home()))
    result = _check_path_allowlist("read_file", {"path": str(Path.home() / ".aws" / "credentials")})
    assert result is not None
    assert "sensitive" in result.lower()


def test_gnupg_dir_is_denied(monkeypatch):
    monkeypatch.setenv("ALLOWED_ROOT", str(Path.home()))
    result = _check_path_allowlist("read_file", {"path": str(Path.home() / ".gnupg" / "private-keys-v1.d")})
    assert result is not None
    assert "sensitive" in result.lower()


def test_normal_path_is_allowed(monkeypatch, tmp_path):
    monkeypatch.setenv("ALLOWED_ROOT", str(tmp_path))
    result = _check_path_allowlist("read_file", {"path": str(tmp_path / "readme.txt")})
    assert result is None


def test_sensitive_path_denied_even_inside_allowed_root(monkeypatch):
    """Sensitive paths should be denied even if they fall under ALLOWED_ROOT."""
    monkeypatch.setenv("ALLOWED_ROOT", str(Path.home()))
    result = _check_path_allowlist("read_file", {"path": str(Path.home() / ".ssh")})
    assert result is not None
    assert "sensitive" in result.lower()
