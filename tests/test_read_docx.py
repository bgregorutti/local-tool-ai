import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from tools.read_docx import run


def _make_mock_doc(paragraphs: list[str]):
    doc = MagicMock()
    doc.paragraphs = [MagicMock(text=p) for p in paragraphs]
    return doc


def test_valid_docx_returns_paragraph_text():
    mock_doc = _make_mock_doc(["Hello", "World"])
    with patch("docx.Document", return_value=mock_doc):
        result = run(file_path="/fake/doc.docx")
    assert "Hello" in result
    assert "World" in result


def test_empty_docx_returns_empty_message():
    mock_doc = _make_mock_doc(["", "  "])
    with patch("docx.Document", return_value=mock_doc):
        result = run(file_path="/fake/empty.docx")
    assert "empty" in result.lower()


def test_nonexistent_file_returns_error():
    result = run(file_path="/no/such/file.docx")
    assert "Error" in result


def test_corrupt_file_returns_error():
    with patch("docx.Document", side_effect=Exception("bad zip")):
        result = run(file_path="/fake/corrupt.docx")
    assert "Error" in result


def test_path_outside_allowed_root_is_blocked(monkeypatch, tmp_path):
    monkeypatch.setenv("ALLOWED_ROOT", str(tmp_path))
    from tools.registry import dispatch

    result = dispatch("read_docx", {"file_path": "/etc/passwd"})
    assert "outside" in result.lower()


def test_path_inside_allowed_root_proceeds(monkeypatch, tmp_path):
    monkeypatch.setenv("ALLOWED_ROOT", str(tmp_path))
    docx_path = str(tmp_path / "doc.docx")
    from tools.registry import dispatch

    mock_doc = _make_mock_doc(["Paragraph one", "Paragraph two"])
    with patch("docx.Document", return_value=mock_doc):
        result = dispatch("read_docx", {"file_path": docx_path})
    assert "Paragraph one" in result
