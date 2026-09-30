"""
Lesson 14: Evaluation (how do you KNOW your agent got better?).

KEY IDEA: Trying 2-3 questions by hand after every change is not testing.
Changing the prompt can fix one case and quietly break five others. An EVAL
is a fixed TEST SET plus automatic SCORING that you run after every change:

    test set          inputs + what a good answer must contain
    run               send every input through your app (same code as production)
    grade             score each output:
                        1. CODE checks   exact, free, instant (right label? JSON valid?)
                        2. LLM-AS-JUDGE  for things code can't check (polite? answers
                                         the question? invents facts?)
    compare           version A vs version B, case by case. Keep the winner.
    save              keep the results file, so you can see trends over time

Tips:
    - Start small (10-20 cases) with REAL examples, including the hard and
      weird ones. Add a case every time you find a bug.
    - Prefer code checks. Use a judge only where you need judgement, give it
      a clear RUBRIC, and ask for a reason before the verdict.
    - Don't judge with a weaker model than the one being judged.
    - Models are not fully deterministic: for small differences, run each
      case a few times (TRIALS) before believing the numbers.

The app under test: a support-ticket triage function for the shop. It reads a
customer message and returns JSON: category, urgency and a reply.
Version A has a one-line prompt; version B has a detailed one.

Results are saved to lesson_data/evals/.

Run:
    python 14_eval.py         (runs the eval: about 20 small calls per version)
"""

import json
import os
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from pathlib import Path

import anthropic
from dotenv import find_dotenv, load_dotenv

MODEL = "claude-opus-5-5"        # the app
JUDGE_MODEL = "claude-opus-5-5"  # the judge: at least as strong as the app
TRIALS = 1                       # raise to 3 to measure run-to-run variation

load_dotenv(find_dotenv())
api_key = os.getenv("ANTHROPIC_API_KEY")
if not api_key:
    raise SystemExit("ANTHROPIC_API_KEY not found. Add it to your .env file.")

client = anthropic.Anthropic(api_key=api_key)

RESULTS_DIR = Path(__file__).resolve().parent / "lesson_data" / "evals"

CATEGORIES = ["delivery", "refund", "product_question", "account", "complaint", "other"]
URGENCIES = ["low", "medium", "high"]

POLICY = (
    "Shop policy: same-day delivery in Chennai for orders before 2 pm; free delivery from Rs 999, else Rs 49. "
    "Unopened items can be returned within 7 days; opened food only if damaged or expired (photo within 48 hours). "
    "Refunds take 5 working days to the original payment method. Support: 7 am - 10 pm."
)

# ---------------------------------------------------------------------------
# STEP A: The test set. Each case: input, expected labels, and reply rules.
# ---------------------------------------------------------------------------
TEST_SET = [
    {"id": "late-order", "message": "My order from yesterday still hasn't arrived. Where is it??",
     "category": "delivery", "urgency": "medium", "must_mention": [], "rubric": "Apologises and says what the customer should do or what will happen next."},
    {"id": "refund-time", "message": "I returned the ghee last week. When will I get my money?",
     "category": "refund", "urgency": "low", "must_mention": ["5 working days"], "rubric": "Gives the refund timeline from the policy."},
    {"id": "opened-dal", "message": "Can I return an opened packet of dal? I just don't like it.",
     "category": "refund", "urgency": "low", "must_mention": [], "rubric": "Politely says no (opened food can't be returned unless damaged or expired)."},
    {"id": "spoiled-milk", "message": "The milk you delivered this morning is spoiled and my baby needs it NOW.",
     "category": "complaint", "urgency": "high", "must_mention": ["photo"], "rubric": "Urgent and empathetic; asks for a photo; offers a replacement or refund."},
    {"id": "free-delivery", "message": "Is delivery free if my cart is Rs 850?",
     "category": "delivery", "urgency": "low", "must_mention": ["49"], "rubric": "Says delivery costs Rs 49 because the cart is under Rs 999."},
    {"id": "password", "message": "I forgot my password and can't log in to the app.",
     "category": "account", "urgency": "medium", "must_mention": [], "rubric": "Gives a sensible next step (reset link or contact support) without asking for the password."},
    {"id": "organic", "message": "Do you have organic jaggery?",
     "category": "product_question", "urgency": "low", "must_mention": [], "rubric": "Does not invent stock or prices it doesn't know; offers to check or points to the app."},
    {"id": "tamil", "message": "என் ஆர்டர் இன்னும் வரவில்லை",  # "my order hasn't come yet"
     "category": "delivery", "urgency": "medium", "must_mention": [], "rubric": "Understands it's about a late order; replies helpfully (Tamil or English both fine)."},
    {"id": "angry", "message": "This is the THIRD time you sent the wrong rice. Useless shop. I want my money back.",
     "category": "complaint", "urgency": "high", "must_mention": [], "rubric": "Calm, apologetic, takes responsibility, offers a refund per policy; no blaming the customer."},
    {"id": "offtopic", "message": "Who will win the cricket match tonight?",
     "category": "other", "urgency": "low", "must_mention": [], "rubric": "Politely steers back to shop help; no predictions."},
]

# ---------------------------------------------------------------------------
# STEP B: The app, in two versions. Only the system prompt differs.
# ---------------------------------------------------------------------------
PROMPT_A = "You are a support assistant for Chennai Pantry. Triage the message and reply to the customer."

PROMPT_B = f"""You are the support assistant for Chennai Pantry, an online grocery shop in Chennai.

For every customer message, decide:
- category: delivery (late/missing/fees), refund (returns, money back, refund timing),
  product_question, account (login, app, profile), complaint (wrong, damaged or spoiled items,
  repeated problems, angry customers: complaint wins over refund when both apply), other.
- urgency: high = health/safety, spoiled food, very angry or repeated problem;
  medium = something is broken or late; low = general questions.
- reply: 2-4 sentences, warm and specific. Use ONLY the policy below for facts; never invent
  stock, prices or dates. For damaged/spoiled items, ask for a photo. For anything off-topic,
  politely steer back. Reply in the customer's language.

{POLICY}"""

