import tempfile
from pathlib import Path

from local_tool_ai.tools.read_file import run, MAX_CHARS


def test_reads_full_file():
    with tempfile.TemporaryDirectory() as tmp:
        f = Path(tmp) / "hello.txt"
        f.write_text("line1\nline2\nline3\n")
        result = run(path=str(f))
        assert "line1" in result
        assert "line3" in result


def test_line_range():
    with tempfile.TemporaryDirectory() as tmp:
        f = Path(tmp) / "lines.txt"
        f.write_text("\n".join(f"line{i}" for i in range(1, 11)))
        result = run(path=str(f), start_line=3, end_line=5)
        assert "line3" in result
        assert "line5" in result
        assert "line1" not in result
        assert "line6" not in result


def test_truncation():
    with tempfile.TemporaryDirectory() as tmp:
        f = Path(tmp) / "big.txt"
        f.write_text("x" * (MAX_CHARS + 1000))
        result = run(path=str(f))
        assert "truncated" in result
        assert len(result) <= MAX_CHARS + 100  # a bit of slack for the truncation message


def test_nonexistent_file():
    result = run(path="/no/such/file.txt")
    assert "Error" in result


def test_empty_file():
    with tempfile.TemporaryDirectory() as tmp:
        f = Path(tmp) / "empty.txt"
        f.write_text("")
        result = run(path=str(f))
        assert "empty" in result.lower()
