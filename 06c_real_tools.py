"""
Lesson 6c: Real tools.

Until now our tools used FAKE data. Now they do REAL things:

    get_weather_forecast  -> calls a real weather web API (Open-Meteo: free, no key)
    list_notes            -> lists files in a folder on your computer
    read_note             -> reads a file
    write_note            -> WRITES a file
    query_database        -> runs SQL on a real SQLite database

KEY IDEA: Real tools can FAIL in new ways and can DO DAMAGE, so every tool:
    1. Handles failures: no internet, slow server, city not found, missing file
       -> raise an error with a helpful message -> sent back with is_error (lesson 5)
    2. Is LIMITED to what it needs:
       - web calls have a timeout, so a slow server can't freeze the agent
       - file tools only work inside ONE folder (lesson_data/notes/)
       - the database is opened READ-ONLY and only SELECT is allowed
       Claude decides WHAT to call, but YOUR code decides what is ALLOWED.

Setup (one time):
    pip install requests

Try these:
    You: What's the weather in Chennai for the next 3 days?
    You: Save that forecast to a note called chennai.txt
    You: What notes do I have? Read chennai.txt
    You: Which product category earned the most money?
    You: Which city ordered the most items? Save a short report to sales.md
    You: Save "print('hi')" as a note called hi.py (blocked: only .txt / .md)
    You: Delete all orders from the database      (blocked: read-only)
    You: Read the file ../.env                    (Anthropic's safety filter usually refuses this:
                                                   stop_reason "refusal". If a call ever got through,
                                                   safe_note_path() would still block it. Never rely
                                                   on the model alone for safety.)

Files this lesson creates (safe to delete, they are rebuilt):
    lesson_data/shop.db       sample shop database
    lesson_data/notes/        where write_note saves files

Run:
    python 06c_real_tools.py
"""

import json
import os
import sqlite3
from pathlib import Path

import anthropic
import requests
from dotenv import find_dotenv, load_dotenv

MODEL = "claude-opus-5-5"
MAX_TOOL_TURNS = 10

load_dotenv(find_dotenv())
api_key = os.getenv("ANTHROPIC_API_KEY")
if not api_key:
    raise SystemExit("ANTHROPIC_API_KEY not found. Add it to your .env file.")

client = anthropic.Anthropic(api_key=api_key)

DATA_DIR = Path(__file__).resolve().parent / "lesson_data"
NOTES_DIR = DATA_DIR / "notes"
DB_PATH = DATA_DIR / "shop.db"
NOTES_DIR.mkdir(parents=True, exist_ok=True)


# ---------------------------------------------------------------------------
# TOOL 1: Real weather from a web API.
# ---------------------------------------------------------------------------
# Open-Meteo returns the weather as a number code (WMO code). Translate the
# common ones into words.
WEATHER_CODES = {
    0: "clear sky", 1: "mainly clear", 2: "partly cloudy", 3: "overcast",
    45: "fog", 48: "fog", 51: "light drizzle", 53: "drizzle", 55: "heavy drizzle",
    61: "light rain", 63: "rain", 65: "heavy rain", 80: "rain showers",
    81: "heavy showers", 82: "violent showers", 95: "thunderstorm",
    96: "thunderstorm with hail", 99: "thunderstorm with hail",
}


def get_json(url: str, params: dict) -> dict:
    """GET a URL and return its JSON. Turns network problems into clear errors."""
    try:
        response = requests.get(url, params=params, timeout=10)  # never wait forever
        response.raise_for_status()  # turns HTTP errors (404, 500...) into exceptions
    except requests.Timeout:
        raise RuntimeError("The weather service took too long to answer. Try again later.")
    except requests.ConnectionError:
        raise RuntimeError("Can't reach the weather service. Is the internet working?")
    except requests.HTTPError as e:
        raise RuntimeError(f"The weather service returned an error: {e}")
    return response.json()


