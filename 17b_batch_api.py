"""
Lesson 17b: The Message Batches API (half price, when you can wait).

KEY IDEA: Some jobs don't need an answer NOW: tag 10,000 reviews, summarise
last month's tickets, translate a product catalogue, run an eval overnight.
Send them as ONE batch and Anthropic processes them in the background:

    - 50% cheaper than normal calls (all tokens)
    - usually done within 1 hour, at most 24 hours
    - up to 100,000 requests per batch
    - each request is a normal messages.create(...) request (tools, system
      prompts, structured output, caching all work)

The flow:
    1. CREATE   client.messages.batches.create(requests=[{custom_id, params}, ...])
    2. WAIT     client.messages.batches.retrieve(id).processing_status == "ended"
    3. RESULTS  for r in client.messages.batches.results(id): ...
                r.custom_id, r.result.type in succeeded / errored / canceled / expired

IMPORTANT: results come back in ANY order. Match them by custom_id, never by
position. Give every request a custom_id you can look up (e.g. the review id).

Because it can take a while, this lesson saves the batch id to a file, so
you can submit, close the terminal, and come back later for the results.

Run:
    python 17b_batch_api.py submit     create a batch of 12 review-tagging requests
    python 17b_batch_api.py status     check the last batch
    python 17b_batch_api.py wait       poll every 30 s until it ends
    python 17b_batch_api.py results    print the results
    python 17b_batch_api.py list       your recent batches
    python 17b_batch_api.py cancel     cancel the last batch
    python 17b_batch_api.py            (menu)
"""

import json
import os
import sys
import time
from pathlib import Path

import anthropic
from dotenv import find_dotenv, load_dotenv

MODEL = "claude-opus-5-5"
PRICE_IN, PRICE_OUT = 4.00, 20.00  # normal price per 1M tokens; batches cost HALF

load_dotenv(find_dotenv())
api_key = os.getenv("ANTHROPIC_API_KEY")
if not api_key:
    raise SystemExit("ANTHROPIC_API_KEY not found. Add it to your .env file.")

client = anthropic.Anthropic(api_key=api_key)

STATE_FILE = Path(__file__).resolve().parent / "lesson_data" / "batches" / "last_batch.json"

REVIEWS = {
    "r01": "The dosa batter was sour and runny. Had to throw it away.",
    "r02": "Delivery boy was very polite and came 10 minutes early!",
    "r03": "Good rice but the bag was torn, lost some on the floor.",
    "r04": "Prices are a little high but quality is consistent.",
    "r05": "App keeps logging me out when I try to pay with UPI.",
    "r06": "Best filter coffee I've had outside my grandmother's house.",
    "r07": "Ordered 2 kg onions, got 1 kg. Nobody answers the phone.",
    "r08": "Fine.",
    "r09": "Ghee jar leaked in the bag and spoiled my other groceries.",
    "r10": "Love the Sunday offers, saved Rs 200 this week.",
    "r11": "Why is there no sugar-free option for the sweets?",
    "r12": "Refund took 3 weeks instead of 5 days. Very disappointed.",
}

SCHEMA = {
    "type": "object",
    "properties": {
        "sentiment": {"type": "string", "enum": ["positive", "neutral", "negative"]},
        "topic": {"type": "string", "enum": ["product_quality", "delivery", "packaging", "price", "app", "support", "refund", "other"]},
        "needs_follow_up": {"type": "boolean"},
    },
    "required": ["sentiment", "topic", "needs_follow_up"],
    "additionalProperties": False,
}


def heading(title: str) -> None:
    print(f"\n{'=' * 70}\n{title}\n{'=' * 70}")


def last_batch_id() -> str:
    if not STATE_FILE.exists():
        raise SystemExit("No batch yet. Run:  python 17b_batch_api.py submit")
    return json.loads(STATE_FILE.read_text())["id"]


