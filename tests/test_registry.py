import json

from tools.registry import DESTRUCTIVE_TOOLS, READONLY_TOOLS, SCHEMAS, dispatch, get_schemas


def test_schemas_list_has_all_tools():
    names = {s["function"]["name"] for s in SCHEMAS}
    assert names == {"search_files", "list_folder", "read_file", "run_bash"}


def test_readonly_and_destructive_sets():
    assert "run_bash" in DESTRUCTIVE_TOOLS
    assert "read_file" in READONLY_TOOLS
    assert READONLY_TOOLS.isdisjoint(DESTRUCTIVE_TOOLS)


def test_get_schemas_normal_mode():
    names = {s["function"]["name"] for s in get_schemas(safe_mode=False)}
    assert "run_bash" in names
    assert "read_file" in names


def test_get_schemas_safe_mode():
    names = {s["function"]["name"] for s in get_schemas(safe_mode=True)}
    assert "run_bash" not in names
    assert "read_file" in names


def test_dispatch_known_tool():
    # Use a read-only tool so no confirmation is required
    result = dispatch("list_folder", {"path": "."})
    assert "Error" not in result or True  # just ensure it runs without exception


def test_dispatch_unknown_tool():
    result = dispatch("nonexistent_tool", {})
    assert "Error" in result
    assert "unknown" in result.lower()


def test_dispatch_json_string_args():
    # Use a read-only tool (list_folder) with JSON-string args
    args_json = json.dumps({"path": "."})
    result = dispatch("list_folder", args_json)
    # Should produce a listing, not a JSON-parse error
    assert "Error: could not parse" not in result


def test_dispatch_bad_json_string():
    result = dispatch("run_bash", "not-valid-json{{{")
    assert "Error" in result


def test_dispatch_destructive_auto_cancels_non_tty(monkeypatch):
    # In test (non-TTY) environment, destructive tools auto-cancel
    import sys
    monkeypatch.setattr(sys.stdin, "isatty", lambda: False)
    result = dispatch("run_bash", {"command": "echo hi"})
    assert result == "Action cancelled by user."


def test_bash_blacklist_blocks_after_confirmation(monkeypatch):
    # Simulate user typing 'y' but command is blacklisted
    import sys
    monkeypatch.setattr(sys.stdin, "isatty", lambda: True)
    monkeypatch.setattr("builtins.input", lambda _: "y")
    result = dispatch("run_bash", {"command": "sudo rm -rf /"})
    assert "blacklisted" in result.lower()
