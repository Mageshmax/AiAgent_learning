"""
Lesson 8: Context management (why `messages` can't grow forever).

KEY IDEA: Claude has no memory (lesson 2), so we resend the WHOLE `messages`
list on every call. That has three costs that grow with every turn:

    1. MONEY    - you pay input tokens for the whole history, every call.
                  Turn 20 pays for turns 1-19 again.
    2. SPEED    - more input = slower replies.
    3. A LIMIT  - the context window. claude-opus-5-5 takes up to 1M input
                  tokens; past that the API returns a 400 error.

So long chats need a plan. Three options, simplest first:

    TRIM       keep only the last N turns. Cheap and simple, but Claude
               FORGETS everything older (demo 2).
    SUMMARISE  replace old turns with a short summary written by Claude.
               Keeps the important facts, costs one extra call now and then
               (demo 3).
    SERVER-SIDE COMPACTION (beta)  the API summarises for you when the
               conversation gets big (demo 4).

IMPORTANT rule on claude-opus-5-5 ("preserved thinking"): if you store
Claude's FULL replies (response.content, with thinking blocks) and then cut
or edit OLD turns, the thinking blocks in the turns you kept no longer match
and the API can reject the request (400). So in this lesson we store only
the reply TEXT (a string), which is always safe to trim or summarise.
If you need full replies (tool loops), use server-side compaction instead.

Tools used:
    client.messages.count_tokens(...)  -> exact input size of a request (free)
    client.models.retrieve(MODEL)      -> .max_input_tokens = context window

Run:
    python 08_context_management.py      (menu)
    python 08_context_management.py 1    (one demo)
"""

import os
import sys

import anthropic
from dotenv import find_dotenv, load_dotenv

MODEL = "claude-opus-5-5"
PRICE_IN, PRICE_OUT = 4.00, 20.00  # US$ per 1M tokens for claude-opus-5-5

load_dotenv(find_dotenv())
api_key = os.getenv("ANTHROPIC_API_KEY")
if not api_key:
    raise SystemExit("ANTHROPIC_API_KEY not found. Add it to your .env file.")

client = anthropic.Anthropic(api_key=api_key)

SYSTEM = "You are a friendly assistant. Keep answers to 1-2 sentences."


def heading(title: str) -> None:
    print(f"\n{'=' * 70}\n{title}\n{'=' * 70}")


def answer_text(response) -> str:
    return "".join(b.text for b in response.content if b.type == "text").strip()


def ask(messages: list, system: str = SYSTEM) -> str:
    """One call. Stores only the reply TEXT, so the history is safe to trim."""
    response = client.messages.create(
        model=MODEL,
        max_tokens=2000,
        system=system,
        output_config={"effort": "low"},  # simple chat: low effort is enough
        messages=messages,
    )
    reply = answer_text(response)
    messages.append({"role": "assistant", "content": reply})
    print(f"   (input tokens this call: {response.usage.input_tokens})")
    return reply


def count_tokens(messages: list, system: str = SYSTEM) -> int:
    """Exact input size of a request, without running it. Free to call."""
    return client.messages.count_tokens(model=MODEL, system=system, messages=messages).input_tokens


# A made-up chat we can "replay" without paying for answers.
FAKE_TURNS = [
    ("Hi! My name is Santhosh and I live in Chennai.", "Nice to meet you, Santhosh! How's Chennai today?"),
    ("Hot as usual. I'm learning to build AI agents.", "That's a great skill to learn. What are you building?"),
    ("A shop assistant that answers questions about orders.", "Nice. Will it look up orders in a database?"),
    ("Yes, SQLite for now. Maybe Postgres later.", "SQLite is perfect to start with; switching later is easy."),
    ("My favourite food is masala dosa, by the way.", "Great choice! Crispy dosa with sambar is hard to beat."),
    ("How do I make my agent remember things between chats?", "Save important facts to a file or database, then load them at the start."),
] * 4  # 24 turns


