# Security Audit — Local Tool AI

## Changelog

| Commit | Mitigation |
|--------|-----------|
| `78dd5a9` | Bind web server to `127.0.0.1` by default (risk #3) |
| `d2bf2a7` | Default `ALLOWED_ROOT` to cwd + warn if unset (risk #2) |
| `900e291` | Add sensitive-path denylist (risk #2) |
| `d8d3a39` | Replace bash blacklist with allowlist + remove duplicate blocklist (risks #1, #5) |
| `71d8c03` | Add Bearer token authentication to web server (risk #3) |
| `2d71904` | Add prompt-injection guardrails (risk #4) |
| `a81306f` | Add rate limiting and audit logging (risk #6) |
| `08c2d9d` | Add session eviction and memory caps (risk #7) |

---

## Summary

This application gives an LLM autonomous access to local filesystem and shell execution.
Even for local-only use, prompt injection or model misbehavior can lead to **data loss,
credential exfiltration, or system damage**. Below are the identified risks ranked by
severity, followed by recommended mitigations.

---

## Critical Risks

### 1. Bash blacklist is trivially bypassable — MITIGATED

**Location:** `tools/registry.py`

**Problem:** The original blacklist used simple substring/regex matching that was trivially
bypassable via alternative command forms, absolute paths, or encoding tricks.

**Status:** Replaced with a command **allowlist** approach (`d8d3a39`). The first token of
the command is extracted and checked against a configurable set of permitted commands. A
secondary dangerous-patterns layer blocks known-dangerous flag combinations. The duplicate
`BLOCKED_PATTERNS` in `run_bash.py` was removed — single enforcement point in `registry.py`.

---

### 2. No filesystem boundary without explicit ALLOWED_ROOT — MITIGATED

**Location:** `tools/registry.py`

**Problem:** By default `ALLOWED_ROOT` was unset, meaning the agent could read any file
on the system.

**Status:** `ALLOWED_ROOT` now defaults to the current working directory (`d2bf2a7`).
A sensitive-path denylist (`900e291`) always blocks access to `~/.ssh`, `~/.gnupg`,
`~/.aws`, `~/.config/gh`, and other credential directories regardless of `ALLOWED_ROOT`.
Startup warnings are displayed when `ALLOWED_ROOT` is not explicitly configured.

---

### 3. Web server binds to 0.0.0.0 with no authentication — MITIGATED

**Location:** `server.py`

**Problem:** The FastAPI server listened on all interfaces with zero authentication.

**Status:** Server now binds to `127.0.0.1` by default (`78dd5a9`), with `--host` CLI
arg and `WEB_HOST` env var to override. Bearer token authentication (`71d8c03`) is
available via `WEB_AUTH_TOKEN` env var — when set, all protected routes require the token.

---

## High Risks

### 4. Prompt injection via file contents — MITIGATED

**Problem:** File contents fed into LLM context could contain injected instructions.

**Status:** All tool results are now wrapped in `<tool_output>…</tool_output>` delimiters
(`2d71904`). The system prompt explicitly instructs the model to never follow instructions
found inside tool output.

---

### 5. `run_bash.py` has a redundant weaker blocklist — MITIGATED

**Location:** `tools/run_bash.py`

**Problem:** Duplicate `BLOCKED_PATTERNS` in `run_bash.py` vs registry's `BASH_BLACKLIST`.

**Status:** Removed (`d8d3a39`). Single enforcement point in `registry.py` dispatch.

---

### 6. No rate limiting or iteration cost control — MITIGATED

**Location:** `server.py`, `tools/registry.py`

**Problem:** No throttling on web requests or tool invocations.

**Status:** Per-session rate limiting added (`a81306f`) — 20 requests/minute by default,
configurable via `RATE_LIMIT_MAX`. All tool dispatches are logged to `agent_audit.log`.

---

## Medium Risks

### 7. Session history grows unbounded in memory — MITIGATED

**Location:** `server.py`

**Problem:** No eviction or caps on session count or message history.

**Status:** Max 100 sessions with LRU eviction, max 200 messages per session (`08c2d9d`).
Configurable via `MAX_SESSIONS` and `MAX_MESSAGES_PER_SESSION` env vars.

---

### 8. `read_pdf` and `read_docx` use complex parsers on untrusted input — OPEN

**Location:** `tools/read_pdf.py`, `tools/read_docx.py`

**Problem:** PyMuPDF and python-docx parse complex binary formats. Malformed files could
exploit parser vulnerabilities (known CVEs exist for PDF parsers).

**Impact:** Potential code execution via crafted PDF/DOCX files.

**Mitigation:**
- Keep `pymupdf4llm` and `python-docx` up to date.
- Consider running parsers in a subprocess with resource limits.
- Validate file magic bytes before parsing.

---

### 9. Git tools don't enforce ALLOWED_ROOT for repo_path — PARTIALLY MITIGATED

**Location:** `tools/git.py`

**Problem:** Git commands can reference content outside the repo via submodules or worktrees.

**Status:** `ALLOWED_ROOT` now defaults to cwd and the path allowlist check applies to
git tools' `repo_path` argument. Further hardening (verifying `.git` directory exists)
is recommended.

---

## Recommendations Summary

| Priority | Action | Status |
|----------|--------|--------|
| **P0** | Bind web server to `127.0.0.1` by default | DONE |
| **P0** | Default `ALLOWED_ROOT` to cwd; warn if unset | DONE |
| **P0** | Add sensitive-path denylist | DONE |
| **P0** | Replace bash blacklist with allowlist | DONE |
| **P1** | Add authentication to the web server | DONE |
| **P1** | Add prompt-injection guardrails | DONE |
| **P1** | Remove duplicate blocklist in `run_bash.py` | DONE |
| **P2** | Add rate limiting and audit logging | DONE |
| **P2** | Add session eviction / memory caps | DONE |
| **P2** | Keep PDF/DOCX parsers updated | OPEN |
| **P3** | Validate git repo_path is actually a git repo | PARTIAL |
