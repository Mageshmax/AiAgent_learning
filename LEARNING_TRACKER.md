# AI Agent Learning Tracker

Beginner to advanced path for building AI agents with the Claude API.
Tick a box (`[x]`) when you finish a topic. Put the lesson file name next to it.

**Progress:** 6 / 40 topics done · Chat UI: 15 / 15 steps done ✅ (update these as you go)

**Last updated:** 2026-09-24. Chat UI finished (Streamlit, Gradio, FastAPI). Next: Level 2 (system prompts, error handling).

---

## Level 1: Basics ✅

- [x] **Call the API**: send one question, get one answer, read `stop_reason` and `usage` (`01_ask_claude.py`)
- [x] **Chat with memory**: the LLM has no memory; keep a `messages` list and resend it every call (`02_chat_with_memory.py`)
- [x] **Tool use**: describe tools, Claude returns `tool_use`, *our* code runs the tool, send back `tool_result` (`03_tool_use.py`)
- [x] **Agent loop**: keep calling Claude `while stop_reason == "tool_use"`, with a max-turns safety limit (`03_tool_use.py`, `04_chat_agent.py`)
- [x] **Chat agent**: outer chat loop (memory) + inner tool loop, all in one `messages` list (`04_chat_agent.py`)

Tools built so far: `get_weather` (fake data), `calculator`, `get_current_time` (real, uses `zoneinfo`).

## Chat UI: Put the Agent in a Chat Window (`chat_ui/`) ✅

📖 **Full guide:** [`chat_ui/GUIDE.md`](chat_ui/GUIDE.md) explains how to run every app and walks through the code line by line.

Shared agent used by every UI: `chat_ui/agent_core.py` (`ask_agent`, `stream_agent`, `save_history`, `load_history`).

| Step | Streamlit (`streamlit_app/`) | Gradio (`gradio_app/`) | FastAPI + HTML/JS (`fastapi_app/`) |
|---|---|---|---|
| 1. Basic chat window | ✅ `01_basic.py` | ✅ `01_basic.py` | ✅ `01_basic/` |
| 2. Streaming replies | ✅ `02_streaming.py` | ✅ `02_streaming.py` | ✅ `02_streaming/` |
| 3. Show tool calls | ✅ `03_tool_calls.py` | ✅ `03_tool_calls.py` | ✅ `03_tool_calls/` |
| 4. Clear chat button | ✅ `04_clear_chat.py` | ✅ `04_clear_chat.py` | ✅ `04_clear_chat/` |
| 5. Save chat history | ✅ `05_save_history.py` | ✅ `05_save_history.py` | ✅ `05_save_history/` |

(Change ⬜ to ✅ when a step is done.)

Run a step (from the `AiAgent_learning` folder):
- Streamlit: `streamlit run chat_ui/streamlit_app/01_basic.py`, then open http://localhost:8501
- Gradio: `python chat_ui/gradio_app/01_basic.py`, then open http://127.0.0.1:7860
- FastAPI: `python chat_ui/fastapi_app/01_basic/server.py`, then open http://127.0.0.1:8000

What each Streamlit step taught:
- **Basic**: Streamlit reruns the whole script on every input, so memory must live in `st.session_state`.
- **Streaming**: `stream_agent()` is a generator; `st.write_stream()` draws each piece as it arrives.
- **Tool calls**: use every event type; pair old `tool_use` blocks with their `tool_result` by id to redraw them.
- **Clear chat**: clearing = emptying `messages` (not just the screen), then `st.rerun()`.
- **Save history**: store Claude's replies as plain dicts (`model_dump`) so `messages` can be saved as JSON.

What each Gradio step taught:
- **Basic**: `gr.ChatInterface(fn)` builds the page; Gradio does NOT rerun the script, it calls `fn` per message. Keep Claude's memory in `gr.State` (`additional_inputs` / `additional_outputs`).
- **Streaming**: make `fn` a generator; each `yield` replaces the reply on screen with the answer so far.
- **Tool calls**: yield a list of `gr.ChatMessage`; `metadata={"title": ..., "status": ...}` becomes a collapsible tool box.
- **Clear chat**: build the page yourself with `gr.Blocks`: place components, then connect events (`.submit`, `.click`) with `inputs` and `outputs`. Clear = empty the chatbot AND the state.
- **Save history**: `demo.load(fn)` runs when a browser opens the page; turn saved `messages` back into chat bubbles with `to_chatbot()`.

What each FastAPI + HTML/JS step taught:
- **Basic**: backend (Python routes: `@app.get("/")`, `@app.post("/chat")`, Pydantic `BaseModel`) + frontend (HTML/CSS/JS, `fetch()` sends JSON). Plain `def` routes run in a thread, so a slow Claude call doesn't block others.
- **Streaming**: `StreamingResponse` over a generator sends NDJSON (one JSON event per line); JS reads it with `response.body.getReader()` and keeps unfinished lines in a buffer.
- **Tool calls**: no backend change (the API already sent tool events); `<details>`/`<summary>` is a built-in collapsible box.
- **Clear chat**: sessions. The page makes a `crypto.randomUUID()` id, keeps it in `localStorage`, sends it with every request; the server keeps `sessions = {id: messages}`. Validate the id with a pattern: never trust browser input.
- **Save history**: one file per session; `GET /history` returns the old chat as the same events `/chat` streams, so one `handleEvent()` draws both live and saved replies.

Streamlit vs Gradio vs FastAPI: Streamlit reruns your script top to bottom and you draw everything; Gradio calls your functions and updates only the components you list as outputs. FastAPI: you build both halves yourself and they talk over HTTP + JSON; the most code, but full control.