# ---------------------------------------------------------------------------
# DEMO 1: See the growth. Count tokens as a chat gets longer (no answers
# generated; count_tokens is free). Every call pays for the whole history.
# ---------------------------------------------------------------------------
def demo_growth():
    heading("DEMO 1: how the input grows (and what it costs)")
    info = client.models.retrieve(MODEL)
    print(f"{MODEL}: context window = {info.max_input_tokens:,} input tokens, max output = {info.max_tokens:,}\n")

    messages = []
    total_paid = 0
    first = size = 0
    print(f"{'turn':>4}  {'input tokens this call':>22}  {'total input paid so far':>24}")
    for turn, (question, answer) in enumerate(FAKE_TURNS, start=1):
        messages.append({"role": "user", "content": question})
        size = count_tokens(messages)
        total_paid += size
        first = first or size
        if turn in (1, 2, 5, 10, 15, 20, 24):
            print(f"{turn:>4}  {size:>22,}  {total_paid:>24,}")
        messages.append({"role": "assistant", "content": answer})

    print(f"\nTotal input over {len(FAKE_TURNS)} calls: {total_paid:,} tokens = ${total_paid * PRICE_IN / 1e6:.4f}")
    print(f"The last call alone is ~{size / first:.0f}x the first. The TOTAL grows with the square of the turns.")
    print("A real chat with tool results and documents grows much faster than this one.")


# ---------------------------------------------------------------------------
# DEMO 2: Trimming. Keep only the last N turns.
#
# A "turn" starts at a user message whose content is a plain string (a real
# question). Cutting there is always safe: we never separate a tool_use from
# its tool_result, and the list still starts with a user message.
# ---------------------------------------------------------------------------
def trim_to_last_turns(messages: list, max_turns: int) -> list:
    """Return the messages from the last `max_turns` real questions onwards."""
    starts = [i for i, m in enumerate(messages) if m["role"] == "user" and isinstance(m["content"], str)]
    if len(starts) <= max_turns:
        return messages
    return messages[starts[-max_turns]:]


def replay(turns) -> list:
    messages = []
    for question, answer in turns:
        messages.append({"role": "user", "content": question})
        messages.append({"role": "assistant", "content": answer})
    return messages


def demo_trim():
    heading("DEMO 2: trimming to the last 3 turns (Claude forgets old facts)")
    messages = replay(FAKE_TURNS[:6])
    messages.append({"role": "user", "content": "What's my name and my favourite food?"})

    trimmed = trim_to_last_turns(messages, max_turns=3)
    print(f"Full history: {len(messages)} messages, {count_tokens(messages)} tokens")
    print(f"Trimmed:      {len(trimmed)} messages, {count_tokens(trimmed)} tokens")
    print(f"Trimmed history starts with: {trimmed[0]['content']!r}\n")

    print("Asking with the TRIMMED history:")
    print("Claude:", ask(trimmed))
    print("\nThe name was in turn 1, which was cut, so Claude can't know it.")
    print("The food (turn 5) survived. Trimming is cheap but forgetful.")


# ---------------------------------------------------------------------------
# DEMO 3: Summarising. When the chat gets long, Claude turns the OLD turns
# into a short summary. The summary goes in the system prompt; only the
# recent turns stay as messages.
# ---------------------------------------------------------------------------
SUMMARY_PROMPT = (
    "Summarise this conversation for your future self in at most 6 bullet points. "
    "Keep facts about the user (name, city, preferences, projects), decisions made, "
    "and open questions. Drop small talk. Call the user 'the user' (no he/she)."
)


def summarise(old_messages: list, old_summary: str = "") -> str:
    """Ask Claude to fold `old_messages` (and any earlier summary) into one summary."""
    transcript = "\n".join(f"{m['role'].upper()}: {m['content']}" for m in old_messages)
    if old_summary:
        transcript = f"EARLIER SUMMARY:\n{old_summary}\n\nNEWER MESSAGES:\n{transcript}"
    response = client.messages.create(
        model=MODEL,
        max_tokens=2000,
        output_config={"effort": "low"},
        messages=[{"role": "user", "content": f"{SUMMARY_PROMPT}\n\n<conversation>\n{transcript}\n</conversation>"}],
    )
    return answer_text(response)


