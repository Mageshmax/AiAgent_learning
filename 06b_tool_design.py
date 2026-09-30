"""
Lesson 6b: Tool design.

KEY IDEA: Claude never sees your Python code. It only sees the tool's
NAME, DESCRIPTION and INPUT SCHEMA. Those three things decide:
    - WHETHER Claude uses the tool
    - WHAT inputs it sends
So a tool definition is really a small instruction manual for Claude.

This lesson asks the SAME questions twice:
    BAD tool:  name "weather", description "weather", one vague text input
    GOOD tool: clear name, full description, typed inputs with enums
and prints the inputs Claude sends, so you can compare.

Checklist for a good tool:
    1. NAME: verb_noun, specific               get_weather_forecast, not weather
    2. DESCRIPTION: what it does, WHEN to use it, what it returns, its limits
    3. Every PARAMETER has a type and a description with an example
    4. "enum" for fixed choices               unit: celsius | fahrenheit
    5. "required" lists what must be sent; "additionalProperties": False
       blocks made-up extra fields
    6. "strict": True -> the API guarantees the inputs match the schema
    7. One tool = one job. Fewer, clearer tools beat many similar ones.
    8. STILL validate in your code (strict can't check number ranges like 1-7)
       and return helpful errors with is_error (lesson 5).

Run:
    python 06b_tool_design.py
"""

import json
import os
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import anthropic
from dotenv import find_dotenv, load_dotenv

MODEL = "claude-opus-5-5"
MAX_TOOL_TURNS = 5

load_dotenv(find_dotenv())
api_key = os.getenv("ANTHROPIC_API_KEY")
if not api_key:
    raise SystemExit("ANTHROPIC_API_KEY not found. Add it to your .env file.")

client = anthropic.Anthropic(api_key=api_key)


# ---------------------------------------------------------------------------
# STEP A: Fake 7-day forecast data (a real app would call a weather API).
# ---------------------------------------------------------------------------
CITIES = ["Chennai", "Delhi", "Mumbai", "Bangalore"]
FORECAST = {  # (temperature in °C, conditions) for today and the next 6 days
    "Chennai":   [(34, "humid, sunny"), (33, "sunny"), (31, "thunderstorms"), (30, "heavy rain"),
                  (32, "cloudy"), (34, "sunny"), (35, "hot, sunny")],
    "Delhi":     [(28, "hazy"), (27, "hazy"), (25, "light rain"), (26, "cloudy"),
                  (29, "sunny"), (30, "sunny"), (27, "windy")],
    "Mumbai":    [(30, "light rain"), (29, "heavy rain"), (29, "heavy rain"), (30, "showers"),
                  (31, "cloudy"), (31, "cloudy"), (32, "sunny")],
    "Bangalore": [(24, "cloudy"), (23, "light rain"), (22, "rain"), (24, "cloudy"),
                  (25, "sunny"), (26, "sunny"), (24, "showers")],
}


def forecast_line(city: str, day: int, unit: str = "celsius") -> str:
    """One day of forecast, e.g. 'Sat 27 Sep: 31°C, thunderstorms'."""
    date = datetime.now(ZoneInfo("Asia/Kolkata")) + timedelta(days=day)
    temp, conditions = FORECAST[city][day]
    if unit == "fahrenheit":
        temp, symbol = round(temp * 9 / 5 + 32), "°F"
    else:
        symbol = "°C"
    return f"{date:%a %d %b}: {temp}{symbol}, {conditions}"


# ---------------------------------------------------------------------------
# STEP B: The BAD tool.
# ---------------------------------------------------------------------------
# Problems: vague name, one-word description, one free-text input "q" with no
# description. Claude has to GUESS what to send, and our code has to guess
# what Claude meant.
BAD_TOOLS = [
    {
        "name": "weather",
        "description": "weather",
        "input_schema": {
            "type": "object",
            "properties": {"q": {"type": "string"}},
        },
    },
]


def bad_weather(q: str = "") -> str:
    """Looks for a known city name somewhere in the text. Today only, °C only."""
    for city in CITIES:
        if city.lower() in q.lower():
            return forecast_line(city, 0)
    return "no data"  # unhelpful error: doesn't say WHY or what would work


