"""
Lesson 7: Structured output (reliable JSON).

KEY IDEA: Chat answers are for PEOPLE. When your CODE needs to use the answer
(save it to a database, count things, show it in a table), you need DATA in a
fixed shape, e.g.:
    {"intent": "complaint", "sentiment": "negative", "items": [...], "urgent": true}

Three ways to get it, from worst to best:

    1. Just ASK for JSON in the prompt
         -> usually works, but NOT guaranteed: extra words, ```json fences,
            a missing field or a different spelling break your code.

    2. output_config={"format": {"type": "json_schema", "schema": {...}}}
         -> the API GUARANTEES the reply is valid JSON matching your schema.

    3. client.messages.parse(..., output_format=MyPydanticModel)
         -> same guarantee, but you write the shape as a Pydantic class
            (like pydant_example.py) and get back a ready Python OBJECT:
            result.intent, result.items[0].quantity ...  (the recommended way)

Still check stop_reason: if Claude refuses or hits max_tokens, the output can
be missing or incomplete.

Run:
    python 07_structured_output.py
"""

import json
import os
from collections import Counter
from typing import Literal

import anthropic
from dotenv import find_dotenv, load_dotenv
from pydantic import BaseModel, Field

MODEL = "claude-opus-5-5"

load_dotenv(find_dotenv())
api_key = os.getenv("ANTHROPIC_API_KEY")
if not api_key:
    raise SystemExit("ANTHROPIC_API_KEY not found. Add it to your .env file.")

client = anthropic.Anthropic(api_key=api_key)

# Messy messages from customers of the shop in lesson 6c.
CUSTOMER_MESSAGES = [
    "Hi, I'm Priya from Chennai. Please send 2 packs of filter coffee and one pressure cooker. Need it before Friday!!",
    "The silk saree I got yesterday has a tear near the border. Very disappointed. - Arun, Mumbai",
    "Do you deliver to Coimbatore? How many days does it take?",
    "cancel my order 1043 pls, ordered by mistake. thanks",
]

SYSTEM = "You read messages sent to an Indian online shop and extract information from them."


def heading(title: str) -> None:
    print(f"\n{'=' * 70}\n{title}\n{'=' * 70}")


# ---------------------------------------------------------------------------
# WAY 1: Just ask for JSON in the prompt (NOT guaranteed).
# ---------------------------------------------------------------------------
heading("WAY 1: ask for JSON in the prompt")

response = client.messages.create(
    model=MODEL,
    max_tokens=16000,
    system=SYSTEM,
    messages=[{
        "role": "user",
        "content": "Return JSON with the fields intent, sentiment and city for this message:\n\n"
                   + CUSTOMER_MESSAGES[0],
    }],
)
text = "".join(b.text for b in response.content if b.type == "text")
print(f"Raw reply:\n{text}\n")
try:
    print(f"✅ json.loads worked: {json.loads(text)}")
except json.JSONDecodeError as e:
    print(f"❌ json.loads FAILED: {e}")
    print("   (The reply isn't pure JSON: that's why prompting alone isn't enough.)")


# ---------------------------------------------------------------------------
# WAY 2: JSON schema with output_config (guaranteed valid JSON).
# ---------------------------------------------------------------------------
heading("WAY 2: output_config with a JSON schema")

SCHEMA = {
    "type": "object",
    "properties": {
        "intent": {"type": "string", "enum": ["new_order", "complaint", "question", "cancel"]},
        "sentiment": {"type": "string", "enum": ["positive", "neutral", "negative"]},
        "city": {"type": ["string", "null"], "description": "null if no city is mentioned"},
    },
    "required": ["intent", "sentiment", "city"],
    "additionalProperties": False,
}

response = client.messages.create(
    model=MODEL,
    max_tokens=16000,
    system=SYSTEM,
    messages=[{"role": "user", "content": CUSTOMER_MESSAGES[0]}],
    output_config={"format": {"type": "json_schema", "schema": SCHEMA}},
)
text = next(b.text for b in response.content if b.type == "text")
print(f"Raw reply:\n{text}\n")
data = json.loads(text)  # safe: the API guarantees valid JSON (unless stop_reason is refusal/max_tokens)
print(f"✅ A normal Python dict: intent={data['intent']!r}, city={data['city']!r}")


# ---------------------------------------------------------------------------
# WAY 3: Pydantic + messages.parse() (guaranteed, and you get an OBJECT).
# ---------------------------------------------------------------------------
heading("WAY 3: Pydantic model + client.messages.parse()")


# The shape we want, written as Python classes. The Field descriptions are
# sent to Claude too, so they work like tool parameter descriptions (lesson 6b).
class OrderItem(BaseModel):
    product: str = Field(description="Product name as the customer wrote it")
    quantity: int


class CustomerMessage(BaseModel):
    customer_name: str | None = Field(description="null if the name isn't given")
    city: str | None = Field(description="null if no city is mentioned")
    intent: Literal["new_order", "complaint", "question", "cancel"]  # Literal = enum
    sentiment: Literal["positive", "neutral", "negative"]
    items: list[OrderItem] = Field(description="Products mentioned with quantities; empty list if none")
    order_number: str | None = Field(description="null if no order number is given")
    urgent: bool = Field(description="true if the customer needs a fast reply or delivery")
    summary: str = Field(description="One short sentence for the support team")


def read_message(message: str) -> CustomerMessage | None:
    """Turn one messy customer message into a CustomerMessage object."""
    response = client.messages.parse(
        model=MODEL,
        max_tokens=16000,
        system=SYSTEM,
        messages=[{"role": "user", "content": message}],
        output_format=CustomerMessage,  # <-- the Pydantic class IS the schema
    )
    if response.stop_reason in ("refusal", "max_tokens"):
        print(f"    ⚠️ no usable output (stop_reason: {response.stop_reason})")
        return None
    return response.parsed_output  # a CustomerMessage object, already validated


results = []
for message in CUSTOMER_MESSAGES:
    print(f"\n📩 {message}")
    result = read_message(message)
    if result is None:
        continue
    results.append(result)
    # A real Python object: use dot access, loops, if-statements...
    print(f"    intent={result.intent}  sentiment={result.sentiment}  city={result.city}  urgent={result.urgent}")
    for item in result.items:
        print(f"    item: {item.quantity} x {item.product}")
    if result.order_number:
        print(f"    order number: {result.order_number}")
    print(f"    summary: {result.summary}")


# ---------------------------------------------------------------------------
# WHY THIS MATTERS: now plain Python code can work with Claude's output.
# ---------------------------------------------------------------------------
heading("Using the data in code")

print("Messages by intent:", dict(Counter(r.intent for r in results)))
print("Urgent messages from:", [r.customer_name or "(unknown)" for r in results if r.urgent])
print("Unhappy customers:", [r.customer_name or "(unknown)" for r in results if r.sentiment == "negative"])

# Pydantic objects turn back into JSON easily, e.g. to save or send to a web page.
print("\nFirst result as JSON:")
print(results[0].model_dump_json(indent=2))
