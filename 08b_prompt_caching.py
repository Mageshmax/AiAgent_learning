"""
Lesson 8b: Prompt caching (pay less for the part of the prompt that never changes).

KEY IDEA: Most of what you send is THE SAME every call: the tools, a long
system prompt, a document, the old chat turns. With prompt caching, Anthropic
keeps that START of the prompt ready for a few minutes. The next call that
begins with EXACTLY the same text reads it from the cache:

    normal input      $4.00  per 1M tokens (claude-opus-5-5)
    cache WRITE       $5.00  per 1M  (1.25x, first time, 5-minute cache)
    cache READ        $0.20  per 1M  (0.05x, every later hit)  -> 95% cheaper
    ... and cached input is also FASTER.

How to switch it on: add a "cache_control" marker. Everything BEFORE and
including the marked block is cached:

    system=[{"type": "text", "text": LONG_TEXT, "cache_control": {"type": "ephemeral"}}]

or the simple "automatic" form, which marks the last block for you (good for chats):

    client.messages.create(..., cache_control={"type": "ephemeral"})

Rules that trip people up:
    - It is a PREFIX match, in this order: tools -> system -> messages.
      Change ONE character early on (a timestamp, a random id, a re-ordered
      tool list) and everything after it misses the cache (demo 2).
    - The cached part must be at least 512 tokens on claude-opus-5-5. Shorter
      prompts silently don't cache (no error, just 0 cache tokens).
    - The cache lives 5 minutes after the last use ({"ttl": "1h"} for longer,
      but 1-hour writes cost 2x).
    - Check it worked: response.usage.cache_read_input_tokens > 0.

usage fields:
    input_tokens                  tokens AFTER the last cache marker (full price)
    cache_creation_input_tokens   tokens written to the cache this call (1.25x)
    cache_read_input_tokens       tokens read from the cache this call (0.05x)

Run:
    python 08b_prompt_caching.py        (menu)
    python 08b_prompt_caching.py 1      (one demo)
"""

import os
import sys
import time
from datetime import datetime

import anthropic
from dotenv import find_dotenv, load_dotenv

MODEL = "claude-opus-5-5"
# US$ per 1M tokens for claude-opus-5-5.
PRICE_IN, PRICE_OUT = 4.00, 20.00
PRICE_CACHE_WRITE, PRICE_CACHE_READ = 5.00, 0.20

load_dotenv(find_dotenv())
api_key = os.getenv("ANTHROPIC_API_KEY")
if not api_key:
    raise SystemExit("ANTHROPIC_API_KEY not found. Add it to your .env file.")

client = anthropic.Anthropic(api_key=api_key)


def heading(title: str) -> None:
    print(f"\n{'=' * 70}\n{title}\n{'=' * 70}")


def cost(usage) -> float:
    return (
        usage.input_tokens * PRICE_IN
        + (usage.cache_creation_input_tokens or 0) * PRICE_CACHE_WRITE
        + (usage.cache_read_input_tokens or 0) * PRICE_CACHE_READ
        + usage.output_tokens * PRICE_OUT
    ) / 1_000_000


def cost_without_cache(usage) -> float:
    """What the same call would cost if nothing were cached."""
    all_input = usage.input_tokens + (usage.cache_creation_input_tokens or 0) + (usage.cache_read_input_tokens or 0)
    return (all_input * PRICE_IN + usage.output_tokens * PRICE_OUT) / 1_000_000


def report(label: str, response, seconds: float) -> None:
    u = response.usage
    print(
        f"  {label:<28} write={u.cache_creation_input_tokens or 0:>5}  read={u.cache_read_input_tokens or 0:>5}  "
        f"uncached={u.input_tokens:>4}  {seconds:4.1f}s  ${cost(u):.4f} (no cache: ${cost_without_cache(u):.4f})"
    )


def answer_text(response) -> str:
    return "".join(b.text for b in response.content if b.type == "text").strip()


# A long, unchanging system prompt: the shop's handbook (~3,000 tokens).
# In real apps this is your instructions, tool docs, a product catalogue, a
# PDF... anything big you send on every call.
PRODUCTS = [
    (f"SKU-{100 + i}", name, price, stock)
    for i, (name, price, stock) in enumerate([
        ("Filter coffee powder 500g", 349, 120), ("Masala tea 250g", 199, 80), ("Ghee 1L", 689, 45),
        ("Basmati rice 5kg", 799, 60), ("Toor dal 1kg", 179, 150), ("Coconut oil 1L", 299, 90),
        ("Idli rice 5kg", 459, 30), ("Sambar powder 200g", 89, 200), ("Rasam powder 200g", 85, 180),
        ("Jaggery 1kg", 119, 70), ("Cashews 500g", 549, 25), ("Tamarind 500g", 99, 110),
    ] * 4)
]
HANDBOOK = "You are the support assistant for 'Chennai Pantry', an online grocery shop.\n\n" + \
    "RULES\n" + "\n".join(f"{i}. {rule}" for i, rule in enumerate([
        "Be polite and brief: at most 3 sentences unless asked for a list.",
        "Only answer from this handbook. If the answer is not here, say you will pass it to a human.",
        "Prices are in rupees and include GST.",
        "Free delivery on orders of Rs 999 or more; otherwise delivery costs Rs 49.",
        "Orders placed before 2 pm are delivered the same day inside Chennai city limits.",
        "Returns: unopened items within 7 days; opened food items cannot be returned.",
        "Refunds go to the original payment method within 5 working days.",
        "Never share another customer's details.",
        "Cash on delivery is available for orders up to Rs 3,000.",
        "Bulk orders (more than 20 of one item) need manager approval.",
    ], start=1)) + "\n\nCATALOGUE (sku | name | price Rs | stock)\n" + \
    "\n".join(f"{sku} | {name} (batch {n // 12 + 1}) | {price} | {stock}" for n, (sku, name, price, stock) in enumerate(PRODUCTS)) + \
    "\n\nFAQ\n" + "\n".join(
        f"Q: {q}\nA: {a}" for q, a in [
            ("Do you deliver outside Chennai?", "Yes, to Tamil Nadu only, in 2-3 days, delivery Rs 99."),
            ("Can I change my order?", "Yes, until it is packed. Packing starts 30 minutes after ordering."),
            ("Do you have organic products?", "Not yet. We plan to add them next year."),
            ("How do I track my order?", "Use the link in the SMS we send when the order ships."),
            ("Which payment methods do you accept?", "UPI, cards, net banking and cash on delivery."),
        ] * 3
    )

