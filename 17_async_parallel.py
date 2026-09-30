"""
Lesson 17: Async and parallel tools (do independent work at the same time).

KEY IDEA: An API call or a web request is mostly WAITING (for the network,
for the model). While one call waits, Python could start the next one.

    one after another:   [call 1 ....][call 2 ....][call 3 ....]   = 3x the time
    at the same time:    [call 1 ....]
                         [call 2 ....]                               = about 1x
                         [call 3 ....]

Python's tool for this is asyncio:
    async def f(): ...          a function that can pause while it waits
    await something             "wait here, let other tasks run meanwhile"
    asyncio.gather(a, b, c)     run several at once, wait for all of them
    asyncio.Semaphore(3)        allow at most 3 at a time (stay under rate limits)
    asyncio.run(main())         start the async world from normal code

The SDK has an async client with the same methods:
    client = anthropic.AsyncAnthropic()
    response = await client.messages.create(...)

Where parallel helps an agent:
    1. Many INDEPENDENT questions (a batch of documents, several sub-agents)  (demos 1-2)
    2. PARALLEL TOOL CALLS: Claude often asks for several tools in ONE turn
       ("weather in Chennai AND Delhi AND Mumbai"). Run them together, then
       send ALL the results back in ONE user message                          (demo 3)

Only parallelise work that doesn't depend on each other. If step B needs
step A's result, B must wait.

(Lessons 12 and 14 used a thread pool (ThreadPoolExecutor) for the same
idea with the normal client. Threads are simpler to add to existing code;
asyncio scales better to many tasks.)

Run:
    python 17_async_parallel.py        (menu)
    python 17_async_parallel.py 1      (one demo)
"""

import asyncio
import os
import sys
import time

import anthropic
from dotenv import find_dotenv, load_dotenv

MODEL = "claude-opus-5-5"
MAX_CONCURRENT = 3

load_dotenv(find_dotenv())
api_key = os.getenv("ANTHROPIC_API_KEY")
if not api_key:
    raise SystemExit("ANTHROPIC_API_KEY not found. Add it to your .env file.")

sync_client = anthropic.Anthropic(api_key=api_key)
async_client = None  # made fresh for each asyncio.run() in run_demo(), see below


def heading(title: str) -> None:
    print(f"\n{'=' * 70}\n{title}\n{'=' * 70}")


def answer_text(response) -> str:
    return "".join(b.text for b in response.content if b.type == "text").strip()


QUESTIONS = [
    "In one sentence: what is a Python list?",
    "In one sentence: what is a Python dictionary?",
    "In one sentence: what is a Python tuple?",
    "In one sentence: what is a Python set?",
    "In one sentence: what is a Python generator?",
]
PARAMS = {"model": MODEL, "max_tokens": 1000, "output_config": {"effort": "low"}}


# ---------------------------------------------------------------------------
# DEMO 1: The same 5 questions, one after another vs all at once.
# ---------------------------------------------------------------------------
async def ask_async(question: str) -> str:
    response = await async_client.messages.create(**PARAMS, messages=[{"role": "user", "content": question}])
    return answer_text(response)


async def demo_sequential_vs_parallel():
    heading("DEMO 1: 5 questions, sequential vs parallel")

    started = time.perf_counter()
    for q in QUESTIONS:
        sync_client.messages.create(**PARAMS, messages=[{"role": "user", "content": q}])
    sequential = time.perf_counter() - started
    print(f"Sequential (normal client, a for loop): {sequential:5.1f}s")

    started = time.perf_counter()
    answers = await asyncio.gather(*(ask_async(q) for q in QUESTIONS))  # all 5 start now
    parallel = time.perf_counter() - started
    print(f"Parallel   (async client + gather):     {parallel:5.1f}s   ({sequential / parallel:.1f}x faster)\n")
    for q, a in zip(QUESTIONS, answers):  # gather keeps the ORDER of the inputs
        print(f"   {q.split(': ')[1]:<34} {a[:80]}")
    print("\nSame cost either way: parallel saves TIME, not tokens.")


