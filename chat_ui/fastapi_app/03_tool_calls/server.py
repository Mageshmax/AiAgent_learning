"""
FastAPI step 3: Show tool calls in the chat.

NEW HERE: nothing in Python! The server already streams ALL of
stream_agent's events (text, tool_call, tool_result) since step 2; the page
simply ignored the tool events. Only static/index.html changed: it now
draws each tool call as a <details> box (a built-in HTML collapsible box).

KEY IDEA: with a frontend/backend split, a new UI feature often needs no
backend change at all, as long as the API already sends the data.

Run (from the AiAgent_learning folder), then open http://127.0.0.1:8000
    python chat_ui/fastapi_app/03_tool_calls/server.py
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
