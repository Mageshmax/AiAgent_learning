"""
Gradio step 1: Basic chat window.

NEW HERE: a chat window built with Gradio's ready-made gr.ChatInterface.
You only write ONE function, and Gradio builds the whole page around it:

    def respond(question, history, ...):  ->  the answer

KEY IDEA (different from Streamlit): Gradio does NOT rerun your script.
The script runs once, builds the page, and then Gradio calls `respond()`
every time you send a message.

Gradio passes `history` (what is shown on screen), but that is only text.
Claude's memory also needs tool_use / tool_result blocks, so we keep our
own `messages` list in a gr.State:
    additional_inputs=[state]   -> Gradio passes our list INTO respond()
    additional_outputs=[state]  -> respond() hands the updated list BACK
Each browser tab gets its own copy of the state.

NOTE: the 🗑 icon on the chat only clears the SCREEN; Claude still remembers
(our state list is not emptied). Step 4 builds a proper "New chat" button.

Run (from the AiAgent_learning folder), then open http://127.0.0.1:7860
    python chat_ui/gradio_app/01_basic.py
"""

import sys
from pathlib import Path

import gradio as gr

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))  # so we can import agent_core
from agent_core import ask_agent


def respond(question: str, history: list, messages: list):
    """Called by Gradio for every new message. Returns (answer, updated memory)."""
    messages.append({"role": "user", "content": question})
    answer = ask_agent(messages)  # tool loop runs here; it adds to `messages`
    return answer, messages


state = gr.State([])  # our Claude memory, one per browser tab

demo = gr.ChatInterface(
    fn=respond,
    title="🤖 Claude Chat Agent",
    textbox=gr.Textbox(placeholder="Ask me anything (weather, time, maths...)"),
    additional_inputs=[state],
    additional_outputs=[state],
)

if __name__ == "__main__":
    demo.launch()
