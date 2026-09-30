"""
Lesson 12: Multi-agent systems (an orchestrator + specialist sub-agents).

KEY IDEA: A sub-agent is just ANOTHER agent loop with its own system prompt,
its own tools and its OWN, FRESH `messages` list. The main agent (the
ORCHESTRATOR) calls it like a tool:

    orchestrator (claude-opus-5-5)
        |-- tool: ask_analyst(question)  -> sub-agent with the SQL tool
        |-- tool: ask_writer(brief)      -> sub-agent that only writes
        '-- tool: ask_reviewer(draft)    -> sub-agent that only checks

Why split one agent into several?
    - FOCUS: each sub-agent has a short, specific prompt and only the tools it needs.
    - CLEAN CONTEXT: the analyst may run 6 queries with big results, but only its
      short ANSWER goes back to the orchestrator. The orchestrator's context stays small.
    - PARALLEL: independent sub-tasks can run at the same time (demo 2).
    - CHEAPER: sub-agents doing narrow work can use a cheaper model
      (here claude-sonnet-5-5 at low effort; lesson 8d).
    - CHECKS: one agent reviews another's work (demo 3).

The costs: more calls (so more tokens), more moving parts to debug, and the
orchestrator only knows what sub-agents tell it. Use it when a single agent
gets confused or its context fills up, not by default.

Rules of thumb:
    - Give each sub-agent a COMPLETE task description: it can't see the
      orchestrator's conversation.
    - Ask sub-agents for SHORT, structured answers.
    - Put a limit on everything: turns per agent, review rounds, total calls.

The analyst uses the shop database from lesson 6c (read-only).

Run:
    python 12_multi_agent.py        (menu)
    python 12_multi_agent.py 1      (one demo)
"""

import json
import os
import sqlite3
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import anthropic
from dotenv import find_dotenv, load_dotenv

ORCHESTRATOR_MODEL = "claude-opus-5-5"
WORKER_MODEL = "claude-sonnet-5-5"  # cheaper model for the narrow sub-tasks
MAX_TOOL_TURNS = 8
MAX_REVIEW_ROUNDS = 3

load_dotenv(find_dotenv())
api_key = os.getenv("ANTHROPIC_API_KEY")
if not api_key:
    raise SystemExit("ANTHROPIC_API_KEY not found. Add it to your .env file.")

client = anthropic.Anthropic(api_key=api_key)

DB_PATH = Path(__file__).resolve().parent / "lesson_data" / "shop.db"
if not DB_PATH.exists():
    raise SystemExit("lesson_data/shop.db not found. Run 06c_real_tools.py once to create it.")


def heading(title: str) -> None:
    print(f"\n{'=' * 70}\n{title}\n{'=' * 70}")


def answer_text(response) -> str:
    return "".join(b.text for b in response.content if b.type == "text").strip()


def agent_loop(model, system, tools, run_tool, user_message, label, effort="low") -> str:
    """A complete agent (lesson 3 loop) with a FRESH history. Returns its final text."""
    messages = [{"role": "user", "content": user_message}]
    for _ in range(MAX_TOOL_TURNS):
        kwargs = {"tools": tools} if tools else {}
        response = client.messages.create(
            model=model, max_tokens=16000, output_config={"effort": effort},
            system=system, messages=messages, **kwargs,
        )
        messages.append({"role": "assistant", "content": response.content})
        if response.stop_reason != "tool_use":
            return answer_text(response)
        results = []
        for block in response.content:
            if block.type == "tool_use":
                print(f"      [{label}] 🔧 {block.name}({json.dumps(block.input)[:110]})")
                try:
                    output, is_error = run_tool(block.name, block.input), False
                except Exception as e:
                    output, is_error = f"Error: {e}", True
                results.append({"type": "tool_result", "tool_use_id": block.id, "content": output, "is_error": is_error})
        messages.append({"role": "user", "content": results})
    return f"({label} stopped: too many tool turns)"


# ---------------------------------------------------------------------------
# STEP A: The specialists.
# ---------------------------------------------------------------------------
def query_database(sql: str) -> str:
    if not sql.strip().lower().startswith(("select", "with")):
        raise PermissionError("Only SELECT queries are allowed.")
    db = sqlite3.connect(f"file:{DB_PATH}?mode=ro", uri=True)
    try:
        cursor = db.execute(sql)
        return json.dumps({"columns": [c[0] for c in cursor.description], "rows": cursor.fetchmany(30)})
    except sqlite3.Error as e:
        raise ValueError(f"SQL error: {e}")
    finally:
        db.close()


SQL_TOOL = [{
    "name": "query_database",
    "description": (
        "Run ONE read-only SQLite SELECT. Tables: products(id, name, category, price_inr, stock), "
        "orders(id, product_id -> products.id, quantity, order_date 'YYYY-MM-DD', city). "
        "Revenue = quantity * price_inr."
    ),
    "strict": True,
    "input_schema": {"type": "object", "properties": {"sql": {"type": "string"}}, "required": ["sql"], "additionalProperties": False},
}]


def ask_analyst(question: str) -> str:
    return agent_loop(
        WORKER_MODEL,
        "You are a data analyst. Answer the question with the database. Reply with the key numbers only, "
        "in at most 5 short lines. Never guess numbers.",
        SQL_TOOL, lambda name, args: query_database(**args), question, "analyst",
    )


def ask_writer(brief: str) -> str:
    return agent_loop(
        WORKER_MODEL,
        "You are a business writer for a small Indian shop. Write clear, friendly, plain English. "
        "Use only the facts you are given. Reply with only the text asked for.",
        None, None, brief, "writer",
    )


