"""
Lesson 18: Deployment. The FastAPI chat (chat_ui step 5), ready for a server.

What changes when other people can reach your app over the internet:

    AUTH          Anyone who finds the URL could spend YOUR Claude credits.
                  Every /chat, /history, /clear request needs an access key
                  (header X-Access-Key). Keys live in the APP_ACCESS_KEYS env var.
    ISOLATION     Each key has its own folder of chat histories, so one user
                  can never read another user's chat, even with the same session id.
    RATE LIMIT    At most RATE_LIMIT_PER_MINUTE messages per key per minute (429 after).
    INPUT LIMITS  Message length is capped; ids are checked with a pattern.
    ERRORS        API failures become an "error" event; the server keeps running.
    CONFIG        Everything comes from environment variables (.env locally,
                  real env vars on the server). No secrets in the code or in git.
    HEALTH        GET /health lets Docker / your host check the app is alive.
    LOGS          One log line per request and per Claude call (with request_id).
    HTTPS         Done by a reverse proxy in front (Caddy, see README.md), not here.

Run locally (from this folder):
    cp .env.example .env        then edit .env
    python server.py            open http://127.0.0.1:8000 and paste an access key

See README.md for Docker and deploying to a server with HTTPS.
"""

import hashlib
import json
import logging
import os
import secrets
import time
from collections import defaultdict, deque
from pathlib import Path

from dotenv import load_dotenv

HERE = Path(__file__).resolve().parent
load_dotenv(HERE / ".env")  # local development; on a server, set real env vars instead

import uvicorn  # noqa: E402
from fastapi import Depends, FastAPI, Header, HTTPException, Query  # noqa: E402
from fastapi.responses import FileResponse, StreamingResponse  # noqa: E402
from pydantic import BaseModel, Field  # noqa: E402

from agent import load_history, save_history, stream_agent  # noqa: E402

# ---------------------------------------------------------------------------
# Settings (from the environment).
# ---------------------------------------------------------------------------
if not os.getenv("ANTHROPIC_API_KEY"):
    raise SystemExit("ANTHROPIC_API_KEY is not set.")
ACCESS_KEYS = [k.strip() for k in os.getenv("APP_ACCESS_KEYS", "").split(",") if k.strip()]
if not ACCESS_KEYS:
    raise SystemExit("APP_ACCESS_KEYS is not set. Make one with: python -c \"import secrets; print(secrets.token_urlsafe(24))\"")
RATE_LIMIT_PER_MINUTE = int(os.getenv("RATE_LIMIT_PER_MINUTE", "10"))
MAX_MESSAGE_CHARS = int(os.getenv("MAX_MESSAGE_CHARS", "2000"))
DATA_DIR = Path(os.getenv("DATA_DIR", HERE / "data"))
HOST = os.getenv("HOST", "127.0.0.1")  # 127.0.0.1 = only this computer; Docker sets 0.0.0.0
PORT = int(os.getenv("PORT", "8000"))

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
log = logging.getLogger("server")

app = FastAPI(docs_url=None, redoc_url=None)  # no public API docs page in production

SESSION_ID_PATTERN = r"^[A-Za-z0-9-]{1,64}$"


# ---------------------------------------------------------------------------
# Auth + rate limit, as a FastAPI dependency: any route that lists
# `user: str = Depends(require_user)` is protected.
# ---------------------------------------------------------------------------
recent_requests: dict[str, deque] = defaultdict(deque)


def require_user(x_access_key: str = Header(default="")) -> str:
    # compare_digest takes the same time whether the key is nearly right or
    # totally wrong, so attackers can't guess it character by character.
    if not any(secrets.compare_digest(x_access_key, key) for key in ACCESS_KEYS):
        raise HTTPException(status_code=401, detail="Missing or wrong access key.")
    # Never log or store the key itself: use a short hash as the user id.
    return hashlib.sha256(x_access_key.encode()).hexdigest()[:16]


def check_rate_limit(user: str) -> None:
    now = time.time()
    window = recent_requests[user]
    while window and now - window[0] > 60:
        window.popleft()
    if len(window) >= RATE_LIMIT_PER_MINUTE:
        raise HTTPException(status_code=429, detail=f"Too many messages: max {RATE_LIMIT_PER_MINUTE} per minute.")
    window.append(now)


# ---------------------------------------------------------------------------
# Sessions: memory in RAM, saved to DATA_DIR/<user>/<session>.json
# ---------------------------------------------------------------------------
sessions: dict[tuple[str, str], list] = {}


def history_file(user: str, session_id: str) -> Path:
    return DATA_DIR / user / f"{session_id}.json"


def get_messages(user: str, session_id: str) -> list:
    key = (user, session_id)
    if key not in sessions:
        sessions[key] = load_history(history_file(user, session_id))
    return sessions[key]


def to_events(messages: list) -> list:
    """Saved memory -> the same events /chat streams (see chat_ui step 5)."""
    results = {
        b["tool_use_id"]: b["content"]
        for m in messages if isinstance(m["content"], list)
        for b in m["content"] if b["type"] == "tool_result"
    }
    events = []
    for m in messages:
        if isinstance(m["content"], str):
            events.append({"type": "user", "text": m["content"]})
        elif m["role"] == "assistant":
            for b in m["content"]:
                if b["type"] == "text":
                    events.append({"type": "text", "text": b["text"]})
                elif b["type"] == "tool_use":
                    events.append({"type": "tool_call", "name": b["name"], "input": b["input"]})
                    events.append({"type": "tool_result", "name": b["name"], "result": results.get(b["id"], "")})
    return events


class ChatRequest(BaseModel):
    session_id: str = Field(pattern=SESSION_ID_PATTERN)
    message: str = Field(min_length=1, max_length=MAX_MESSAGE_CHARS)


class ClearRequest(BaseModel):
    session_id: str = Field(pattern=SESSION_ID_PATTERN)


# ---------------------------------------------------------------------------
# Routes.
# ---------------------------------------------------------------------------
@app.get("/health")
def health():
    return {"status": "ok"}


@app.get("/")
def home():
    return FileResponse(HERE / "static" / "index.html")


@app.get("/history")
def history(session_id: str = Query(pattern=SESSION_ID_PATTERN), user: str = Depends(require_user)):
    return to_events(get_messages(user, session_id))


@app.post("/chat")
def chat(request: ChatRequest, user: str = Depends(require_user)):
    check_rate_limit(user)
    log.info("chat user=%s session=%s chars=%d", user, request.session_id, len(request.message))
    messages = get_messages(user, request.session_id)
    messages.append({"role": "user", "content": request.message})

    def events():
        for event in stream_agent(messages):
            yield json.dumps(event) + "\n"
        save_history(messages, history_file(user, request.session_id))

    return StreamingResponse(events(), media_type="application/x-ndjson")


@app.post("/clear")
def clear(request: ClearRequest, user: str = Depends(require_user)):
    sessions[(user, request.session_id)] = []
    history_file(user, request.session_id).unlink(missing_ok=True)
    return {"ok": True}


if __name__ == "__main__":
    # ONE worker: sessions live in this process's memory. To run several
    # workers or servers, move sessions to a database (e.g. Redis/Postgres).
    uvicorn.run(app, host=HOST, port=PORT, proxy_headers=True)
