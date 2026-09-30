"""
Lesson 8d: Model selection (Haiku vs Sonnet vs Opus).

KEY IDEA: Anthropic sells the same kind of model in three sizes. Bigger =
smarter but slower and pricier. Pick per TASK, not per app.

    model               in / out $ per 1M   good for
    claude-haiku-4-5      1 /  5            simple, high-volume, fast: classify, route,
                                            extract fields, short summaries
    claude-sonnet-5-5     2 / 10            everyday work: coding, agents, chat, writing
    claude-opus-5-5       4 / 20            the hardest reasoning, long agent runs,
                                            when a mistake is expensive

How to choose, in practice:
    1. Start with the strongest model to find out if the task can be done at all.
    2. Build a small test set with known answers (lesson 14 does this properly).
    3. Try cheaper models / lower effort on it. Keep the cheapest that still passes.
    4. Judge cost per FINISHED task, not per call: a cheap model that needs
       retries or extra turns may cost more in the end.
    5. Mix models: a cheap model for easy sub-tasks, a strong one for the hard
       parts (demo 2 routes questions this way; lesson 12 uses a cheaper
       model for sub-agents).

Differences you must handle in code:
    - claude-haiku-4-5 has a 200K context (the others 1M) and does NOT accept
      output_config={"effort": ...} (400 error). Its thinking is off unless you
      send thinking={"type": "enabled", "budget_tokens": N}.
    - claude-opus-5-5 defaults to effort "medium"; claude-sonnet-5-5 to "high".
    - Effort is a second dial: Opus at "low" is often cheaper than you think.

This lesson runs the same 3 tasks on all 3 models and prints a table of
correctness, time and cost.

Run:
    python 08d_model_selection.py        (menu)
    python 08d_model_selection.py 1      (one demo)
"""

import os
import sys
import time

import anthropic
from dotenv import find_dotenv, load_dotenv

load_dotenv(find_dotenv())
api_key = os.getenv("ANTHROPIC_API_KEY")
if not api_key:
    raise SystemExit("ANTHROPIC_API_KEY not found. Add it to your .env file.")

client = anthropic.Anthropic(api_key=api_key)

# model -> (input, output) US$ per 1M tokens
PRICES = {
    "claude-haiku-4-5": (1.00, 5.00),
    "claude-sonnet-5-5": (2.00, 10.00),
    "claude-opus-5-5": (4.00, 20.00),
}


def heading(title: str) -> None:
    print(f"\n{'=' * 70}\n{title}\n{'=' * 70}")


def ask(model: str, prompt: str, max_tokens: int = 8000, effort: str | None = None):
    """One call that works on every model. Returns (text, seconds, cost)."""
    kwargs = {}
    if effort and model != "claude-haiku-4-5":  # Haiku 4.5 rejects the effort setting
        kwargs["output_config"] = {"effort": effort}
    started = time.time()
    # Streaming + get_final_message(): with a big max_tokens the SDK refuses a
    # plain create() ("Streaming is required for operations that may take
    # longer than 10 minutes"). Streaming has no such limit.
    with client.messages.stream(
        model=model, max_tokens=max_tokens, messages=[{"role": "user", "content": prompt}], **kwargs
    ) as stream:
        response = stream.get_final_message()
    seconds = time.time() - started
    p_in, p_out = PRICES[model]
    usd = (response.usage.input_tokens * p_in + response.usage.output_tokens * p_out) / 1e6
    text = "".join(b.text for b in response.content if b.type == "text").strip()
    return text, seconds, usd


def last_line(text: str) -> str:
    return text.strip().splitlines()[-1].strip() if text.strip() else ""


# ---------------------------------------------------------------------------
# The tasks. Each has an answer Python can check.
# ---------------------------------------------------------------------------
REVIEWS = [
    ("The dosa was crispy and the chutney was fresh. Will come again!", "positive"),
    ("Waited 45 minutes and the food was cold.", "negative"),
    ("It was okay. Nothing special, nothing bad.", "neutral"),
    ("Best filter coffee in Mylapore, hands down.", "positive"),
    ("Rude staff and they got my order wrong twice.", "negative"),
]


def task_classify(model):
    prompt = "Label each review as positive, negative or neutral. Reply with ONLY the labels, one per line, in order.\n\n" + \
        "\n".join(f"{i}. {r}" for i, (r, _) in enumerate(REVIEWS, 1))
    text, s, usd = ask(model, prompt, max_tokens=2000, effort="low")
    got = [line.strip(" .0123456789").lower() for line in text.splitlines() if line.strip()]
    ok = got == [label for _, label in REVIEWS]
    return ok, s, usd, ", ".join(got)


