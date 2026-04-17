# Local Tool-Calling Agent — Developer Guide

## Project Overview
A local agentic loop that connects to LM Studio's OpenAI-compatible API and
can call Python-implemented tools (file search, folder listing, file reading,
bash execution) to answer user queries.

## Stack
- **Runtime**: Python 3.11+, managed with `uv`
- **LLM backend**: LM Studio (`http://localhost:1234/v1`) — OpenAI-compatible
- **Client**: `openai` Python SDK (pointed at local base URL)
- **CLI UI**: `rich` for terminal output
- **Web UI**: FastAPI + SSE streaming, vanilla HTML/CSS/JS (`static/index.html`)
- **Config**: `.env` via `python-dotenv`

## Model Configuration
Set in `.env`:
```
LM_STUDIO_BASE_URL=http://localhost:1234/v1
LM_STUDIO_MODEL=qwen2.5-14b-instruct   # or any model loaded in LM Studio
LM_STUDIO_API_KEY=lm-studio            # arbitrary, LM Studio ignores it
```

## Project Layout
```
local-tool-ai/
├── agent.py          # Core agentic loop (CLI) + run_events async generator (web)
├── main.py           # CLI entry point
├── server.py         # FastAPI web server (SSE streaming, session history)
├── static/
│   └── index.html    # Web chat UI (self-contained HTML/CSS/JS)
├── tools/
│   ├── __init__.py
│   ├── registry.py   # Schema export + dispatch(name, args)
│   ├── search_files.py
│   ├── list_folder.py
│   ├── read_file.py
│   └── run_bash.py
├── tests/
│   ├── __init__.py
│   ├── test_search_files.py
│   ├── test_list_folder.py
│   ├── test_read_file.py
│   └── test_run_bash.py
├── pyproject.toml
├── .env.example
└── CLAUDE.md
```

## Conventions
- One file per tool under `tools/`. Each file exports:
  - `SCHEMA: dict` — the OpenAI tool JSON schema
  - `run(**kwargs) -> str` — the implementation (always returns a string)
- `tools/registry.py` aggregates all schemas and provides `dispatch(name, args)`
- `agent.py` is model-agnostic; all LM Studio config comes from env vars
- Max agent iterations: 20 (configurable via `MAX_ITERATIONS` env var)
- Tool output is truncated to 8 000 chars before being fed back to the model
- All tool errors are caught and returned as error strings (never raise into agent)

## Running

**CLI:**
```bash
uv run main.py "list the files in the current directory"
uv run main.py --repl          # interactive mode
```

**Web UI:**
```bash
uv run server.py               # serves on http://localhost:7860
# or
uvicorn server:app --reload    # dev mode with auto-reload
```

## Testing
```bash
uv run pytest tests/ -v
```

## Linting / Formatting
```bash
uv run ruff check .
uv run ruff format .
```
