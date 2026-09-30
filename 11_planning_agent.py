"""
Lesson 11: Agent patterns: ReAct, plan-and-execute, reflection.

KEY IDEA: The agent loop from lesson 3 is the engine. A PATTERN is how you
organise the thinking around it. Three classic ones:

    1. ReAct  (Reason + Act)
       Thought -> Action (tool call) -> Observation (tool result) -> Thought -> ...
       Decide the next step one at a time, based on what you just saw.
       Good for: exploring, when you can't know the steps in advance.
       Our loop from lesson 3 + thinking (lesson 7b) IS ReAct. Demo 1 just
       makes each part visible.

    2. Plan-and-execute
       PLAN:    one call writes the whole plan as a list of steps (JSON).
       EXECUTE: run each step with the tool loop, passing earlier results on.
       ANSWER:  one call combines the step results into the final answer.
       Good for: long tasks, when you want to SHOW or APPROVE the plan first,
       or run steps with cheaper models. Weak when step 3 reveals the plan was wrong
       (fix: re-plan when a step fails).

    3. Reflection (self-critique)
       DRAFT -> CRITIQUE against a checklist -> REVISE -> critique again ...
       Good for: writing, code, anything with clear rules to check.
       Best with a mix of CODE checks (word count, tests) and an LLM critic.
       Always put a cap on rounds.

The tasks use the sample shop database from lesson 6c (lesson_data/shop.db),
opened read-only.

Run:
    python 11_planning_agent.py        (menu)
    python 11_planning_agent.py 2      (one demo)
"""

import json
import os
import sqlite3
import sys
from pathlib import Path

import anthropic
from dotenv import find_dotenv, load_dotenv

MODEL = "claude-opus-5-5"
MAX_TOOL_TURNS = 10
MAX_REFLECTION_ROUNDS = 3

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


# ---------------------------------------------------------------------------
# Tools (read-only SQL + calculator, as in lessons 6c and 3).
# ---------------------------------------------------------------------------
def query_database(sql: str) -> str:
    if not sql.strip().lower().startswith(("select", "with")):
        raise PermissionError("Only SELECT queries are allowed.")
    db = sqlite3.connect(f"file:{DB_PATH}?mode=ro", uri=True)
    try:
        cursor = db.execute(sql)
        columns = [c[0] for c in cursor.description]
        rows = cursor.fetchmany(30)
    except sqlite3.Error as e:
        raise ValueError(f"SQL error: {e}")
    finally:
        db.close()
    return json.dumps({"columns": columns, "rows": rows})


def calculator(expression: str) -> str:
    if not set(expression) <= set("0123456789+-*/(). "):
        raise ValueError("Only numbers and + - * / ( ) are allowed.")
    return str(round(eval(expression, {"__builtins__": {}}), 4))


TOOLS = [
    {
        "name": "query_database",
        "description": (
            "Run ONE read-only SQLite SELECT on the shop database. Tables: "
            "products(id, name, category, price_inr, stock), "
            "orders(id, product_id -> products.id, quantity, order_date 'YYYY-MM-DD', city). "
            "Revenue of an order = quantity * price_inr. Returns at most 30 rows as JSON."
        ),
        "strict": True,
        "input_schema": {
            "type": "object",
            "properties": {"sql": {"type": "string"}},
            "required": ["sql"],
            "additionalProperties": False,
        },
    },
    {
        "name": "calculator",
        "description": "Evaluate arithmetic, e.g. '1250 / 8400 * 100'. Use it for every calculation.",
        "strict": True,
        "input_schema": {
            "type": "object",
            "properties": {"expression": {"type": "string"}},
            "required": ["expression"],
            "additionalProperties": False,
        },
    },
]
RUN_TOOL = {"query_database": query_database, "calculator": calculator}


def run_tool_block(block) -> dict:
    try:
        output, is_error = RUN_TOOL[block.name](**block.input), False
    except Exception as e:
        output, is_error = f"Error: {e}", True
    return {"type": "tool_result", "tool_use_id": block.id, "content": output, "is_error": is_error}


