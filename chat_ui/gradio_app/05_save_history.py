"""
Gradio step 5: Save chat history.

NEW HERE: the conversation is saved to chat_history.json after every reply
and loaded again when the page opens, so it is still there after a restart.

KEY IDEA: two new pieces.
    save_history(...)  after every reply, and in clear_chat
    demo.load(fn)      Gradio calls fn every time a browser OPENS the page.
                       We use it to load the file and fill BOTH the state
                       (memory) and the chatbot (screen).

The file holds Claude's memory (`messages`), not what the screen shows, so
`to_chatbot()` turns it back into chat bubbles and tool boxes. A tool_use
block (assistant message) is paired with its tool_result (next user
message) by id, just like Streamlit's step 3.

NOTE: the file is shared by every tab and restart; this is a single-user app.
FastAPI step 5 shows how to give each user their own history.

Run (from the AiAgent_learning folder), then open http://127.0.0.1:7860
    python chat_ui/gradio_app/05_save_history.py
"""

import json
import sys
from pathlib import Path

import gradio as gr

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from agent_core import load_history, save_history, stream_agent

HISTORY_FILE = Path(__file__).resolve().parent / "chat_history.json"


def tool_label(name: str, tool_input: dict) -> str:
    return f"🔧 {name}({json.dumps(tool_input)})"


def to_chatbot(messages: list) -> list:
    """Claude's memory -> chat bubbles and tool boxes for gr.Chatbot."""
    results = {
        block["tool_use_id"]: block["content"]
        for m in messages if isinstance(m["content"], list)
        for block in m["content"] if block["type"] == "tool_result"
    }
    chat = []
    for message in messages:
        content = message["content"]
        if isinstance(content, str):  # a question the user typed
            chat.append(gr.ChatMessage(role="user", content=content))
        elif message["role"] == "assistant":
            for block in content:
                if block["type"] == "text":
                    chat.append(gr.ChatMessage(role="assistant", content=block["text"]))
                elif block["type"] == "tool_use":
                    chat.append(gr.ChatMessage(
                        role="assistant",
                        content=results.get(block["id"], "(no result)"),
                        metadata={"title": tool_label(block["name"], block["input"]), "status": "done"},
                    ))
    return chat


def load_chat():
    """Runs when a browser opens the page: fill the screen and the memory."""
    messages = load_history(HISTORY_FILE)
    return to_chatbot(messages), messages


def respond(question: str, chat: list, messages: list):
    """Yields (textbox value, chatbot value, memory) as events arrive."""
    if not question.strip():
        return
    messages.append({"role": "user", "content": question})
    chat = chat + [gr.ChatMessage(role="user", content=question)]
    reply = []
    yield "", chat, messages

    for event in stream_agent(messages):
        if event["type"] == "text":
            if not reply or reply[-1].metadata:
                reply.append(gr.ChatMessage(role="assistant", content=""))
            reply[-1].content += event["text"]
        elif event["type"] == "tool_call":
            reply.append(gr.ChatMessage(
                role="assistant",
                content="",
                metadata={"title": tool_label(event["name"], event["input"]), "status": "pending"},
            ))
        elif event["type"] == "tool_result":
            reply[-1].content = event["result"]
            reply[-1].metadata["status"] = "done"
        yield "", chat + reply, messages

    save_history(messages, HISTORY_FILE)  # NEW: save after every reply


def clear_chat():
    """Empty the screen, the memory AND the saved file."""
    save_history([], HISTORY_FILE)  # NEW
    return [], []


with gr.Blocks(title="Claude Chat Agent") as demo:
    gr.Markdown("# 🤖 Claude Chat Agent")
    chatbot = gr.Chatbot(height=500)
    textbox = gr.Textbox(
        placeholder="Ask me anything (weather, time, maths...)",
        show_label=False,
        submit_btn=True,
    )
    with gr.Row():
        clear_button = gr.Button("🗑️ New chat")
        gr.Markdown(f"Saved to: `{HISTORY_FILE.name}`")
    state = gr.State([])

    textbox.submit(respond, inputs=[textbox, chatbot, state], outputs=[textbox, chatbot, state])
    clear_button.click(clear_chat, inputs=None, outputs=[chatbot, state])
    demo.load(load_chat, inputs=None, outputs=[chatbot, state])  # NEW

if __name__ == "__main__":
    demo.launch()
