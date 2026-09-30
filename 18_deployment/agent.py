"""
The agent for the deployed app (lesson 18).

This is chat_ui/agent_core.py made production-ready:
    - settings come from environment variables, not the code
    - API errors become an "error" event instead of crashing the request,
      and the unanswered question is removed from memory
    - the folder is self-contained, so Docker can build it on its own
"""

import json
import logging
import os
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

import anthropic

log = logging.getLogger("agent")

MODEL = os.getenv("CLAUDE_MODEL", "claude-opus-5-5")
EFFORT = os.getenv("CLAUDE_EFFORT", "low")
MAX_TOKENS = 8000
MAX_TOOL_TURNS = 8
SYSTEM_PROMPT = "You are a helpful assistant. Use the tools when they help. Answer clearly and concisely."

# The SDK reads ANTHROPIC_API_KEY from the environment. Retries are on by default.
client = anthropic.Anthropic(timeout=120, max_retries=2)


# ---------------------------------------------------------------------------
# Tools (same as the chat UI lessons).
# ---------------------------------------------------------------------------
def get_weather(city: str) -> str:
    fake_data = {"chennai": "34°C, humid, sunny", "delhi": "28°C, hazy", "mumbai": "30°C, light rain", "bangalore": "24°C, cloudy"}
    return fake_data.get(city.lower(), f"No weather data for {city}")


def calculator(expression: str) -> str:
    if not set(expression) <= set("0123456789+-*/(). "):
        return "Error: only numbers and + - * / ( ) are allowed"
    try:
        return str(eval(expression, {"__builtins__": {}}))
    except Exception as e:
        return f"Error: {e}"


def get_current_time(timezone: str = "Asia/Kolkata") -> str:
    try:
        return datetime.now(ZoneInfo(timezone)).strftime("%A, %d %B %Y, %I:%M %p %Z")
    except ZoneInfoNotFoundError:
        return f"Error: unknown timezone '{timezone}'."


TOOL_FUNCTIONS = {"get_weather": get_weather, "calculator": calculator, "get_current_time": get_current_time}

TOOLS = [
    {"name": "get_weather", "description": "Get the current weather for a city.",
     "input_schema": {"type": "object", "properties": {"city": {"type": "string"}}, "required": ["city"]}},
    {"name": "calculator", "description": "Evaluate a math expression. Use it for any arithmetic.",
     "input_schema": {"type": "object", "properties": {"expression": {"type": "string"}}, "required": ["expression"]}},
    {"name": "get_current_time", "description": "Current date and time in an IANA timezone (default Asia/Kolkata).",
     "input_schema": {"type": "object", "properties": {"timezone": {"type": "string"}}, "required": []}},
]


def run_tool(name: str, tool_input: dict) -> str:
    function = TOOL_FUNCTIONS.get(name)
    if function is None:
        return f"Error: unknown tool {name}"
    try:
        return function(**tool_input)
    except Exception as e:
        return f"Error: {e}"


# ---------------------------------------------------------------------------
# Streaming agent. Events: text / tool_call / tool_result / error.
# ---------------------------------------------------------------------------
def stream_agent(messages: list):
    start = len(messages) - 1  # the user's question, for rollback
    try:
        for _ in range(MAX_TOOL_TURNS):
            with client.messages.stream(
                model=MODEL,
                max_tokens=MAX_TOKENS,
                output_config={"effort": EFFORT},
                system=SYSTEM_PROMPT,
                tools=TOOLS,
                messages=messages,
            ) as stream:
                for text in stream.text_stream:
                    yield {"type": "text", "text": text}
                response = stream.get_final_message()
                request_id = stream.request_id  # streamed messages don't carry ._request_id

            log.info("claude call: request_id=%s stop=%s in=%s out=%s", request_id,
                     response.stop_reason, response.usage.input_tokens, response.usage.output_tokens)

            if response.stop_reason == "refusal":
                del messages[start:]
                yield {"type": "error", "text": "Sorry, I can't help with that request."}
                return

            messages.append({"role": "assistant", "content": [b.model_dump(exclude_none=True) for b in response.content]})
            if response.stop_reason != "tool_use":
                return

            results = []
            for block in response.content:
                if block.type == "tool_use":
                    yield {"type": "tool_call", "name": block.name, "input": block.input}
                    result = run_tool(block.name, block.input)
                    yield {"type": "tool_result", "name": block.name, "result": result}
                    results.append({"type": "tool_result", "tool_use_id": block.id, "content": result})
            messages.append({"role": "user", "content": results})

        del messages[start:]
        yield {"type": "error", "text": f"Stopped after {MAX_TOOL_TURNS} tool calls without an answer."}

    except anthropic.APIError as e:
        # Log the details for us; show the user a short, safe message.
        log.error("Claude API error: %s", e)
        del messages[start:]
        yield {"type": "error", "text": "The AI service had a problem. Please try again in a moment."}
    except Exception:
        # A bug in OUR code. Full traceback in the log; memory rolled back so
        # the next question still works.
        log.exception("Unexpected error in stream_agent")
        del messages[start:]
        yield {"type": "error", "text": "Something went wrong on our side. Please try again."}


def save_history(messages: list, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(messages, ensure_ascii=False))
    tmp.replace(path)  # write-then-rename: a crash never leaves a half-written file


def load_history(path: Path) -> list:
    return json.loads(path.read_text()) if path.exists() else []
