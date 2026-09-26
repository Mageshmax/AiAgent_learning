"""
FastAPI step 2: Streaming replies.

NEW HERE: the server sends the answer piece by piece, and the page shows
each piece the moment it arrives.

KEY IDEA: a normal response is sent all at once when the function returns.
A StreamingResponse is built from a GENERATOR: every `yield` is sent to the
browser straight away, while the connection stays open.

We send NDJSON ("newline-delimited JSON"): one small JSON object per line,
one line per event from stream_agent:
    {"type": "text", "text": "It's "}
    {"type": "text", "text": "11:49 PM"}
    ...

Compare with 01_basic: only the /chat route changed (and the page's JavaScript).

Run (from the AiAgent_learning folder), then open http://127.0.0.1:8000
    python chat_ui/fastapi_app/02_streaming/server.py
Watch the raw stream in a terminal:
    curl -N -X POST http://127.0.0.1:8000/chat -H "Content-Type: application/json" -d '{"message": "Hi"}'
"""

import json
import sys
from pathlib import Path

import uvicorn
from fastapi import FastAPI
from fastapi.responses import FileResponse, StreamingResponse
from pydantic import BaseModel

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent.parent))
from agent_core import stream_agent

app = FastAPI()

messages = []


class ChatRequest(BaseModel):
    message: str


@app.get("/")
def home():
    return FileResponse(HERE / "static" / "index.html")


@app.post("/chat")
def chat(request: ChatRequest):
    """Stream the agent's events to the browser, one JSON object per line."""
    messages.append({"role": "user", "content": request.message})

    def events():
        for event in stream_agent(messages):
            yield json.dumps(event) + "\n"

    return StreamingResponse(events(), media_type="application/x-ndjson")


if __name__ == "__main__":
    uvicorn.run(app, host="127.0.0.1", port=8000)
