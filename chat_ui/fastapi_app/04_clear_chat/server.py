"""
FastAPI step 4: Clear chat button + one memory per browser.

NEW HERE:
    1. A POST /clear route and a "New chat" button that calls it.
    2. SESSIONS: each browser gets its own conversation.

KEY IDEA: until now `messages` was ONE list shared by everyone. A clear
button would wipe everybody's chat! So now:
    - the page makes a random id once (its "session id") and remembers it
      in the browser's localStorage
    - it sends that id with every request
    - the server keeps a dict:  session id -> that browser's messages list

(Streamlit's session_state and Gradio's gr.State did this for us, hidden.)

Run (from the AiAgent_learning folder), then open http://127.0.0.1:8000
    python chat_ui/fastapi_app/04_clear_chat/server.py
"""

import json
import sys
from pathlib import Path

import uvicorn
from fastapi import FastAPI
from fastapi.responses import FileResponse, StreamingResponse
from pydantic import BaseModel, Field

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent.parent))
from agent_core import stream_agent

app = FastAPI()

sessions = {}  # NEW: session id -> that browser's messages list

# Only letters, digits and dashes, so an id can never be something strange
# (step 5 uses it as a file name).
SessionId = Field(pattern=r"^[A-Za-z0-9-]{1,64}$")


class ChatRequest(BaseModel):
    session_id: str = SessionId  # NEW
    message: str


class ClearRequest(BaseModel):
    session_id: str = SessionId


def get_messages(session_id: str) -> list:
    """This browser's memory. A new browser starts with an empty list."""
    if session_id not in sessions:
        sessions[session_id] = []
    return sessions[session_id]


@app.get("/")
def home():
    return FileResponse(HERE / "static" / "index.html")


@app.post("/chat")
def chat(request: ChatRequest):
    messages = get_messages(request.session_id)  # NEW: this browser's memory
    messages.append({"role": "user", "content": request.message})

    def events():
        for event in stream_agent(messages):
            yield json.dumps(event) + "\n"

    return StreamingResponse(events(), media_type="application/x-ndjson")


@app.post("/clear")
def clear(request: ClearRequest):
    """NEW: forget this browser's conversation."""
    sessions[request.session_id] = []
    return {"ok": True}


if __name__ == "__main__":
    uvicorn.run(app, host="127.0.0.1", port=8000)
