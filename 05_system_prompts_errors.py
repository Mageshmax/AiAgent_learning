"""
Lesson 5: System prompts + tool error handling.

Builds on lesson 4 (chat memory + tool loop). Two new ideas:

1. SYSTEM PROMPT = the agent's job description. It is sent with EVERY call,
   separately from `messages`. A good one has:
       - a ROLE      (who the agent is)
       - RULES       (what it must / must not do)
       - TOOL GUIDANCE (when to use which tool, what to do when one fails)

2. TOOL ERRORS. Tools fail: unknown city, bad timezone, divide by zero...
   Instead of crashing the program, we catch the error and send it back as a
   tool_result with "is_error": True. Claude reads the error message and
   recovers: it fixes its input and retries, or explains the problem to the user.
   TIP: write error messages that help Claude fix the problem
   (e.g. list the valid choices).

Commands while chatting:
    system   -> show the system prompt being sent
    history  -> show what we are sending to the LLM (including tool errors)
    exit     -> quit

Try these:
    You: What's the weather in London?        (tool error -> Claude explains, suggests known cities)
    You: What time is it in Bangalore?        (may guess 'Asia/Bangalore' -> error -> retries with 'Asia/Kolkata')
    You: What is 10 / 0?                       (calculator error -> Claude explains)
    You: What is 17 * 23?                      (rule: must use the calculator, not mental maths)
    You: Write me a poem about the sea.        (rule: politely declines off-topic requests)

Experiment:
    Set USE_SYSTEM_PROMPT = False below and ask the same questions.
    Without rules, Claude may answer off-topic questions, guess the maths,
    or give long answers. Compare!

Run:
    python 05_system_prompts_errors.py
"""

import json
import os
from datetime import datetime
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

import anthropic
from dotenv import find_dotenv, load_dotenv

USE_SYSTEM_PROMPT = True  # set to False to see how Claude behaves without it

MODEL = "claude-opus-5-5"
MAX_TOOL_TURNS = 10  # safety limit for the inner tool loop

load_dotenv(find_dotenv())
api_key = os.getenv("ANTHROPIC_API_KEY")
if not api_key:
    raise SystemExit("ANTHROPIC_API_KEY not found. Add it to your .env file.")

client = anthropic.Anthropic(api_key=api_key)


# ---------------------------------------------------------------------------
# STEP A: The system prompt (NEW).
# ---------------------------------------------------------------------------
# Role -> rules -> tool guidance. Plain, specific sentences work best.
SYSTEM_PROMPT = """\
You are "Daily Helper", a friendly assistant for weather, time and maths questions.

Rules:
- Only help with weather, dates/times and arithmetic. For anything else, say briefly
  and politely that you can only help with those three things.
- Keep answers short: at most 3 sentences.
- Never make up weather data. If the weather tool has no data, say so.

Using tools:
- Use get_weather for any weather question.
- Use get_current_time for any question about the current time or date. Convert city
  names to IANA timezones yourself (for example Bangalore -> Asia/Kolkata).
- Use calculator for ALL arithmetic, even easy sums. Never calculate in your head.
- If a tool returns an error, read the message. If you can fix your input, try again
  once. Otherwise tell the user, in plain words, what went wrong.
"""


# ---------------------------------------------------------------------------
# STEP B: Tools that can FAIL (NEW: they raise errors instead of returning text).
# ---------------------------------------------------------------------------
FAKE_WEATHER = {
    "chennai": "34°C, humid, sunny",
    "delhi": "28°C, hazy",
    "mumbai": "30°C, light rain",
    "bangalore": "24°C, cloudy",
}


def get_weather(city: str) -> str:
    """Fake weather data (a real app would call a weather API here)."""
    if city.lower() not in FAKE_WEATHER:
        # A HELPFUL error: it tells Claude which cities do work.
        known = ", ".join(c.title() for c in FAKE_WEATHER)
        raise ValueError(f"No weather data for '{city}'. Known cities: {known}.")
    return FAKE_WEATHER[city.lower()]


def calculator(expression: str) -> str:
    """Evaluate a simple math expression like '1234 * 5678'."""
    allowed = set("0123456789+-*/(). ")
    if not set(expression) <= allowed:
        raise ValueError("Only numbers and + - * / ( ) are allowed.")
    return str(eval(expression, {"__builtins__": {}}))  # 1/0 raises ZeroDivisionError


def get_current_time(timezone: str = "Asia/Kolkata") -> str:
    """Return the current date and time in an IANA timezone like 'Asia/Tokyo'."""
    try:
        now = datetime.now(ZoneInfo(timezone))
    except (ZoneInfoNotFoundError, ValueError):
        raise ValueError(
            f"Unknown timezone '{timezone}'. Use an IANA name like 'Asia/Kolkata' or 'Europe/London'."
        )
    return now.strftime("%A, %d %B %Y, %I:%M:%S %p %Z")


