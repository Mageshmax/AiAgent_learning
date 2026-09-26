"""
FastAPI step 5: Save chat history (one file per browser).

NEW HERE:
    1. Each session's memory is saved to history/<session id>.json after
       every reply, and loaded from that file when the server doesn't have
       it in memory yet (for example after a restart).
    2. A GET /history route. When the page opens, it asks for its old chat
       and draws it again.

KEY IDEA: /history does not send Claude's raw memory. It sends the SAME
kind of events that /chat streams ("text", "tool_call", "tool_result"), plus
a "user" event for each question. So the page redraws old chats with the
same handleEvent() function it uses for live replies: no second drawing code.

Unlike Gradio step 5 (one shared file), every browser has its own file.

Run (from the AiAgent_learning folder), then open http://127.0.0.1:8000
    python chat_ui/fastapi_app/05_save_history/server.py
"""

import json
import sys
from pathlib import Path

import uvicorn
from fastapi import FastAPI, Query
from fastapi.responses import FileResponse, StreamingResponse
from pydantic import BaseModel, Field

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent.parent))
from agent_core import load_history, save_history, stream_agent

HISTORY_DIR = HERE / "history"  # NEW: one JSON file per session in here

app = FastAPI()

sessions = {}

SESSION_ID_PATTERN = r"^[A-Za-z0-9-]{1,64}$"  # safe to use as a file name


class ChatRequest(BaseModel):
    session_id: str = Field(pattern=SESSION_ID_PATTERN)
    message: str


class ClearRequest(BaseModel):
    session_id: str = Field(pattern=SESSION_ID_PATTERN)


def history_file(session_id: str) -> Path:
    return HISTORY_DIR / f"{session_id}.json"


def get_messages(session_id: str) -> list:
    """This browser's memory: from RAM if we have it, else from its file."""
    if session_id not in sessions:
        sessions[session_id] = load_history(history_file(session_id))  # NEW
    return sessions[session_id]


def to_events(messages: list) -> list:
    """NEW: Claude's memory -> the same events /chat streams, plus "user" events."""
    results = {
        block["tool_use_id"]: block["content"]
        for m in messages if isinstance(m["content"], list)
        for block in m["content"] if block["type"] == "tool_result"
    }
    events = []
    for message in messages:
        content = message["content"]
        if isinstance(content, str):  # a question the user typed
            events.append({"type": "user", "text": content})
        elif message["role"] == "assistant":
            for block in content:
                if block["type"] == "text":
                    events.append({"type": "text", "text": block["text"]})
                elif block["type"] == "tool_use":
                    events.append({"type": "tool_call", "name": block["name"], "input": block["input"]})
                    events.append({"type": "tool_result", "name": block["name"],
                                   "result": results.get(block["id"], "(no result)")})
    return events


@app.get("/")
def home():
    return FileResponse(HERE / "static" / "index.html")


@app.get("/history")
def history(session_id: str = Query(pattern=SESSION_ID_PATTERN)):
    """NEW: the old conversation, as events, so the page can redraw it."""
    return to_events(get_messages(session_id))


@app.post("/chat")
def chat(request: ChatRequest):
    messages = get_messages(request.session_id)
    messages.append({"role": "user", "content": request.message})

    def events():
        for event in stream_agent(messages):
            yield json.dumps(event) + "\n"
        save_history(messages, history_file(request.session_id))  # NEW: save after the reply

    return StreamingResponse(events(), media_type="application/x-ndjson")


@app.post("/clear")
def clear(request: ClearRequest):
    sessions[request.session_id] = []
    history_file(request.session_id).unlink(missing_ok=True)  # NEW: delete the saved file
    return {"ok": True}


if __name__ == "__main__":
    uvicorn.run(app, host="127.0.0.1", port=8000)
