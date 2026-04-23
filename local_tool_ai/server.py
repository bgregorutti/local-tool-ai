"""FastAPI web server: chat UI with SSE streaming and per-session history."""

from __future__ import annotations

import asyncio
import json
import os
import time
import uuid
from collections import defaultdict
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

import hmac

from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, JSONResponse, StreamingResponse

from local_tool_ai import agent
from local_tool_ai.tools.registry import _allowed_root_is_explicit, _get_allowed_root

app = FastAPI(title="Local Tool AI")

_AUTH_TOKEN: str | None = os.environ.get("WEB_AUTH_TOKEN", "").strip() or None

# Routes that skip auth (public endpoints)
_PUBLIC_ROUTES: frozenset[str] = frozenset({"/", "/info"})

# Rate limiting: per-session request timestamps
_RATE_LIMIT_MAX = int(os.environ.get("RATE_LIMIT_MAX", "20"))  # max requests per window
_RATE_LIMIT_WINDOW = 60  # seconds
_rate_limits: dict[str, list[float]] = defaultdict(list)


@app.middleware("http")
async def _auth_middleware(request: Request, call_next):
    """Require Bearer token on protected routes when WEB_AUTH_TOKEN is set."""
    if _AUTH_TOKEN and request.url.path not in _PUBLIC_ROUTES:
        auth_header = request.headers.get("Authorization", "")
        if not auth_header.startswith("Bearer "):
            return JSONResponse({"error": "unauthorized"}, status_code=401)
        token = auth_header[len("Bearer "):]
        if not hmac.compare_digest(token, _AUTH_TOKEN):
            return JSONResponse({"error": "unauthorized"}, status_code=401)
    return await call_next(request)


@app.on_event("startup")
async def _startup() -> None:
    if not _allowed_root_is_explicit():
        print(
            f"⚠️  ALLOWED_ROOT not set — defaulting to cwd: {_get_allowed_root()}"
        )
    if _AUTH_TOKEN:
        print("🔒 Authentication enabled (WEB_AUTH_TOKEN is set).")
    else:
        print("⚠️  No WEB_AUTH_TOKEN set — web server has no authentication.")
    if os.environ.get("BASH_ENABLED") == "1":
        print("⚠️  run_bash is enabled. Only use this in a trusted environment.")


# Session limits
_MAX_SESSIONS = int(os.environ.get("MAX_SESSIONS", "100"))
_MAX_MESSAGES_PER_SESSION = int(os.environ.get("MAX_MESSAGES_PER_SESSION", "200"))

# In-memory session store: session_id -> {"messages": list, "last_active": float}
_sessions: dict[str, dict] = {}

# Pending web-based confirmation futures: session_id -> Future[bool]
_pending_confirmations: dict[str, asyncio.Future] = {}


def _get_or_create_session(session_id: str) -> list:
    """Get or create a session, enforcing max sessions via LRU eviction."""
    if session_id in _sessions:
        _sessions[session_id]["last_active"] = time.monotonic()
        return _sessions[session_id]["messages"]

    # Evict oldest sessions if at capacity
    while len(_sessions) >= _MAX_SESSIONS:
        oldest_id = min(_sessions, key=lambda k: _sessions[k]["last_active"])
        del _sessions[oldest_id]

    _sessions[session_id] = {
        "messages": [{"role": "system", "content": agent.DEFAULT_SYSTEM}],
        "last_active": time.monotonic(),
    }
    return _sessions[session_id]["messages"]


def _trim_messages(messages: list) -> None:
    """Drop oldest non-system messages if over the cap."""
    while len(messages) > _MAX_MESSAGES_PER_SESSION:
        # Keep the system message at index 0, remove the oldest after it
        messages.pop(1)

_STATIC = Path(__file__).parent / "static"


@app.get("/", response_class=HTMLResponse)
async def index() -> HTMLResponse:
    return HTMLResponse((_STATIC / "index.html").read_text())


