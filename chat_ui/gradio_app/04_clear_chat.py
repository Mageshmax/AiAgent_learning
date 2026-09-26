"""
Gradio step 4: Clear chat button.

NEW HERE: a "New chat" button that clears the screen AND Claude's memory.

KEY IDEA: gr.ChatInterface is a ready-made page, so it is hard to add our
own button that also empties our state. So this step builds the page by
hand with gr.Blocks, the "Lego" way to build Gradio apps:

    1. PLACE components inside `with gr.Blocks() as demo:`
         gr.Chatbot  -> the chat area
         gr.Textbox  -> the input box
         gr.Button   -> the clear button
         gr.State    -> our Claude memory (invisible)
    2. CONNECT events to functions:
         textbox.submit(fn, inputs=[...], outputs=[...])
         button.click(fn, inputs=[...], outputs=[...])
       Gradio passes the `inputs` components' values into fn, and puts
       what fn returns (or yields) into the `outputs` components, in order.

Clearing = returning empty lists for BOTH the chatbot (screen) and the
state (memory). Emptying only the screen would leave Claude remembering.

Run (from the AiAgent_learning folder), then open http://127.0.0.1:7860
    python chat_ui/gradio_app/04_clear_chat.py
"""

import json
import sys
from pathlib import Path

import gradio as gr

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from agent_core import stream_agent


def tool_label(name: str, tool_input: dict) -> str:
    return f"🔧 {name}({json.dumps(tool_input)})"


def respond(question: str, chat: list, messages: list):
    """Yields (textbox value, chatbot value, memory) as events arrive."""
    if not question.strip():
        return
    messages.append({"role": "user", "content": question})
    chat = chat + [gr.ChatMessage(role="user", content=question)]
    reply = []
    yield "", chat, messages  # clear the textbox and show the question right away

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


def clear_chat():
    """Empty BOTH the screen (chatbot) and Claude's memory (state)."""
    return [], []


# 1. PLACE the components.
with gr.Blocks(title="Claude Chat Agent") as demo:
    gr.Markdown("# 🤖 Claude Chat Agent")
    chatbot = gr.Chatbot(height=500)
    textbox = gr.Textbox(
        placeholder="Ask me anything (weather, time, maths...)",
        show_label=False,
        submit_btn=True,
    )
    clear_button = gr.Button("🗑️ New chat")
    state = gr.State([])  # our Claude memory, one per browser tab

    # 2. CONNECT events to functions.
    textbox.submit(respond, inputs=[textbox, chatbot, state], outputs=[textbox, chatbot, state])
    clear_button.click(clear_chat, inputs=None, outputs=[chatbot, state])

if __name__ == "__main__":
    demo.launch()
