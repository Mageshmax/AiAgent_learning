"""
Gradio step 2: Streaming replies.

NEW HERE: the answer appears word by word instead of all at once.

KEY IDEA: if `respond()` uses `yield` instead of `return`, Gradio treats it
as a stream. Every `yield` REPLACES the reply on screen, so we yield the
answer-so-far, growing a little each time:
    yield "Hel"  ->  yield "Hello"  ->  yield "Hello there"

stream_agent also yields tool events. In this step we keep only the
"text" events; step 3 shows the tool events.

Compare with 01_basic.py: only respond() changed.

Run (from the AiAgent_learning folder), then open http://127.0.0.1:7860
    python chat_ui/gradio_app/02_streaming.py
"""

import sys
from pathlib import Path

import gradio as gr

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from agent_core import stream_agent


def respond(question: str, history: list, messages: list):
    """A generator: yields (answer so far, memory) while Claude is writing."""
    messages.append({"role": "user", "content": question})
    answer = ""
    for event in stream_agent(messages):
        if event["type"] == "text":
            answer += event["text"]
        elif event["type"] == "tool_call" and answer:
            answer += "\n\n"  # keep text from before and after a tool call apart
        yield answer, messages


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
