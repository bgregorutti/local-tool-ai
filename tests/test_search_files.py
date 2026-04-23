import os
import tempfile
from pathlib import Path

from local_tool_ai.tools.search_files import run


def _make_tree(base: Path) -> None:
    (base / "a.py").write_text("# a")
    (base / "b.txt").write_text("b")
    sub = base / "sub"
    sub.mkdir()
    (sub / "c.py").write_text("# c")


def test_finds_py_files():
    with tempfile.TemporaryDirectory() as tmp:
        _make_tree(Path(tmp))
        result = run(pattern="*.py", root=tmp)
        paths = result.splitlines()
        assert any("a.py" in p for p in paths)
        assert any("c.py" in p for p in paths)


def test_no_match_returns_message():
    with tempfile.TemporaryDirectory() as tmp:
        result = run(pattern="*.xyz", root=tmp)
        assert "No files" in result


def test_max_results_respected():
    with tempfile.TemporaryDirectory() as tmp:
        for i in range(10):
            (Path(tmp) / f"f{i}.py").write_text("")
        result = run(pattern="*.py", root=tmp, max_results=3)
        assert len(result.splitlines()) == 3


def test_invalid_root():
    result = run(pattern="*.py", root="/nonexistent_dir_xyz")
    assert "Error" in result
