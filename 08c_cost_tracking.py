"""
Lesson 8c: Token and cost tracking.

KEY IDEA: Every response carries a `usage` object. Add it up and you always
know what a question, a session, or a whole agent run cost:

    response.usage.input_tokens                 new input (full price)
    response.usage.cache_creation_input_tokens  written to cache (1.25x input price)
    response.usage.cache_read_input_tokens      read from cache  (cheap)
    response.usage.output_tokens                the answer + thinking (output price)

An AGENT makes several calls per question (one per tool turn), so the cost of
one question = the sum over all its calls. Tool results become input on the
next call, so big tool results cost money twice: once when they arrive and
again on every later call.

This lesson builds a small UsageTracker you can copy into any project:
    tracker.record(response, label)   add one call
    tracker.estimate(...)             count_tokens BEFORE a call (free) to guess its cost
    tracker.check_budget()            stop when the session spends more than a limit
    tracker.report() / tracker.save() a table on screen and a JSON log on disk

Prices below are US$ per 1M tokens (from Anthropic's pricing, 2026-09).
Check https://www.anthropic.com/pricing when they change.

Run:
    python 08c_cost_tracking.py         (menu)
    python 08c_cost_tracking.py 1       (one demo)
"""

import json
import os
import sys
from dataclasses import asdict, dataclass, field
from datetime import datetime
from pathlib import Path

import anthropic
from dotenv import find_dotenv, load_dotenv

MODEL = "claude-opus-5-5"
SESSION_BUDGET_USD = 0.10  # the chat stops when a session spends more than this

load_dotenv(find_dotenv())
api_key = os.getenv("ANTHROPIC_API_KEY")
if not api_key:
    raise SystemExit("ANTHROPIC_API_KEY not found. Add it to your .env file.")

client = anthropic.Anthropic(api_key=api_key)

LOG_DIR = Path(__file__).resolve().parent / "lesson_data" / "usage_logs"

# model -> (input, output, cache write 5 min, cache read), US$ per 1M tokens
PRICES = {
    "claude-opus-5-5": (4.00, 20.00, 5.00, 0.20),
    "claude-sonnet-5-5": (2.00, 10.00, 2.50, 0.20),
    "claude-haiku-4-5": (1.00, 5.00, 1.25, 0.10),
}


def heading(title: str) -> None:
    print(f"\n{'=' * 70}\n{title}\n{'=' * 70}")


# ---------------------------------------------------------------------------
# STEP A: The tracker.
# ---------------------------------------------------------------------------
class BudgetExceeded(Exception):
    pass


@dataclass
class CallRecord:
    label: str
    model: str
    input_tokens: int
    cache_write_tokens: int
    cache_read_tokens: int
    output_tokens: int
    cost_usd: float
    time: str = field(default_factory=lambda: datetime.now().isoformat(timespec="seconds"))


def price_of(model: str, usage) -> float:
    p_in, p_out, p_write, p_read = PRICES[model]
    return (
        usage.input_tokens * p_in
        + (usage.cache_creation_input_tokens or 0) * p_write
        + (usage.cache_read_input_tokens or 0) * p_read
        + usage.output_tokens * p_out
    ) / 1_000_000


class UsageTracker:
    def __init__(self, budget_usd: float | None = None):
        self.calls: list[CallRecord] = []
        self.budget_usd = budget_usd

    def record(self, response, label: str = "") -> CallRecord:
        u = response.usage
        rec = CallRecord(
            label=label,
            model=response.model,
            input_tokens=u.input_tokens,
            cache_write_tokens=u.cache_creation_input_tokens or 0,
            cache_read_tokens=u.cache_read_input_tokens or 0,
            output_tokens=u.output_tokens,
            cost_usd=price_of(response.model, u),
        )
        self.calls.append(rec)
        return rec

    @property
    def total_usd(self) -> float:
        return sum(c.cost_usd for c in self.calls)

    def estimate(self, model: str, messages: list, max_tokens: int, **kwargs) -> tuple[float, float]:
        """(minimum, maximum) cost of a call BEFORE making it. The input is exact
        (count_tokens); the output is unknown, so the max assumes all max_tokens."""
        n_in = client.messages.count_tokens(model=model, messages=messages, **kwargs).input_tokens
        p_in, p_out, _, _ = PRICES[model]
        return n_in * p_in / 1e6, (n_in * p_in + max_tokens * p_out) / 1e6

    def check_budget(self) -> None:
        if self.budget_usd is not None and self.total_usd > self.budget_usd:
            raise BudgetExceeded(f"Session spent ${self.total_usd:.4f}, budget is ${self.budget_usd:.2f}")

    def report(self) -> None:
        print(f"\n{'call':<22} {'in':>6} {'c.write':>7} {'c.read':>7} {'out':>6} {'cost $':>9}")
        for c in self.calls:
            print(f"{c.label[:22]:<22} {c.input_tokens:>6} {c.cache_write_tokens:>7} {c.cache_read_tokens:>7} {c.output_tokens:>6} {c.cost_usd:>9.5f}")
        totals = [sum(getattr(c, f) for c in self.calls) for f in ("input_tokens", "cache_write_tokens", "cache_read_tokens", "output_tokens")]
        print(f"{'TOTAL':<22} {totals[0]:>6} {totals[1]:>7} {totals[2]:>7} {totals[3]:>6} {self.total_usd:>9.5f}")

    def save(self) -> Path:
        LOG_DIR.mkdir(parents=True, exist_ok=True)
        path = LOG_DIR / f"session_{datetime.now():%Y%m%d_%H%M%S}.json"
        path.write_text(json.dumps({"total_usd": self.total_usd, "calls": [asdict(c) for c in self.calls]}, indent=2))
        return path


