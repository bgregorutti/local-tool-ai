# local-tool-ai

A local agentic loop that connects to [LM Studio](https://lmstudio.ai)'s OpenAI-compatible API and answers queries by calling Python-backed tools — file search, folder listing, file reading, and bash execution.

## Requirements

- [LM Studio](https://lmstudio.ai) running locally with a model loaded
- [uv](https://docs.astral.sh/uv/) for Python environment management

## Setup

```bash
cp .env.example .env
# edit .env and set LM_STUDIO_MODEL to the model loaded in LM Studio
uv sync
```

## Usage

**Single query:**
```bash
uv run main.py "find all Python files in the current directory"
```

**Interactive REPL:**
```bash
uv run main.py --repl
```

**Options:**
```
--model   -m   Override the model name (LM_STUDIO_MODEL)
--system  -s   Override the system prompt
--quiet   -q   Suppress step-by-step tool output
--repl    -r   Start interactive REPL mode
```

## Tools

| Tool | Description |
|---|---|
| `search_files` | Recursively search for files by glob pattern |
| `list_folder` | List directory contents with file sizes |
| `read_file` | Read file contents, optionally scoped to a line range |
| `run_bash` | Execute a shell command and capture stdout/stderr |

## Project layout

```
local-tool-ai/
├── agent.py          # Agentic loop
├── main.py           # CLI entry point
├── tools/
│   ├── registry.py   # Schema aggregator + dispatch()
│   ├── search_files.py
│   ├── list_folder.py
│   ├── read_file.py
│   └── run_bash.py
└── tests/            # Unit tests (25 tests, no LLM required)
```

## Development

```bash
uv run pytest tests/ -v      # run tests
uv run ruff check .          # lint
uv run ruff format .         # format
```

## Configuration

All config lives in `.env`:

```
LM_STUDIO_BASE_URL=http://localhost:1234/v1
LM_STUDIO_MODEL=qwen2.5-14b-instruct
LM_STUDIO_API_KEY=lm-studio
MAX_ITERATIONS=20
```

`MAX_ITERATIONS` caps the tool-call loop to prevent infinite cycles.