SCHEMA = {
    "type": "object",
    "properties": {
        "category": {"type": "string", "enum": CATEGORIES},
        "urgency": {"type": "string", "enum": URGENCIES},
        "reply": {"type": "string"},
    },
    "required": ["category", "urgency", "reply"],
    "additionalProperties": False,
}


def triage(message: str, system_prompt: str) -> dict:
    """The function under test (the same code you'd use in the real app)."""
    response = client.messages.create(
        model=MODEL,
        max_tokens=2000,
        output_config={"effort": "low", "format": {"type": "json_schema", "schema": SCHEMA}},
        system=system_prompt + ("" if POLICY in system_prompt else f"\n\n{POLICY}"),
        messages=[{"role": "user", "content": message}],
    )
    return json.loads("".join(b.text for b in response.content if b.type == "text"))


# ---------------------------------------------------------------------------
# STEP C: Graders.
# ---------------------------------------------------------------------------
def code_grade(case: dict, output: dict) -> dict:
    missing = [m for m in case["must_mention"] if m.lower() not in output["reply"].lower()]
    return {
        "category_ok": output["category"] == case["category"],
        "urgency_ok": output["urgency"] == case["urgency"],
        "mentions_ok": not missing,
        "missing": missing,
    }


JUDGE_SCHEMA = {
    "type": "object",
    "properties": {
        "reason": {"type": "string", "description": "One or two sentences, BEFORE the verdict."},
        "passes": {"type": "boolean"},
    },
    "required": ["reason", "passes"],
    "additionalProperties": False,
}


def judge(case: dict, output: dict) -> dict:
    response = client.messages.create(
        model=JUDGE_MODEL,
        max_tokens=1000,
        output_config={"effort": "low", "format": {"type": "json_schema", "schema": JUDGE_SCHEMA}},
        messages=[{"role": "user", "content": (
            "You grade a customer-support reply. Be strict but fair.\n\n"
            f"{POLICY}\n\nCustomer message:\n{case['message']}\n\nReply to grade:\n{output['reply']}\n\n"
            f"Rubric (the reply passes only if it meets ALL of this): {case['rubric']}\n"
            "Also fail it if it states facts that contradict or go beyond the policy."
        )}],
    )
    return json.loads("".join(b.text for b in response.content if b.type == "text"))


# ---------------------------------------------------------------------------
# STEP D: Run one case (app + graders), then the whole suite in parallel.
# ---------------------------------------------------------------------------
def run_case(case: dict, system_prompt: str) -> dict:
    try:
        output = triage(case["message"], system_prompt)
    except Exception as e:  # a crash is a failed case, not a crashed eval
        return {"id": case["id"], "error": str(e), "passed": False}
    checks = code_grade(case, output)
    verdict = judge(case, output)
    passed = checks["category_ok"] and checks["urgency_ok"] and checks["mentions_ok"] and verdict["passes"]
    return {"id": case["id"], "output": output, **checks, "judge_passes": verdict["passes"],
            "judge_reason": verdict["reason"], "passed": passed}


def run_suite(name: str, system_prompt: str) -> list[dict]:
    started = time.time()
    jobs = [case for case in TEST_SET for _ in range(TRIALS)]
    with ThreadPoolExecutor(max_workers=5) as pool:  # lesson 17 explains parallel calls
        results = list(pool.map(lambda c: run_case(c, system_prompt), jobs))
    print(f"   {name}: {len(results)} runs in {time.time() - started:.0f}s")
    return results


def score(results: list[dict], key: str) -> str:
    ok = sum(1 for r in results if r.get(key))
    return f"{ok}/{len(results)}"


def main():
    print("Running the eval (each case: 1 app call + 1 judge call)...")
    suites = {"A (one-line prompt)": run_suite("A", PROMPT_A), "B (detailed prompt)": run_suite("B", PROMPT_B)}

    print(f"\n{'version':<22} {'category':>9} {'urgency':>8} {'mentions':>9} {'judge':>6} {'PASSED':>7}")
    for name, results in suites.items():
        print(f"{name:<22} {score(results, 'category_ok'):>9} {score(results, 'urgency_ok'):>8} "
              f"{score(results, 'mentions_ok'):>9} {score(results, 'judge_passes'):>6} {score(results, 'passed'):>7}")

    print("\nCase by case (A -> B):")
    a_results, b_results = suites.values()
    for a, b in zip(a_results, b_results):
        mark = lambda r: "✅" if r["passed"] else "❌"
        change = "  <- fixed by B" if b["passed"] and not a["passed"] else ("  <- BROKEN by B" if a["passed"] and not b["passed"] else "")
        print(f"   {a['id']:<14} {mark(a)} -> {mark(b)}{change}")
        for label, r in (("A", a), ("B", b)):
            if not r["passed"]:
                why = r.get("error") or (
                    f"got {r['output']['category']}/{r['output']['urgency']}"
                    + (f", missing {r['missing']}" if r["missing"] else "")
                    + ("" if r["judge_passes"] else f"; judge: {r['judge_reason']}")
                )
                print(f"        {label} failed: {why[:220]}")

    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    path = RESULTS_DIR / f"eval_{datetime.now():%Y%m%d_%H%M%S}.json"
    path.write_text(json.dumps({"model": MODEL, "trials": TRIALS, "suites": suites}, indent=2, ensure_ascii=False))
    print(f"\nSaved full results: {path}")


if __name__ == "__main__":
    main()
