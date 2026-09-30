"""
Capstone starter: a small, complete agent skeleton to grow into your project.

It already runs (with two fake tools), and every place where an earlier
lesson plugs in is marked TODO (lesson N). Copy this folder to start your
capstone, then replace the example tools with your own. See CAPSTONE.md.

    config           -> constants below (later: env vars, lesson 18)
    tools            -> TOOLS registry with risk levels (lessons 6b, 15)
    agent loop       -> run_agent() with turn limit + stop_reason handling (3, 6c)
    guardrails       -> check_tool_call() + approve() (15)
    cost + tracing   -> Usage totals + a JSONL trace per run (8c, 16)
    memory           -> the `messages` list per session (4; later 8 / 9)
    eval             -> EVAL_CASES + run_eval() (14)

Run:
    python 19_capstone/starter_agent.py          chat
    python 19_capstone/starter_agent.py eval     run the eval cases
"""

import json
import os
import sys
import time
import uuid
from datetime import datetime
from pathlib import Path

import anthropic
from dotenv import find_dotenv, load_dotenv

# ---------------------------------------------------------------------------
# Config. TODO (lesson 18): read these from environment variables.
# ---------------------------------------------------------------------------
MODEL = "claude-opus-5-5"      # TODO (lesson 8d): measure a cheaper model / lower effort on your eval
EFFORT = "low"
MAX_TOOL_TURNS = 8
PRICE_IN, PRICE_OUT, PRICE_CACHE_WRITE, PRICE_CACHE_READ = 4.00, 20.00, 5.00, 0.20
TRACE_FILE = Path(__file__).resolve().parent / "traces.jsonl"

SYSTEM_PROMPT = """You are <ROLE> for <WHO>.
Your job: <ONE SENTENCE>.
Rules:
- Use the tools for facts; never guess numbers, prices or dates.
- If a tool fails or an action is declined, explain briefly; don't try to get around it.
- Keep answers short and clear."""  # TODO (lesson 5): write your real prompt

load_dotenv(find_dotenv())
if not os.getenv("ANTHROPIC_API_KEY"):
    raise SystemExit("ANTHROPIC_API_KEY not found. Add it to your .env file.")
client = anthropic.Anthropic()


# ---------------------------------------------------------------------------
# Tools. Each entry: the function, its schema, and a RISK level.
#   read  -> runs automatically
#   write -> needs human approval (lesson 15)
# TODO (lessons 6c, 10, 13): replace these examples with your real tools.
# ---------------------------------------------------------------------------
NOTES = {}


def get_time(timezone: str) -> str:
    from zoneinfo import ZoneInfo
    return datetime.now(ZoneInfo(timezone)).strftime("%Y-%m-%d %H:%M")


def save_note(title: str, text: str) -> str:
    if len(text) > 1000:
        raise ValueError("Note too long (max 1000 characters).")  # TODO (lesson 15): your real limits
    NOTES[title] = text
    return f"Saved note '{title}'."


TOOLS = {
    "get_time": {
        "function": get_time,
        "risk": "read",
        "description": "Current date and time in an IANA timezone such as Asia/Kolkata.",
        "properties": {"timezone": {"type": "string"}},
    },
    "save_note": {
        "function": save_note,
        "risk": "write",
        "description": "Save a short note for the user.",
        "properties": {"title": {"type": "string"}, "text": {"type": "string"}},
    },
}


def tool_definitions() -> list:
    return [
        {
            "name": name,
            "description": t["description"],
            "strict": True,
            "input_schema": {"type": "object", "properties": t["properties"], "required": list(t["properties"]),
                             "additionalProperties": False},
        }
        for name, t in TOOLS.items()
    ]


# ---------------------------------------------------------------------------
# Guardrails (lesson 15).
# ---------------------------------------------------------------------------
AUTO_APPROVE = False  # the eval sets this to True so it can run unattended


def check_tool_call(name: str, args: dict) -> str | None:
    """Return a reason to BLOCK the call, or None. TODO: ownership, limits, allow-lists."""
    if name not in TOOLS:
        return f"Unknown tool {name}."
    return None


def approve(name: str, args: dict) -> bool:
    if TOOLS[name]["risk"] == "read" or AUTO_APPROVE:
        return True
    return input(f"   👤 Allow {name}({json.dumps(args)})? [y/N] ").strip().lower() == "y"


def run_tool(block) -> dict:
    problem = check_tool_call(block.name, block.input)
    if problem:
        output, is_error = f"Blocked: {problem}", True
    elif not approve(block.name, block.input):
        output, is_error = "Declined by the user. Do not try again.", False
    else:
        try:
            output, is_error = TOOLS[block.name]["function"](**block.input), False
        except Exception as e:
            output, is_error = f"Error: {e}", True
    return {"type": "tool_result", "tool_use_id": block.id, "content": output, "is_error": is_error}