INVOICE = "Invoice INV-2291 from Sri Balaji Traders, dated 3 March 2026, for 12 bags of rice at Rs 1,150 each. Payment due in 30 days."


def task_extract(model):
    prompt = f"{INVOICE}\n\nWhat is the invoice total in rupees, and the due date (YYYY-MM-DD)? " \
             "Last line exactly: '<total> | <due date>' with the total as a plain number."
    text, s, usd = ask(model, prompt, max_tokens=4000, effort="low")
    answer = last_line(text)
    return answer.replace(",", "").replace(" ", "") == "13800|2026-04-02", s, usd, answer


# A counting puzzle that is easy to get wrong without careful reasoning.
PUZZLE_ANSWER = sum(1 for n in range(1, 10000) if sum(map(int, str(n))) == 20 and n % 4 == 0)


def task_reason(model):
    prompt = ("How many whole numbers from 1 to 9999 have digits that add up to exactly 20 "
              "AND are divisible by 4? Work it out carefully. Last line: 'ANSWER: <number>'.")
    text, s, usd = ask(model, prompt, max_tokens=32000, effort="medium")
    answer = last_line(text)
    return answer.replace("ANSWER:", "").strip() == str(PUZZLE_ANSWER), s, usd, answer


TASKS = [("classify 5 reviews", task_classify), ("extract invoice data", task_extract), ("hard counting puzzle", task_reason)]


# ---------------------------------------------------------------------------
# DEMO 1: Same tasks, three models. Print a comparison table.
# Test run 2026-09-30: all 3 models got the reviews and the invoice right,
# with Haiku ~5-10x cheaper than Opus. On the puzzle Haiku answered 65 (wrong),
# Sonnet and Opus answered 154 (right). Easy work -> small model; hard -> big.
# ---------------------------------------------------------------------------
def demo_compare():
    heading("DEMO 1: the same 3 tasks on Haiku, Sonnet and Opus")
    print(f"(correct puzzle answer, worked out by Python: {PUZZLE_ANSWER})\n")
    print(f"{'task':<22} {'model':<18} {'ok':<3} {'time':>6} {'cost $':>8}  answer")
    for task_name, task in TASKS:
        for model in PRICES:
            try:
                ok, s, usd, answer = task(model)
                print(f"{task_name:<22} {model:<18} {'✅' if ok else '❌':<3} {s:5.1f}s {usd:8.5f}  {answer[:40]}")
            except anthropic.APIError as e:
                print(f"{task_name:<22} {model:<18} error: {e}")
        print()
    print("Read the table per task: the cheapest model that is ✅ is the one to use.")


# ---------------------------------------------------------------------------
# DEMO 2: A router. A cheap model decides how hard a question is; easy ones
# go to Haiku, normal ones to Sonnet, hard ones to Opus.
# ---------------------------------------------------------------------------
ROUTER_PROMPT = """Rate how hard this question is to answer well.
easy   = small talk, a simple fact, a one-line answer
medium = explanation, writing, simple code
hard   = multi-step maths or logic, tricky code, careful analysis
Reply with ONE word: easy, medium or hard.

Question: {question}"""

ROUTE = {"easy": "claude-haiku-4-5", "medium": "claude-sonnet-5-5", "hard": "claude-opus-5-5"}


def route(question: str) -> str:
    label, _, _ = ask("claude-haiku-4-5", ROUTER_PROMPT.format(question=question), max_tokens=10)
    label = label.strip().lower().strip(".")
    return ROUTE.get(label, "claude-opus-5-5")  # unsure? use the strongest model


def demo_router():
    heading("DEMO 2: route each question to a model")
    for question in (
        "What is the capital of Tamil Nadu?",
        "Explain what a Python list comprehension is, with one example.",
        "A train leaves at 9:40 and travels 212 km at 53 km/h, stopping 3 times for 7 minutes each. When does it arrive?",
    ):
        model = route(question)
        answer, s, usd = ask(model, question, max_tokens=8000)
        print(f"\nQ: {question}\n   -> {model}  ({s:.1f}s, ${usd:.5f})\n   A: {answer[:300]}")
    print("\nThe router call itself costs a fraction of a cent on Haiku.")
    print("Before building a router, also try ONE strong model at low effort: it is often simpler.")


# ---------------------------------------------------------------------------
# Menu.
# ---------------------------------------------------------------------------
DEMOS = {"1": demo_compare, "2": demo_router}

MENU = """
Pick a demo:
  1  Compare Haiku / Sonnet / Opus on 3 tasks (9 calls, under $0.10)
  2  Route questions to a model (6 small calls)
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