def get_weather_forecast(city: str, days: int) -> str:
    if not 1 <= days <= 7:
        raise ValueError(f"days must be between 1 and 7, got {days}.")

    # Step 1: city name -> latitude/longitude (the "geocoding" API).
    found = get_json(
        "https://geocoding-api.open-meteo.com/v1/search",
        {"name": city, "count": 1},
    ).get("results")
    if not found:
        raise ValueError(f"Couldn't find a city called '{city}'. Try the English spelling.")
    place = found[0]

    # Step 2: latitude/longitude -> forecast.
    data = get_json(
        "https://api.open-meteo.com/v1/forecast",
        {
            "latitude": place["latitude"],
            "longitude": place["longitude"],
            "daily": "weather_code,temperature_2m_max,temperature_2m_min,precipitation_probability_max",
            "forecast_days": days,
            "timezone": "auto",
        },
    )

    # Step 3: turn the JSON into short, readable lines for Claude.
    daily = data["daily"]
    lines = [f"Forecast for {place['name']}, {place.get('country', '')}:"]
    for i, date in enumerate(daily["time"]):
        conditions = WEATHER_CODES.get(daily["weather_code"][i], "unknown")
        lines.append(
            f"{date}: {conditions}, {daily['temperature_2m_min'][i]}–{daily['temperature_2m_max'][i]}°C, "
            f"rain chance {daily['precipitation_probability_max'][i]}%"
        )
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# TOOLS 2-4: Files, locked inside ONE folder.
# ---------------------------------------------------------------------------
ALLOWED_EXTENSIONS = {".txt", ".md"}
MAX_NOTE_SIZE = 20_000  # characters


def safe_note_path(filename: str) -> Path:
    """Turn a filename into a path INSIDE the notes folder, or refuse.

    Blocks tricks like '../.env' or '/etc/passwd' that would reach files
    outside the folder (called "path traversal").
    """
    path = (NOTES_DIR / filename).resolve()
    if path.parent != NOTES_DIR.resolve():
        raise PermissionError(f"'{filename}' is outside the notes folder. Use a plain name like 'todo.txt'.")
    if path.suffix not in ALLOWED_EXTENSIONS:
        raise PermissionError(f"Only {', '.join(sorted(ALLOWED_EXTENSIONS))} files are allowed.")
    return path


def list_notes() -> str:
    names = sorted(p.name for p in NOTES_DIR.iterdir() if p.is_file())
    return "\n".join(names) if names else "(no notes yet)"


def read_note(filename: str) -> str:
    path = safe_note_path(filename)
    if not path.exists():
        raise FileNotFoundError(f"No note called '{filename}'. Existing notes: {list_notes()}")
    return path.read_text(encoding="utf-8")


def write_note(filename: str, content: str) -> str:
    path = safe_note_path(filename)
    if len(content) > MAX_NOTE_SIZE:
        raise ValueError(f"Note is too long ({len(content)} characters, max {MAX_NOTE_SIZE}).")
    existed = path.exists()
    path.write_text(content, encoding="utf-8")
    return f"{'Replaced' if existed else 'Created'} {filename} ({len(content)} characters)."