TOOL_FUNCTIONS = {
    "get_weather": get_weather,
    "calculator": calculator,
    "get_current_time": get_current_time,
}

# Tool descriptions (same as lesson 4).
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


# ---------------------------------------------------------------------------
# STEP C: Run tools and CATCH their errors (NEW).
# ---------------------------------------------------------------------------
def run_tools(response) -> list:
    """Run every tool Claude asked for. Errors become tool_results with is_error=True."""
    tool_results = []
    for block in response.content:
        if block.type == "text":
            print(f"    Claude says: {block.text}")
        elif block.type == "tool_use":
            print(f"    Claude asks to run: {block.name}({json.dumps(block.input)})")

            function = TOOL_FUNCTIONS.get(block.name)
            try:
                if function is None:
                    raise ValueError(f"Unknown tool '{block.name}'.")
                result = function(**block.input)  # <-- OUR code runs the tool
                is_error = False
                print(f"    We ran it. Result: {result}")
            except Exception as e:
                # Don't crash: turn the error into a message Claude can read.
                result = f"Error ({type(e).__name__}): {e}"
                is_error = True
                print(f"    ❌ Tool failed: {result}")

            tool_results.append({
                "type": "tool_result",
                "tool_use_id": block.id,  # links this result to Claude's request
                "content": result,
                "is_error": is_error,     # NEW: tells Claude this call failed
            })
    # All results go back together, in ONE user message.
    return tool_results


def show_history(messages: list) -> None:
    """Print the messages list, including tool calls and tool results."""
    print("\n--- messages list (sent to the LLM on every call) ---")
    for i, msg in enumerate(messages):
        content = msg["content"]
        if isinstance(content, str):
            parts = [content]
        else:
            parts = []
            for b in content:
                # Claude's blocks are SDK objects; our tool_result blocks are dicts.
                b_type = b["type"] if isinstance(b, dict) else b.type
                if b_type == "text":
                    parts.append(b.text)
                elif b_type == "tool_use":
                    parts.append(f"[tool_use {b.name}({json.dumps(b.input)})]")
                elif b_type == "tool_result":
                    label = "tool_result ERROR" if b.get("is_error") else "tool_result"
                    parts.append(f"[{label} {b['content']}]")
        print(f"[{i}] {msg['role']:9}: {' '.join(parts)}")
    print("-----------------------------------------------------\n")


# ---------------------------------------------------------------------------
# STEP D: The chat agent (same two loops as lesson 4).
# ---------------------------------------------------------------------------
messages = []

# The system prompt is a separate parameter, NOT part of `messages`.
extra = {"system": SYSTEM_PROMPT} if USE_SYSTEM_PROMPT else {}

status = "ON" if USE_SYSTEM_PROMPT else "OFF"
print(f"Daily Helper (system prompt {status}) - type 'system', 'history' or 'exit'\n")

while True:
    question = input("You: ").strip()
    if not question:
        continue
    if question.lower() == "exit":
        break
    if question.lower() == "history":
        show_history(messages)
        continue
    if question.lower() == "system":
        print(f"\n--- system prompt ({status}) ---\n{SYSTEM_PROMPT if USE_SYSTEM_PROMPT else '(none)'}")
        continue

    start = len(messages)  # so we can undo this question if it fails
    messages.append({"role": "user", "content": question})

    turn = 0
    while turn < MAX_TOOL_TURNS:
        turn += 1
        response = client.messages.create(
            model=MODEL,
            max_tokens=16000,
            tools=TOOLS,
            messages=messages,
            **extra,  # adds system=SYSTEM_PROMPT when USE_SYSTEM_PROMPT is True
        )
        messages.append({"role": "assistant", "content": response.content})

        if response.stop_reason != "tool_use":
            break  # final answer for this question

        messages.append({"role": "user", "content": run_tools(response)})
    else:
        print(f"    Stopped after {MAX_TOOL_TURNS} calls without a final answer.")
        del messages[start:]
        continue

    if response.stop_reason == "refusal":
        print("\nClaude declined to answer this request.\n")
        continue
    if response.stop_reason == "max_tokens":
        print("    (answer was cut off: raise max_tokens)")

    answer = "".join(b.text for b in response.content if b.type == "text")
    print(f"\nClaude: {answer}")
    print(
        f"[API calls this question: {turn} | "
        f"input_tokens: {response.usage.input_tokens} | "
        f"output_tokens: {response.usage.output_tokens}]\n"
    )
