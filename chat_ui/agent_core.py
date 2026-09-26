"""
Shared agent for all the chat UIs (Streamlit, Gradio, FastAPI).

This is the agent from 04_chat_agent.py (tools + tool loop), turned into
functions so every UI can import it. The UI files then contain ONLY UI code.

    ask_agent(messages)     -> final answer text          (step 1 of each UI)
    stream_agent(messages)  -> yields events as they come (step 2 onwards)
    save_history / load_history                           (step 5)

Both agent functions add to `messages` in place, exactly like lesson 04:
the question, Claude's replies, tool calls and tool results all go in.
"""

import json
import os
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

import anthropic
from dotenv import find_dotenv, load_dotenv

load_dotenv(find_dotenv())
api_key = os.getenv("ANTHROPIC_API_KEY")
if not api_key:
    raise SystemExit("ANTHROPIC_API_KEY not found. Add it to your .env file.")

client = anthropic.Anthropic(api_key=api_key)

MODEL = "claude-opus-5"
MAX_TOKENS = 16000
MAX_TOOL_TURNS = 10  # safety limit for the tool loop
SYSTEM_PROMPT = "You are a helpful assistant. Use the tools when they help. Answer clearly and concisely."


# ---------------------------------------------------------------------------
# Tools (same as lesson 04).
# ---------------------------------------------------------------------------
def get_weather(city: str) -> str:
    """Fake weather data (a real app would call a weather API here)."""
    fake_data = {
        "chennai": "34°C, humid, sunny",
        "delhi": "28°C, hazy",
        "mumbai": "30°C, light rain",
        "bangalore": "24°C, cloudy",
    }
    return fake_data.get(city.lower(), f"No weather data for {city}")


def calculator(expression: str) -> str:
    """Evaluate a simple math expression like '1234 * 5678'."""
    allowed = set("0123456789+-*/(). ")
    if not set(expression) <= allowed:
        return "Error: only numbers and + - * / ( ) are allowed"
    try:
        return str(eval(expression, {"__builtins__": {}}))
    except Exception as e:
        return f"Error: {e}"


def get_current_time(timezone: str = "Asia/Kolkata") -> str:
    """Return the current date and time in an IANA timezone like 'Asia/Tokyo'."""
    try:
        now = datetime.now(ZoneInfo(timezone))
    except ZoneInfoNotFoundError:
        return f"Error: unknown timezone '{timezone}'. Use an IANA name like 'Europe/London'."
    return now.strftime("%A, %d %B %Y, %I:%M:%S %p %Z")


TOOL_FUNCTIONS = {
    "get_weather": get_weather,
    "calculator": calculator,
    "get_current_time": get_current_time,
}

TOOLS = [
    {
        "name": "get_weather",
        "description": "Get the current weather for a city. Use this when the user asks about weather.",
        "input_schema": {
            "type": "object",
            "properties": {
                "city": {"type": "string", "description": "City name, e.g. Chennai"},
            },
            "required": ["city"],
        },
    },
    {
        "name": "calculator",
        "description": "Evaluate a math expression. Use this for any arithmetic instead of calculating yourself.",
        "input_schema": {
            "type": "object",
            "properties": {
                "expression": {"type": "string", "description": "Math expression, e.g. '1234 * 5678'"},
            },
            "required": ["expression"],
        },
    },
    {
        "name": "get_current_time",
        "description": "Get the current date and time in a timezone. Use this whenever the user asks about the current time or date.",
        "input_schema": {
            "type": "object",
            "properties": {
                "timezone": {
                    "type": "string",
                    "description": "IANA timezone name, e.g. 'Asia/Kolkata', 'Europe/London', 'America/New_York'. Defaults to Asia/Kolkata.",
                },
            },
            "required": [],
        },
    },
]


def run_tool(name: str, tool_input: dict) -> str:
    """Run one tool Claude asked for. OUR code runs it, never Claude."""
    function = TOOL_FUNCTIONS.get(name)
    if function is None:
        return f"Error: unknown tool {name}"
    return function(**tool_input)


def _to_dicts(content) -> list:
    """SDK blocks -> plain dicts, so `messages` can be saved as JSON (step 5)."""
    return [block.model_dump(exclude_none=True) for block in content]


# ---------------------------------------------------------------------------
# Non-streaming agent: returns the final answer when everything is done.
# ---------------------------------------------------------------------------
def ask_agent(messages: list) -> str:
    """Run the tool loop for the last user message. Returns the final text."""
    start = len(messages) - 1  # index of the user's question, for rollback

    for _ in range(MAX_TOOL_TURNS):
        response = client.messages.create(
            model=MODEL,
            max_tokens=MAX_TOKENS,
            system=SYSTEM_PROMPT,
            tools=TOOLS,
            messages=messages,
        )
        messages.append({"role": "assistant", "content": _to_dicts(response.content)})

        if response.stop_reason != "tool_use":
            return "".join(b.text for b in response.content if b.type == "text")

        tool_results = []
        for block in response.content:
            if block.type == "tool_use":
                tool_results.append({
                    "type": "tool_result",
                    "tool_use_id": block.id,
                    "content": run_tool(block.name, block.input),
                })
        messages.append({"role": "user", "content": tool_results})

    # Hit the limit: memory ends with an unanswered tool_use, which the API
    # rejects. Forget this whole question so the chat can continue.
    del messages[start:]
    return f"Sorry, I stopped after {MAX_TOOL_TURNS} tool calls without a final answer."


# ---------------------------------------------------------------------------
# Streaming agent: yields events WHILE Claude is working.
#   {"type": "text", "text": "..."}                         a piece of the answer
#   {"type": "tool_call", "name": ..., "input": {...}}      Claude wants a tool
#   {"type": "tool_result", "name": ..., "result": "..."}   we ran it
# ---------------------------------------------------------------------------
def stream_agent(messages: list):
    """Same loop as ask_agent, but yields events so a UI can show them live."""
    start = len(messages) - 1

    for _ in range(MAX_TOOL_TURNS):
        with client.messages.stream(
            model=MODEL,
            max_tokens=MAX_TOKENS,
            system=SYSTEM_PROMPT,
            tools=TOOLS,
            messages=messages,
        ) as stream:
            for text in stream.text_stream:
                yield {"type": "text", "text": text}
            response = stream.get_final_message()

        messages.append({"role": "assistant", "content": _to_dicts(response.content)})

        if response.stop_reason != "tool_use":
            return

        tool_results = []
        for block in response.content:
            if block.type == "tool_use":
                yield {"type": "tool_call", "name": block.name, "input": block.input}
                result = run_tool(block.name, block.input)
                yield {"type": "tool_result", "name": block.name, "result": result}
                tool_results.append({
                    "type": "tool_result",
                    "tool_use_id": block.id,
                    "content": result,
                })
        messages.append({"role": "user", "content": tool_results})

    del messages[start:]
    yield {"type": "text", "text": f"\n\nSorry, I stopped after {MAX_TOOL_TURNS} tool calls without a final answer."}


# ---------------------------------------------------------------------------
# Saving memory to a file (step 5 of each UI).
# ---------------------------------------------------------------------------
def save_history(messages: list, path) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(messages, indent=2, ensure_ascii=False))


def load_history(path) -> list:
    path = Path(path)
    if not path.exists():
        return []
    return json.loads(path.read_text())
