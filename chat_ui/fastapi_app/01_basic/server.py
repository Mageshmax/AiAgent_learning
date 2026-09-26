"""
FastAPI step 1: Basic chat window (backend + frontend).

NEW HERE: we build the web app ourselves, in two separate parts:
    BACKEND  (this file, Python)   -> a web server with a JSON API
    FRONTEND (static/index.html)   -> the chat page, with HTML + CSS + JavaScript

They talk over HTTP, like every website:
    browser  --GET /------------------------------->  server   "give me the page"
    browser  <------------------------ index.html --  server
    browser  --POST /chat {"message": "Hi"}-------->  server   "here is a question"
    browser  <------------- {"reply": "Hello!"} ----  server   "here is the answer"

KEY IDEA: Streamlit and Gradio did this for us, hidden. Here every piece is
visible: the URL routes, the JSON sent both ways, and the page's JavaScript.

NOTE: `messages` is ONE list for the whole server, so everyone who opens the
page shares one conversation. Step 4 gives each browser its own memory.

Run (from the AiAgent_learning folder), then open http://127.0.0.1:8000
    python chat_ui/fastapi_app/01_basic/server.py
"""

import sys
from pathlib import Path

import uvicorn
from fastapi import FastAPI
from fastapi.responses import FileResponse
from pydantic import BaseModel

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent.parent))  # so we can import agent_core
from agent_core import ask_agent

app = FastAPI()

messages = []  # Claude's memory (shared by everyone, see NOTE above)


class ChatRequest(BaseModel):
    """The JSON the browser sends: {"message": "..."}"""
    message: str


@app.get("/")
def home():
    """Send the chat page to the browser."""
    return FileResponse(HERE / "static" / "index.html")


@app.post("/chat")
def chat(request: ChatRequest):
    """Receive a question, run the agent, send back the answer as JSON."""
    messages.append({"role": "user", "content": request.message})
    answer = ask_agent(messages)  # tool loop runs here
    return {"reply": answer}


if __name__ == "__main__":
    uvicorn.run(app, host="127.0.0.1", port=8000)