def ask_reviewer(draft: str, facts: str) -> str:
    return agent_loop(
        WORKER_MODEL,
        "You are a strict reviewer. Check the draft against the facts: every number must match the facts, "
        "nothing may be invented, and it must be under 120 words. Reply 'APPROVED' if it passes; otherwise "
        "reply 'CHANGES:' and a short numbered list of fixes.",
        None, None, f"FACTS:\n{facts}\n\nDRAFT:\n{draft}", "reviewer",
    )


# ---------------------------------------------------------------------------
# DEMO 1: The orchestrator uses the specialists as tools.
# ---------------------------------------------------------------------------
ORCHESTRATOR_TOOLS = [
    {
        "name": "ask_analyst",
        "description": "Ask the data analyst (who can query the shop database) ONE clear data question. Returns short numeric findings.",
        "strict": True,
        "input_schema": {"type": "object", "properties": {"question": {"type": "string"}}, "required": ["question"], "additionalProperties": False},
    },
    {
        "name": "ask_writer",
        "description": "Ask the writer to write text. Give a COMPLETE brief: audience, length, tone, and ALL facts to use (the writer can't see anything else).",
        "strict": True,
        "input_schema": {"type": "object", "properties": {"brief": {"type": "string"}}, "required": ["brief"], "additionalProperties": False},
    },
    {
        "name": "ask_reviewer",
        "description": "Ask the reviewer to check a draft against the facts. Returns APPROVED or a list of changes.",
        "strict": True,
        "input_schema": {
            "type": "object",
            "properties": {"draft": {"type": "string"}, "facts": {"type": "string"}},
            "required": ["draft", "facts"],
            "additionalProperties": False,
        },
    },
]
SPECIALISTS = {"ask_analyst": ask_analyst, "ask_writer": ask_writer, "ask_reviewer": ask_reviewer}


def run_specialist(name: str, args: dict) -> str:
    started = time.time()
    result = SPECIALISTS[name](**args)
    print(f"   ↩️  {name} answered in {time.time() - started:.1f}s: {result[:150]}{'...' if len(result) > 150 else ''}")
    return result


def demo_orchestrator():
    heading("DEMO 1: orchestrator + analyst / writer / reviewer")
    task = (
        "Write a short weekly update (under 120 words) for the shop owner: total revenue, "
        "the best category, the top city, and one product that is low on stock. Make sure it is reviewed."
    )
    print(f"Task: {task}\n")
    answer = agent_loop(
        ORCHESTRATOR_MODEL,
        "You are a manager who delegates. You have no data yourself: get numbers from the analyst, "
        "have the writer draft, have the reviewer check, and fix issues via the writer. "
        "When the reviewer approves, reply with the final text only.",
        ORCHESTRATOR_TOOLS, run_specialist, task, "orchestrator", effort="medium",
    )
    print(f"\n✅ Final update:\n{answer}")


# ---------------------------------------------------------------------------
# DEMO 2: Fan-out. Independent questions go to parallel analyst sub-agents;
# a final call combines their answers (map -> reduce).
# ---------------------------------------------------------------------------
def demo_parallel():
    heading("DEMO 2: parallel sub-agents (fan-out, then combine)")
    questions = [
        "What is total revenue per city?",
        "Which 3 products have the lowest stock?",
        "How many orders per category?",
    ]
    started = time.time()
    with ThreadPoolExecutor(max_workers=3) as pool:  # each sub-agent is independent, so run them together
        answers = list(pool.map(ask_analyst, questions))
    print(f"\n3 sub-agents finished in {time.time() - started:.1f}s (in parallel)\n")
    findings = "\n\n".join(f"Q: {q}\nA: {a}" for q, a in zip(questions, answers))
    print(findings)

    response = client.messages.create(
        model=ORCHESTRATOR_MODEL,
        max_tokens=2000,
        output_config={"effort": "low"},
        messages=[{"role": "user", "content": f"{findings}\n\nGive the shop owner 3 action points based on these findings. One line each."}],
    )
    print(f"\n✅ Combined advice:\n{answer_text(response)}")


# ---------------------------------------------------------------------------
# DEMO 3: Agents checking each other. The loop is in CODE (not an
# orchestrator), so it is predictable: writer -> reviewer -> writer ...
# ---------------------------------------------------------------------------
def demo_review_loop():
    heading("DEMO 3: writer and reviewer check each other")
    facts = ask_analyst("Total revenue, the top category by revenue, and the city with the most orders.")
    print(f"\nFacts from the analyst:\n{facts}\n")
    brief = f"Write a cheerful 2-sentence social media post for the shop using these facts:\n{facts}"
    draft = ask_writer(brief)
    for round_no in range(1, MAX_REVIEW_ROUNDS + 1):
        print(f"\n--- Draft {round_no} ---\n{draft}")
        verdict = ask_reviewer(draft, facts)
        print(f"🧐 Reviewer: {verdict}")
        if verdict.strip().upper().startswith("APPROVED"):
            print("\n✅ Approved.")
            return
        draft = ask_writer(f"{brief}\n\nYour previous draft:\n{draft}\n\nReviewer's requested changes:\n{verdict}\n\nRewrite it.")
    print(f"\n⚠️ Not approved after {MAX_REVIEW_ROUNDS} rounds: a human should decide.")


# ---------------------------------------------------------------------------
# Menu.
# ---------------------------------------------------------------------------
DEMOS = {"1": demo_orchestrator, "2": demo_parallel, "3": demo_review_loop}

MENU = """
Pick a demo:
  1  Orchestrator delegates to analyst / writer / reviewer
  2  Parallel sub-agents, then combine
  3  Writer and reviewer check each other
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
