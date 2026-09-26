"""
Streamlit step 2: Streaming replies.

NEW HERE: the answer appears word by word instead of all at once.

KEY IDEA: `stream_agent()` is a GENERATOR. It yields events while Claude is
still writing. `st.write_stream()` takes a generator of text pieces and
draws each piece the moment it arrives.

stream_agent also yields tool events. In this step we keep only the
"text" events; step 3 shows the tool events.

Compare with 01_basic.py: only the "Handle a new question" part changed.

Run (from the AiAgent_learning folder):
    streamlit run chat_ui/streamlit_app/02_streaming.py
"""

import sys
from pathlib import Path

import streamlit as st

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from agent_core import stream_agent

st.title("🤖 Claude Chat Agent")

if "messages" not in st.session_state:
    st.session_state.messages = []


def text_of(message: dict) -> str:
    """The text to show for one message ('' for tool-only messages)."""
    content = message["content"]
    if isinstance(content, str):
        return content
    return "".join(b.get("text", "") for b in content if b["type"] == "text")


def text_only(events):
    """Keep only the text pieces from stream_agent's events."""
    for event in events:
        if event["type"] == "text":
            yield event["text"]
        elif event["type"] == "tool_call":
            yield "\n\n"  # keep text from before and after a tool call apart


bubble = None
for message in st.session_state.messages:
    text = text_of(message)
    if not text:
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

if question := st.chat_input("Ask me anything (weather, time, maths...)"):
    with st.chat_message("user"):
        st.markdown(question)

    st.session_state.messages.append({"role": "user", "content": question})

    with st.chat_message("assistant"):
        # NEW: draw the answer piece by piece as Claude writes it.
        st.write_stream(text_only(stream_agent(st.session_state.messages)))
