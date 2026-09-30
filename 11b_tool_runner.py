"""
Lesson 11b: The SDK Tool Runner (the built-in agent loop).

KEY IDEA: Since lesson 3 we wrote the agent loop by hand:

    while True:
        response = client.messages.create(..., tools=TOOLS)
        if response.stop_reason != "tool_use": break
        run each tool_use block, append tool_result blocks, call again

The SDK can do that loop for you. You write only the tool FUNCTIONS:

    from anthropic import beta_tool
from anthropic.lib.tools import ToolError

    @beta_tool
    def get_weather(city: str) -> str:
        '''Get the weather for a city.          <- becomes the tool description

        Args:
            city: City name, e.g. Chennai.     <- becomes the parameter description
        '''
        ...

    runner = client.beta.messages.tool_runner(model=..., max_tokens=..., tools=[get_weather], messages=[...])
    final = runner.until_done()          # run the whole loop, get the last message
    # or: for message in runner: ...     # see every turn as it happens

What the runner does for you:
    - builds the JSON input_schema from your type hints + docstring
    - calls your function with Claude's input
    - if your function RAISES, sends the error back with is_error=True (lesson 5).
      Raise ToolError("message") for EXPECTED problems (bad city, unknown id):
      Claude gets exactly your message. Any other exception also goes back as
      an error, but the SDK logs a full traceback, which is right for BUGS.
    - stops when Claude stops asking for tools (or at max_iterations)

Manual loop vs runner:
    manual loop   full control, no beta dependency, more code (lessons 3-11)
    tool runner   less code, same behaviour; it is a BETA feature (client.beta...),
                  so its details may still change

Human approval still works with the runner: ask inside the tool function
and return "declined" instead of doing the action (demo 3).

Caution: the runner does NOT continue a turn that ends with stop_reason
"pause_turn" (server tools, lesson 11c). Use a manual loop for those.

Run:
    python 11b_tool_runner.py        (menu)
    python 11b_tool_runner.py 1 2    (demos 1 and 2)
"""

import os
import sys
from datetime import datetime
from typing import Literal
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

import anthropic
from anthropic import beta_tool
from anthropic.lib.tools import ToolError
from dotenv import find_dotenv, load_dotenv

MODEL = "claude-opus-5-5"

load_dotenv(find_dotenv())
api_key = os.getenv("ANTHROPIC_API_KEY")
if not api_key:
    raise SystemExit("ANTHROPIC_API_KEY not found. Add it to your .env file.")

client = anthropic.Anthropic(api_key=api_key)


def heading(title: str) -> None:
    print(f"\n{'=' * 70}\n{title}\n{'=' * 70}")


def answer_text(message) -> str:
    return "".join(b.text for b in message.content if b.type == "text").strip()


# ---------------------------------------------------------------------------
# STEP A: Tools are plain Python functions with type hints + a docstring.
# ---------------------------------------------------------------------------
FAKE_WEATHER = {"chennai": 33, "bengaluru": 24, "delhi": 38, "mumbai": 30}


@beta_tool
def get_weather(city: str, unit: Literal["celsius", "fahrenheit"] = "celsius") -> str:
    """Get the current temperature in an Indian city.

    Args:
        city: City name, e.g. Chennai.
        unit: Temperature unit.
    """
    temp = FAKE_WEATHER.get(city.lower())
    if temp is None:
        # The runner sends this back to Claude with is_error=True.
        raise ToolError(f"No weather data for '{city}'. Known cities: {', '.join(FAKE_WEATHER)}.")
    if unit == "fahrenheit":
        temp = round(temp * 9 / 5 + 32)
    return f"{temp}°{'F' if unit == 'fahrenheit' else 'C'} in {city.title()}"


@beta_tool
def calculator(expression: str) -> str:
    """Evaluate an arithmetic expression such as '(38 - 24) * 2'.

    Args:
        expression: Numbers and + - * / ( ) only.
    """
    if not set(expression) <= set("0123456789+-*/(). "):
        raise ToolError("Only numbers and + - * / ( ) are allowed.")
    return str(eval(expression, {"__builtins__": {}}))


@beta_tool
def get_current_time(timezone: str = "Asia/Kolkata") -> str:
    """Get the current date and time in a timezone.

    Args:
        timezone: IANA timezone name, e.g. Asia/Kolkata or Europe/London.
    """
    try:
        return datetime.now(ZoneInfo(timezone)).strftime("%A %d %B %Y, %H:%M")
    except ZoneInfoNotFoundError:
        raise ToolError(f"Unknown timezone '{timezone}'.")


TOOLS = [get_weather, calculator, get_current_time]


