import tempfile
from pathlib import Path

from local_tool_ai.tools.list_folder import run


def test_lists_files_and_dirs():
    with tempfile.TemporaryDirectory() as tmp:
        (Path(tmp) / "file.txt").write_text("hi")
        (Path(tmp) / "subdir").mkdir()
        result = run(path=tmp)
        assert "file.txt" in result
        assert "subdir/" in result


def test_hidden_files_excluded_by_default():
    with tempfile.TemporaryDirectory() as tmp:
        (Path(tmp) / ".hidden").write_text("x")
        (Path(tmp) / "visible.py").write_text("x")
        result = run(path=tmp, show_hidden=False)
        assert ".hidden" not in result
        assert "visible.py" in result


def test_hidden_files_included_when_requested():
    with tempfile.TemporaryDirectory() as tmp:
        (Path(tmp) / ".hidden").write_text("x")
        result = run(path=tmp, show_hidden=True)
        assert ".hidden" in result


def test_nonexistent_path():
    result = run(path="/no/such/path/xyz")
    assert "Error" in result


def test_file_instead_of_dir():
    with tempfile.TemporaryDirectory() as tmp:
        f = Path(tmp) / "file.txt"
        f.write_text("hi")
        result = run(path=str(f))
        assert "Error" in result