@app.get("/info")
async def info() -> JSONResponse:
    return JSONResponse({"model": os.environ.get("LM_STUDIO_MODEL", "unknown")})


def _check_rate_limit(session_id: str) -> bool:
    """Return True if the session is within rate limits."""
    now = time.monotonic()
    timestamps = _rate_limits[session_id]
    # Prune old entries
    cutoff = now - _RATE_LIMIT_WINDOW
    _rate_limits[session_id] = [t for t in timestamps if t > cutoff]
    if len(_rate_limits[session_id]) >= _RATE_LIMIT_MAX:
        return False
    _rate_limits[session_id].append(now)
    return True


@app.post("/chat")
async def chat(request: Request) -> StreamingResponse:
    session_id = request.headers.get("X-Session-ID") or str(uuid.uuid4())

    if not _check_rate_limit(session_id):
        return JSONResponse(
            {"error": f"rate limit exceeded ({_RATE_LIMIT_MAX} requests/minute)"},
            status_code=429,
        )

    body = await request.json()
    user_message: str = body.get("message", "").strip()
    if not user_message:
        return JSONResponse({"error": "empty message"}, status_code=400)

    messages = _get_or_create_session(session_id)
    messages.append({"role": "user", "content": user_message})
    _trim_messages(messages)

    async def confirm_destructive(tool_name: str, args: dict) -> bool:  # noqa: ARG001
        """Create a Future, store it, and wait for /confirm to resolve it."""
        loop = asyncio.get_event_loop()
        fut: asyncio.Future[bool] = loop.create_future()
        _pending_confirmations[session_id] = fut
        try:
            return await asyncio.wait_for(asyncio.shield(fut), timeout=300)
        except TimeoutError:
            return False
        finally:
            _pending_confirmations.pop(session_id, None)

    async def event_stream():
        try:
            async for event in agent.run_events(
                messages, confirm_destructive=confirm_destructive
            ):
                yield f"data: {json.dumps(event)}\n\n"
        except Exception as exc:
            yield f"data: {json.dumps({'type': 'error', 'message': str(exc)})}\n\n"
        finally:
            _pending_confirmations.pop(session_id, None)

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@app.post("/confirm")
async def confirm(request: Request) -> JSONResponse:
    """Resolve a pending destructive-tool confirmation for the given session."""
    session_id = request.headers.get("X-Session-ID")
    body = await request.json()
    allowed: bool = bool(body.get("allowed", False))
    fut = _pending_confirmations.get(session_id)
    if fut and not fut.done():
        fut.set_result(allowed)
    return JSONResponse({"ok": True})


@app.post("/reset")
async def reset(request: Request) -> JSONResponse:
    session_id = request.headers.get("X-Session-ID")
    if session_id:
        _sessions.pop(session_id, None)
    return JSONResponse({"ok": True})


def run() -> None:
    import argparse

    import uvicorn

    parser = argparse.ArgumentParser(description="Local Tool AI web server")
    parser.add_argument(
        "--enable-bash",
        action="store_true",
        help="Enable run_bash tool (trusted environments only).",
    )
    parser.add_argument("--port", type=int, default=None, help="Port to listen on.")
    parser.add_argument(
        "--host",
        type=str,
        default=None,
        help="Host to bind to (default: 127.0.0.1). Use 0.0.0.0 to expose on all interfaces.",
    )
    parsed = parser.parse_args()

    if parsed.enable_bash:
        os.environ["BASH_ENABLED"] = "1"
        print("⚠️  run_bash is enabled. Only use this in a trusted environment.")

    host = parsed.host or os.environ.get("WEB_HOST", "127.0.0.1")
    port = parsed.port or int(os.environ.get("WEB_PORT", "7860"))

    if host != "127.0.0.1":
        print(
            f"⚠️  Server binding to {host} — accessible beyond localhost. "
            "Consider adding authentication (WEB_AUTH_TOKEN)."
        )

    uvicorn.run(app, host=host, port=port, log_level="info")


if __name__ == "__main__":
    run()
