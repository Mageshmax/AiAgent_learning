"""
Lesson 3: Tool use - your first step to a real agent.

KEY IDEA: Claude cannot run code. It can only ASK us to run a tool.

    1. We describe our tools to Claude (name, what it does, what inputs it needs).
    2. Claude replies with stop_reason="tool_use" and a tool_use block:
          "please call get_weather with {'city': 'Chennai'}"
    3. OUR code runs the Python function.
    4. We send the result back as a tool_result block.
    5. Claude uses the result to write the final answer.

Try questions like:
    What is the weather in Chennai?
    What is 1234 * 5678?
    What is the weather in Delhi and Mumbai?      (two tool calls at once)
    What time is it in Tokyo?
    What time is it in London, and what is 17 * 23?
    How many hours until midnight in Chennai?     (time tool, then calculator -> needs the loop)
    Who wrote Thirukkural?                        (no tool needed)

Run:
    python 03_tool_use.py
"""

import json
import os
from datetime import datetime
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

import anthropic
from dotenv import find_dotenv, load_dotenv

load_dotenv(find_dotenv())
api_key = os.getenv("ANTHROPIC_API_KEY")
if not api_key:
    raise SystemExit("ANTHROPIC_API_KEY not found. Add it to your .env file.")

client = anthropic.Anthropic(api_key=api_key)


# ---------------------------------------------------------------------------
# STEP A: Our tools - plain Python functions.
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


# Map tool names (what Claude says) -> Python functions (what we run).
TOOL_FUNCTIONS = {
    "get_weather": get_weather,
    "calculator": calculator,
    "get_current_time": get_current_time,
}


# ---------------------------------------------------------------------------
# STEP B: Describe the tools to Claude.
# Claude only sees these descriptions, never your Python code.
# A clear description = Claude knows WHEN and HOW to use the tool.
# ---------------------------------------------------------------------------
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
# STEP C: The agent loop.
# Keep calling Claude WHILE it asks for tools. Each time, run the tools and
# send the results back. Stop when Claude gives a final answer.
# ---------------------------------------------------------------------------
question = input("Ask Claude a question: ")
messages = [{"role": "user", "content": question}]

MAX_TURNS = 10  # safety limit so a confused model can't loop forever
turn = 0

while turn < MAX_TURNS:
    turn += 1
    print(f"\n>>> CALL {turn}: sending messages to Claude")
    response = client.messages.create(
        model="claude-opus-5",
        max_tokens=16000,
        tools=TOOLS,
        messages=messages,
    )
    print(f"<<< stop_reason = {response.stop_reason}")

    # Save Claude's reply (including any tool_use blocks) to memory.
    messages.append({"role": "assistant", "content": response.content})

    if response.stop_reason != "tool_use":
        # No more tools needed - this is the final answer.
        break

    # Run every tool Claude asked for, and collect the results.
    tool_results = []
    for block in response.content:
        if block.type == "text":
            print(f"    Claude says: {block.text}")
        elif block.type == "tool_use":
            print(f"    Claude asks to run: {block.name}({json.dumps(block.input)})   [id={block.id}]")

            function = TOOL_FUNCTIONS.get(block.name)
            if function is None:
                result = f"Error: unknown tool {block.name}"
            else:
                result = function(**block.input)  # <-- OUR code runs the tool
            print(f"    We ran it. Result: {result}")

            tool_results.append({
                "type": "tool_result",
                "tool_use_id": block.id,  # links this result to Claude's request
                "content": result,
            })

    # All tool results go back together, in ONE user message.
    messages.append({"role": "user", "content": tool_results})
else:
    print(f"\nStopped after {MAX_TURNS} calls without a final answer.")

answer = "".join(b.text for b in response.content if b.type == "text")
print(f"\nClaude: {answer}")
