"""
Gradio step 3: Show tool calls in the chat.

NEW HERE: every tool call appears as a collapsible box inside the reply,
showing what Claude asked for and what our code returned.

KEY IDEA: instead of yielding one string, `respond()` now yields a LIST of
gr.ChatMessage objects. A message with `metadata={"title": ...}` is drawn by
Gradio as a collapsible box (no extra code needed):

    gr.ChatMessage(content="34°C, humid, sunny",
                   metadata={"title": "🔧 get_weather({...})", "status": "done"})

    "text"        -> add to the last text message (or start a new one)
    "tool_call"   -> add a tool box with status "pending" (shows a spinner)
    "tool_result" -> put the result in that box, set status "done"

Run (from the AiAgent_learning folder), then open http://127.0.0.1:7860
    python chat_ui/gradio_app/03_tool_calls.py
"""

import json
import sys
from pathlib import Path

import gradio as gr

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from agent_core import stream_agent


def tool_label(name: str, tool_input: dict) -> str:
    return f"🔧 {name}({json.dumps(tool_input)})"


def respond(question: str, history: list, messages: list):
    """Yields (list of ChatMessages for this reply, memory) as events arrive."""
    messages.append({"role": "user", "content": question})
    reply = []  # the text messages and tool boxes that make up this answer

    for event in stream_agent(messages):
        if event["type"] == "text":
            if not reply or reply[-1].metadata:  # last one is a tool box -> new text message
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
        yield reply, messages


state = gr.State([])

demo = gr.ChatInterface(
    fn=respond,
    title="🤖 Claude Chat Agent",
    textbox=gr.Textbox(placeholder="Ask me anything (weather, time, maths...)"),
    additional_inputs=[state],
    additional_outputs=[state],
)

if __name__ == "__main__":
    demo.launch()
