"""
Lesson 7b: Extended thinking (let Claude reason before it answers).

KEY IDEA: Before writing its answer, Claude can THINK: work through the
problem privately, check its steps, then reply. Thinking makes hard questions
(maths, logic, planning, multi-step tool use) more accurate, but it costs
time and tokens.

On claude-opus-5-5:
    - Thinking is ALWAYS ON. You can't turn it off, and the old
      `budget_tokens` setting returns a 400 error.
    - You control HOW MUCH it thinks with EFFORT:
          output_config={"effort": "low" | "medium" | "high" | "xhigh" | "max"}
      The default is "medium". Low = fast and cheap, max = slow and thorough.
    - Thinking comes back as "thinking" blocks in response.content, BEFORE the
      text block. By default their text is EMPTY ("omitted"). Ask for a
      readable SUMMARY with:
          thinking={"type": "adaptive", "display": "summarized"}
      You never get the raw reasoning, only a summary.
    - Thinking tokens are billed as OUTPUT tokens ($20 per 1M on
      claude-opus-5-5), even when you can't see the text. They also count
      toward max_tokens, so don't set max_tokens too low.
    - In a tool loop, send Claude's reply back UNCHANGED (thinking blocks
      included), so it keeps its reasoning between tool calls.

Don't ask Claude to "write out all your hidden reasoning" in its answer:
it may refuse (stop_reason "refusal", category "reasoning_extraction").
Use display="summarized" instead.

Every demo makes real (paid) API calls. The effort demo is the biggest:
3 calls on the same puzzle.

Run:
    python 07b_extended_thinking.py
"""

import os
import time

import anthropic
from dotenv import find_dotenv, load_dotenv

MODEL = "claude-opus-5-5"
PRICE_IN, PRICE_OUT = 4.00, 20.00  # US$ per 1M tokens for claude-opus-5-5

load_dotenv(find_dotenv())
api_key = os.getenv("ANTHROPIC_API_KEY")
if not api_key:
    raise SystemExit("ANTHROPIC_API_KEY not found. Add it to your .env file.")

client = anthropic.Anthropic(api_key=api_key)

# A puzzle with one exact answer, so our code can check Claude.
PUZZLE = (
    "How many whole numbers from 1 to 1000 are divisible by 3 or by 5, "
    "but NOT by 15? End with a last line of the form 'ANSWER: <number>'."
)
EXPECTED = sum(1 for n in range(1, 1001) if (n % 3 == 0 or n % 5 == 0) and n % 15 != 0)


def heading(title: str) -> None:
    print(f"\n{'=' * 70}\n{title}\n{'=' * 70}")


def cost(usage) -> float:
    """Dollar cost of one call. output_tokens INCLUDES the thinking tokens."""
    return (usage.input_tokens * PRICE_IN + usage.output_tokens * PRICE_OUT) / 1_000_000


def answer_text(response) -> str:
    """Join the text blocks only. Read blocks by TYPE: thinking blocks come first."""
    return "".join(b.text for b in response.content if b.type == "text").strip()


def last_line(text: str) -> str:
    return text.splitlines()[-1] if text else "(empty)"


# ---------------------------------------------------------------------------
# DEMO 1: Effort levels. Same puzzle, three effort levels.
# Thinking is ADAPTIVE: Claude decides how much a question needs. On this
# easy puzzle every level answered right in ~3.5s with ~300 tokens (tested
# 2026-09-29). Effort pays off on HARD, multi-step work, so measure before
# raising it. Try your own harder question to see the gap grow.
# ---------------------------------------------------------------------------
heading("DEMO 1: effort = low / medium / high")
print(f"Puzzle: {PUZZLE}\nCorrect answer (worked out by Python): {EXPECTED}\n")

for effort in ("low", "medium", "high"):
    started = time.time()
    response = client.messages.create(
        model=MODEL,
        max_tokens=16000,  # thinking counts toward this limit too
        output_config={"effort": effort},
        messages=[{"role": "user", "content": PUZZLE}],
    )
    seconds = time.time() - started
    if response.stop_reason == "refusal":
        print(f"  {effort:<6} refused")
        continue
    reply = last_line(answer_text(response))
    ok = "✅" if reply.replace("ANSWER:", "").strip() == str(EXPECTED) else "❌"
    print(
        f"  {effort:<6} {ok} {reply:<14} {seconds:5.1f}s  "
        f"out={response.usage.output_tokens:>5} tokens  ${cost(response.usage):.4f}"
    )


# ---------------------------------------------------------------------------
# DEMO 2: See the thinking. Default ("omitted") vs "summarized".
# The thinking happens (and is billed) either way; display only changes
# whether you get to READ a summary of it.
# ---------------------------------------------------------------------------
heading("DEMO 2: display = omitted (default) vs summarized")