# ---------------------------------------------------------------------------
# STEP B: A small agent (tools from lesson 4) that records every call.
# ---------------------------------------------------------------------------
FAKE_WEATHER = {"chennai": "33°C, humid", "bengaluru": "24°C, cloudy", "delhi": "38°C, sunny"}


def get_weather(city: str) -> str:
    return FAKE_WEATHER.get(city.lower(), f"No data for {city}")


def calculator(expression: str) -> str:
    if not set(expression) <= set("0123456789+-*/(). "):
        return "Error: only numbers and + - * / ( ) are allowed"
    return str(eval(expression, {"__builtins__": {}}))


TOOLS = [
    {
        "name": "get_weather",
        "description": "Current weather for an Indian city.",
        "input_schema": {"type": "object", "properties": {"city": {"type": "string"}}, "required": ["city"]},
    },
    {
        "name": "calculator",
        "description": "Evaluate an arithmetic expression like '12 * (3 + 4)'.",
        "input_schema": {"type": "object", "properties": {"expression": {"type": "string"}}, "required": ["expression"]},
    },
]
RUN_TOOL = {"get_weather": get_weather, "calculator": calculator}


def run_agent(question: str, tracker: UsageTracker, messages: list | None = None) -> str:
    messages = messages if messages is not None else []
    messages.append({"role": "user", "content": question})
    for turn in range(1, 11):
        response = client.messages.create(
            model=MODEL,
            max_tokens=4000,
            output_config={"effort": "low"},
            cache_control={"type": "ephemeral"},  # lesson 8b: later turns read earlier ones from cache
            tools=TOOLS,
            messages=messages,
        )
        rec = tracker.record(response, f"{question[:12]}.. turn {turn}")
        print(
            f"   turn {turn}: in={rec.input_tokens} write={rec.cache_write_tokens} "
            f"read={rec.cache_read_tokens} out={rec.output_tokens}  ${rec.cost_usd:.5f}"
        )
        messages.append({"role": "assistant", "content": response.content})
        if response.stop_reason != "tool_use":
            return "".join(b.text for b in response.content if b.type == "text")
        results = [
            {"type": "tool_result", "tool_use_id": b.id, "content": RUN_TOOL[b.name](**b.input)}
            for b in response.content if b.type == "tool_use"
        ]
        messages.append({"role": "user", "content": results})
    return "(stopped: too many tool turns)"


# ---------------------------------------------------------------------------
# DEMO 1: Cost of each question, and of the whole session.
# Watch the cache columns: in the 2026-09-30 test run, a 2-turn question
# WROTE 641 tokens to the cache (1.25x) that nothing read again, so caching
# cost a little extra there. It pays off from the 3rd call on the same
# prefix (the 3-turn question read 658 tokens at 0.05x). Measure, don't guess.
# ---------------------------------------------------------------------------
def demo_agent_costs():
    heading("DEMO 1: what does each agent question cost?")
    tracker = UsageTracker()
    for question in (
        "What is 17 * 23?",
        "What's the weather in Chennai and Delhi?",
        "Temperature difference between Delhi and Bengaluru, in °C? Use the tools.",
    ):
        before = tracker.total_usd
        print(f"\nQ: {question}")
        answer = run_agent(question, tracker)
        print(f"A: {answer}\n   => this question cost ${tracker.total_usd - before:.5f}")
    tracker.report()
    print(f"\nSaved log: {tracker.save()}")


# ---------------------------------------------------------------------------
# DEMO 2: Estimate BEFORE you send. count_tokens is free, so you can check a
# big request (a long document, a huge history) before paying for it.
# ---------------------------------------------------------------------------
def demo_estimate():
    heading("DEMO 2: estimate a call's cost before sending it")
    tracker = UsageTracker()
    long_doc = "The quick brown fox jumps over the lazy dog. " * 2000
    messages = [{"role": "user", "content": f"{long_doc}\n\nHow many times does 'fox' appear? Just the number."}]
    for model in PRICES:
        low, high = tracker.estimate(model, messages, max_tokens=500)
        print(f"  {model:<18} between ${low:.4f} and ${high:.4f}")
    print("\nThe same text costs different amounts per model (price AND tokenizer differ).")
    print("Use this to refuse or warn before sending something huge.")


# ---------------------------------------------------------------------------
# DEMO 3: A chat with a budget. It shows the running cost after every reply
# and stops when the session goes over SESSION_BUDGET_USD.
# ---------------------------------------------------------------------------
def chat():
    heading(f"DEMO 3: chat with a ${SESSION_BUDGET_USD:.2f} session budget")
    print("Ask about weather or maths. Type 'exit' to go back.\n")
    tracker = UsageTracker(budget_usd=SESSION_BUDGET_USD)
    messages = []
    while True:
        question = input("You: ").strip()
        if not question:
            continue
        if question.lower() == "exit":
            break
        try:
            tracker.check_budget()
            answer = run_agent(question, tracker, messages)
            print(f"Claude: {answer}")
            print(f"   💰 session so far: ${tracker.total_usd:.4f} of ${SESSION_BUDGET_USD:.2f}\n")
        except BudgetExceeded as e:
            print(f"🛑 {e}. Start a new session.")
            break
    tracker.report()
    print(f"Saved log: {tracker.save()}")


# ---------------------------------------------------------------------------
# Menu.
# ---------------------------------------------------------------------------
DEMOS = {"1": demo_agent_costs, "2": demo_estimate, "3": chat}

MENU = """
Pick a demo:
  1  Cost of each agent question (a few small calls)
  2  Estimate before sending    (count_tokens only: free)
  3  Chat with a session budget
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
