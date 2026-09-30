"""
Lesson 9: Long-term memory (remember FACTS across sessions).

KEY IDEA: In chat_ui step 5 we saved the WHOLE chat. That doesn't scale: it
gets long (lesson 8) and most of it is small talk. Instead, save only the
FACTS worth keeping ("name is Santhosh", "prefers Python", "shop uses
SQLite") in a small file, and load them into the system prompt at the start
of every new session.

Two ways to collect facts:

    A. Memory TOOLS (demo 1): give the agent `remember` and `forget` tools.
       Claude decides, during the chat, what is worth saving.
    B. EXTRACTION after the chat (demo 2): when a session ends, one extra call
       reads the transcript and returns new facts as JSON (lesson 7).

The facts live in lesson_data/memory/facts.json:
    [{"id": 1, "fact": "User's name is Santhosh", "category": "personal", "saved": "2026-09-30"}]

Rules that keep memory healthy:
    - Freeze the system prompt for the whole session. Load the facts ONCE when
      the session starts. Facts saved mid-chat are already in the conversation
      (as tool calls), so Claude knows them. Rebuilding `system` every call
      breaks prompt caching (lesson 8b) and, on claude-opus-5-5, the thinking
      blocks of earlier turns.
    - Keep facts short, one idea each, and give each an id so it can be
      removed ("forget that") or replaced when it goes out of date.
    - Never store secrets (passwords, card numbers). The remember tool blocks them.
    - Once you have hundreds of facts, don't put them all in the prompt:
      SEARCH them instead (lesson 10, RAG).

Anthropic also has a built-in memory tool ({"type": "memory_20250818", "name":
"memory"}) where Claude reads and writes memory FILES in a folder you
control. Same idea, bigger scale; worth a look after this lesson.

Try (demo 1):
    You: Hi, I'm Santhosh. I live in Chennai and I'm learning to build AI agents.
    You: I prefer short answers with code examples.
    You: new                      <- starts a NEW session (Claude forgets the chat)
    You: What do you know about me?
    You: Actually I moved to Bengaluru.   (watch it forget the old fact and save the new one)
    You: facts                    <- print the saved facts file

Run:
    python 09_long_term_memory.py        (menu)
    python 09_long_term_memory.py 2      (one demo)
"""

import json
import os
import re
import sys
from datetime import date
from pathlib import Path

import anthropic
from dotenv import find_dotenv, load_dotenv

MODEL = "claude-opus-5-5"
MAX_TOOL_TURNS = 10

load_dotenv(find_dotenv())
api_key = os.getenv("ANTHROPIC_API_KEY")
if not api_key:
    raise SystemExit("ANTHROPIC_API_KEY not found. Add it to your .env file.")

client = anthropic.Anthropic(api_key=api_key)

MEMORY_FILE = Path(__file__).resolve().parent / "lesson_data" / "memory" / "facts.json"
CATEGORIES = ["personal", "preference", "project", "other"]


def heading(title: str) -> None:
    print(f"\n{'=' * 70}\n{title}\n{'=' * 70}")


# ---------------------------------------------------------------------------
# STEP A: The fact store (a JSON file).
# ---------------------------------------------------------------------------
def load_facts() -> list[dict]:
    if not MEMORY_FILE.exists():
        return []
    return json.loads(MEMORY_FILE.read_text())


def save_facts(facts: list[dict]) -> None:
    MEMORY_FILE.parent.mkdir(parents=True, exist_ok=True)
    MEMORY_FILE.write_text(json.dumps(facts, indent=2, ensure_ascii=False))


# Things that look like secrets: never write them to disk.
SECRET_PATTERN = re.compile(r"password|passcode|\bpin\b|otp|cvv|\b\d{12,19}\b|api[_ ]?key|sk-ant-", re.I)


def remember(fact: str, category: str) -> str:
    fact = fact.strip()
    if SECRET_PATTERN.search(fact):
        raise ValueError("That looks like a secret (password, card number, key). Secrets are never saved.")
    if len(fact) > 200:
        raise ValueError("Fact too long: keep it to one short sentence.")
    facts = load_facts()
    if any(f["fact"].lower() == fact.lower() for f in facts):
        return "Already remembered."
    new_id = max((f["id"] for f in facts), default=0) + 1
    facts.append({"id": new_id, "fact": fact, "category": category, "saved": date.today().isoformat()})
    save_facts(facts)
    return f"Saved as fact #{new_id}."


def forget(fact_id: int) -> str:
    facts = load_facts()
    kept = [f for f in facts if f["id"] != fact_id]
    if len(kept) == len(facts):
        raise ValueError(f"No fact with id {fact_id}.")
    save_facts(kept)
    return f"Forgot fact #{fact_id}."


def facts_as_text(facts: list[dict]) -> str:
    if not facts:
        return "(nothing yet)"
    return "\n".join(f"#{f['id']} [{f['category']}] {f['fact']}" for f in facts)


# ---------------------------------------------------------------------------
# STEP B: Memory tools + the system prompt that carries the facts.
# ---------------------------------------------------------------------------
TOOLS = [
    {
        "name": "remember",
        "description": (
            "Save ONE lasting fact about the user for future sessions: who they are, preferences, "
            "ongoing projects, decisions. Not for small talk or one-off questions. "
            "Write it in the third person, e.g. 'User prefers Python'. Never save secrets."
        ),
        "strict": True,
        "input_schema": {
            "type": "object",
            "properties": {
                "fact": {"type": "string", "description": "One short sentence."},
                "category": {"type": "string", "enum": CATEGORIES},
            },
            "required": ["fact", "category"],
            "additionalProperties": False,
        },
    },
    {
        "name": "forget",
        "description": (
            "Delete a saved fact by its id, when the user asks you to forget it or when it is "
            "out of date. To UPDATE a fact: forget the old one, then remember the new one."
        ),
        "strict": True,
        "input_schema": {
            "type": "object",
            "properties": {"fact_id": {"type": "integer"}},
            "required": ["fact_id"],
            "additionalProperties": False,
        },
    },
]
RUN_TOOL = {"remember": remember, "forget": forget}