def system_with_summary(summary: str) -> str:
    if not summary:
        return SYSTEM
    return f"{SYSTEM}\n\nSummary of the earlier conversation:\n{summary}"


def demo_summarise():
    heading("DEMO 3: summarise the old turns, keep the last 2")
    messages = replay(FAKE_TURNS[:6])
    keep = trim_to_last_turns(messages, max_turns=2)
    old = messages[: len(messages) - len(keep)]

    summary = summarise(old)
    print(f"Summary of the {len(old)} old messages:\n{summary}\n")

    keep.append({"role": "user", "content": "What's my name and my favourite food?"})
    system = system_with_summary(summary)
    print(f"Input now: {count_tokens(keep, system)} tokens (summary + 2 turns)")
    print("Claude:", ask(keep, system))
    print("\nThe name survived because it is in the summary.")


# ---------------------------------------------------------------------------
# DEMO 4: Server-side compaction (beta). The API summarises for you once the
# input passes a trigger (default ~150K tokens), and returns a "compaction"
# block. You MUST append response.content (not just the text) so the block
# goes back next time. A short demo chat never reaches the trigger, so this
# just shows the code works; watch for the block in a very long chat.
# ---------------------------------------------------------------------------
def demo_compaction():
    heading("DEMO 4: server-side compaction (beta)")
    messages = [{"role": "user", "content": "Hi, I'm Santhosh. Give me one tip for naming Python variables."}]
    response = client.beta.messages.create(
        betas=["compact-2026-01-12"],
        model=MODEL,
        max_tokens=2000,
        output_config={"effort": "low"},
        context_management={"edits": [{"type": "compact_20260112"}]},
        messages=messages,
    )
    messages.append({"role": "assistant", "content": response.content})  # FULL content, not just text
    print("Block types:", [b.type for b in response.content])
    print("Claude:", answer_text(response))
    print("\nNo 'compaction' block yet: the conversation is tiny. When the input passes the")
    print("trigger, the API replaces the old turns with a summary block and you keep going.")


# ---------------------------------------------------------------------------
# DEMO 5: A chat that manages its own context: once it has more than
# MAX_TURNS turns, the older ones are folded into the summary.
# ---------------------------------------------------------------------------
MAX_TURNS = 4
KEEP_TURNS = 2


def chat():
    heading(f"DEMO 5: chat with auto-summary (summarises when over {MAX_TURNS} turns)")
    print("Tell it facts about yourself, chat for 5+ turns, then ask what it remembers.")
    print("Type 'exit' to go back.\n")
    messages, summary = [], ""
    while True:
        question = input("You: ").strip()
        if not question:
            continue
        if question.lower() == "exit":
            return
        messages.append({"role": "user", "content": question})

        turns = sum(1 for m in messages if m["role"] == "user" and isinstance(m["content"], str))
        if turns > MAX_TURNS:
            keep = trim_to_last_turns(messages, KEEP_TURNS)
            old = messages[: len(messages) - len(keep)]
            summary = summarise(old, summary)
            messages = keep
            print(f"   📝 Summarised {len(old)} old messages. Summary is now:\n{summary}\n")

        try:
            print(f"Claude: {ask(messages, system_with_summary(summary))}\n")
        except anthropic.APIError as e:
            messages.pop()  # remove the question so the history stays valid
            print(f"❌ {e}\n")


# ---------------------------------------------------------------------------
# Menu.
# ---------------------------------------------------------------------------
DEMOS = {"1": demo_growth, "2": demo_trim, "3": demo_summarise, "4": demo_compaction, "5": chat}

MENU = """
Pick a demo:
  1  How the input grows      (count_tokens only: free)
  2  Trimming                 (1 small call)
  3  Summarising              (2 small calls)
  4  Server-side compaction   (1 small call)
  5  Chat with auto-summary
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
