# local-tool-ai

A local agentic loop that connects to [LM Studio](https://lmstudio.ai)'s OpenAI-compatible API and answers queries by calling Python-backed tools — file search, folder listing, file reading, and bash execution.

Available as both a **web chat UI** (streaming, conversation history) and a **CLI**.

## Requirements

- [LM Studio](https://lmstudio.ai) running locally with a model loaded
- [uv](https://docs.astral.sh/uv/) for Python environment management

## Setup

```bash
cp .env.example .env
# edit .env — set LM_STUDIO_MODEL to whatever model is loaded in LM Studio
uv sync
```

## Install globally (recommended)

```bash
uv tool install .
ai-agent init        # one-time: creates ~/.config/local-tool-ai/.env with a generated auth token
```

Then, from any folder:

```bash
ai-agent             # TUI mode, scoped to the current directory
ai-agent gui         # Web UI, scoped to the current directory
```

`ai-agent` automatically sets `ALLOWED_ROOT` to your current working directory so the agent can only read/search inside it (Claude-Code-style scoping).

### Config lookup order

Both entrypoints load `.env` from, in order (earlier wins):

1. `$PWD/.env` (or any ancestor) — per-project config
2. `~/.config/local-tool-ai/.env` — user-global config (populated by `ai-agent init`)

You can override `LM_STUDIO_MODEL`, `WEB_AUTH_TOKEN`, etc. per project by dropping a `.env` next to your code.

## Web UI

```bash
ai-agent gui
# or, from the repo:
uv run server
# open http://localhost:7860
```

Features:
- Streaming responses token by token
- Persistent conversation history per browser session
- Collapsible tool-call cards showing arguments and results
- "New conversation" button to reset history

## CLI

**Single query:**
```bash
uv run main "find all Python files in the current directory"
```

**Interactive REPL:**
```bash
ai-agent
# or
uv run main --repl
```

**Options:**
```
--model   -m   Override LM_STUDIO_MODEL
--system  -s   Override the system prompt
--quiet   -q   Suppress step-by-step tool output
--repl    -r   Start interactive REPL mode
--safe         Disable destructive tools
--enable-bash  Enable run_bash (trusted environments only)
```

## Tools

| Tool | Description |
|---|---|
| `search_files` | Recursively search for files by glob pattern |
| `list_folder` | List directory contents with file sizes |
| `read_file` | Read file contents, optionally scoped to a line range |
| `read_pdf` | Extract text from a PDF as markdown |
| `read_docx` | Extract text from a `.docx` file |
| `git_status` / `git_log` / `git_tags` / `git_show` / `git_diff` | Read-only git introspection. `git_log` takes `revision_range`, `paths`, `no_merges`, `with_stat`; `git_diff` takes `staged`, `base`/`head`, `paths`, `stat_only`; `git_tags` is sorted by version with dates |
| `git_commit_context` | Everything needed for a commit message in one call: staged/unstaged diffs, untracked files, recent commit style |
| `git_range_report` | Structured changes between two refs (commits grouped by type, authors, PRs, diffstat) |
| `git_release_notes_context` | One `git_range_report` per consecutive pair of tags, e.g. `3.0.0→3.0.1`, `3.0.1→3.0.2` |
| `run_bash` | Execute a shell command (allowlisted, off by default) |

### Git context

Git tools default to the current repository (`repo_path` is optional). When the
working directory is a git repo, a snapshot (status, last 10 commits, 15 newest
tags) is added to the system prompt on every turn, so the model needs fewer
discovery calls. Large diffs are trimmed per file, lock/generated files are
skipped, and omitted files are listed so the model can ask for them.

## Project layout

```
local-tool-ai/
├── local_tool_ai/
│   ├── cli.py          # `ai-agent [tui|gui]` dispatcher
│   ├── agent.py        # Agentic loop (CLI) + run_events async generator (web)
│   ├── main.py         # TUI entry point
│   ├── server.py       # FastAPI web server
│   ├── static/
│   │   └── index.html  # Web chat UI (self-contained)
│   └── tools/
│       ├── registry.py # Schema aggregator + dispatch()
│       ├── search_files.py
│       ├── list_folder.py
│       ├── read_file.py
│       ├── read_pdf.py
│       ├── read_docx.py
│       ├── git.py
│       └── run_bash.py
└── tests/              # Unit tests, no LLM required
```

## Development

```bash
uv run pytest tests/ -v                     # run tests
uv run ruff check .                         # lint
uv run ruff format .                        # format
uvicorn local_tool_ai.server:app --reload   # web server with auto-reload
```

## Configuration

All config lives in `.env`:

```
LM_STUDIO_BASE_URL=http://localhost:1234/v1
LM_STUDIO_MODEL=qwen2.5-14b-instruct
LM_STUDIO_API_KEY=lm-studio
MAX_ITERATIONS=20
WEB_PORT=7860
```

`MAX_ITERATIONS` caps the tool-call loop to prevent infinite cycles.

Optional git settings:

```
GIT_CONTEXT_MAX_CHARS=20000   # output budget of git_commit_context / git_range_report
REPO_CONTEXT=1                # set to 0 to disable the git snapshot in the system prompt
```

Keep LM Studio's context length for the model well above `GIT_CONTEXT_MAX_CHARS`
(about 16k tokens or more).