# ---------------------------------------------------------------------------
# Cost + tracing (lessons 8c, 16).
# ---------------------------------------------------------------------------
def call_cost(u) -> float:
    return (u.input_tokens * PRICE_IN + (u.cache_creation_input_tokens or 0) * PRICE_CACHE_WRITE
            + (u.cache_read_input_tokens or 0) * PRICE_CACHE_READ + u.output_tokens * PRICE_OUT) / 1e6


def trace(record: dict) -> None:
    with TRACE_FILE.open("a", encoding="utf-8") as f:
        f.write(json.dumps({"time": datetime.now().isoformat(timespec="seconds"), **record}, ensure_ascii=False) + "\n")


# ---------------------------------------------------------------------------
# The agent loop.
# ---------------------------------------------------------------------------
def run_agent(messages: list, question: str) -> tuple[str, float]:
    """Answer one question. Returns (answer, cost in US$). `messages` is the session memory."""
    trace_id, cost, started = uuid.uuid4().hex[:10], 0.0, time.time()
    start = len(messages)
    messages.append({"role": "user", "content": question})
    try:
        for turn in range(1, MAX_TOOL_TURNS + 1):
            response = client.messages.create(
                model=MODEL,
                max_tokens=8000,
                output_config={"effort": EFFORT},
                cache_control={"type": "ephemeral"},  # lesson 8b: check cache_read_input_tokens grows
                system=SYSTEM_PROMPT,
                tools=tool_definitions(),
                messages=messages,
            )
            cost += call_cost(response.usage)
            trace({"trace_id": trace_id, "kind": "llm", "turn": turn, "stop": response.stop_reason,
                   "request_id": response._request_id, "in": response.usage.input_tokens,
                   "cache_read": response.usage.cache_read_input_tokens, "out": response.usage.output_tokens})

            if response.stop_reason == "refusal":
                del messages[start:]
                return "Sorry, I can't help with that.", cost
            if response.stop_reason == "max_tokens":
                del messages[start:]
                return "That answer got too long. Please ask for something shorter.", cost

            messages.append({"role": "assistant", "content": response.content})
            if response.stop_reason != "tool_use":
                answer = "".join(b.text for b in response.content if b.type == "text")
                trace({"trace_id": trace_id, "kind": "done", "seconds": round(time.time() - started, 2), "cost": round(cost, 6)})
                return answer, cost

            results = []
            for block in response.content:
                if block.type == "tool_use":
                    result = run_tool(block)
                    trace({"trace_id": trace_id, "kind": "tool", "name": block.name, "input": block.input,
                           "output": str(result["content"])[:300], "is_error": result["is_error"]})
                    results.append(result)
            messages.append({"role": "user", "content": results})  # all results in ONE message

        del messages[start:]
        return f"Stopped after {MAX_TOOL_TURNS} tool turns without an answer.", cost
    except anthropic.APIError as e:
        del messages[start:]  # keep memory valid for the next question
        trace({"trace_id": trace_id, "kind": "error", "error": str(e)})
        return f"API problem, please try again ({type(e).__name__}).", cost


# ---------------------------------------------------------------------------
# Eval (lesson 14). TODO: 10-20 REAL cases from your users.
# `check` gets (answer, tools_used) and returns True if the case passes.
# ---------------------------------------------------------------------------
EVAL_CASES = [
    {"input": "What time is it in Tokyo?", "check": lambda a, tools: "get_time" in tools},
    {"input": "Save a note called 'milk' saying buy 2 litres", "check": lambda a, tools: "save_note" in tools and "milk" in NOTES},
    {"input": "Who won the 1983 cricket world cup?", "check": lambda a, tools: "india" in a.lower()},
]


def run_eval() -> None:
    global AUTO_APPROVE
    AUTO_APPROVE = True
    passed, total_cost = 0, 0.0
    for case in EVAL_CASES:
        messages = []
        answer, cost = run_agent(messages, case["input"])
        tools_used = [b.name for m in messages if m["role"] == "assistant" for b in m["content"] if b.type == "tool_use"]
        ok = case["check"](answer, tools_used)
        passed += ok
        total_cost += cost
        print(f"{'✅' if ok else '❌'} {case['input'][:50]:<50} tools={tools_used}  ${cost:.4f}")
    print(f"\n{passed}/{len(EVAL_CASES)} passed, ${total_cost:.4f} total")


# ---------------------------------------------------------------------------
# Chat. TODO (chat_ui / lesson 18): put a UI or web API in front of run_agent().
# TODO (lesson 8): trim or summarise `messages` when it gets long.
# ---------------------------------------------------------------------------
def chat() -> None:
    print("Capstone starter. Type 'exit' to quit.\n")
    messages, session_cost = [], 0.0
    while True:
        question = input("You: ").strip()
        if not question:
            continue
        if question.lower() == "exit":
            break
        answer, cost = run_agent(messages, question)
        session_cost += cost
        print(f"Agent: {answer}\n   (${cost:.4f} this question, ${session_cost:.4f} session)\n")


if __name__ == "__main__":
    run_eval() if sys.argv[1:] == ["eval"] else chat()