for display in ("omitted", "summarized"):
    response = client.messages.create(
        model=MODEL,
        max_tokens=16000,
        thinking={"type": "adaptive", "display": display},
        output_config={"effort": "medium"},
        messages=[{"role": "user", "content": PUZZLE}],
    )
    print(f"\n--- display='{display}' ---")
    print("Block types:", [b.type for b in response.content])
    for block in response.content:
        if block.type == "thinking":
            summary = block.thinking or "(empty: thinking happened, but its text is hidden)"
            print(f"💭 Thinking: {summary[:600]}{'...' if len(summary) > 600 else ''}")
        elif block.type == "text":
            print(f"💬 Answer: {last_line(block.text)}")
    print(f"   output tokens: {response.usage.output_tokens} (thinking + answer)")


# ---------------------------------------------------------------------------
# DEMO 3: Stream the thinking summary live, then the answer.
# Without display="summarized", a stream just looks like a long pause
# before the answer starts.
# ---------------------------------------------------------------------------
heading("DEMO 3: streaming thinking + answer")

with client.messages.stream(
    model=MODEL,
    max_tokens=16000,
    thinking={"type": "adaptive", "display": "summarized"},
    output_config={"effort": "medium"},
    messages=[{"role": "user", "content": "Plan a 3-stop day trip from Chennai for a family with a 5-year-old. Keep it short."}],
) as stream:
    for event in stream:
        if event.type == "content_block_start":
            if event.content_block.type == "thinking":
                print("\n💭 [Thinking...]")
            elif event.content_block.type == "text":
                print("\n\n💬 [Answer]")
        elif event.type == "content_block_delta":
            if event.delta.type == "thinking_delta":
                print(event.delta.thinking, end="", flush=True)
            elif event.delta.type == "text_delta":
                print(event.delta.text, end="", flush=True)
    final = stream.get_final_message()
print(f"\n\n   stop_reason={final.stop_reason}  output tokens={final.usage.output_tokens}  ${cost(final.usage):.4f}")


# ---------------------------------------------------------------------------
# DEMO 4: Thinking + tools. Claude thinks, calls a tool, reads the result,
# thinks again. Adaptive thinking may skip thinking on easy turns (in the
# 2026-09-29 test run, neither turn had a thinking block). RULE: append response.content UNCHANGED (thinking blocks
# included). Don't keep only the text, and don't edit old messages.
# ---------------------------------------------------------------------------
heading("DEMO 4: thinking in a tool loop")


def calculator(expression: str) -> str:
    """Evaluate a simple math expression like '349 * 17 * 1.18'."""
    allowed = set("0123456789+-*/(). ")
    if not set(expression) <= allowed:
        return "Error: only numbers and + - * / ( ) are allowed"
    try:
        return str(eval(expression, {"__builtins__": {}}))
    except Exception as e:
        return f"Error: {e}"


TOOLS = [{
    "name": "calculator",
    "description": "Evaluate an arithmetic expression. Use it for every calculation instead of doing maths in your head.",
    "strict": True,
    "input_schema": {
        "type": "object",
        "properties": {"expression": {"type": "string", "description": "e.g. '349 * 17'"}},
        "required": ["expression"],
        "additionalProperties": False,
    },
}]

messages = [{
    "role": "user",
    "content": (
        "A shop sells filter coffee at ₹349 a pack. Priya buys 17 packs, gets 10% off, "
        "then 5% GST is added on the discounted price. What does she pay? Use the calculator."
    ),
}]

for turn in range(1, 11):  # safety limit, as in lesson 3
    response = client.messages.create(
        model=MODEL,
        max_tokens=16000,
        thinking={"type": "adaptive", "display": "summarized"},
        output_config={"effort": "medium"},
        tools=TOOLS,
        messages=messages,
    )
    print(f"\nTurn {turn}: blocks = {[b.type for b in response.content]}")
    for block in response.content:
        if block.type == "thinking" and block.thinking:
            print(f"  💭 {block.thinking[:200]}{'...' if len(block.thinking) > 200 else ''}")
        elif block.type == "tool_use":
            print(f"  🔧 calculator({block.input['expression']})")
        elif block.type == "text":
            print(f"  💬 {block.text}")

    # Keep the WHOLE reply, thinking blocks included.
    messages.append({"role": "assistant", "content": response.content})

    if response.stop_reason != "tool_use":
        break

    results = []
    for block in response.content:
        if block.type == "tool_use":
            output = calculator(block.input["expression"])
            print(f"     = {output}")
            results.append({
                "type": "tool_result",
                "tool_use_id": block.id,
                "content": output,
                "is_error": output.startswith("Error"),
            })
    messages.append({"role": "user", "content": results})

print(f"\nCorrect total (worked out by Python): ₹{349 * 17 * 0.9 * 1.05:.2f}")