def tool_loop(system: str, messages: list, show_trace: bool = True) -> str:
    """The lesson-3 loop, printing Thought / Action / Observation."""
    for _ in range(MAX_TOOL_TURNS):
        response = client.messages.create(
            model=MODEL,
            max_tokens=16000,
            thinking={"type": "adaptive", "display": "summarized"},  # makes the "Thought" visible
            output_config={"effort": "medium"},
            system=system,
            tools=TOOLS,
            messages=messages,
        )
        messages.append({"role": "assistant", "content": response.content})
        results = []
        for block in response.content:
            if block.type == "thinking" and block.thinking and show_trace:
                print(f"   💭 Thought: {block.thinking.strip()[:300]}")
            elif block.type == "tool_use":
                result = run_tool_block(block)
                results.append(result)
                if show_trace:
                    print(f"   🔧 Action: {block.name}({json.dumps(block.input)[:200]})")
                    print(f"   👀 Observation: {result['content'][:200]}")
        if response.stop_reason != "tool_use":
            return answer_text(response)
        messages.append({"role": "user", "content": results})
    return "(stopped: too many tool turns)"


QUESTION = (
    "Which product category earned the most revenue overall, what percentage of total revenue is that, "
    "and which city spent the most on that category?"
)


# ---------------------------------------------------------------------------
# DEMO 1: ReAct. One loop, decide as you go.
# ---------------------------------------------------------------------------
def demo_react():
    heading("DEMO 1: ReAct (think -> act -> observe -> repeat)")
    print(f"Task: {QUESTION}\n")
    system = "You are a data analyst for a shop. Explore the database step by step with the tools. Be brief."
    answer = tool_loop(system, [{"role": "user", "content": QUESTION}])
    print(f"\n✅ Answer: {answer}")


# ---------------------------------------------------------------------------
# DEMO 2: Plan-and-execute.
# ---------------------------------------------------------------------------
PLAN_SCHEMA = {
    "type": "object",
    "properties": {
        "steps": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "id": {"type": "integer"},
                    "task": {"type": "string", "description": "One small, checkable step."},
                },
                "required": ["id", "task"],
                "additionalProperties": False,
            },
        }
    },
    "required": ["steps"],
    "additionalProperties": False,
}


def make_plan(goal: str) -> list[dict]:
    response = client.messages.create(
        model=MODEL,
        max_tokens=4000,
        output_config={"effort": "medium", "format": {"type": "json_schema", "schema": PLAN_SCHEMA}},
        system=(
            "You plan data-analysis tasks. Tools available later: query_database (read-only SQL on "
            + TOOLS[0]["description"].split("Tables: ")[1]
            + ") and calculator. Write 2-5 short steps. Don't run anything now."
        ),
        messages=[{"role": "user", "content": f"Goal: {goal}"}],
    )
    return json.loads(answer_text(response))["steps"]


def demo_plan_execute():
    heading("DEMO 2: plan-and-execute")
    print(f"Goal: {QUESTION}\n")

    # PLAN
    steps = make_plan(QUESTION)
    print("📋 Plan:")
    for s in steps:
        print(f"   {s['id']}. {s['task']}")
    if input("\nRun this plan? [Y/n] ").strip().lower() == "n":  # a human can check the plan first
        return

    # EXECUTE each step with its own short tool loop; results are passed forward.
    results = []
    for s in steps:
        print(f"\n▶ Step {s['id']}: {s['task']}")
        done_so_far = "\n".join(f"Step {r['id']} result: {r['result']}" for r in results) or "(none yet)"
        result = tool_loop(
            system="You carry out ONE step of a plan with the tools. Reply with only the result of this step, in 1-3 lines.",
            messages=[{"role": "user", "content": f"Overall goal: {QUESTION}\n\nEarlier results:\n{done_so_far}\n\nDo this step now: {s['task']}"}],
            show_trace=False,
        )
        print(f"   ✔ {result}")
        results.append({"id": s["id"], "result": result})

    # ANSWER
    response = client.messages.create(
        model=MODEL,
        max_tokens=2000,
        output_config={"effort": "low"},
        messages=[{"role": "user", "content": (
            f"Goal: {QUESTION}\n\nStep results:\n"
            + "\n".join(f"{r['id']}. {r['result']}" for r in results)
            + "\n\nWrite the final answer in 2-3 sentences."
        )}],
    )
    print(f"\n✅ Answer: {answer_text(response)}")


