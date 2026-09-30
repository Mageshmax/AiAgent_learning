# Capstone: build a complete agent that solves a real problem

Every earlier lesson taught one piece. The capstone puts the pieces together in **one** agent that someone (you, your family, a friend's shop) would actually use. The goal isn't more features; it's a finished thing that works reliably, costs what you expect, and fails safely.

`starter_agent.py` in this folder is a small, runnable skeleton with a `TODO` wherever a lesson plugs in. Copy it to your own project folder and grow it.

## 1. Pick a problem (one sentence)

Choose something **you** understand and can test. Some ideas at the right size:

| Idea | Who uses it | Lessons it exercises |
|---|---|---|
| **Shop assistant** for a real small business: answers from their policy docs, looks up orders in a database, drafts replies a human approves | shop staff | RAG (10), real tools (6c), guardrails + approval (15), eval (14) |
| **Study buddy** for a course: reads your PDFs/notes, quizzes you, remembers what you got wrong | you | vision/PDF (7c), memory (9), structured output (7), caching (8b) |
| **Expense tracker**: reads photos of receipts, stores them in SQLite, answers "how much on food this month?" | your family | vision (7c), structured output (7), tools (6c), cost tracking (8c) |
| **Research digest**: every morning, searches the web for a topic you follow and emails you a cited summary | you | server tools (11c), batch or schedule (17b), prompt injection defence (15b) |
| **Code-review helper** for this repo: reads a diff, checks it against rules, suggests fixes | you | Agent SDK (13b), reflection (11), eval (14) |

Write it down: **"\_\_\_\_\_\_\_\_\_ helps \_\_\_\_\_\_\_\_\_ do \_\_\_\_\_\_\_\_\_ so that \_\_\_\_\_\_\_\_\_."**

## 2. Write the spec before any code

Answer these in a `SPEC.md` in your project:

1. **Users and inputs.** Who types what? Which files, databases or websites does the agent read?
2. **Tools.** List each tool: name, what it does, read or write, and **risk** (read / write / dangerous). Dangerous ones need approval (lesson 15).
3. **What must never happen.** Examples: refund more than paid, email outsiders, show another customer's data, make up prices. Each line becomes a code check **and** an eval case.
4. **Success test.** 10-20 real example inputs with what a good answer must contain (lesson 14). You will run these after every change.
5. **Budget.** Expected messages per day × cost per message (measure it with lesson 8c). Set a spending limit in the Anthropic Console.

## 3. Requirements checklist

Your capstone is "done" when every box is ticked.

**Core**
- [ ] Agent loop with a turn limit (lesson 3/4) or the Tool Runner (11b)
- [ ] A clear system prompt: role, rules, when to use each tool (5)
- [ ] At least 3 real tools, each doing one job with a strict schema (6b, 6c)
- [ ] Tool errors returned with `is_error`, API errors caught with retries (5, 6)
- [ ] `stop_reason` handled: `end_turn`, `tool_use`, `max_tokens`, `refusal` (6c, 15)

**Quality**
- [ ] Eval set of 10+ cases, run with one command, results saved (14)
- [ ] At least one change you **proved** better with the eval (prompt A vs B)
- [ ] Right model and effort chosen per task, backed by numbers (8d)

**Memory and cost**
- [ ] Long conversations handled: trimming, summary or compaction (8)
- [ ] Prompt caching on the fixed part of the prompt, verified with `cache_read_input_tokens` (8b)
- [ ] Cost per question known and logged (8c)

**Safety**
- [ ] Every write/dangerous tool checked in code (limits, ownership, allow-lists) (15)
- [ ] Human approval for anything that spends money, sends messages or deletes (15)
- [ ] Untrusted text (web, files, emails) treated as data; dangerous tools not given to the agent that reads it (15b)
- [ ] No secrets in code or git; `.env` ignored

**Operations**
- [ ] Every run traced: calls, tools, tokens, cost, request ids (16)
- [ ] Independent work done in parallel where it helps (17)
- [ ] Runs somewhere other than your terminal: a UI (chat_ui) or a deployed server (18)

**Optional stretch**
- [ ] RAG over your own documents (10) or long-term memory of facts (9)
- [ ] MCP server so Claude Code/Desktop can use your tools too (13)
- [ ] Multi-agent split, if a single agent gets confused (12)
- [ ] Nightly batch job at half price (17b)

## 4. Build it in milestones

Commit after each milestone. Don't start the next one until the current one works.

| # | Milestone | Done when |
|---|---|---|
| 1 | Spec + eval cases written | `SPEC.md` and `evals.py` with 10 cases exist; **no agent code yet** |
| 2 | Walking skeleton | `starter_agent.py` runs end to end with your tools returning fake data |
| 3 | Real tools | Tools hit the real database/files/API, with validation; eval runs |
| 4 | Make it good | Iterate on prompt, tools and model until the eval passes ≥ 90% |
| 5 | Make it safe | Guardrails + approval + injection tests added to the eval |
| 6 | Make it cheap and observable | Caching, cost log, traces; you know the cost per question |
| 7 | Ship it | A UI or deployed server; one real user tries it; you fix what they hit |

## 5. Write-up (for your portfolio)

When you finish, add a `README.md` to the project with:
- the problem and who it helps (with a screenshot or short demo GIF),
- an architecture sketch (which tools, which models, where data lives),
- eval results before/after your best improvement,
- cost per question and how you reduced it,
- what you would do next.

That write-up is often worth more to an employer or client than the code itself.