## Level 2: Better Agents (Beginner → Intermediate)

- [x] **Streaming**: print the answer as it is generated (`client.messages.stream`) (`chat_ui/agent_core.py` → `stream_agent`)
- [ ] **System prompts**: give the agent a role, rules, and guidance on when to use each tool
- [ ] **Tool error handling**: return failures with `"is_error": True` so Claude can recover
- [ ] **API error handling**: retries, timeouts, rate limits (429), overloaded errors (529)
- [ ] **Tool design**: clear names, good descriptions, input schemas with enums and required fields
- [ ] **Tool choice**: `tool_choice` = auto / any / a specific tool / none
- [ ] **Real tools**: call a real weather API, read/write files, run a database query
- [ ] **Structured output**: get reliable JSON back (tool schema or structured outputs)
- [ ] **Extended thinking**: let Claude reason before answering hard questions
- [ ] **Vision and files**: send images and PDFs to Claude

## Level 3: Memory, Context and Cost (Intermediate)

- [ ] **Context window limits**: why `messages` can't grow forever
- [ ] **Trimming and summarising**: keep the last N turns, summarise older ones
- [ ] **Long-term memory**: save facts to a file or database and load them in later sessions (started: whole chat saved to JSON in `streamlit_app/05_save_history.py`; still to do: save *facts* instead of the whole chat)
- [ ] **Prompt caching**: cache the unchanging start of the prompt to cut cost and latency
- [ ] **Token and cost tracking**: add up usage per session; estimate cost
- [ ] **Model selection**: when to use Haiku vs Sonnet vs Opus

## Level 4: Agent Patterns (Intermediate → Advanced)

- [ ] **ReAct**: think, act, observe, repeat
- [ ] **Plan-and-execute**: write a plan first, then carry it out step by step
- [ ] **Reflection / self-critique**: the agent checks and fixes its own answer
- [ ] **SDK Tool Runner**: the built-in tool loop (`client.beta.messages.tool_runner`) vs your manual loop
- [ ] **RAG**: embeddings, vector store, retrieve relevant chunks, answer from your own documents
- [ ] **Web search / web fetch tools**: server-side tools that Claude runs for you
- [ ] **Code execution tool**: let Claude run code in a sandbox
- [ ] **Multi-agent systems**: orchestrator + specialist sub-agents; agents reviewing each other
- [ ] **MCP (Model Context Protocol)**: connect ready-made tool servers; build your own MCP server
- [ ] **Claude Agent SDK**: build agents on the same framework as Claude Code

## Level 5: Production (Advanced)

- [ ] **Guardrails**: validate tool inputs, allow-lists, limit what tools can do
- [ ] **Human-in-the-loop**: ask for approval before risky actions (delete, send, pay)
- [ ] **Prompt injection defence**: treat tool results and web content as data, not instructions
- [ ] **Evaluation**: test sets with expected results; LLM-as-judge; compare prompt versions
- [ ] **Observability**: log every call, tool use, result and token count; trace a full agent run
- [ ] **Async and parallel tools**: run independent tool calls at the same time
- [ ] **Batch API**: process many requests cheaply when you don't need instant answers
- [ ] **Deployment**: wrap the agent in a web API (FastAPI) or a simple UI (started: web API + UI built in `chat_ui/fastapi_app/`, runs locally; still to do: put it on a server, authentication, HTTPS)
- [ ] **Capstone project**: build a complete agent that solves a real problem end to end

---

## Suggested Next Lessons

| Lesson file | Topics |
|---|---|
| `05_system_prompts_errors.py` | System prompts, tool error handling (streaming is already done) (**next**) |
| `06_real_tools.py` | Real API tool, file read/write tool, API retries |
| `07_structured_output.py` | JSON output, tool choice |
| `08_context_management.py` | Trimming, summarising, prompt caching, cost tracking |
| `09_long_term_memory.py` | Save and load facts across sessions |
| `10_rag.py` | Embeddings, retrieval, answering from documents |
| `11_planning_agent.py` | ReAct, plan-and-execute, reflection |
| `12_multi_agent.py` | Orchestrator + sub-agents |
| `13_mcp.py` | Connect to and build an MCP server |
| `14_eval.py` | Test set and scoring for your agent |

## Changelog

- **2026-09-24**: `03_tool_use.py`: added the `get_current_time` tool; replaced the 2 fixed calls with a `while` agent loop (max 10 turns).
- **2026-09-24**: `04_chat_agent.py`: chat memory (lesson 02) + tool loop (lesson 03) in one script; `history` shows tool calls; an unfinished question is rolled back if the loop limit is hit.
- **2026-09-24**: `chat_ui/agent_core.py`: shared agent module (`ask_agent`, `stream_agent`, `save_history`, `load_history`), reused by every chat UI.
- **2026-09-24**: `chat_ui/streamlit_app/01–05`: Streamlit chatbot built one feature at a time; all 5 steps tested with real API calls.
- **2026-09-24**: `chat_ui/gradio_app/01–05`: Gradio (6.28) chatbot, same 5 steps: `ChatInterface` for steps 1–3, `gr.Blocks` for steps 4–5; all tested with real API calls.
- **2026-09-24**: `chat_ui/fastapi_app/01–05`: FastAPI (0.141) + HTML/JS chatbot, same 5 steps; step 4 adds per-browser sessions, step 5 saves one history file per session. Tested with curl and in headless Chrome.
- **2026-09-24**: `chat_ui/GUIDE.md`: how to run all 15 apps, plus a line-by-line beginner explanation of every step.

## Notes

Write down what you learned, what confused you, and questions to come back to.

- 