# ---------------------------------------------------------------------------
# 1. CREATE
# ---------------------------------------------------------------------------
def submit():
    heading("SUBMIT: one batch, one request per review")
    requests = [
        {
            "custom_id": review_id,  # how we match the result later
            "params": {
                "model": MODEL,
                "max_tokens": 1000,
                "output_config": {"effort": "low", "format": {"type": "json_schema", "schema": SCHEMA}},
                "system": "Tag this grocery shop review. needs_follow_up = the customer has a problem we should fix.",
                "messages": [{"role": "user", "content": text}],
            },
        }
        for review_id, text in REVIEWS.items()
    ]
    batch = client.messages.batches.create(requests=requests)
    STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
    STATE_FILE.write_text(json.dumps({"id": batch.id, "created": str(batch.created_at)}))
    print(f"Created batch {batch.id} with {len(requests)} requests. Status: {batch.processing_status}")
    print(f"Saved the id to {STATE_FILE}")
    print("Now run:  python 17b_batch_api.py wait   (or check back later with 'status')")


# ---------------------------------------------------------------------------
# 2. WAIT / STATUS
# ---------------------------------------------------------------------------
def status(batch_id: str | None = None):
    batch = client.messages.batches.retrieve(batch_id or last_batch_id())
    c = batch.request_counts
    print(f"{batch.id}: {batch.processing_status}  processing={c.processing} succeeded={c.succeeded} "
          f"errored={c.errored} canceled={c.canceled} expired={c.expired}")
    return batch


def wait(poll_seconds: int = 30):
    heading("WAIT: poll until the batch ends")
    started = time.time()
    while True:
        batch = status()
        if batch.processing_status == "ended":
            print(f"Finished after about {time.time() - started:.0f}s of waiting. Run 'results'.")
            return
        time.sleep(poll_seconds)


# ---------------------------------------------------------------------------
# 3. RESULTS (matched by custom_id)
# ---------------------------------------------------------------------------
def results():
    heading("RESULTS")
    batch_id = last_batch_id()
    batch = client.messages.batches.retrieve(batch_id)
    if batch.processing_status != "ended":
        print(f"Not finished yet ({batch.processing_status}). Try 'wait'.")
        return
    tags, tokens_in, tokens_out = {}, 0, 0
    for r in client.messages.batches.results(batch_id):
        if r.result.type == "succeeded":
            msg = r.result.message
            tags[r.custom_id] = json.loads("".join(b.text for b in msg.content if b.type == "text"))
            tokens_in += msg.usage.input_tokens
            tokens_out += msg.usage.output_tokens
        elif r.result.type == "errored":
            tags[r.custom_id] = {"error": r.result.error.error.type if hasattr(r.result.error, "error") else str(r.result.error)}
        else:  # canceled / expired: resubmit these
            tags[r.custom_id] = {"error": r.result.type}

    for review_id in sorted(tags):  # sort by OUR id; the API order is random
        t = tags[review_id]
        if "error" in t:
            print(f"   {review_id} ❌ {t['error']}")
        else:
            flag = "🔔" if t["needs_follow_up"] else "  "
            print(f"   {review_id} {flag} {t['sentiment']:<8} {t['topic']:<16} {REVIEWS[review_id][:55]}")

    normal = (tokens_in * PRICE_IN + tokens_out * PRICE_OUT) / 1e6
    print(f"\nTokens: in={tokens_in:,} out={tokens_out:,}.  Normal price ${normal:.4f} -> batch price ${normal / 2:.4f}")
    follow = [k for k, v in tags.items() if v.get("needs_follow_up")]
    print(f"Reviews needing follow-up: {', '.join(sorted(follow))}")


def list_batches():
    heading("YOUR RECENT BATCHES")
    for batch in client.messages.batches.list(limit=10):
        print(f"   {batch.id}  {batch.processing_status:<11} created {batch.created_at:%Y-%m-%d %H:%M}  "
              f"succeeded={batch.request_counts.succeeded}")


def cancel():
    batch = client.messages.batches.cancel(last_batch_id())
    print(f"{batch.id}: {batch.processing_status} (requests already finished are still billed)")


# ---------------------------------------------------------------------------
# Commands / menu.
# ---------------------------------------------------------------------------
COMMANDS = {"submit": submit, "status": status, "wait": wait, "results": results, "list": list_batches, "cancel": cancel}

if len(sys.argv) > 1:
    command = sys.argv[1].lower()
    if command not in COMMANDS:
        raise SystemExit(f"Unknown command. Use one of: {', '.join(COMMANDS)}")
    COMMANDS[command]()
    sys.exit()

while True:
    print("\nCommands: " + " / ".join(COMMANDS) + " / q")
    choice = input("Choice: ").strip().lower()
    if choice == "q":
        break
    if choice in COMMANDS:
        COMMANDS[choice]()
    else:
        print("Unknown choice.")