QUESTIONS = [
    "Is delivery free if I buy 2 packs of ghee?",
    "Can I return an opened pack of sambar powder?",
    "How much is 3 kg of toor dal?",
]


# ---------------------------------------------------------------------------
# DEMO 1: Same long system prompt, 3 different questions.
# Call 1 WRITES the cache; calls 2 and 3 READ it.
# ---------------------------------------------------------------------------
def demo_basic():
    heading("DEMO 1: cache a long system prompt")
    size = client.messages.count_tokens(
        model=MODEL, system=HANDBOOK, messages=[{"role": "user", "content": "hi"}]
    ).input_tokens
    print(f"Handbook size: about {size:,} tokens (minimum to cache on {MODEL}: 512)\n")

    total, total_no_cache = 0.0, 0.0
    for i, question in enumerate(QUESTIONS, start=1):
        started = time.time()
        response = client.messages.create(
            model=MODEL,
            max_tokens=1000,
            output_config={"effort": "low"},
            system=[{"type": "text", "text": HANDBOOK, "cache_control": {"type": "ephemeral"}}],
            messages=[{"role": "user", "content": question}],  # changes every call: AFTER the marker
        )
        report(f"call {i}", response, time.time() - started)
        print(f"     Q: {question}\n     A: {answer_text(response)}")
        total += cost(response.usage)
        total_no_cache += cost_without_cache(response.usage)
    print(f"\nTotal: ${total:.4f} with caching vs ${total_no_cache:.4f} without.")
    print("Call 1 costs a little MORE (cache write = 1.25x); every later call is much cheaper.")
    print("If you run this demo again within 5 minutes, even call 1 is a cache read.")


# ---------------------------------------------------------------------------
# DEMO 2: The silent cache killer. A timestamp at the START of the system
# prompt changes every call, so the prefix never matches. No error: just
# cache_read = 0 every time. Fix: put changing things AFTER the cached part.
# ---------------------------------------------------------------------------
def demo_invalidator():
    heading("DEMO 2: a timestamp breaks the cache (and how to fix it)")
    print("❌ BAD: timestamp BEFORE the handbook (inside the cached part)")
    for i in range(2):
        started = time.time()
        now = datetime.now().isoformat()  # different every call
        response = client.messages.create(
            model=MODEL,
            max_tokens=300,
            output_config={"effort": "low"},
            system=[{"type": "text", "text": f"Current time: {now}\n\n{HANDBOOK}", "cache_control": {"type": "ephemeral"}}],
            messages=[{"role": "user", "content": QUESTIONS[0]}],
        )
        report(f"bad call {i + 1}", response, time.time() - started)
        time.sleep(1)

    print("\n✅ GOOD: handbook cached, timestamp in the user message (after the marker)")
    for i in range(2):
        started = time.time()
        now = datetime.now().isoformat()
        response = client.messages.create(
            model=MODEL,
            max_tokens=300,
            output_config={"effort": "low"},
            system=[{"type": "text", "text": HANDBOOK, "cache_control": {"type": "ephemeral"}}],
            messages=[{"role": "user", "content": f"(Current time: {now})\n{QUESTIONS[0]}"}],
        )
        report(f"good call {i + 1}", response, time.time() - started)
        time.sleep(1)
    print("\nEvery BAD call writes a new cache entry (you pay 1.25x) and never reads it.")


# ---------------------------------------------------------------------------
# DEMO 3: Caching a whole chat. With the automatic form, the marker moves
# to the last block each call, so each turn reads everything before it from
# the cache and only pays full price for the new question.
# ---------------------------------------------------------------------------
def demo_chat():
    heading("DEMO 3: caching a growing chat (automatic cache_control)")
    messages = []
    for i, question in enumerate(QUESTIONS, start=1):
        messages.append({"role": "user", "content": question})
        started = time.time()
        response = client.messages.create(
            model=MODEL,
            max_tokens=1000,
            output_config={"effort": "low"},
            cache_control={"type": "ephemeral"},  # automatic: caches up to the last block
            system=HANDBOOK,
            messages=messages,
        )
        report(f"turn {i}", response, time.time() - started)
        messages.append({"role": "assistant", "content": answer_text(response)})
    print("\nEach turn: 'read' = everything cached by the turn before; 'write' = the new part.")
    print("Append-only history keeps the prefix identical, so the cache keeps hitting.")


# ---------------------------------------------------------------------------
# Menu.
# ---------------------------------------------------------------------------
DEMOS = {"1": demo_basic, "2": demo_invalidator, "3": demo_chat}

MENU = """
Pick a demo:
  1  Cache a long system prompt (3 calls)
  2  A timestamp breaks the cache (4 calls)
  3  Caching a growing chat (3 calls)
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
