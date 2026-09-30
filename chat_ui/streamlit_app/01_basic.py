"""
Streamlit step 1: Basic chat window.

NEW HERE: a chat window instead of the terminal.
    st.chat_input    -> the text box at the bottom
    st.chat_message  -> a chat bubble ("user" or "assistant")

KEY IDEA: Streamlit RERUNS THIS WHOLE SCRIPT from top to bottom every time
you send a message. A normal `messages = []` would be reset on every rerun,
so the memory must live in `st.session_state`, which survives reruns.

On every rerun we:
    1. redraw all old messages from session_state
    2. if the user typed something, ask the agent and draw the new answer

Run (from the AiAgent_learning folder):
    streamlit run chat_ui/streamlit_app/01_basic.py
"""

import sys
from pathlib import Path

import streamlit as st

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))  # so we can import agent_core
from agent_core import ask_agent

st.title("🤖 Claude Chat Agent for magesh")

# The memory. Created once, then kept across reruns.
if "messages" not in st.session_state:
    st.session_state.messages = []


def text_of(message: dict) -> str:
    """The text to show for one message ('' for tool-only messages)."""
    content = message["content"]
    if isinstance(content, str):
        return content
    return "".join(b.get("text", "") for b in content if b["type"] == "text")


# 1. Redraw the conversation so far.
bubble = None
for message in st.session_state.messages:
    text = text_of(message)
    if not text:  # skip tool_use / tool_result messages; step 3 shows those
        continue
    if message["role"] == "user":
        st.chat_message("user").markdown(text)
        bubble = None
    else:
        # One question can take several API calls (tool loop); keep their
        # text together in ONE assistant bubble.
        if bubble is None:
            bubble = st.chat_message("assistant")
        bubble.markdown(text)

# 2. Handle a new question.
if question := st.chat_input("Ask me anything (weather, time, maths...)"):
    with st.chat_message("user"):
        st.markdown(question)

    st.session_state.messages.append({"role": "user", "content": question})

    with st.chat_message("assistant"):
        with st.spinner("Thinking..."):
            answer = ask_agent(st.session_state.messages)  # tool loop runs here
        st.markdown(answer)
