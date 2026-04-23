from local_tool_ai.tools.run_bash import run


def test_simple_command():
    result = run(command="echo hello")
    assert result.strip() == "hello"


def test_stderr_captured():
    result = run(command="echo err >&2")
    assert "err" in result


def test_nonzero_exit_code_reported():
    result = run(command="exit 42", timeout=5)
    assert "42" in result


def test_timeout():
    result = run(command="sleep 60", timeout=1)
    assert "timed out" in result.lower()


def test_run_executes_directly():
    """run_bash.run() no longer has its own blocklist — validation is in registry."""
    result = run(command="echo safe")
    assert result.strip() == "safe"


def test_working_dir(tmp_path):
    (tmp_path / "marker.txt").write_text("found")
    result = run(command="cat marker.txt", working_dir=str(tmp_path))
    assert "found" in result