# ---------------------------------------------------------------------------
# TOOL 5: A real database, READ-ONLY.
# ---------------------------------------------------------------------------
def create_sample_database() -> None:
    """Build a small shop database the first time the lesson runs."""
    if DB_PATH.exists():
        return
    db = sqlite3.connect(DB_PATH)
    db.executescript("""
        CREATE TABLE products (
            id INTEGER PRIMARY KEY, name TEXT, category TEXT, price_inr INTEGER, stock INTEGER
        );
        CREATE TABLE orders (
            id INTEGER PRIMARY KEY, product_id INTEGER REFERENCES products(id),
            quantity INTEGER, order_date TEXT, city TEXT
        );
        INSERT INTO products VALUES
            (1, 'Filter coffee powder 500g', 'Grocery', 320, 40),
            (2, 'Basmati rice 5kg', 'Grocery', 650, 25),
            (3, 'Cotton kurta', 'Clothing', 899, 15),
            (4, 'Silk saree', 'Clothing', 4500, 5),
            (5, 'Bluetooth earphones', 'Electronics', 1499, 30),
            (6, 'Phone charger 20W', 'Electronics', 799, 50),
            (7, 'Steel water bottle', 'Home', 450, 60),
            (8, 'Pressure cooker 3L', 'Home', 1850, 12);
        INSERT INTO orders VALUES
            (1, 1, 3, '2026-09-01', 'Chennai'),
            (2, 5, 1, '2026-09-02', 'Bangalore'),
            (3, 4, 1, '2026-09-03', 'Chennai'),
            (4, 2, 2, '2026-09-05', 'Delhi'),
            (5, 6, 4, '2026-09-08', 'Mumbai'),
            (6, 3, 2, '2026-09-10', 'Chennai'),
            (7, 8, 1, '2026-09-12', 'Delhi'),
            (8, 7, 5, '2026-09-15', 'Bangalore'),
            (9, 5, 2, '2026-09-18', 'Mumbai'),
            (10, 1, 6, '2026-09-20', 'Chennai'),
            (11, 4, 2, '2026-09-22', 'Mumbai'),
            (12, 6, 3, '2026-09-25', 'Bangalore');
    """)
    db.commit()
    db.close()


MAX_ROWS = 50


def query_database(sql: str) -> str:
    # Check 1 (friendly message): only SELECT queries.
    if not sql.strip().lower().startswith(("select", "with")):
        raise PermissionError("Only SELECT queries are allowed. This database is read-only.")
    # Check 2 (the REAL protection): open the file in read-only mode, so even a
    # sneaky query can't change anything.
    db = sqlite3.connect(f"file:{DB_PATH}?mode=ro", uri=True)
    try:
        cursor = db.execute(sql)  # execute() runs ONE statement only
        columns = [c[0] for c in cursor.description]
        rows = cursor.fetchmany(MAX_ROWS + 1)
    except sqlite3.Error as e:
        raise ValueError(f"SQL error: {e}")  # Claude can read this and fix its query
    finally:
        db.close()

    lines = [" | ".join(columns)]
    lines += [" | ".join(str(v) for v in row) for row in rows[:MAX_ROWS]]
    if len(rows) > MAX_ROWS:
        lines.append(f"(only the first {MAX_ROWS} rows shown)")
    return "\n".join(lines)


create_sample_database()


# ---------------------------------------------------------------------------
# Tool descriptions (lesson 6b: clear names, WHEN to use, strict schemas).
# ---------------------------------------------------------------------------
TOOLS = [
    {
        "name": "get_weather_forecast",
        "description": (
            "Get the real weather forecast for any city in the world, for today and up to 6 more days. "
            "Use this for any question about weather, temperature or rain. "
            "Returns one line per day: date, conditions, min–max °C, and rain chance."
        ),
        "strict": True,
        "input_schema": {
            "type": "object",
            "properties": {
                "city": {"type": "string", "description": "City name in English, e.g. Chennai, Paris"},
                "days": {"type": "integer", "description": "Number of days, 1 (today only) to 7"},
            },
            "required": ["city", "days"],
            "additionalProperties": False,
        },
    },
    {
        "name": "list_notes",
        "description": "List the user's saved notes (file names). Use this before reading a note if you don't know its exact name.",
        "strict": True,
        "input_schema": {"type": "object", "properties": {}, "required": [], "additionalProperties": False},
    },
    {
        "name": "read_note",
        "description": "Read one of the user's saved notes and return its text.",
        "strict": True,
        "input_schema": {
            "type": "object",
            "properties": {
                "filename": {"type": "string", "description": "Plain file name, e.g. todo.txt"},
            },
            "required": ["filename"],
            "additionalProperties": False,
        },
    },
    {
        "name": "write_note",
        "description": (
            "Save text to a note. Creates the note, or REPLACES it completely if it already exists. "
            "Use this only when the user asks you to save or write something."
        ),
        "strict": True,
        "input_schema": {
            "type": "object",
            "properties": {
                "filename": {"type": "string", "description": "Plain file name ending in .txt or .md, e.g. todo.txt"},
                "content": {"type": "string", "description": "The full text of the note"},
            },
            "required": ["filename", "content"],
            "additionalProperties": False,
        },
    },
    {
        "name": "query_database",
        "description": (
            "Run ONE read-only SQLite SELECT query on the shop database and return the rows. "
            "Use this for any question about products, stock, orders or sales. Tables:\n"
            "  products(id, name, category, price_inr, stock)\n"
            "  orders(id, product_id -> products.id, quantity, order_date 'YYYY-MM-DD', city)\n"
            "Revenue of an order = orders.quantity * products.price_inr."
        ),
        "strict": True,
        "input_schema": {
            "type": "object",
            "properties": {
                "sql": {"type": "string", "description": "One SELECT statement"},
            },
            "required": ["sql"],
            "additionalProperties": False,
        },
    },
]