# ---------------------------------------------------------------------------
# DEMO 2: A limit on how many run at once, and errors that don't sink the batch.
# ---------------------------------------------------------------------------
async def demo_semaphore():
    heading(f"DEMO 2: at most {MAX_CONCURRENT} at a time + error handling")
    limit = asyncio.Semaphore(MAX_CONCURRENT)
    running = 0

    async def limited_ask(i: int, question: str) -> str:
        nonlocal running
        async with limit:  # waits here if MAX_CONCURRENT calls are already running
            running += 1
            print(f"   start #{i}  (running now: {running})")
            try:
                if i == 3:  # one bad request, on purpose
                    await async_client.messages.create(model="claude-no-such-model", max_tokens=10,
                                                       messages=[{"role": "user", "content": question}])
                return await ask_async(question)
            finally:
                running -= 1
                print(f"   done  #{i}")

    results = await asyncio.gather(
        *(limited_ask(i, q) for i, q in enumerate(QUESTIONS, start=1)),
        return_exceptions=True,  # a failure comes back as a value instead of cancelling the rest
    )
    print()
    for i, r in enumerate(results, start=1):
        if isinstance(r, Exception):
            print(f"   #{i} ❌ {type(r).__name__}: {str(r)[:70]}")
        else:
            print(f"   #{i} ✅ {r[:70]}")
    print("\nThe semaphore protects you from 429 rate-limit errors when you have hundreds of items.")


# ---------------------------------------------------------------------------
# DEMO 3: Parallel TOOL calls inside the agent loop.
# The tool is slow (a fake 2-second API call). Claude asks for 4 cities in
# one turn; we run the 4 calls together and return all results at once.
# ---------------------------------------------------------------------------
FAKE_WEATHER = {"chennai": 33, "delhi": 38, "mumbai": 30, "kolkata": 31, "bengaluru": 24}


async def slow_get_weather(city: str) -> str:
    await asyncio.sleep(2)  # pretend this is a slow web API (async-friendly wait)
    temp = FAKE_WEATHER.get(city.lower())
    if temp is None:
        raise ValueError(f"No data for {city}")
    return f"{temp}°C in {city}"


TOOLS = [{
    "name": "get_weather",
    "description": "Current temperature for ONE Indian city. Call it once per city; you may call it for several cities at once.",
    "input_schema": {"type": "object", "properties": {"city": {"type": "string"}}, "required": ["city"]},
}]


async def run_one_tool(block) -> dict:
    try:
        output, is_error = await slow_get_weather(**block.input), False
    except Exception as e:
        output, is_error = f"Error: {e}", True
    return {"type": "tool_result", "tool_use_id": block.id, "content": output, "is_error": is_error}


async def agent(question: str, parallel_tools: bool) -> str:
    messages = [{"role": "user", "content": question}]
    tool_time = 0.0
    for _ in range(8):
        response = await async_client.messages.create(**PARAMS, tools=TOOLS, messages=messages)
        messages.append({"role": "assistant", "content": response.content})
        if response.stop_reason != "tool_use":
            print(f"   time spent in tools: {tool_time:.1f}s")
            return answer_text(response)
        calls = [b for b in response.content if b.type == "tool_use"]
        print(f"   Claude asked for {len(calls)} tool calls in one turn: {[b.input['city'] for b in calls]}")
        started = time.perf_counter()
        if parallel_tools:
            results = await asyncio.gather(*(run_one_tool(b) for b in calls))
        else:
            results = [await run_one_tool(b) for b in calls]
        tool_time += time.perf_counter() - started
        # ALL results go back in ONE user message (splitting them teaches
        # Claude to stop making parallel calls).
        messages.append({"role": "user", "content": results})
    return "(stopped: too many turns)"


async def demo_parallel_tools():
    heading("DEMO 3: parallel tool calls in the agent loop")
    question = "What's the temperature in Chennai, Delhi, Mumbai and Kolkata? Which is hottest?"
    for parallel in (False, True):
        print(f"\n--- tools run {'IN PARALLEL' if parallel else 'one after another'} ---")
        started = time.perf_counter()
        answer = await agent(question, parallel_tools=parallel)
        print(f"   total: {time.perf_counter() - started:.1f}s\n   Claude: {answer[:200]}")


# ---------------------------------------------------------------------------
# Menu. RULE: an async client belongs to ONE event loop. Every asyncio.run()
# starts a new loop, so make a new client inside it and close it at the end
# (reusing one across asyncio.run() calls gives "Event loop is closed").
# ---------------------------------------------------------------------------
async def run_demo(demo) -> None:
    global async_client
    async with anthropic.AsyncAnthropic(api_key=api_key) as async_client:
        await demo()


DEMOS = {"1": demo_sequential_vs_parallel, "2": demo_semaphore, "3": demo_parallel_tools}

MENU = """
Pick a demo:
  1  Sequential vs parallel calls   (10 small calls)
  2  Concurrency limit + errors     (5 small calls)
  3  Parallel tool calls in a loop  (4 small calls)
  q  Quit"""

if len(sys.argv) > 1:
    for key in sys.argv[1:]:
        asyncio.run(run_demo(DEMOS[key]))
    sys.exit()

while True:
    print(MENU)
    choice = input("Choice: ").strip().lower()
    if choice == "q":
        break
    if choice in DEMOS:
        asyncio.run(run_demo(DEMOS[choice]))
    else:
        print("Unknown choice.")