# ---------------------------------------------------------------------------
# STEP C: The GOOD tool.
# ---------------------------------------------------------------------------
GOOD_TOOLS = [
    {
        # 1. Specific verb_noun name.
        "name": "get_weather_forecast",
        # 2. What it does + WHEN to use it + what it returns + limits.
        "description": (
            "Get the weather forecast for one city, for today and up to the next 6 days. "
            "Use this whenever the user asks about weather, temperature, rain, or what to wear, "
            "including questions about future days such as 'tomorrow' or 'this weekend'. "
            "Returns one line per day, starting with today, in the form 'Sat 27 Sep: 31°C, thunderstorms'. "
            "Only these cities are available: Chennai, Delhi, Mumbai, Bangalore."
        ),
        # 6. strict: the API guarantees the inputs match this schema.
        "strict": True,
        "input_schema": {
            "type": "object",
            "properties": {
                "city": {
                    "type": "string",
                    "enum": CITIES,  # 4. fixed choices: Claude must pick one of these
                    "description": "The city. Map other spellings to these names, e.g. Bengaluru -> Bangalore.",
                },
                "days": {
                    "type": "integer",
                    "description": "How many days to return, from 1 (today only) to 7 (today + 6 days). "
                                   "Pick enough days to cover the dates the user asked about.",
                },
                "unit": {
                    "type": "string",
                    "enum": ["celsius", "fahrenheit"],
                    "description": "Temperature unit. Use fahrenheit only if the user asks for it "
                                   "or says they are from the USA; otherwise celsius.",
                },
            },
            "required": ["city", "days", "unit"],  # 5. must always be sent
            "additionalProperties": False,          # 5. no made-up extra fields
        },
    },
]


def get_weather_forecast(city: str, days: int, unit: str) -> str:
    # 8. strict can't check number ranges, so check them here.
    if not 1 <= days <= 7:
        raise ValueError(f"days must be between 1 and 7, got {days}.")
    return "\n".join(forecast_line(city, day, unit) for day in range(days))


BAD_FUNCTIONS = {"weather": bad_weather}
GOOD_FUNCTIONS = {"get_weather_forecast": get_weather_forecast}


# ---------------------------------------------------------------------------
# STEP D: Ask one question with one set of tools (the loop from lesson 4-5).
# ---------------------------------------------------------------------------
def ask(question: str, tools: list, functions: dict) -> str:
    messages = [{"role": "user", "content": question}]
    for _ in range(MAX_TOOL_TURNS):
        response = client.messages.create(
            model=MODEL,
            max_tokens=16000,
            system="You are a helpful weather assistant. Answer in at most 2 sentences.",
            tools=tools,
            messages=messages,
        )
        messages.append({"role": "assistant", "content": response.content})
        if response.stop_reason != "tool_use":
            return "".join(b.text for b in response.content if b.type == "text")

        tool_results = []
        for block in response.content:
            if block.type != "tool_use":
                continue
            print(f"    Claude sends: {block.name}({json.dumps(block.input)})")
            try:
                result, is_error = functions[block.name](**block.input), False
            except Exception as e:
                result, is_error = f"Error: {e}", True
            print(f"    Tool returns: {result.replace(chr(10), ' | ')}")
            tool_results.append({
                "type": "tool_result",
                "tool_use_id": block.id,
                "content": result,
                "is_error": is_error,
            })
        messages.append({"role": "user", "content": tool_results})
    return f"(stopped after {MAX_TOOL_TURNS} tool calls)"


# ---------------------------------------------------------------------------
# STEP E: Same questions, both designs.
# ---------------------------------------------------------------------------
QUESTIONS = [
    "Will it rain in Chennai this weekend?",               # needs several days
    "What's the weather in Bengaluru for the next 3 days?", # other spelling + days
    "I'm visiting Delhi tomorrow from New York. How warm will it be?",  # tomorrow + °F
]

for question in QUESTIONS:
    print(f"\n{'=' * 70}\nQ: {question}")
    for label, tools, functions in (
        ("BAD tool", BAD_TOOLS, BAD_FUNCTIONS),
        ("GOOD tool", GOOD_TOOLS, GOOD_FUNCTIONS),
    ):
        print(f"\n  --- {label} ---")
        answer = ask(question, tools, functions)
        print(f"  Claude: {answer}")