TOOL_FUNCTIONS = {
    "get_weather_forecast": get_weather_forecast,
    "list_notes": list_notes,
    "read_note": read_note,
    "write_note": write_note,
    "query_database": query_database,
}

SYSTEM_PROMPT = """\
You are a helpful assistant with real tools: a weather forecast, the user's notes, and a shop database.
- Always use the tools for weather, notes and shop data. Never guess these.
- Before replacing an existing note, tell the user it will be overwritten.
- If a tool returns an error, fix your input and try again once; otherwise explain the problem simply.
- Keep answers short. Show money as ₹ with commas, e.g. ₹12,500."""


# ---------------------------------------------------------------------------
# Run tools (same as lesson 5: errors go back to Claude with is_error).
# ---------------------------------------------------------------------------
def run_tools(response) -> list:
    tool_results = []
    for block in response.content:
        if block.type != "tool_use":
            continue
        print(f"    🔧 {block.name}({json.dumps(block.input, ensure_ascii=False)[:200]})")
        function = TOOL_FUNCTIONS.get(block.name)
        try:
            if function is None:
                raise ValueError(f"Unknown tool '{block.name}'.")
            result, is_error = function(**block.input), False
            preview = result.replace("\n", " | ")
            print(f"       ✅ {preview[:150]}{'...' if len(preview) > 150 else ''}")
        except Exception as e:
            result, is_error = f"Error: {e}", True
            print(f"       ❌ {result}")
        tool_results.append({
            "type": "tool_result",
            "tool_use_id": block.id,
            "content": result,
            "is_error": is_error,
        })
    return tool_results


# ---------------------------------------------------------------------------
# The chat agent (same two loops as lessons 4-5).
# ---------------------------------------------------------------------------
messages = []
print("Assistant with REAL tools: weather, notes, shop database. Type 'exit' to quit.\n")

while True:
    question = input("You: ").strip()
    if not question:
        continue
    if question.lower() == "exit":
        break

    start = len(messages)
    messages.append({"role": "user", "content": question})

    for turn in range(1, MAX_TOOL_TURNS + 1):
        response = client.messages.create(
            model=MODEL,
            max_tokens=16000,
            system=SYSTEM_PROMPT,
            tools=TOOLS,
            messages=messages,
        )
        messages.append({"role": "assistant", "content": response.content})
        if response.stop_reason != "tool_use":
            break
        messages.append({"role": "user", "content": run_tools(response)})
    else:
        print(f"    Stopped after {MAX_TOOL_TURNS} calls without a final answer.")
        del messages[start:]
        continue

    # Anthropic's safety filter can block a request (e.g. one that looks like
    # stealing secrets). The reply is then EMPTY, so say so, and forget the
    # question so it doesn't confuse the next turn.
    if response.stop_reason == "refusal":
        print("\nClaude: (request blocked by the safety filter: stop_reason 'refusal')\n")
        del messages[start:]
        continue

    answer = "".join(b.text for b in response.content if b.type == "text")
    print(f"\nClaude: {answer}\n[API calls: {turn}]\n")
