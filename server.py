"""FastAPI web server: chat UI with SSE streaming and per-session history."""

from __future__ import annotations

import asyncio
import json
import os
import uuid
from pathlib import Path

_env = Path(__file__).parent / ".env"
if _env.exists():
    from dotenv import load_dotenv

    load_dotenv(_env)

import agent
from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, JSONResponse, StreamingResponse

app = FastAPI(title="Local Tool AI")

# In-memory session store: session_id -> message list (includes system message)
_sessions: dict[str, list] = {}

# Pending web-based confirmation futures: session_id -> Future[bool]
_pending_confirmations: dict[str, asyncio.Future] = {}

_STATIC = Path(__file__).parent / "static"


@app.get("/", response_class=HTMLResponse)
async def index() -> HTMLResponse:
    return HTMLResponse((_STATIC / "index.html").read_text())


@app.get("/info")
async def info() -> JSONResponse:
    return JSONResponse({"model": os.environ.get("LM_STUDIO_MODEL", "unknown")})


@app.post("/chat")
async def chat(request: Request) -> StreamingResponse:
    session_id = request.headers.get("X-Session-ID") or str(uuid.uuid4())

    body = await request.json()
    user_message: str = body.get("message", "").strip()
    if not user_message:
        return JSONResponse({"error": "empty message"}, status_code=400)

    if session_id not in _sessions:
        _sessions[session_id] = [{"role": "system", "content": agent.DEFAULT_SYSTEM}]

    messages = _sessions[session_id]
    messages.append({"role": "user", "content": user_message})

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
    if session_id and session_id in _sessions:
        del _sessions[session_id]
    return JSONResponse({"ok": True})


def run() -> None:
    import uvicorn

    port = int(os.environ.get("WEB_PORT", "7860"))
    uvicorn.run(app, host="0.0.0.0", port=port, log_level="info")


if __name__ == "__main__":
    run()