# ---------------------------------------------------------------------------
# DEMO 1: until_done(). The whole agent loop in one call.
# ---------------------------------------------------------------------------
def demo_until_done():
    heading("DEMO 1: runner.until_done()")
    print("The schema the runner built from get_weather's signature + docstring:")
    print(f"   {get_weather.to_dict()}\n")

    runner = client.beta.messages.tool_runner(
        model=MODEL,
        max_tokens=4000,
        output_config={"effort": "low"},
        tools=TOOLS,
        messages=[{"role": "user", "content": "How much hotter is Delhi than Bengaluru right now, in °F?"}],
    )
    final = runner.until_done()
    print(f"Claude: {answer_text(final)}")


# ---------------------------------------------------------------------------
# DEMO 2: Iterate to SEE every turn (and an error handled for you).
# ---------------------------------------------------------------------------
def demo_iterate():
    heading("DEMO 2: iterate over the runner (see each turn)")
    runner = client.beta.messages.tool_runner(
        model=MODEL,
        max_tokens=4000,
        output_config={"effort": "low"},
        tools=TOOLS,
        max_iterations=6,  # safety limit, like MAX_TOOL_TURNS in lesson 3
        messages=[{"role": "user", "content": "What's the weather in Chennai and in Ooty? And what time is it in London?"}],
    )
    for turn, message in enumerate(runner, start=1):
        print(f"\nTurn {turn}: stop_reason={message.stop_reason}")
        for block in message.content:
            if block.type == "tool_use":
                print(f"   🔧 {block.name}({block.input})")
            elif block.type == "text" and block.text.strip():
                print(f"   💬 {block.text.strip()}")
        # Peek at what the runner will send back (it runs the tools once and caches the result).
        tool_response = runner.generate_tool_call_response()
        if tool_response:
            for result in tool_response["content"]:
                flag = "❌" if result.get("is_error") else "✅"
                print(f"   {flag} result: {str(result['content'])[:120]}")
    print("\nOoty isn't in our data: the tool raised ToolError, the runner sent it back as an error,")
    print("and Claude explained it. No try/except needed in our code.")


# ---------------------------------------------------------------------------
# DEMO 3: Human approval inside a tool (works with the runner).
# ---------------------------------------------------------------------------
ORDERS = {"A101": "2 x Filter coffee", "A102": "1 x Ghee 1L", "A103": "5 x Toor dal"}


@beta_tool
def cancel_order(order_id: str) -> str:
    """Cancel a customer's order. This cannot be undone.

    Args:
        order_id: Order id such as A101.
    """
    if order_id not in ORDERS:
        raise ToolError(f"No order {order_id}.")
    answer = input(f"   ⚠️  Claude wants to CANCEL order {order_id} ({ORDERS[order_id]}). Allow? [y/N] ")
    if answer.strip().lower() != "y":
        return "The user declined. The order was NOT cancelled."
    del ORDERS[order_id]
    return f"Order {order_id} cancelled."


def demo_approval():
    heading("DEMO 3: approval inside a tool")
    runner = client.beta.messages.tool_runner(
        model=MODEL,
        max_tokens=4000,
        output_config={"effort": "low"},
        tools=[cancel_order],
        messages=[{"role": "user", "content": "Please cancel orders A101 and A103."}],
    )
    print(f"Claude: {answer_text(runner.until_done())}")
    print(f"Orders left: {ORDERS}")


# ---------------------------------------------------------------------------
# DEMO 4: A chat with the runner. The runner keeps its OWN copy of the
# history, so to remember across questions we mirror each turn into our
# `messages` list (the same list shape as lesson 4).
# ---------------------------------------------------------------------------
def demo_chat():
    heading("DEMO 4: chat using the tool runner")
    print("Ask about weather, time or maths. Type 'exit' to go back.\n")
    messages = []
    while True:
        question = input("You: ").strip()
        if not question:
            continue
        if question.lower() == "exit":
            return
        messages.append({"role": "user", "content": question})
        runner = client.beta.messages.tool_runner(
            model=MODEL, max_tokens=4000, output_config={"effort": "low"}, tools=TOOLS, messages=messages,
        )
        last = None
        for message in runner:
            last = message
            messages.append({"role": "assistant", "content": message.content})
            tool_response = runner.generate_tool_call_response()  # cached: tools still run only once
            if tool_response:
                messages.append(tool_response)
        print(f"Claude: {answer_text(last)}\n")


# ---------------------------------------------------------------------------
# Menu.
# ---------------------------------------------------------------------------
DEMOS = {"1": demo_until_done, "2": demo_iterate, "3": demo_approval, "4": demo_chat}

MENU = """
Pick a demo:
  1  until_done(): the whole loop in one call
  2  Iterate: see every turn, errors handled for you
  3  Human approval inside a tool
  4  Chat with the runner
  q  Quit"""

if len(sys.argv) > 1:
    for key in sys.argv[1:]:
        DEMOS[key]()
    sys.exit()

while True:
    print(MENU)
    choice = input("Choice: ").strip().lower()
    if choice == "q":
        break
    if choice in DEMOS:
        DEMOS[choice]()
    else:
        print("Unknown choice.")
