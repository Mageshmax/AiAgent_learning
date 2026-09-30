"""
Lesson 16: Observability (see what your agent actually did).

KEY IDEA: When a user says "the bot gave a wrong answer yesterday", you need
to replay what happened: which calls, which tools, what inputs and outputs,
how long, how many tokens, what it cost, what failed. print() is gone
by then. So LOG EVERYTHING, in a structured way:

    TRACE   one agent run (one user question). Has a trace_id.
    SPAN    one step inside it: an LLM call, or a tool call.
            Each span records: start time, duration, inputs, outputs,
            tokens, cost, stop_reason, request_id, error.

    trace 7f3a...  "Weather in Chennai + Delhi?"            2.9s  $0.012
      ├─ llm      turn 1  stop=tool_use   in=480 out=95      1.4s
      ├─ tool     get_weather(Chennai)    ok                 0.0s
      ├─ tool     get_weather(Delhi)      ok                 0.0s
      └─ llm      turn 2  stop=end_turn   in=610 out=60      1.5s

We write one JSON object per line (JSONL) to lesson_data/traces/<date>.jsonl.
JSONL is easy to append to, grep, and load into pandas or a dashboard.

Worth logging on EVERY call:
    - response._request_id   Anthropic's id for the call: quote it when
                             you contact support about a strange response
    - usage (all 4 token fields), model, stop_reason, duration
    - tool name, input, output (shortened), is_error
Do NOT log secrets (API keys, passwords). Be careful with personal data.

Bigger setups send the same data to a tracing tool (OpenTelemetry, Langfuse,
LangSmith, Datadog...). The idea is identical: traces made of spans.
Also handy: run any script with ANTHROPIC_LOG=debug to see the SDK's own
HTTP log (method, URL, status, retries).

Run:
    python 16_observability.py       (menu)
    python 16_observability.py 1 2   (run traced agent, then view traces)
"""

import json
import os
import sys
import time
import uuid
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path

import anthropic
from dotenv import find_dotenv, load_dotenv

MODEL = "claude-opus-5-5"
PRICE_IN, PRICE_OUT, PRICE_CACHE_WRITE, PRICE_CACHE_READ = 4.00, 20.00, 5.00, 0.20
MAX_TOOL_TURNS = 8
MAX_FIELD_CHARS = 500  # shorten long inputs/outputs in the log

load_dotenv(find_dotenv())
api_key = os.getenv("ANTHROPIC_API_KEY")
if not api_key:
    raise SystemExit("ANTHROPIC_API_KEY not found. Add it to your .env file.")

client = anthropic.Anthropic(api_key=api_key)

TRACE_DIR = Path(__file__).resolve().parent / "lesson_data" / "traces"


def heading(title: str) -> None:
    print(f"\n{'=' * 70}\n{title}\n{'=' * 70}")


def short(value) -> str:
    text = value if isinstance(value, str) else json.dumps(value, ensure_ascii=False, default=str)
    return text if len(text) <= MAX_FIELD_CHARS else text[:MAX_FIELD_CHARS] + "...(cut)"


# ---------------------------------------------------------------------------
# STEP A: A tiny tracer. Every span is one line in today's JSONL file.
# ---------------------------------------------------------------------------
class Tracer:
    def __init__(self):
        TRACE_DIR.mkdir(parents=True, exist_ok=True)
        self.path = TRACE_DIR / f"{datetime.now():%Y-%m-%d}.jsonl"
        self.trace_id = None

    def write(self, record: dict) -> None:
        record = {"time": datetime.now().isoformat(timespec="milliseconds"), "trace_id": self.trace_id, **record}
        with self.path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(record, ensure_ascii=False) + "\n")

    @contextmanager
    def trace(self, name: str, user_input: str):
        """Wrap one agent run. Records start, end, total duration and any crash."""
        self.trace_id = uuid.uuid4().hex[:12]
        started = time.perf_counter()
        self.write({"kind": "trace_start", "name": name, "input": short(user_input)})
        status = "ok"
        try:
            yield self.trace_id
        except Exception as e:
            status = f"error: {type(e).__name__}: {e}"
            raise
        finally:
            self.write({"kind": "trace_end", "status": status, "duration_s": round(time.perf_counter() - started, 3)})

    @contextmanager
    def span(self, kind: str, name: str, **attrs):
        """Wrap one step. The code inside can add more attributes to `record`."""
        record = {"kind": kind, "name": name, **attrs}
        started = time.perf_counter()
        try:
            yield record
            record.setdefault("status", "ok")
        except Exception as e:
            record["status"] = f"error: {type(e).__name__}: {e}"
            raise
        finally:
            record["duration_s"] = round(time.perf_counter() - started, 3)
            self.write(record)


tracer = Tracer()


# ---------------------------------------------------------------------------
# STEP B: The agent (weather + calculator, as in lesson 4), with spans.
# ---------------------------------------------------------------------------
FAKE_WEATHER = {"chennai": "33°C, humid", "delhi": "38°C, sunny", "bengaluru": "24°C, cloudy"}


def get_weather(city: str) -> str:
    if city.lower() not in FAKE_WEATHER:
        raise ValueError(f"No data for {city}")
    return FAKE_WEATHER[city.lower()]


def calculator(expression: str) -> str:
    if not set(expression) <= set("0123456789+-*/(). "):
        raise ValueError("Only numbers and + - * / ( ) are allowed.")
    return str(eval(expression, {"__builtins__": {}}))


