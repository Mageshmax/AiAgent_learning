"""
Streamlit step 4: Clear chat button.

NEW HERE: a sidebar with a "New chat" button that starts a fresh conversation.

KEY IDEA: "clearing the chat" = emptying the memory list. Clearing the
screen alone is not enough: if `messages` still held the old turns, Claude
would still remember them. After clearing we call st.rerun() so the page
redraws right away with the empty history.

Run (from the AiAgent_learning folder):
    streamlit run chat_ui/streamlit_app/04_clear_chat.py
"""

import json
import sys
from pathlib import Path

import streamlit as st

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from agent_core import stream_agent

st.title("🤖 Claude Chat Agent")

if "messages" not in st.session_state:
    st.session_state.messages = []


def tool_label(name: str, tool_input: dict) -> str:
    return f"🔧 {name}({json.dumps(tool_input)})"


def draw_history(messages: list) -> None:
    """Redraw old messages, including tool calls and their results."""
    # tool_use_id -> result, collected from the tool_result messages.
    results = {
        block["tool_use_id"]: block["content"]
        for m in messages if isinstance(m["content"], list)
        for block in m["content"] if block["type"] == "tool_result"
    }
    bubble = None
    for message in messages:
        content = message["content"]
        if isinstance(content, str):  # a question the user typed
            st.chat_message("user").markdown(content)
            bubble = None
        elif message["role"] == "assistant":
            # One question can take several API calls (tool loop). Put all of
            # them in ONE assistant bubble, like the live reply.
            if bubble is None:
                bubble = st.chat_message("assistant")
            for block in content:
                if block["type"] == "text":
                    bubble.markdown(block["text"])
                elif block["type"] == "tool_use":
                    box = bubble.status(tool_label(block["name"], block["input"]), state="complete")
                    box.write(results.get(block["id"], "(no result)"))
        # user messages holding tool_result blocks were shown above, inside the box


def draw_live_reply(events) -> None:
    """Draw stream_agent's events as they arrive."""
    text, area = "", st.empty()
    box = None
    for event in events:
        if event["type"] == "text":
            text += event["text"]
            area.markdown(text)
        elif event["type"] == "tool_call":
            box = st.status(tool_label(event["name"], event["input"]), state="running")
            text, area = "", st.empty()  # text after the tool goes below the box
        elif event["type"] == "tool_result":
            box.write(event["result"])
            box.update(state="complete")


# NEW: sidebar with a clear button.
with st.sidebar:
    st.header("Chat")
    if st.button("🗑️ New chat", use_container_width=True):
        st.session_state.messages = []  # forget everything
        st.rerun()                       # redraw the page now
    st.caption(f"Messages in memory: {len(st.session_state.messages)}")

draw_history(st.session_state.messages)

if question := st.chat_input("Ask me anything (weather, time, maths...)"):
    with st.chat_message("user"):
        st.markdown(question)

    st.session_state.messages.append({"role": "user", "content": question})

    with st.chat_message("assistant"):
        draw_live_reply(stream_agent(st.session_state.messages))
