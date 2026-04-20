import os
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from tools.read_pdf import run


def test_valid_pdf_returns_markdown():
    with patch("pymupdf4llm.to_markdown", return_value="# Title\n\nSome content."):
        result = run(file_path="/fake/doc.pdf")
    assert "Title" in result
    assert "Some content" in result


def test_image_only_pdf_returns_empty_message():
    with patch("pymupdf4llm.to_markdown", return_value="   "):
        result = run(file_path="/fake/scanned.pdf")
    assert "no extractable text" in result.lower()


def test_nonexistent_file_returns_error():
    result = run(file_path="/no/such/file.pdf")
    assert "Error" in result


def test_corrupt_file_returns_error():
    with patch("pymupdf4llm.to_markdown", side_effect=Exception("corrupted PDF")):
        result = run(file_path="/fake/corrupt.pdf")
    assert "Error" in result


def test_path_outside_allowed_root_is_blocked(monkeypatch, tmp_path):
    monkeypatch.setenv("ALLOWED_ROOT", str(tmp_path))
    from tools.registry import dispatch

    result = dispatch("read_pdf", {"file_path": "/etc/passwd"})
    assert "outside" in result.lower()


def test_path_inside_allowed_root_proceeds(monkeypatch, tmp_path):
    monkeypatch.setenv("ALLOWED_ROOT", str(tmp_path))
    pdf_path = str(tmp_path / "doc.pdf")
    from tools.registry import dispatch

    with patch("pymupdf4llm.to_markdown", return_value="Hello PDF"):
        result = dispatch("read_pdf", {"file_path": pdf_path})
    assert "Hello PDF" in result