TOOLS = [
    {"name": "get_weather", "description": "Current weather for an Indian city.",
     "input_schema": {"type": "object", "properties": {"city": {"type": "string"}}, "required": ["city"]}},
    {"name": "calculator", "description": "Evaluate arithmetic like '38 - 24'.",
     "input_schema": {"type": "object", "properties": {"expression": {"type": "string"}}, "required": ["expression"]}},
]
RUN_TOOL = {"get_weather": get_weather, "calculator": calculator}


def cost(u) -> float:
    return (u.input_tokens * PRICE_IN + (u.cache_creation_input_tokens or 0) * PRICE_CACHE_WRITE
            + (u.cache_read_input_tokens or 0) * PRICE_CACHE_READ + u.output_tokens * PRICE_OUT) / 1e6


def traced_call(turn: int, messages: list):
    with tracer.span("llm", f"turn {turn}", model=MODEL, n_messages=len(messages)) as span:
        response = client.messages.create(
            model=MODEL, max_tokens=4000, output_config={"effort": "low"}, tools=TOOLS, messages=messages,
        )
        u = response.usage
        span.update({
            "request_id": response._request_id,
            "stop_reason": response.stop_reason,
            "input_tokens": u.input_tokens,
            "cache_read_tokens": u.cache_read_input_tokens or 0,
            "cache_write_tokens": u.cache_creation_input_tokens or 0,
            "output_tokens": u.output_tokens,
            "cost_usd": round(cost(u), 6),
            "output": short([b.to_dict() for b in response.content]),
        })
        return response


def traced_tool(block) -> dict:
    with tracer.span("tool", block.name, input=short(block.input)) as span:
        try:
            output, is_error = RUN_TOOL[block.name](**block.input), False
        except Exception as e:
            output, is_error = f"Error: {e}", True
        span.update({"output": short(output), "is_error": is_error})
    return {"type": "tool_result", "tool_use_id": block.id, "content": output, "is_error": is_error}


def run_agent(question: str) -> str:
    with tracer.trace("weather_agent", question) as trace_id:
        messages = [{"role": "user", "content": question}]
        for turn in range(1, MAX_TOOL_TURNS + 1):
            response = traced_call(turn, messages)
            messages.append({"role": "assistant", "content": response.content})
            if response.stop_reason != "tool_use":
                answer = "".join(b.text for b in response.content if b.type == "text")
                tracer.write({"kind": "answer", "output": short(answer)})
                return f"{answer}\n   (trace {trace_id})"
            messages.append({"role": "user", "content": [traced_tool(b) for b in response.content if b.type == "tool_use"]})
        return "(stopped: too many tool turns)"


# ---------------------------------------------------------------------------
# DEMO 1: Run a few questions. Everything goes to the trace file.
# ---------------------------------------------------------------------------
def demo_run():
    heading("DEMO 1: run the agent with tracing on")
    for question in (
        "What's the weather in Chennai?",
        "How many degrees hotter is Delhi than Bengaluru?",
        "What's the weather in Shimla and Chennai?",  # Shimla -> tool error, visible in the trace
    ):
        print(f"\nQ: {question}\nA: {run_agent(question)}")
    print(f"\nTrace file: {tracer.path}")


# ---------------------------------------------------------------------------
# DEMO 2: A trace viewer. Rebuild each run from the JSONL file.
# ---------------------------------------------------------------------------
def demo_view():
    heading("DEMO 2: read the traces back")
    if not tracer.path.exists():
        print("No traces for today yet. Run demo 1 first.")
        return
    records = [json.loads(line) for line in tracer.path.read_text(encoding="utf-8").splitlines()]
    traces = {}
    for r in records:
        traces.setdefault(r["trace_id"], []).append(r)

    total_cost, errors = 0.0, 0
    for trace_id, spans in list(traces.items())[-5:]:  # the last 5 runs
        start = next((s for s in spans if s["kind"] == "trace_start"), {})
        end = next((s for s in spans if s["kind"] == "trace_end"), {})
        llm = [s for s in spans if s["kind"] == "llm"]
        tools = [s for s in spans if s["kind"] == "tool"]
        run_cost = sum(s.get("cost_usd", 0) for s in llm)
        total_cost += run_cost
        print(f"\ntrace {trace_id}  {start.get('input', '')[:50]!r}  {end.get('duration_s', '?')}s  ${run_cost:.4f}  {end.get('status', '?')}")
        for s in spans:
            if s["kind"] == "llm":
                print(f"   ├─ llm   {s['name']:<8} stop={s.get('stop_reason'):<9} in={s.get('input_tokens')} "
                      f"out={s.get('output_tokens')}  {s['duration_s']}s  req={s.get('request_id')}")
            elif s["kind"] == "tool":
                flag = "❌" if s.get("is_error") else "ok"
                errors += bool(s.get("is_error"))
                print(f"   ├─ tool  {s['name']}({s['input']}) {flag} -> {s['output'][:50]}")
        print(f"   └─ {len(llm)} LLM calls, {len(tools)} tool calls")

    slowest = max((r for r in records if r["kind"] == "llm"), key=lambda r: r["duration_s"], default=None)
    print(f"\nLast 5 runs: ${total_cost:.4f}, {errors} tool errors.")
    if slowest:
        print(f"Slowest LLM call today: {slowest['duration_s']}s (trace {slowest['trace_id']}, request {slowest.get('request_id')})")
    print(f"\nEach line in the file is JSON, so you can also search it:  grep '\"is_error\": true' {tracer.path}")


# ---------------------------------------------------------------------------
# Menu.
# ---------------------------------------------------------------------------
DEMOS = {"1": demo_run, "2": demo_view}

MENU = """
Pick a demo:
  1  Run the agent with tracing (3 questions)
  2  View today's traces      (free)
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
