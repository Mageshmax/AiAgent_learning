"""
Lesson 4: Chat agent = chat with memory (lesson 2) + tool loop (lesson 3).

KEY IDEA: Two loops, one `messages` list.

    OUTER loop (lesson 2): keep asking the user for questions. Every question
        and answer stays in `messages`, so Claude remembers the conversation.
    INNER loop (lesson 3): for each question, keep calling Claude WHILE it
        asks for tools. Tool calls and tool results also go into `messages`.

Commands while chatting:
    history  -> show what we are sending to the LLM (including tool calls)
    exit     -> quit

Try a conversation like:
    You: What is the weather in Chennai?
    You: And in Delhi?                             (memory: knows you mean weather)
    You: What time is it in Tokyo?
    You: How many hours until midnight there?      (memory + time tool + calculator)
    You: What was the first city I asked about?    (memory, no tool)

Run:
    python 04_chat_agent.py
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

MAX_TOOL_TURNS = 10  # safety limit for the inner tool loop


# ---------------------------------------------------------------------------
# STEP A: Our tools - plain Python functions (same as lesson 3).
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
# STEP B: Describe the tools to Claude (same as lesson 3).
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
# STEP C: Helpers.
# ---------------------------------------------------------------------------
def run_tools(response) -> list:
    """Run every tool Claude asked for and return the tool_result blocks."""
    tool_results = []
    for block in response.content:
        if block.type == "text":
            print(f"    Claude says: {block.text}")
        elif block.type == "tool_use":
            print(f"    Claude asks to run: {block.name}({json.dumps(block.input)})")

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
                    parts.append(f"[tool_result {b['content']}]")
        print(f"[{i}] {msg['role']:9}: {' '.join(parts)}")
    print("-----------------------------------------------------\n")


# ---------------------------------------------------------------------------
# STEP D: The chat agent.
# ---------------------------------------------------------------------------
# This list IS the memory: questions, answers, tool calls and tool results.
messages = []

print("Chat agent with tools (type 'history' to see memory, 'exit' to quit)\n")

# OUTER loop: one pass per user question (lesson 2).
while True:
    question = input("You: ").strip()
    if not question:
        continue
    if question.lower() == "exit":
        break
    if question.lower() == "history":
        show_history(messages)
        continue

    start = len(messages)  # so we can undo this question if it fails
    messages.append({"role": "user", "content": question})

    # INNER loop: keep calling Claude while it asks for tools (lesson 3).
    turn = 0
    while turn < MAX_TOOL_TURNS:
        turn += 1
        response = client.messages.create(
            model="claude-opus-5",
            max_tokens=16000,
            system="You are a helpful assistant. Use the tools when they help. Answer clearly and concisely.",
            tools=TOOLS,
            messages=messages,
        )
        messages.append({"role": "assistant", "content": response.content})

        if response.stop_reason != "tool_use":
            break  # final answer for this question

        messages.append({"role": "user", "content": run_tools(response)})
    else:
        # Memory would end with a tool_use that has no tool_result, and the API
        # rejects that. Forget this unfinished question so the chat can continue.
        print(f"    Stopped after {MAX_TOOL_TURNS} calls without a final answer.")
        del messages[start:]
        continue

    answer = "".join(b.text for b in response.content if b.type == "text")
    print(f"\nClaude: {answer}")
    print(
        f"[messages in memory: {len(messages)} | API calls this question: {turn} | "
        f"input_tokens: {response.usage.input_tokens} | "
        f"output_tokens: {response.usage.output_tokens}]\n"
    )
