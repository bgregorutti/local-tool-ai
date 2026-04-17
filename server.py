"""FastAPI web server: chat UI with SSE streaming and per-session history."""

from __future__ import annotations

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

    async def event_stream():
        try:
            async for event in agent.run_events(messages):
                yield f"data: {json.dumps(event)}\n\n"
        except Exception as exc:
            yield f"data: {json.dumps({'type': 'error', 'message': str(exc)})}\n\n"

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@app.post("/reset")
async def reset(request: Request) -> JSONResponse:
    session_id = request.headers.get("X-Session-ID")
    if session_id and session_id in _sessions:
        del _sessions[session_id]
    return JSONResponse({"ok": True})


if __name__ == "__main__":
    import uvicorn

    port = int(os.environ.get("WEB_PORT", "7860"))
    uvicorn.run(app, host="0.0.0.0", port=port, log_level="info")
