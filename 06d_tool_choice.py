"""
Lesson 6d: Tool choice.

KEY IDEA: `tool_choice` controls WHETHER Claude may, must, or must not use tools.

    tool_choice                              Meaning
    {"type": "auto"}              (default)  Claude decides: a tool, or a plain answer
    {"type": "none"}                         Claude may NOT call tools (text only)
    {"type": "any"}                          Claude MUST call a tool (it picks which)
    {"type": "tool", "name": "get_weather"}  Claude MUST call THIS tool

    Extra option (works with auto):
    {"type": "auto", "disable_parallel_tool_use": True}
                                             At most ONE tool call per reply

IMPORTANT for claude-opus-5-5 (our main model):
    "any" and "tool" are NOT supported -> the API returns a 400 error.
    (claude-opus-5 still supports them, so demo 3 uses that model to show them.)
    The claude-opus-5-5 way to make sure a tool gets used:
        1. tool_choice auto + say which tool to use in the system prompt
        2. "strict": True on the tool, so its inputs always match the schema
        3. CHECK the reply really has a tool_use; if not, remind Claude once

Each demo makes ONE call (or two) and prints what Claude sent back, so you can
see the effect of tool_choice on the very first reply.

Run:
    python 06d_tool_choice.py
"""

import json
import os

import anthropic
from dotenv import find_dotenv, load_dotenv

MODEL = "claude-opus-5-5"
OLDER_MODEL = "claude-opus-5"  # still supports tool_choice "any" and "tool"

load_dotenv(find_dotenv())
api_key = os.getenv("ANTHROPIC_API_KEY")
if not api_key:
    raise SystemExit("ANTHROPIC_API_KEY not found. Add it to your .env file.")

client = anthropic.Anthropic(api_key=api_key)


# ---------------------------------------------------------------------------
# STEP A: Two small tools (strict, as in lesson 6b). We never run them here:
# this lesson only looks at what Claude ASKS for.
# ---------------------------------------------------------------------------
TOOLS = [
    {
        "name": "get_weather",
        "description": "Get today's weather for a city. Use this when the user asks about weather.",
        "strict": True,
        "input_schema": {
            "type": "object",
            "properties": {
                "city": {"type": "string", "description": "City name, e.g. Chennai"},
            },
            "required": ["city"],
            "additionalProperties": False,
        },
    },
    {
        "name": "get_current_time",
        "description": "Get the current date and time in an IANA timezone. Use this when the user asks about the time or date.",
        "strict": True,
        "input_schema": {
            "type": "object",
            "properties": {
                "timezone": {"type": "string", "description": "IANA timezone, e.g. Asia/Kolkata"},
            },
            "required": ["timezone"],
            "additionalProperties": False,
        },
    },
]


# ---------------------------------------------------------------------------
# STEP B: Helpers.
# ---------------------------------------------------------------------------
def ask_once(question: str, model: str = MODEL, max_tokens: int = 16000, **options):
    """ONE API call. Returns the response, or None if the API rejected it."""
    try:
        return client.messages.create(
            model=model,
            max_tokens=max_tokens,
            tools=TOOLS,
            messages=[{"role": "user", "content": question}],
            **options,  # tool_choice=..., system=...
        )
    except anthropic.BadRequestError as e:
        print(f"    ❌ 400 error: {e.body['error']['message']}")
        return None


def show(response) -> None:
    """Print the tool calls and text in Claude's reply."""
    if response is None:
        return
    for block in response.content:
        if block.type == "tool_use":
            print(f"    🔧 tool call: {block.name}({json.dumps(block.input)})")
        elif block.type == "text":
            print(f"    💬 text: {block.text}")
    print(f"    stop_reason: {response.stop_reason}")


def heading(title: str, question: str, tool_choice) -> None:
    print(f"\n{'=' * 70}\n{title}\n  Q: {question}\n  tool_choice: {tool_choice}")


# ---------------------------------------------------------------------------
# STEP C: Demos.
# ---------------------------------------------------------------------------

# 1. AUTO: Claude decides. Uses a tool only when it helps.
for q in ["What's the weather in Chennai?", "What is the capital of France?"]:
    heading("1. auto (the default)", q, {"type": "auto"})
    show(ask_once(q, tool_choice={"type": "auto"}))

# 2. NONE: tools are in the request, but Claude may not call them.
#    Useful for a final "summarise now, no more tools" call at the end of
#    an agent loop (e.g. when you hit MAX_TOOL_TURNS).
#    CAREFUL: Claude still SEES the tools. Without an instruction, it may try
#    to "call" them by writing tool-call text, again and again, until
#    max_tokens. (When we tested this lesson, that happened and burned
#    16,000 tokens!) So always:
#      - TELL Claude that tools are off for this reply
#      - use a small max_tokens as a safety net
NO_TOOLS_SYSTEM = (
    "Tools are turned off for this reply. Answer in plain text only. "
    "If you would need a tool to answer, say so briefly. "
    "Do not write tool calls or XML tags in your answer."
)
q = "What's the weather in Chennai?"
heading("2. none (+ tell Claude tools are off)", q, {"type": "none"})
show(ask_once(q, tool_choice={"type": "none"}, system=NO_TOOLS_SYSTEM, max_tokens=500))

# 3. ANY and TOOL: forcing a tool call.
q = "Hi there!"
heading(f"3a. any on {MODEL}", q, {"type": "any"})
show(ask_once(q, tool_choice={"type": "any"}))  # -> 400 on claude-opus-5-5

heading(f"3b. any on {OLDER_MODEL}", q, {"type": "any"})
show(ask_once(q, model=OLDER_MODEL, tool_choice={"type": "any"}))  # must call SOME tool, even for "Hi"

q = "Tell me about Chennai."
choice = {"type": "tool", "name": "get_weather"}
heading(f"3c. tool (a specific one) on {OLDER_MODEL}", q, choice)
show(ask_once(q, model=OLDER_MODEL, tool_choice=choice))  # must call get_weather (may add others too)

# 4. The claude-opus-5-5 way: auto + instruction in the prompt + check + remind.
SYSTEM = (
    "You are a travel assistant. Before answering ANY question about a city, "
    "call get_weather for that city first."
)


def ask_must_use_tool(question: str):
    """auto + system prompt instruction; if no tool was called, remind Claude once."""
    messages = [{"role": "user", "content": question}]
    for attempt in (1, 2):
        response = client.messages.create(
            model=MODEL, max_tokens=16000, system=SYSTEM, tools=TOOLS,
            tool_choice={"type": "auto"}, messages=messages,
        )
        if any(b.type == "tool_use" for b in response.content):
            print(f"    ✅ tool used on attempt {attempt}")
            return response
        # No tool call: keep Claude's reply, then add a reminder and try again.
        messages.append({"role": "assistant", "content": response.content})
        messages.append({"role": "user", "content": "Please call get_weather first, as instructed."})
    print("    ⚠️ still no tool call after a reminder")
    return response


q = "Tell me about Chennai."
heading(f"4. auto + prompt + check (the {MODEL} way)", q, {"type": "auto"})
show(ask_must_use_tool(q))

# 5. PARALLEL tool calls: by default Claude may ask for several tools at once.
q = "What's the weather in Chennai, Delhi and Mumbai?"
heading("5a. auto: parallel calls allowed", q, {"type": "auto"})
show(ask_once(q, tool_choice={"type": "auto"}))

choice = {"type": "auto", "disable_parallel_tool_use": True}
heading("5b. auto + disable_parallel_tool_use", q, choice)
show(ask_once(q, tool_choice=choice))  # only ONE call; the rest come in later turns
