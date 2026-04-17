import json

from tools.registry import SCHEMAS, dispatch


def test_schemas_list_has_all_tools():
    names = {s["function"]["name"] for s in SCHEMAS}
    assert names == {"search_files", "list_folder", "read_file", "run_bash"}


def test_dispatch_known_tool():
    result = dispatch("run_bash", {"command": "echo hi"})
    assert "hi" in result


def test_dispatch_unknown_tool():
    result = dispatch("nonexistent_tool", {})
    assert "Error" in result
    assert "unknown" in result.lower()


def test_dispatch_json_string_args():
    args_json = json.dumps({"command": "echo json"})
    result = dispatch("run_bash", args_json)
    assert "json" in result


def test_dispatch_bad_json_string():
    result = dispatch("run_bash", "not-valid-json{{{")
    assert "Error" in result