def build_system_prompt() -> str:
    """Called ONCE per session. The facts are frozen into it."""
    return f"""You are a friendly personal assistant with long-term memory.

What you remember about the user from earlier sessions (id, category, fact):
{facts_as_text(load_facts())}

Memory rules:
- Use these facts naturally; don't list them unless asked.
- When the user tells you something lasting about themselves, call `remember`.
- When a saved fact becomes wrong, `forget` it (by id) and `remember` the new version.
- Don't mention the memory tools unless the user asks about memory."""


def run_tools(response) -> list:
    results = []
    for block in response.content:
        if block.type != "tool_use":
            continue
        try:
            output, is_error = RUN_TOOL[block.name](**block.input), False
        except Exception as e:
            output, is_error = f"Error: {e}", True
        print(f"   🧠 {block.name}({block.input}) -> {output}")
        results.append({"type": "tool_result", "tool_use_id": block.id, "content": output, "is_error": is_error})
    return results


def chat_turn(system: str, messages: list, question: str) -> str:
    messages.append({"role": "user", "content": question})
    for _ in range(MAX_TOOL_TURNS):
        response = client.messages.create(
            model=MODEL, max_tokens=4000, output_config={"effort": "low"},
            system=system, tools=TOOLS, messages=messages,
        )
        messages.append({"role": "assistant", "content": response.content})
        if response.stop_reason != "tool_use":
            return "".join(b.text for b in response.content if b.type == "text")
        messages.append({"role": "user", "content": run_tools(response)})
    return "(stopped: too many tool turns)"


# ---------------------------------------------------------------------------
# DEMO 1: Chat with memory tools. 'new' starts a fresh session.
# ---------------------------------------------------------------------------
def demo_memory_chat():
    heading("DEMO 1: chat with memory tools")
    print("Commands: 'new' = new session, 'facts' = show saved facts, 'wipe' = delete all facts, 'exit'.\n")
    system, messages = build_system_prompt(), []
    print(f"Loaded {len(load_facts())} facts from {MEMORY_FILE.name}\n")
    while True:
        question = input("You: ").strip()
        if not question:
            continue
        command = question.lower()
        if command == "exit":
            return
        if command == "facts":
            print(facts_as_text(load_facts()), "\n")
            continue
        if command == "wipe":
            save_facts([])
            print("All facts deleted. Type 'new' to start clean.\n")
            continue
        if command == "new":
            system, messages = build_system_prompt(), []  # the chat is gone; the facts are not
            print(f"--- new session: chat history cleared, {len(load_facts())} facts loaded ---\n")
            continue
        print(f"Claude: {chat_turn(system, messages, question)}\n")


# ---------------------------------------------------------------------------
# DEMO 2: Extract facts AFTER a chat, with structured output (lesson 7).
# Good when you don't want tool calls slowing the chat down.
# ---------------------------------------------------------------------------
TRANSCRIPT = """USER: hey, quick one. I'm Priya, I run a small bakery in Coimbatore.
ASSISTANT: Hi Priya! How can I help?
USER: I want a script that emails me when flour stock drops below 20 kg. I use Google Sheets for stock.
ASSISTANT: We can do that with Apps Script. Do you prefer Python instead?
USER: Python please, I know a bit of it. Also I hate long explanations, keep it short.
ASSISTANT: Got it. Here's a short script...
USER: thanks! btw it's raining a lot here today."""

EXTRACT_SCHEMA = {
    "type": "object",
    "properties": {
        "facts": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "fact": {"type": "string"},
                    "category": {"type": "string", "enum": CATEGORIES},
                },
                "required": ["fact", "category"],
                "additionalProperties": False,
            },
        }
    },
    "required": ["facts"],
    "additionalProperties": False,
}


def demo_extract():
    heading("DEMO 2: extract facts from a finished chat")
    print(TRANSCRIPT, "\n")
    response = client.messages.create(
        model=MODEL,
        max_tokens=2000,
        output_config={"effort": "low", "format": {"type": "json_schema", "schema": EXTRACT_SCHEMA}},
        messages=[{"role": "user", "content": (
            "Extract LASTING facts about the user from this chat, for a memory file. "
            "One short third-person sentence each. Skip small talk and anything only true today "
            f"(like the weather).\n\n<chat>\n{TRANSCRIPT}\n</chat>"
        )}],
    )
    text = "".join(b.text for b in response.content if b.type == "text")
    facts = json.loads(text)["facts"]
    print("Extracted facts:")
    for f in facts:
        print(f"  [{f['category']}] {f['fact']}")
    print("\n(Not saved: this is Priya's chat, not yours. In an app you'd call remember() for each.)")
    print("Notice the weather was skipped: it isn't a lasting fact.")


# ---------------------------------------------------------------------------
# Menu.
# ---------------------------------------------------------------------------
DEMOS = {"1": demo_memory_chat, "2": demo_extract}

MENU = """
Pick a demo:
  1  Chat with memory tools (facts saved across sessions)
  2  Extract facts from a finished chat (1 small call)
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
