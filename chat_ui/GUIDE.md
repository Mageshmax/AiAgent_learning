# Chat UI Guide: Streamlit, Gradio and FastAPI

This guide explains the 15 chat apps in `chat_ui/`. It is written for beginners.

- **Part 1** shows how to run every app.
- **Part 2** explains the shared agent, `agent_core.py`.
- **Parts 3–5** explain each UI, line by line. Step 1 of each UI is explained in full. Steps 2–5 explain only the lines that are new (marked `# NEW` in the code).
- **Part 6** compares the three approaches, lists common errors, and suggests exercises.

---

# Part 1: How to run each app

## One-time setup

Open a terminal and run:

```bash
cd /home/santhosh/AIAgent/AiAgent_learning
source ../.venv/bin/activate          # turn on the virtual environment
pip install -r chat_ui/requirements.txt
```

- `source ../.venv/bin/activate` turns on your virtual environment (a folder with this project's own Python packages). Your prompt will start with `(.venv)`. Do this **every time you open a new terminal**.
- `pip install -r ...` installs every package listed in `requirements.txt`. These are already installed, so this only matters on a new computer.
- Your API key must be in `AiAgent_learning/.env` as `ANTHROPIC_API_KEY=...`. It is already there from lesson 01.

**Always run the commands below from the `AiAgent_learning` folder.**

## Run commands

| UI | Step | Command | Then open |
|---|---|---|---|
| Streamlit | 1 Basic | `streamlit run chat_ui/streamlit_app/01_basic.py` | http://localhost:8501 (opens itsself) |
| Streamlit | 2 Streaming | `streamlit run chat_ui/streamlit_app/02_streaming.py` | http://localhost:8501 |
| Streamlit | 3 Tool calls | `streamlit run chat_ui/streamlit_app/03_tool_calls.py` | http://localhost:8501 |
| Streamlit | 4 Clear chat | `streamlit run chat_ui/streamlit_app/04_clear_chat.py` | http://localhost:8501 |
| Streamlit | 5 Save history | `streamlit run chat_ui/streamlit_app/05_save_history.py` | http://localhost:8501 |
| Gradio | 1 Basic | `python chat_ui/gradio_app/01_basic.py` | http://127.0.0.1:7860 |
| Gradio | 2 Streaming | `python chat_ui/gradio_app/02_streaming.py` | http://127.0.0.1:7860 |
| Gradio | 3 Tool calls | `python chat_ui/gradio_app/03_tool_calls.py` | http://127.0.0.1:7860 |
| Gradio | 4 Clear chat | `python chat_ui/gradio_app/04_clear_chat.py` | http://127.0.0.1:7860 |
| Gradio | 5 Save history | `python chat_ui/gradio_app/05_save_history.py` | http://127.0.0.1:7860 |
| FastAPI | 1 Basic | `python chat_ui/fastapi_app/01_basic/server.py` | http://127.0.0.1:8000 |
| FastAPI | 2 Streaming | `python chat_ui/fastapi_app/02_streaming/server.py` | http://127.0.0.1:8000 |
| FastAPI | 3 Tool calls | `python chat_ui/fastapi_app/03_tool_calls/server.py` | http://127.0.0.1:8000 |
| FastAPI | 4 Clear chat | `python chat_ui/fastapi_app/04_clear_chat/server.py` | http://127.0.0.1:8000 |
| FastAPI | 5 Save history | `python chat_ui/fastapi_app/05_save_history/server.py` | http://127.0.0.1:8000 |

**To stop an app:** click the terminal and press `Ctrl + C`. Stop one app before starting the next one of the same kind, because they use the same port (the number at the end of the address).

**Note:** Streamlit apps start with `streamlit run`, not `python`. `python file.py` won't open a page.

## Test conversation (use it on every app)

```
1. What time is it in Tokyo?                  → uses the get_current_time tool
2. How many hours until midnight there?        → "there" = Tokyo: tests MEMORY (may also use calculator)
3. What's the weather in Chennai and Delhi?    → two tool calls in one reply
4. Which one is hotter?                        → memory again, no tool
```

What to check for each step:

| Step | You should see |
|---|---|
| 1 Basic | Bubbles for you and Claude; the answer appears all at once |
| 2 Streaming | The answer appears word by word |
| 3 Tool calls | A 🔧 box for each tool, which you can click to open and see the result |
| 4 Clear chat | "New chat" empties the screen, and Claude no longer remembers (ask "what was my last question?") |
| 5 Save history | Stop the app (`Ctrl + C`), start it again, and reload the page: the chat is still there and Claude still remembers |

## Where step 5 saves the chat

| UI | File |
|---|---|
| Streamlit | `chat_ui/streamlit_app/chat_history.json` (one file for everyone) |
| Gradio | `chat_ui/gradio_app/chat_history.json` (one file for everyone) |
| FastAPI | `chat_ui/fastapi_app/05_save_history/history/<session id>.json` (**one file per browser**) |

You can open these files to see exactly what Claude's memory looks like.

---

# Part 2: The shared agent (`agent_core.py`)

All 15 apps use this one file. It holds the tools and the tool loop from `04_chat_agent.py`, turned into **functions** so other files can import them. The UI files contain only UI code.

```
Browser  ⇄  UI file (Streamlit / Gradio / FastAPI)  ⇄  agent_core.py  ⇄  Claude API
             "draw the page"                            "think + run tools"
```

## Setup (top of the file)

```python
load_dotenv(find_dotenv())
api_key = os.getenv("ANTHROPIC_API_KEY")
if not api_key:
    raise SystemExit("ANTHROPIC_API_KEY not found. Add it to your .env file.")
client = anthropic.Anthropic(api_key=api_key)
```
The same as lesson 01.
- `find_dotenv()` searches this folder and the folders above it for `.env`. That's how `chat_ui/agent_core.py` finds `AiAgent_learning/.env`.
- `load_dotenv` loads the key into environment variables, and `client` is used for every Claude call.

```python
MODEL = "claude-opus-5"
MAX_TOKENS = 16000
MAX_TOOL_TURNS = 10
SYSTEM_PROMPT = "You are a helpful assistant. Use the tools when they help. ..."
```
**Constants** are settings in one place. To try another model, change `MODEL` here and all 15 apps use it.

## The tools

`get_weather`, `calculator`, `get_current_time`, `TOOL_FUNCTIONS` and `TOOLS` are copied from lesson 04 without changes.

```python
def run_tool(name, tool_input):
    function = TOOL_FUNCTIONS.get(name)
    if function is None:
        return f"Error: unknown tool {name}"
    return function(**tool_input)
```
- This looks up the Python function by the name Claude used. `.get` returns `None` instead of crashing if the name is unknown.
- `function(**tool_input)` unpacks the dictionary into keyword arguments: `{"city": "Delhi"}` becomes `get_weather(city="Delhi")`.

```python
def _to_dicts(content):
    return [block.model_dump(exclude_none=True) for block in content]
```
- Claude's reply comes back as SDK objects such as `TextBlock(...)`. Those can't be saved to a JSON file.
- `.model_dump()` turns each one into a plain dictionary like `{"type": "text", "text": "Hi"}`. `exclude_none=True` leaves out empty fields.
- Because memory holds plain dicts, step 5 of every UI can save it with one line. The `_` at the start of the name means "internal helper, not for other files".

## `ask_agent(messages)`: the whole answer at once (used by step 1)

```python
def ask_agent(messages):
    start = len(messages) - 1
```
This remembers where this question starts in memory, so it can be undone if something goes wrong (see the end of the function).

```python
    for _ in range(MAX_TOOL_TURNS):
```
This loops at most 10 times. `_` means "I don't need the loop number". It is the same safety limit as lesson 04's `while turn < MAX_TURNS`.

```python
        response = client.messages.create(model=MODEL, max_tokens=MAX_TOKENS,
            system=SYSTEM_PROMPT, tools=TOOLS, messages=messages)
        messages.append({"role": "assistant", "content": _to_dicts(response.content)})
```
This calls Claude with the whole memory and the tool list, then saves Claude's reply to memory as plain dicts.

```python
        if response.stop_reason != "tool_use":
            return "".join(b.text for b in response.content if b.type == "text")
```
If Claude doesn't want a tool, this is the final answer. The function joins all the text blocks and returns them.

```python
        tool_results = []
        for block in response.content:
            if block.type == "tool_use":
                tool_results.append({"type": "tool_result", "tool_use_id": block.id,
                                     "content": run_tool(block.name, block.input)})
        messages.append({"role": "user", "content": tool_results})
```
Otherwise it runs every tool Claude asked for and sends all the results back in one message, exactly like lesson 03. Then the loop goes round again.

```python
    del messages[start:]
    return f"Sorry, I stopped after {MAX_TOOL_TURNS} tool calls..."
```
You only get here if the loop hit 10 turns. Memory would then end with a tool request that has no result, and the API would reject the next question. So the whole question is deleted from memory.

**Important:** `ask_agent` changes the list you pass in (it *appends* to it). That's how the UI's memory grows without the UI doing anything extra.

## `stream_agent(messages)`: live events (used by steps 2–5)

This is the same loop, with two differences.

**1. It is a generator.** It uses `yield` instead of `return`:
```python
def count():
    yield 1
    yield 2
for n in count():   # gets 1, then 2, one at a time
    print(n)
```
A generator hands out values one at a time, **while it is still running**. The UI can show each piece immediately.

**2. It streams from Claude:**
```python
        with client.messages.stream(model=MODEL, ...) as stream:
            for text in stream.text_stream:
                yield {"type": "text", "text": text}
            response = stream.get_final_message()
```
- `client.messages.stream(...)` opens a connection that sends text **as Claude writes it**.
- `stream.text_stream` gives each small piece of text ("Hel", "lo"). We pass each one on as an event.
- `get_final_message()` returns the complete reply (the same kind of object as `create()` returns), so the rest of the loop works as before.

```python
                yield {"type": "tool_call", "name": block.name, "input": block.input}
                result = run_tool(block.name, block.input)
                yield {"type": "tool_result", "name": block.name, "result": result}
```
It also announces each tool call and its result, so the UI can draw 🔧 boxes (step 3).

**The 3 event types** every UI understands:
```python
{"type": "text", "text": "It's 34°C"}                         # a piece of the answer
{"type": "tool_call", "name": "get_weather", "input": {...}}  # Claude asked for a tool
{"type": "tool_result", "name": "get_weather", "result": "..."}  # we ran it
```

## `save_history` / `load_history` (used by step 5)

```python
def save_history(messages, path):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(messages, indent=2, ensure_ascii=False))
```
- `mkdir(..., exist_ok=True)` creates the folder if it's missing.
- `json.dumps` turns the list into JSON text. `indent=2` makes it readable, and `ensure_ascii=False` keeps "°C" and emoji as they are.

```python
def load_history(path):
    path = Path(path)
    if not path.exists():
        return []
    return json.loads(path.read_text())
```
If there's no file yet, this starts with an empty memory. Otherwise it reads the JSON back into a list.

---

# Part 3: Streamlit (`chat_ui/streamlit_app/`)

## The big idea

**Streamlit runs your whole script again, from line 1, every time the user does anything.** It clears the page and redraws everything. So:
- Normal variables are reset on every run. Memory must go in **`st.session_state`**, a dictionary that Streamlit keeps between runs.
- Each run first **redraws the whole old conversation**, then handles the new question (if there is one).

## Step 1: `01_basic.py` (line by line)

```python
import sys
from pathlib import Path
import streamlit as st
```
- `sys` is used to change where Python looks for imports.
- `Path` handles file paths.
- `st` is the usual short name for Streamlit.

```python
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from agent_core import ask_agent
```
- `__file__` is the path of this file. `.resolve()` makes it a full path. `.parent` is its folder (`streamlit_app`), and `.parent.parent` is the folder above (`chat_ui`).
- `sys.path` is the list of folders Python searches for imports. Adding `chat_ui` at the front (position 0) lets Python find `agent_core.py`.

```python
st.title("🤖 Claude Chat Agent")
```
Draws a big heading. Every `st.something(...)` call draws one thing, from top to bottom.

```python
if "messages" not in st.session_state:
    st.session_state.messages = []
```
In plain words: "If there's no memory yet, create an empty one." On the first run it's created, and on later runs it already exists, so it's kept. **This one line is why the bot remembers.**

```python
def text_of(message: dict) -> str:
    content = message["content"]
    if isinstance(content, str):
        return content
    return "".join(b.get("text", "") for b in content if b["type"] == "text")
```
Memory holds two shapes of message:
- A **user question** has `"content": "a string"`.
- A **Claude reply** has `"content": [list of blocks]`.

`isinstance(content, str)` checks "is it a string?". For a list, the function joins the text of every `"text"` block. Tool-only messages return `""`.

```python
bubble = None
for message in st.session_state.messages:
    text = text_of(message)
    if not text:
        continue
```
**Part 1 of every run: redraw the old chat.** It loops over memory. `continue` skips messages with no text (tool results).

```python
    if message["role"] == "user":
        st.chat_message("user").markdown(text)
        bubble = None
```
`st.chat_message("user")` draws a chat bubble with a user icon, and `.markdown(text)` writes text inside it. Markdown means `**bold**` really shows as **bold**.

```python
    else:
        if bubble is None:
            bubble = st.chat_message("assistant")
        bubble.markdown(text)
```
- When Claude uses a tool, one question creates **several** assistant messages ("Let me check…", then the answer).
- `bubble` remembers the open assistant bubble, so they all go in one bubble.
- After a user message, `bubble = None`, so the next reply starts a new bubble.

```python
if question := st.chat_input("Ask me anything (weather, time, maths...)"):
```
**Part 2: handle a new question.**
- `st.chat_input` draws the text box at the bottom. It returns `None` normally, and returns **the typed text** only on the run right after you press Enter.
- `:=` (the "walrus operator") saves the value into `question` and checks it in one step. So the block below runs only when a message was just sent.

```python
    with st.chat_message("user"):
        st.markdown(question)
```
Shows your question straight away. `with st.chat_message(...):` means "everything drawn inside this block goes into this bubble".

```python
    st.session_state.messages.append({"role": "user", "content": question})
```
Adds the question to memory, the same as lesson 02.

```python
    with st.chat_message("assistant"):
        with st.spinner("Thinking..."):
            answer = ask_agent(st.session_state.messages)
        st.markdown(answer)
```
- `st.spinner` shows a spinning icon while the code inside runs.
- `ask_agent` runs the tool loop **and adds Claude's replies to memory** itself.
- Then the answer is drawn. On the next run, Part 1 redraws it from memory.

## Step 2: `02_streaming.py` (new lines only)

```python
def text_only(events):
    for event in events:
        if event["type"] == "text":
            yield event["text"]
        elif event["type"] == "tool_call":
            yield "\n\n"
```
A small **generator** that filters `stream_agent`'s events. It passes on only text pieces (tools are shown in step 3). On a tool call, it adds a blank line so text from before and after the tool doesn't run together.

```python
    with st.chat_message("assistant"):
        st.write_stream(text_only(stream_agent(st.session_state.messages)))
```
This is the only real change. `st.write_stream(generator)` takes pieces of text from the generator and adds each one to the page **as it arrives**, which gives the typing effect. It reads from the inside out: `stream_agent` makes events, `text_only` keeps the text, and `write_stream` draws it.

## Step 3: `03_tool_calls.py` (new lines only)

```python
def tool_label(name, tool_input):
    return f"🔧 {name}({json.dumps(tool_input)})"
```
Builds the box title, for example `🔧 get_weather({"city": "Delhi"})`. `json.dumps` turns the dict into text.

```python
def draw_live_reply(events):
    text, area = "", st.empty()
    box = None
```
- `st.empty()` makes an empty **placeholder**. Calling `area.markdown(...)` again **replaces** what's in it instead of adding a new line. This is how the text grows in place.
- `box` will hold the current tool box.

```python
    for event in events:
        if event["type"] == "text":
            text += event["text"]
            area.markdown(text)
```
Each text piece is added to `text`, and the placeholder is redrawn with the longer text.

```python
        elif event["type"] == "tool_call":
            box = st.status(tool_label(event["name"], event["input"]), state="running")
            text, area = "", st.empty()
```
- `st.status(label, state="running")` draws a box you can click to open, with a spinner.
- A new empty placeholder is made **below** the box, so text after the tool appears under it.

```python
        elif event["type"] == "tool_result":
            box.write(event["result"])
            box.update(state="complete")
```
Writes the tool's result inside the box and changes the spinner to a ✓.

```python
def draw_history(messages):
    results = {
        block["tool_use_id"]: block["content"]
        for m in messages if isinstance(m["content"], list)
        for block in m["content"] if block["type"] == "tool_result"
    }
```
To redraw **old** tool boxes, we need each tool call's result. But in memory, the call (`tool_use`, in an assistant message) and its result (`tool_result`, in the next user message) are in **different messages**. They're linked by an id. This **dictionary comprehension** builds a lookup table `{tool id: result}` from every tool_result block.

```python
                elif block["type"] == "tool_use":
                    box = bubble.status(tool_label(...), state="complete")
                    box.write(results.get(block["id"], "(no result)"))
```
For each old tool call, this draws a finished box and looks up its result by id.

## Step 4: `04_clear_chat.py` (new lines only)

```python
with st.sidebar:
    st.header("Chat")
```
`with st.sidebar:` puts everything in this block in the panel on the left.

```python
    if st.button("🗑️ New chat", use_container_width=True):
        st.session_state.messages = []
        st.rerun()
```
- `st.button` returns `True` only on the run right after it's clicked.
- Emptying `messages` is what really makes Claude forget. Clearing only the screen wouldn't be enough.
- `st.rerun()` runs the script again straight away, so the page redraws empty.

```python
    st.caption(f"Messages in memory: {len(st.session_state.messages)}")
```
Small grey text showing how big the memory is. Watch it grow by 2 or more per question.

## Step 5: `05_save_history.py` (new lines only)

```python
from agent_core import load_history, save_history, stream_agent
HISTORY_FILE = Path(__file__).resolve().parent / "chat_history.json"
```
The file sits next to this script. With `Path`, `/` joins path parts.

```python
    st.session_state.messages = load_history(HISTORY_FILE)
```
When memory is first created, it's loaded from the file instead of starting as `[]`.

```python
        save_history([], HISTORY_FILE)
```
The New chat button also empties the file.

```python
    save_history(st.session_state.messages, HISTORY_FILE)
```
After every reply, the whole memory is written to the file.

**Why it works:** `session_state` is lost when the app stops, but the file isn't. On the next start, the memory is loaded from the file, and `draw_history` draws it, including the tool boxes.

---

# Part 4: Gradio (`chat_ui/gradio_app/`)

## The big idea

**Gradio runs your script only once**, to build the page. After that, when the user does something, Gradio **calls one of your functions** and updates only the parts of the page you name. It doesn't rerun everything like Streamlit.

## Step 1: `01_basic.py` (line by line)

```python
import gradio as gr
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from agent_core import ask_agent
```
The same import trick as Streamlit. `gr` is the usual short name for Gradio.

```python
def respond(question: str, history: list, messages: list):
```
Gradio calls this function **every time you send a message**. It passes:
- `question`: what you typed.
- `history`: what's on the screen. Gradio manages this, and we don't use it.
- `messages`: **our** Claude memory, from the `gr.State` below.

```python
    messages.append({"role": "user", "content": question})
    answer = ask_agent(messages)
    return answer, messages
```
It adds the question, runs the agent (which adds Claude's replies to `messages`), and returns **two things**: the answer to show, and the updated memory.

```python
state = gr.State([])
```
`gr.State` is an **invisible** component that stores a value. Gradio gives **each browser tab its own copy**, starting as `[]`. It plays the same role as Streamlit's `session_state`.

**Why not use `history`?** `history` holds only the text on screen. Claude's memory also needs `tool_use` and `tool_result` blocks, so we keep our own list.

```python
demo = gr.ChatInterface(
    fn=respond,
    title="🤖 Claude Chat Agent",
    textbox=gr.Textbox(placeholder="Ask me anything (weather, time, maths...)"),
    additional_inputs=[state],
    additional_outputs=[state],
)
```
- `gr.ChatInterface` is a **ready-made chat page**: bubbles, input box and send button. You give it your function (`fn=respond`), and it does the rest.
- `additional_inputs=[state]` means: pass the state's value into `respond` as an extra argument (that's `messages`).
- `additional_outputs=[state]` means: `respond` returns an extra value, so save it back into the state.

```python
if __name__ == "__main__":
    demo.launch()
```
- `if __name__ == "__main__":` means "only when this file is run directly, not when it's imported".
- `demo.launch()` starts a web server on port 7860.

**Watch out:** the 🗑 icon on the chat clears only the **screen**. Claude still remembers, because our state wasn't emptied. Step 4 fixes this.

## Step 2: `02_streaming.py` (new lines only)

```python
def respond(question, history, messages):
    messages.append({"role": "user", "content": question})
    answer = ""
    for event in stream_agent(messages):
        if event["type"] == "text":
            answer += event["text"]
        elif event["type"] == "tool_call" and answer:
            answer += "\n\n"
        yield answer, messages
```
- `return` became `yield`, so `respond` is now a **generator**, and Gradio streams it.
- **Each `yield` replaces** the reply on screen. So we yield the **whole answer so far**, which gets a little longer each time. We don't yield just the new piece.

## Step 3: `03_tool_calls.py` (new lines only)

```python
    reply = []
```
Instead of one string, the reply is now a **list of messages**: text parts and tool boxes.

```python
        if event["type"] == "text":
            if not reply or reply[-1].metadata:
                reply.append(gr.ChatMessage(role="assistant", content=""))
            reply[-1].content += event["text"]
```
- `reply[-1]` means "the last item in the list".
- If the list is empty, or the last item is a tool box (tool boxes have `metadata`), this starts a new text message. Then it adds the text to the last one.

```python
        elif event["type"] == "tool_call":
            reply.append(gr.ChatMessage(
                role="assistant",
                content="",
                metadata={"title": tool_label(event["name"], event["input"]), "status": "pending"},
            ))
```
**Gradio's built-in tool box:** any `gr.ChatMessage` with `metadata={"title": ...}` is drawn as a box you can open and close. `"status": "pending"` shows a spinner.

```python
        elif event["type"] == "tool_result":
            reply[-1].content = event["result"]
            reply[-1].metadata["status"] = "done"
        yield reply, messages
```
It puts the result inside the box and marks it done. Then it yields the whole list, and Gradio redraws the reply.

## Step 4: `04_clear_chat.py` (new lines only)

`gr.ChatInterface` is ready-made, so it's hard to add our own button that also empties our state. From this step on, we build the page ourselves with **`gr.Blocks`**. It works like Lego, in two stages: **place** the pieces, then **connect** them.

```python
with gr.Blocks(title="Claude Chat Agent") as demo:
    gr.Markdown("# 🤖 Claude Chat Agent")
    chatbot = gr.Chatbot(height=500)
    textbox = gr.Textbox(placeholder="...", show_label=False, submit_btn=True)
    clear_button = gr.Button("🗑️ New chat")
    state = gr.State([])
```
**Place:** everything created inside `with gr.Blocks()` appears on the page, from top to bottom.
- `gr.Chatbot` is the chat area.
- `gr.Textbox(submit_btn=True)` is the input box, with a send arrow.
- `gr.Button` is the clear button.
- `gr.State` is the memory, which isn't visible.

```python
    textbox.submit(respond, inputs=[textbox, chatbot, state], outputs=[textbox, chatbot, state])
    clear_button.click(clear_chat, inputs=None, outputs=[chatbot, state])
```
**Connect:** `component.event(function, inputs, outputs)`.
- When the textbox is submitted, Gradio calls `respond(textbox value, chatbot value, state value)`. It then puts `respond`'s results into textbox, chatbot and state, **in that order**.
- When the button is clicked, it calls `clear_chat()` and puts its two results into chatbot and state.

```python
def respond(question, chat, messages):
    if not question.strip():
        return
    messages.append({"role": "user", "content": question})
    chat = chat + [gr.ChatMessage(role="user", content=question)]
    reply = []
    yield "", chat, messages
```
- Now **we** manage what's on screen (`chat`), so we add the user's bubble ourselves.
- The first `yield` returns `""` for the textbox, which clears it, and shows the question straight away.
- Later yields return `chat + reply`: the old chat plus the growing reply.

```python
def clear_chat():
    return [], []
```
Returns an empty list for the chatbot (the **screen**) and for the state (the **memory**). Both must be emptied.

## Step 5: `05_save_history.py` (new lines only)

```python
HISTORY_FILE = Path(__file__).resolve().parent / "chat_history.json"
```
The file sits next to this script.

```python
def to_chatbot(messages):
```
The file holds **Claude's memory** (`messages`), but `gr.Chatbot` needs **`gr.ChatMessage`s**. This function converts one into the other, using the same `results` lookup table as Streamlit step 3 to pair tool calls with their results.

```python
def load_chat():
    messages = load_history(HISTORY_FILE)
    return to_chatbot(messages), messages
```
This loads the file and returns what to show on screen, plus the memory.

```python
    demo.load(load_chat, inputs=None, outputs=[chatbot, state])
```
**`demo.load`** is an event that runs **every time a browser opens (or reloads) the page**. It fills both the screen and the memory from the file.

```python
    save_history(messages, HISTORY_FILE)
```
At the end of `respond`, after the loop has finished, the memory is saved. `clear_chat` also saves `[]`.

**Limitation:** there's only one file, so every browser shares one chat. FastAPI step 5 fixes this.

---

# Part 5: FastAPI + HTML/JS (`chat_ui/fastapi_app/`)

## The big idea

Streamlit and Gradio **hid** how a web app works. Here we build both halves ourselves:

| Part | Language | File | Job |
|---|---|---|---|
| **Backend** (server) | Python | `server.py` | Runs the agent; answers requests |
| **Frontend** (page) | HTML + CSS + JavaScript | `static/index.html` | Shows the chat; sends questions |

They talk over **HTTP**, like every website:
```
browser  --GET /------------------------------->  server   "give me the page"
browser  <------------------------ index.html --  server
browser  --POST /chat {"message": "Hi"}-------->  server   "here is a question"
browser  <------------- {"reply": "Hello!"} ----  server   "here is the answer"
```
- **GET** means "give me something".
- **POST** means "here's some data, do something with it".
- `/`, `/chat` and so on are **routes**: addresses on your server.
- The data travels as **JSON**, which is text shaped like Python dicts.

Each step folder has a `server.py` and a `static/index.html`.

## Step 1 backend: `01_basic/server.py` (line by line)

```python
import uvicorn
from fastapi import FastAPI
from fastapi.responses import FileResponse
from pydantic import BaseModel
```
- **FastAPI** is the web framework: it maps routes to your functions.
- **Uvicorn** is the web server that actually listens for browsers and hands their requests to FastAPI.
- **Pydantic** checks that incoming JSON has the right shape.
- `FileResponse` sends a file to the browser.

```python
HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent.parent))
from agent_core import ask_agent
```
- `HERE` is this step's folder (`01_basic`). We use it to find `static/index.html`.
- `HERE.parent.parent` is `chat_ui`, where `agent_core.py` lives. This is the same import trick as before, one folder deeper.

```python
app = FastAPI()
messages = []
```
- `app` is the web application. The routes below attach to it.
- `messages` is **one list for the whole server**, so everyone shares a single conversation. Step 4 fixes this.

```python
class ChatRequest(BaseModel):
    message: str
```
This describes the JSON the browser must send: `{"message": "some text"}`. If the browser sends something else, FastAPI automatically replies with a **422 error** that explains what's wrong. You don't write any checking code.

```python
@app.get("/")
def home():
    return FileResponse(HERE / "static" / "index.html")
```
- `@app.get("/")` is a **decorator**. It means "when a browser does GET on `/`, call this function".
- Opening `http://127.0.0.1:8000` does exactly that, so we send back the chat page.

```python
@app.post("/chat")
def chat(request: ChatRequest):
    messages.append({"role": "user", "content": request.message})
    answer = ask_agent(messages)
    return {"reply": answer}
```
- `@app.post("/chat")` means "when a browser POSTs to `/chat`, call this".
- FastAPI reads the JSON body, checks it against `ChatRequest`, and passes it in as `request`. `request.message` is the question.
- Returning a dict makes FastAPI send it back as JSON: `{"reply": "..."}`.
- We use plain `def` (not `async def`) on purpose. `ask_agent` waits for Claude, and FastAPI runs plain `def` routes in a separate thread, so one slow question doesn't freeze the server for everyone else.

```python
if __name__ == "__main__":
    uvicorn.run(app, host="127.0.0.1", port=8000)
```
Starts the server at `127.0.0.1` (your own computer only) on port 8000.

## Step 1 frontend: `01_basic/static/index.html` (line by line)

An HTML file has three languages in it:
- **HTML** says what's on the page.
- **CSS** (inside `<style>`) says how it looks.
- **JavaScript** (inside `<script>`) says what it does.

### HTML structure

```html
<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Claude Chat Agent</title>
```
- `<!DOCTYPE html>` tells the browser this is modern HTML.
- `<head>` holds information *about* the page, which isn't shown in it.
- `charset="UTF-8"` makes emoji and "°C" display correctly.
- The `viewport` line makes the page fit phone screens.
- `<title>` is the text on the browser tab.

```html
<body>
  <div class="app">
    <h1>🤖 Claude Chat Agent</h1>
    <div id="chat"></div>
    <form id="form">
      <input id="input" placeholder="Ask me anything..." autocomplete="off" autofocus>
      <button id="send">Send</button>
    </form>
  </div>
```
- `<body>` is what's shown on the page.
- `<div>` is a plain box, and `<h1>` is a big heading.
- `<div id="chat">` is the **empty box where bubbles will be added** by JavaScript.
- `<form>` holds the input and button. Pressing Enter in the input submits the form.
- `id="..."` gives an element a unique name so JavaScript can find it.
- `class="..."` is a label that CSS uses for styling.
- `autofocus` puts the cursor in the input box when the page opens.

### CSS (the look)

```css
body { font-family: system-ui, sans-serif; background: #f4f4f5; margin: 0; }
```
Each rule is `selector { property: value; }`. This one means: for `<body>`, use the system font, a light grey background, and no outer gap.

```css
.app { max-width: 760px; margin: 0 auto; height: 100vh; display: flex; flex-direction: column; ... }
```
- `.app` targets elements with `class="app"`.
- `max-width` plus `margin: 0 auto` makes a centred column.
- `100vh` means 100% of the window height.
- `display: flex; flex-direction: column` stacks the children vertically.

```css
#chat { flex: 1; overflow-y: auto; display: flex; flex-direction: column; gap: 10px; }
```
- `#chat` targets `id="chat"`.
- `flex: 1` means "take all the free space", which pushes the form to the bottom.
- `overflow-y: auto` adds a scrollbar when there are many messages.
- `gap` is the space between bubbles.

```css
.bubble { max-width: 80%; padding: 10px 14px; border-radius: 14px; white-space: pre-wrap; }
.user { align-self: flex-end; background: #2563eb; color: white; }
.assistant { align-self: flex-start; background: white; border: 1px solid #e4e4e7; }
```
- Every bubble gets padding and rounded corners (`border-radius`).
- `white-space: pre-wrap` keeps line breaks in the text.
- `.user` bubbles are blue and sit on the **right** (`flex-end`).
- `.assistant` bubbles are white and sit on the **left**.

### JavaScript (what it does)

```js
const chat = document.getElementById("chat");
const form = document.getElementById("form");
const input = document.getElementById("input");
const send = document.getElementById("send");
```
- `document` is the page.
- `getElementById("chat")` finds the element with `id="chat"`.
- `const` makes a variable that won't be reassigned (like a normal Python variable you never change).

```js
function addBubble(role, text) {
  const bubble = document.createElement("div");
  bubble.className = "bubble " + role;
  bubble.textContent = text;
  chat.appendChild(bubble);
  chat.scrollTop = chat.scrollHeight;
  return bubble;
}
```
A function that adds one chat bubble:
1. `createElement("div")` makes a new, empty box.
2. `className = "bubble user"` gives it the CSS classes, so it looks like a bubble.
3. `textContent = text` puts the text in. It's treated as **plain text**, so if a reply contains `<b>`, it shows as those characters instead of running as HTML. That's the safe choice.
4. `appendChild` puts it inside the chat box, where it becomes visible.
5. `scrollTop = scrollHeight` scrolls to the bottom.
6. It returns the bubble so the caller can change its text later.

```js
form.addEventListener("submit", async (event) => {
  event.preventDefault();
```
- `addEventListener("submit", ...)` means "when the form is submitted (Enter or the Send button), run this function".
- `(event) => { ... }` is an **arrow function**, a short way to write a function.
- `async` means the function can **wait** for slow things using `await`.
- `event.preventDefault()` stops the browser's default action for forms, which is to reload the page.

```js
  const question = input.value.trim();
  if (!question) return;
```
- `input.value` is the typed text. `.trim()` removes spaces at the ends.
- If it's empty, the function stops.

```js
  addBubble("user", question);
  input.value = "";
  send.disabled = true;
  const bubble = addBubble("assistant", "Thinking...");
```
This shows your question, empties the input box, and greys out the Send button so you can't send twice. It also adds an assistant bubble that says "Thinking...", which will be replaced by the answer.

```js
  try {
    const response = await fetch("/chat", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ message: question }),
    });
```
**This is where the browser talks to the server.**
- `fetch(url, options)` sends an HTTP request.
- `method: "POST"` makes it a POST request to our `/chat` route.
- The `Content-Type` header tells the server the body is JSON.
- `JSON.stringify({...})` turns a JavaScript object into JSON text: `{"message": "Hi"}`. This must match `ChatRequest` in `server.py`.
- `await` waits for the server's answer without freezing the page.
- `try { ... } catch` is like Python's `try/except`.

```js
    const data = await response.json();
    bubble.textContent = data.reply;
  } catch (error) {
    bubble.textContent = "Error: " + error;
  }
```
- `response.json()` reads the reply and turns the JSON into an object, so `data.reply` is the answer text.
- The answer replaces "Thinking...".
- If anything fails (for example, the server is stopped), the error is shown in the bubble.

```js
  send.disabled = false;
  chat.scrollTop = chat.scrollHeight;
  input.focus();
});
```
Turns the Send button back on, scrolls down, and puts the cursor back in the input box.

**Try this:** open the browser's Developer Tools (`F12`), go to the **Network** tab, and send a message. You'll see the `chat` request, and you can click it to see the exact JSON sent and received.

## Step 2: `02_streaming` (new lines only)

**Backend:**
```python
from fastapi.responses import FileResponse, StreamingResponse
```
`StreamingResponse` sends a response **piece by piece** instead of all at once.

```python
@app.post("/chat")
def chat(request: ChatRequest):
    messages.append({"role": "user", "content": request.message})

    def events():
        for event in stream_agent(messages):
            yield json.dumps(event) + "\n"

    return StreamingResponse(events(), media_type="application/x-ndjson")
```
- `events()` is a generator **defined inside** the route function. It turns each agent event into one line of JSON text.
- `StreamingResponse(generator)` sends each `yield` to the browser **straight away**, keeping the connection open until the generator finishes.
- The format is **NDJSON** (newline-delimited JSON): one JSON object per line. `media_type` tells the browser what kind of data this is.

To watch the raw stream in a terminal while the server is running:
```bash
curl -N -X POST http://127.0.0.1:8000/chat -H "Content-Type: application/json" -d '{"message": "Weather in Delhi?"}'
```
(`-N` tells curl to print each piece as it arrives.)

**Frontend:**
```js
async function readStream(response, onEvent) {
  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";
```
- `response.body.getReader()` gives a reader that pulls the response in **chunks** as they arrive.
- `TextDecoder` turns bytes (how data travels) into text.
- `let` makes a variable that *can* change. `buffer` holds text that isn't a complete line yet.

```js
  while (true) {
    const { value, done } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });
```
- It waits for the next chunk. `{ value, done } = ...` unpacks two fields at once, like Python's `a, b = ...`.
- `done` is true when the server has finished.
- Each chunk is added to the buffer.

```js
    const lines = buffer.split("\n");
    buffer = lines.pop();
    for (const line of lines) {
      if (line.trim()) onEvent(JSON.parse(line));
    }
  }
}
```
**The tricky part:** a chunk can end in the middle of a line, like `{"type": "te`. So:
1. The buffer is split into lines.
2. `lines.pop()` removes the **last** part, which may be unfinished, and keeps it in the buffer for next time.
3. Every complete line is turned back into an object with `JSON.parse` and handed to `onEvent`.

```js
  const bubble = addBubble("assistant", "");
  ...
    await readStream(response, (ev) => {
      if (ev.type === "text") {
        bubble.textContent += ev.text;
      } else if (ev.type === "tool_call" && bubble.textContent) {
        bubble.textContent += "\n\n";
      }
      chat.scrollTop = chat.scrollHeight;
    });
```
- The bubble starts empty.
- For every text event, the piece is **added** (`+=`) to the bubble, which gives the typing effect.
- `===` means "equal to" in JavaScript. Use it instead of `==`.

## Step 3: `03_tool_calls` (new lines only)

**Backend:** no change. The server has streamed **all** events, including tool events, since step 2, but the page ignored them. This is a useful lesson: with a separate frontend and backend, a new UI feature often needs no server change.

**Frontend:**
```css
.tool { background: #f4f4f5; border: 1px solid #e4e4e7; border-radius: 8px; ... }
.tool summary { cursor: pointer; font-family: ui-monospace, monospace; }
```
Styles for the tool boxes. `cursor: pointer` shows the hand cursor, so it looks clickable.

```js
function startReply() {
  return { bubble: addBubble("assistant", ""), textPart: null, toolBox: null };
}
```
A reply is now an **object** with three fields:
- `bubble`: the assistant bubble.
- `textPart`: where the next text should go.
- `toolBox`: the tool box that's open now.

`null` means "nothing yet".

```js
function handleEvent(reply, ev) {
  if (ev.type === "text") {
    if (!reply.textPart) {
      reply.textPart = document.createElement("div");
      reply.bubble.appendChild(reply.textPart);
    }
    reply.textPart.textContent += ev.text;
```
On text: if there's no text part yet (the start, or just after a tool box), a new `<div>` is created inside the bubble. Then the text is added to it.

```js
  } else if (ev.type === "tool_call") {
    const box = document.createElement("details");
    box.className = "tool";
    const summary = document.createElement("summary");
    summary.textContent = `🔧 ${ev.name}(${JSON.stringify(ev.input)})`;
    const result = document.createElement("pre");
    result.textContent = "running...";
    box.append(summary, result);
    reply.bubble.appendChild(box);
    reply.toolBox = box;
    reply.textPart = null;
```
On a tool call, this builds a **`<details>`** box. That's plain HTML for a box you can open and close, with no library needed:
- `<summary>` is the always-visible title. Clicking it opens and closes the box.
- `<pre>` is the hidden content. It shows "running..." for now.
- The backticks `` `...${x}...` `` make a **template string**, JavaScript's version of Python's f-string.
- `reply.textPart = null` makes the next text start a new part **below** the box.

```js
  } else if (ev.type === "tool_result") {
    reply.toolBox.querySelector("pre").textContent = ev.result;
    reply.toolBox.querySelector("summary").textContent += "  ✓";
  }
```
On a tool result, `querySelector("pre")` finds the `<pre>` inside the box. The code puts the result there and adds ✓ to the title.

```js
    await readStream(response, (ev) => handleEvent(reply, ev));
```
Every streamed event now goes to `handleEvent`.

## Step 4: `04_clear_chat` (new lines only)

**The problem:** in steps 1–3 the server has **one** `messages` list for everybody. A clear button would wipe everyone's chat. So each browser needs its **own** memory. This is called a **session**.

**Backend:**
```python
sessions = {}
```
A dictionary from session id to that browser's `messages` list, for example `{"3b24...": [...], "9f1c...": [...]}`.

```python
SessionId = Field(pattern=r"^[A-Za-z0-9-]{1,64}$")

class ChatRequest(BaseModel):
    session_id: str = SessionId
    message: str
```
- The browser must now also send its `session_id`.
- `Field(pattern=...)` only accepts ids made of letters, numbers and dashes, 1 to 64 characters long. It's a **regular expression**: `^` means start, `[A-Za-z0-9-]` means allowed characters, `{1,64}` means length, and `$` means end.
- Anything else, like `../../etc`, is rejected with a 422 error. This matters in step 5, where the id becomes a **file name**. **Never trust input from the browser.**

```python
def get_messages(session_id):
    if session_id not in sessions:
        sessions[session_id] = []
    return sessions[session_id]
```
Returns this browser's memory, creating an empty one for a new browser.

```python
    messages = get_messages(request.session_id)
```
In `/chat`, the agent now uses **this browser's** list instead of the shared one.

```python
@app.post("/clear")
def clear(request: ClearRequest):
    sessions[request.session_id] = []
    return {"ok": True}
```
A new route that empties this browser's memory.

**Frontend:**
```html
<header>
  <h1>🤖 Claude Chat Agent</h1>
  <button id="clear">🗑️ New chat</button>
</header>
```
The title and the button sit side by side. The CSS `header { display: flex; justify-content: space-between; }` pushes them to opposite ends.

```js
let sessionId = localStorage.getItem("sessionId");
if (!sessionId) {
  sessionId = crypto.randomUUID();
  localStorage.setItem("sessionId", sessionId);
}
```
- **`localStorage`** is a small storage area in the browser, kept per website. It survives page reloads and browser restarts.
- On the first visit there's no id, so `crypto.randomUUID()` makes a random unique id like `3b241101-e2bb-...`, and it's saved.
- On later visits the same id is read back, so the server finds the same memory.

```js
body: JSON.stringify({ session_id: sessionId, message: question }),
```
Every chat request now includes the id.

```js
clear.addEventListener("click", async () => {
  await fetch("/clear", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ session_id: sessionId }),
  });
  chat.innerHTML = "";
  input.focus();
});
```
When the button is clicked, the page tells the server to forget this session, **then** empties the page. `innerHTML = ""` removes everything inside the chat box.

**Try this:** open the app in a normal window and in a private/incognito window. They get different ids, so they have separate conversations.

## Step 5: `05_save_history` (new lines only)

**Backend:**
```python
HISTORY_DIR = HERE / "history"

def history_file(session_id):
    return HISTORY_DIR / f"{session_id}.json"
```
Each browser gets its own file: `history/3b241101-....json`. This is safe because the id pattern allows only letters, numbers and dashes.

```python
def get_messages(session_id):
    if session_id not in sessions:
        sessions[session_id] = load_history(history_file(session_id))
    return sessions[session_id]
```
If the server doesn't have this session in memory (for example, just after a restart), it loads the session from its file. A new browser has no file, so `load_history` returns `[]`.

```python
def to_events(messages):
    ...
            events.append({"type": "user", "text": content})
    ...
                    events.append({"type": "tool_call", ...})
                    events.append({"type": "tool_result", ...})
```
**A neat trick:** this turns saved memory into the **same events `/chat` streams** (`text`, `tool_call`, `tool_result`), plus a `user` event for each question. The page can then redraw an old chat with the **same** `handleEvent()` it uses for live replies, so there's no second piece of drawing code. It uses the same `results` lookup table as before to pair tool calls with their results.

```python
@app.get("/history")
def history(session_id: str = Query(pattern=SESSION_ID_PATTERN)):
    return to_events(get_messages(session_id))
```
- A new route. The page calls `GET /history?session_id=...`.
- The part after `?` is a **query parameter**. `Query(pattern=...)` checks it with the same safe pattern.
- A returned list becomes a JSON array.

```python
    def events():
        for event in stream_agent(messages):
            yield json.dumps(event) + "\n"
        save_history(messages, history_file(request.session_id))
```
After the last event has been sent, the memory is saved to the file.

```python
    history_file(request.session_id).unlink(missing_ok=True)
```
In `/clear`, `.unlink()` deletes the file. `missing_ok=True` means it's fine if the file doesn't exist.

**Frontend:**
```js
async function loadHistory() {
  const response = await fetch("/history?session_id=" + encodeURIComponent(sessionId));
  const events = await response.json();
```
This asks the server for this browser's old chat. `encodeURIComponent` makes the id safe to put in a URL. `fetch` uses GET by default.

```js
  let reply = null;
  for (const ev of events) {
    if (ev.type === "user") {
      addBubble("user", ev.text);
      reply = null;
    } else {
      if (!reply) reply = startReply();
      handleEvent(reply, ev);
    }
  }
}
loadHistory();
```
It replays the events:
- A `user` event draws your bubble and ends the current reply.
- Any other event goes into the current reply. The reply is started the first time one is needed, and drawn with the same `handleEvent`.

`loadHistory()` at the bottom runs once when the page opens.

---

# Part 6: Comparison, common errors, exercises

## The three approaches side by side

| | Streamlit | Gradio | FastAPI + HTML/JS |
|---|---|---|---|
| How it runs your code | Reruns the **whole script** on every action | Runs the script once; **calls your functions** on events | Server **route functions** called by the page's `fetch` requests |
| Where the memory lives | `st.session_state` | `gr.State` | `sessions` dict on the server, keyed by the browser's id |
| Languages | Python only | Python only | Python + HTML + CSS + JavaScript |
| Streaming | `st.write_stream` | `yield` in your function | `StreamingResponse` + `getReader()` in JS |
| Tool boxes | `st.status` | `gr.ChatMessage(metadata=...)` | `<details>` HTML element |
| Code you write | Least | Little | Most |
| Control over the look | Low | Medium | **Full** |
| Best for | Quick demos, data apps | ML demos, sharing models | Real products, custom designs, mobile apps using the same API |

## Common errors

| Error | Cause | Fix |
|---|---|---|
| `ModuleNotFoundError: No module named 'streamlit'` (or gradio, fastapi) | The virtual environment isn't active | `source ../.venv/bin/activate` |
| `ModuleNotFoundError: No module named 'agent_core'` | The `sys.path.insert` line was removed or changed | Keep the `sys.path.insert(...)` line above the import |
| `ANTHROPIC_API_KEY not found` | No `.env` file, or it's in the wrong folder | Put `.env` in `AiAgent_learning/` |
| `Address already in use` / `port 8000 is in use` | Another copy of the app is still running | Press `Ctrl + C` in the other terminal |
| Streamlit shows nothing / "use streamlit run" warning | You started it with `python` | Use `streamlit run file.py` |
| FastAPI page shows `{"detail":"Not Found"}` | Wrong address | Open `http://127.0.0.1:8000/` exactly |
| Old FastAPI step still shows | The browser cached the page | Hard reload with `Ctrl + Shift + R` |
| `422 Unprocessable Entity` in FastAPI | The JSON sent doesn't match the `BaseModel` | Check the field names in `JSON.stringify({...})` |
| `**bold**` shows with stars in FastAPI | Replies are shown as plain text on purpose (safe) | See exercise 3 below |

## Exercises

1. **Add a tool.** Add a `get_joke` or `convert_currency` tool in `agent_core.py`. All 15 apps get it at once, with no UI changes.
2. **Show token usage.** Make `stream_agent` also yield `{"type": "usage", ...}` from `response.usage`, then show it under each reply in one UI.
3. **Markdown in FastAPI.** Load `marked` and `DOMPurify` from `https://cdn.jsdelivr.net/npm/...`, and set `textPart.innerHTML = DOMPurify.sanitize(marked.parse(text))` instead of `textContent`. **Always sanitize** before using `innerHTML`.
4. **Stop button.** In FastAPI, use an `AbortController` in JS to cancel `fetch` while Claude is still writing.
5. **Chat list.** In FastAPI step 5, add `GET /sessions` to list the saved chats, and a sidebar to switch between them.
6. **Compare.** Open the same step in all three UIs side by side and note where each one keeps the memory.