# ---------------------------------------------------------------------------
# DEMO 3: Reflection. Draft -> critique -> revise, with code checks + an LLM critic.
# ---------------------------------------------------------------------------
# The first draft is written from a quick, exciting request WITHOUT the rule
# list (like a real first draft that misses the style guide), so you can see
# the critique -> revise loop fix it. The checks know all the rules.
FIRST_REQUEST = (
    "Write an exciting product description for our 'Filter coffee powder 500g' (Rs 349) "
    "for the shop website. Reply with only the description."
)
BRIEF = (
    "Product description for 'Filter coffee powder 500g' (Rs 349) for the shop website. "
    "Rules: 40-60 words; mention the price in rupees; mention it is from Kumbakonam; "
    "no exaggerated words (best, perfect, amazing, ultimate); end with a call to action."
)
BANNED = ("best", "perfect", "amazing", "ultimate")

CRITIQUE_SCHEMA = {
    "type": "object",
    "properties": {
        "passes": {"type": "boolean"},
        "problems": {"type": "array", "items": {"type": "string"}},
    },
    "required": ["passes", "problems"],
    "additionalProperties": False,
}


def code_checks(text: str) -> list[str]:
    """Rules code can check exactly. Never ask an LLM to count words."""
    problems = []
    words = len(text.split())
    if not 40 <= words <= 60:
        problems.append(f"Has {words} words; must be 40-60.")
    for w in BANNED:
        if w in text.lower():
            problems.append(f"Uses the banned word '{w}'.")
    if "349" not in text:
        problems.append("Does not mention the price (Rs 349).")
    return problems


def llm_critique(text: str) -> list[str]:
    """Rules that need judgement."""
    response = client.messages.create(
        model=MODEL,
        max_tokens=2000,
        output_config={"effort": "low", "format": {"type": "json_schema", "schema": CRITIQUE_SCHEMA}},
        messages=[{"role": "user", "content": (
            f"Brief:\n{BRIEF}\n\nDraft:\n{text}\n\n"
            "Check ONLY: is Kumbakonam mentioned, does it end with a call to action, is it accurate "
            "and appealing without exaggeration? List concrete problems; passes=true if none."
        )}],
    )
    return json.loads(answer_text(response))["problems"]


def demo_reflection():
    heading("DEMO 3: reflection (draft -> critique -> revise)")
    print(f"First request: {FIRST_REQUEST}\nChecklist: {BRIEF}\n")
    messages = [{"role": "user", "content": FIRST_REQUEST}]
    for round_no in range(1, MAX_REFLECTION_ROUNDS + 1):
        response = client.messages.create(model=MODEL, max_tokens=2000, output_config={"effort": "low"}, messages=messages)
        draft = answer_text(response)
        messages.append({"role": "assistant", "content": draft})
        problems = code_checks(draft) + llm_critique(draft)
        print(f"--- Draft {round_no} ({len(draft.split())} words) ---\n{draft}")
        if not problems:
            print("\n✅ Passes every check.")
            return
        print("❌ Problems:\n   - " + "\n   - ".join(problems) + "\n")
        messages.append({"role": "user", "content": "Revise it to fix these problems:\n- " + "\n- ".join(problems) + "\nReply with only the description."})
    print(f"\n⚠️ Stopped after {MAX_REFLECTION_ROUNDS} rounds; a human should look at it.")


# ---------------------------------------------------------------------------
# Menu.
# ---------------------------------------------------------------------------
DEMOS = {"1": demo_react, "2": demo_plan_execute, "3": demo_reflection}

MENU = """
Pick a demo:
  1  ReAct              (think -> act -> observe)
  2  Plan-and-execute   (plan, approve, run each step, answer)
  3  Reflection         (draft -> critique -> revise)
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
