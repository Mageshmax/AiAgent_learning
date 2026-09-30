# AI Agent Learning Tracker

Beginner to advanced path for building AI agents with the Claude API.
Tick a box (`[x]`) when you finish a topic. Put the lesson file name next to it.

**Progress:** 14 / 40 topics done · Lessons written: 40 / 40 📘 · Chat UI: 15 / 15 steps done ✅ (update these as you go)

**Last updated:** 2026-09-30. Lessons for all 26 remaining topics written and tested (📘 = lesson ready, study it and tick the box). Next: `07c_vision_files.py` (images and PDFs).

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
- [x] **System prompts**: give the agent a role, rules, and guidance on when to use each tool (`05_system_prompts_errors.py`)
- [x] **Tool error handling**: return failures with `"is_error": True` so Claude can recover (`05_system_prompts_errors.py`)
- [x] **API error handling**: retries, timeouts, rate limits (429), overloaded errors (529) (`06_api_errors.py`)
- [x] **Tool design**: clear names, good descriptions, input schemas with enums and required fields (`06b_tool_design.py`)
- [x] **Tool choice** (`06d_tool_choice.py`): `tool_choice` = auto / none. On `claude-opus-5-5`, `any` and "force a specific tool" return a 400 error: use `auto` + say which tool in the prompt, and `strict: true` on the tool for valid inputs
- [x] **Real tools**: call a real weather API, read/write files, run a database query (`06c_real_tools.py`)
- [x] **Structured output**: get reliable JSON back (tool schema or structured outputs) (`07_structured_output.py`)
- [x] **Extended thinking** (`07b_extended_thinking.py`): let Claude reason before answering hard questions. On `claude-opus-5-5` thinking is always on (can't be disabled, no `budget_tokens`); control depth with `output_config={"effort": "low"|"medium"|"high"|"xhigh"|"max"}` (default `medium`); `thinking={"type": "adaptive", "display": "summarized"}` shows a summary
- [ ] **Vision and files**: send images and PDFs to Claude (📘 `07c_vision_files.py`)

## Level 3: Memory, Context and Cost (Intermediate)

- [ ] **Context window limits**: why `messages` can't grow forever (📘 `08_context_management.py`)
- [ ] **Trimming and summarising**: keep the last N turns, summarise older ones; server-side compaction (📘 `08_context_management.py`)
- [ ] **Long-term memory**: save facts to a file or database and load them in later sessions (📘 `09_long_term_memory.py`: `remember` / `forget` tools + extracting facts after a chat)
- [ ] **Prompt caching**: cache the unchanging start of the prompt to cut cost and latency (📘 `08b_prompt_caching.py`)
- [ ] **Token and cost tracking**: add up usage per session; estimate cost (📘 `08c_cost_tracking.py`)
- [ ] **Model selection**: when to use Haiku vs Sonnet vs Opus (📘 `08d_model_selection.py`)

## Level 4: Agent Patterns (Intermediate → Advanced)

- [ ] **ReAct**: think, act, observe, repeat (📘 `11_planning_agent.py`)
- [ ] **Plan-and-execute**: write a plan first, then carry it out step by step (📘 `11_planning_agent.py`)
- [ ] **Reflection / self-critique**: the agent checks and fixes its own answer (📘 `11_planning_agent.py`)
- [ ] **SDK Tool Runner**: the built-in tool loop (`client.beta.messages.tool_runner`) vs your manual loop (📘 `11b_tool_runner.py`)
- [ ] **RAG**: embeddings, vector store, retrieve relevant chunks, answer from your own documents (📘 `10_rag.py`)
- [ ] **Web search / web fetch tools**: server-side tools that Claude runs for you (📘 `11c_server_tools.py`)
- [ ] **Code execution tool**: let Claude run code in a sandbox (📘 `11c_server_tools.py`)
- [ ] **Multi-agent systems**: orchestrator + specialist sub-agents; agents reviewing each other (📘 `12_multi_agent.py`)
- [ ] **MCP (Model Context Protocol)**: connect ready-made tool servers; build your own MCP server (📘 `13_mcp_server.py` + `13_mcp_client.py`)
- [ ] **Claude Agent SDK**: build agents on the same framework as Claude Code (📘 `13b_agent_sdk.py`)

## Level 5: Production (Advanced)

- [ ] **Guardrails**: validate tool inputs, allow-lists, limit what tools can do (📘 `15_guardrails_hitl.py`)
- [ ] **Human-in-the-loop**: ask for approval before risky actions (delete, send, pay) (📘 `15_guardrails_hitl.py`)
- [ ] **Prompt injection defence**: treat tool results and web content as data, not instructions (📘 `15b_prompt_injection.py`)
- [ ] **Evaluation**: test sets with expected results; LLM-as-judge; compare prompt versions (📘 `14_eval.py`)
- [ ] **Observability**: log every call, tool use, result and token count; trace a full agent run (📘 `16_observability.py`)
- [ ] **Async and parallel tools**: run independent tool calls at the same time (📘 `17_async_parallel.py`)
- [ ] **Batch API**: process many requests cheaply when you don't need instant answers (📘 `17b_batch_api.py`)
- [ ] **Deployment**: wrap the agent in a web API (FastAPI) or a simple UI (📘 `18_deployment/`: access keys, per-user history, rate limit, Docker, HTTPS with Caddy; guide in `18_deployment/README.md`)
- [ ] **Capstone project**: build a complete agent that solves a real problem end to end (📘 `19_capstone/CAPSTONE.md` + `starter_agent.py`)

---

## Lesson Plan

Study in this order. ✅ = studied, 📘 = written and tested, ready to study.

| Lesson file | Topics |
|---|---|
| `05_system_prompts_errors.py` | System prompts, tool error handling ✅ |
| `06_api_errors.py` | API errors: which to fix vs retry, SDK retries and timeouts, a `safe_ask()` that never crashes ✅ |
| `06b_tool_design.py` | Bad vs good tool definition, same questions: names, descriptions, enums, `required`, `strict` ✅ |
| `06c_real_tools.py` | Real weather API (Open-Meteo), notes folder tools, read-only SQLite database, safety limits ✅ |
| `06d_tool_choice.py` | `tool_choice` auto / none / any / tool, `disable_parallel_tool_use`, the `claude-opus-5-5` way to require a tool ✅ |
| `07_structured_output.py` | JSON by prompt vs `output_config` JSON schema vs Pydantic + `messages.parse()` ✅ |
| `07b_extended_thinking.py` | Effort levels, thinking summaries, streaming thinking, thinking in a tool loop, cost of thinking tokens ✅ |
| `07c_vision_files.py` | Images (base64 / URL), several images, PDFs, Files API upload + reuse, citations 📘 (**next**) |
| `08_context_management.py` | Token growth, context window, trimming, summarising, server-side compaction, auto-summary chat 📘 |
| `08b_prompt_caching.py` | Cache a long system prompt, a timestamp that breaks the cache, caching a growing chat 📘 |
| `08c_cost_tracking.py` | `UsageTracker`: cost per call / question / session, estimate before sending, session budget 📘 |
| `08d_model_selection.py` | Same tasks on Haiku / Sonnet / Opus (correctness, time, cost), a model router 📘 |
| `09_long_term_memory.py` | `remember` / `forget` tools, facts file, frozen system prompt per session, extract facts after a chat 📘 |
| `10_rag.py` | Chunking, TF-IDF vectors (numpy), vector store, retrieval, RAG with citations, agentic RAG 📘 |
| `11_planning_agent.py` | ReAct (visible thought/action/observation), plan-and-execute, reflection (code checks + LLM critic) 📘 |
| `11b_tool_runner.py` | `@beta_tool`, `until_done()`, iterating turns, `ToolError`, approval inside a tool, chat 📘 |
| `11c_server_tools.py` | Web search, web fetch (domain allow-list), code execution + file download, `pause_turn` 📘 |
| `12_multi_agent.py` | Orchestrator + analyst / writer / reviewer, parallel sub-agents, writer-reviewer loop 📘 |
| `13_mcp_server.py` + `13_mcp_client.py` | Build an MCP server (tools, resource, prompt); connect it to the tool runner 📘 |
| `13b_agent_sdk.py` | Claude Agent SDK: built-in tools, custom tool, PreToolUse hook, sub-agent, multi-turn client 📘 |
| `14_eval.py` | Test set, code checks, LLM-as-judge, prompt A vs B, case-by-case diff, saved results 📘 |
| `15_guardrails_hitl.py` | Role allow-lists, tool input checks, limits, human approval, output filter, refusal fallback 📘 |
| `15b_prompt_injection.py` | Poisoned review, least privilege, marked untrusted data, detector, reader/doer split 📘 |
| `16_observability.py` | Traces and spans to JSONL, request ids, a trace viewer 📘 |
| `17_async_parallel.py` | `AsyncAnthropic` + `gather`, semaphore, parallel tool calls in the loop 📘 |
| `17b_batch_api.py` | Submit / status / wait / results by `custom_id`, 50% price 📘 |
| `18_deployment/` | Production FastAPI chat, Docker, HTTPS with Caddy, deploy checklist 📘 |
| `19_capstone/` | Project brief, requirements checklist, milestones, runnable starter agent 📘 |

## Changelog

- **2026-09-30**: Wrote lessons for all 26 remaining topics (`07c` to `19_capstone/`), each in the same style (docstring with KEY IDEA, numbered demos, menu or command-line demo number). Every lesson was run with real API calls (estimated US$3-4 in total); findings are written into each file. Highlights: `08b` caching cut 3 calls from $0.035 to $0.020, and a timestamp in the system prompt stopped every cache hit; `08d` Haiku got the hard puzzle wrong (65 vs 154) while Sonnet and Opus got it right; `14_eval` prompt B passed 10/10 vs 5/10 for prompt A; `15b` Claude spotted the injected review by itself, and the layers still block a fooled model; `17` parallel tool calls cut tool time from 8 s to 2 s; `18_deployment` Docker image built and ran as a non-root user. API notes found on the way: a big `max_tokens` needs streaming on Haiku; streamed messages have `stream.request_id`, not `._request_id`; an `AsyncAnthropic` client can't be reused across `asyncio.run()` calls; `mcp` 2.x renamed `FastMCP` to `MCPServer`; the Agent SDK's sub-agent tool is now called `Agent`. Installed in the venv: `pillow`, `mcp`, `claude-agent-sdk`.
- **2026-09-29**: `07b_extended_thinking.py`: 4 demos on `claude-opus-5-5`: effort low / medium / high on one puzzle, `display` omitted vs summarized, streaming the thinking summary, thinking in a manual tool loop (reply appended unchanged). Tested with real API calls (under $0.10 in total). Found: on an easy puzzle all three efforts were right, with about the same time (~3.5 s) and tokens (~300), so effort only matters on hard work. With `omitted` the thinking block comes back with empty text but is still billed. In the tool loop Claude skipped thinking entirely (adaptive).
- **2026-09-28**: `07_structured_output.py`: 4 messy customer messages turned into data 3 ways. Tested with real API calls: asking for JSON in the prompt returned it inside ```json fences (so `json.loads` failed) and made up an intent (`place_order`); `output_config` JSON schema and `messages.parse()` with a Pydantic model gave valid data every time; the results are then counted with plain Python.
- **2026-09-28**: `06c_real_tools.py`: 5 real tools: weather from Open-Meteo (no key; `requests` with a timeout), `list_notes` / `read_note` / `write_note` locked to `lesson_data/notes/` (blocks `../`, only .txt/.md), `query_database` on a sample shop DB opened read-only. Tested offline (16 safety checks) and with real API calls. Found: "Read ../.env" is blocked by Anthropic's safety filter (`stop_reason: "refusal"`, empty reply), so the loop now handles refusals and forgets the refused question. Installed `requests` in the venv.
- **2026-09-28**: `06d_tool_choice.py`: one call per demo to show the effect of each `tool_choice`. Tested with real API calls: `any` gives a 400 on `claude-opus-5-5` but works on `claude-opus-5`; `disable_parallel_tool_use` cut 3 calls to 1. Pitfall found: `none` with no instruction made Claude write tool calls as text until `max_tokens` (16,000 tokens); fixed with a "tools are off" system prompt + small `max_tokens`.
- **2026-09-27**: `06b_tool_design.py`: the same 3 questions asked with a bad tool (`weather(q)`) and a good one (`get_weather_forecast(city enum, days, unit enum)`, `strict: true`). Tested with real API calls: the bad tool gave only one day, needed a retry for "Bengaluru", and answered "tomorrow" with today's weather; the good tool got all three right the first time.
- **2026-09-27**: `06_api_errors.py`: menu of demos that trigger real 401 / 404 / 400 / connection / timeout errors; SDK retry log shows the growing wait; `safe_ask()` catches errors most-specific-first; chat removes the question when a call fails. Tested with real API calls.
- **2026-09-26**: `05_system_prompts_errors.py`: system prompt (role, rules, tool guidance) with a `USE_SYSTEM_PROMPT` on/off switch; tools raise errors and `run_tools` returns them with `is_error: True`. Tested with real API calls: unknown city, divide by zero, off-topic request.
- **2026-09-26**: Updated the tool choice and extended thinking topics for `claude-opus-5-5`; added lesson `07b_thinking_vision.py` to the plan.
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
