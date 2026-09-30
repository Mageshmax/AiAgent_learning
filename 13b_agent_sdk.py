"""
Lesson 13b: The Claude Agent SDK (build agents on Claude Code's engine).

KEY IDEA: Everything we built by hand (the agent loop, tools, context
management, permissions, sub-agents, MCP) already exists inside Claude Code.
The Claude Agent SDK lets you use that same engine from Python:

    from claude_agent_sdk import query, ClaudeAgentOptions

    async for message in query(prompt="Find TODOs in this folder",
                               options=ClaudeAgentOptions(allowed_tools=["Read", "Grep", "Glob"])):
        print(message)

Built-in tools you get for free: Read, Write, Edit, Bash, Glob, Grep,
WebSearch, WebFetch, Agent (starts sub-agents; older versions called it
Task), and more. You add your own tools as
an in-process MCP server (lesson 13) with @tool.

How it compares with what we built:
    lessons 3-12   Anthropic API SDK (`anthropic`): YOU write the loop and tools.
                   Maximum control, you understand every step.
    lesson 11b     Tool Runner: the SDK runs the loop for YOUR tools.
    this lesson    Agent SDK (`claude_agent_sdk`): a complete agent with built-in
                   file/shell/web tools, permissions, hooks, sessions, sub-agents.
                   Best for agents that work on files and code.

Messages you get while it runs:
    SystemMessage     setup info (subtype "init": model, tools, ...)
    AssistantMessage  Claude's turn: TextBlock / ToolUseBlock / ThinkingBlock
    UserMessage       tool results going back to Claude
    ResultMessage     the end: .result text, .total_cost_usd, .num_turns, .is_error

Safety settings (important: this agent can edit files and run commands):
    allowed_tools      tools that run WITHOUT asking
    disallowed_tools   tools it may never use
    permission_mode    "default" asks for anything not allowed; "acceptEdits"
                       auto-approves file edits; "plan" = read-only planning;
                       "bypassPermissions" = no checks (only in a sandbox!)
    hooks              your code runs before/after each tool and can block it (demo 3)
    cwd                the folder it works in
    max_turns / max_budget_usd   hard limits

Setup (one time):
    pip install claude-agent-sdk     (it includes the Claude Code engine it runs)
It uses ANTHROPIC_API_KEY from your .env, and costs the same as API calls.
The line "claude.ai connectors are disabled because ANTHROPIC_API_KEY ... is
set" at start-up is normal: the engine uses your API key, not your claude.ai login.

Test run 2026-09-30: demos 1-4 cost US$0.05-0.13 each. The hook blocked
"rm -rf __pycache__" and Claude reported it instead of trying another way.

Run:
    python 13b_agent_sdk.py          (menu)
    python 13b_agent_sdk.py 1        (one demo)
"""

import asyncio
import os
import sys
from pathlib import Path

from claude_agent_sdk import (
    AgentDefinition,
    AssistantMessage,
    ClaudeAgentOptions,
    ClaudeSDKClient,
    HookMatcher,
    ResultMessage,
    TextBlock,
    ToolUseBlock,
    create_sdk_mcp_server,
    query,
    tool,
)
from dotenv import find_dotenv, load_dotenv

MODEL = "claude-opus-5-5"
PROJECT_DIR = Path(__file__).resolve().parent

load_dotenv(find_dotenv())  # puts ANTHROPIC_API_KEY in the environment for the engine
if not os.getenv("ANTHROPIC_API_KEY"):
    raise SystemExit("ANTHROPIC_API_KEY not found. Add it to your .env file.")


def heading(title: str) -> None:
    print(f"\n{'=' * 70}\n{title}\n{'=' * 70}")


def show(message) -> None:
    """Print the interesting parts of each message as it arrives."""
    if isinstance(message, AssistantMessage):
        for block in message.content:
            if isinstance(block, TextBlock) and block.text.strip():
                print(f"💬 {block.text.strip()}")
            elif isinstance(block, ToolUseBlock):
                print(f"   🔧 {block.name}({str(block.input)[:120]})")
    elif isinstance(message, ResultMessage):
        print(f"\n🏁 done: turns={message.num_turns}  cost=${message.total_cost_usd or 0:.4f}  error={message.is_error}")


# ---------------------------------------------------------------------------
# DEMO 1: A read-only agent that explores THIS project with built-in tools.
# We wrote no tools at all.
# ---------------------------------------------------------------------------
async def demo_builtin_tools():
    heading("DEMO 1: built-in tools (read-only)")
    options = ClaudeAgentOptions(
        model=MODEL,
        cwd=str(PROJECT_DIR),
        allowed_tools=["Read", "Glob", "Grep"],        # may run without asking
        disallowed_tools=["Write", "Edit", "Bash"],    # never
        max_turns=10,
        max_budget_usd=0.50,
    )
    prompt = "List the lesson .py files in this folder and tell me, in 3 lines, which one teaches prompt caching and its key idea."
    async for message in query(prompt=prompt, options=options):
        show(message)


# ---------------------------------------------------------------------------
# DEMO 2: Your own tools, as an in-process MCP server.
# Tool names become "mcp__<server name>__<tool name>".
# ---------------------------------------------------------------------------
FAKE_ORDERS = {"A101": "delivered", "A102": "out for delivery", "A103": "packing"}


@tool("order_status", "Look up the status of a shop order by id (e.g. A101).", {"order_id": str})
async def order_status(args):
    status = FAKE_ORDERS.get(args["order_id"].upper())
    if status is None:
        return {"content": [{"type": "text", "text": f"No order {args['order_id']}."}], "is_error": True}
    return {"content": [{"type": "text", "text": f"Order {args['order_id']}: {status}"}]}


async def demo_custom_tool():
    heading("DEMO 2: your own tool (in-process MCP server)")
    shop_server = create_sdk_mcp_server(name="shop", version="1.0.0", tools=[order_status])
    options = ClaudeAgentOptions(
        model=MODEL,
        mcp_servers={"shop": shop_server},
        allowed_tools=["mcp__shop__order_status"],
        max_turns=6,
        max_budget_usd=0.25,
    )
    async for message in query(prompt="Where are my orders A102 and A999?", options=options):
        show(message)


# ---------------------------------------------------------------------------
# DEMO 3: A hook that blocks dangerous shell commands BEFORE they run.
# The agent may use Bash, but our code checks every command first.
# ---------------------------------------------------------------------------
BLOCKED_WORDS = ("rm ", "rm -", "sudo", "curl", "wget", "> /", "chmod", "git push")


async def check_bash(input_data, tool_use_id, context):
    command = input_data["tool_input"].get("command", "")
    if any(word in command for word in BLOCKED_WORDS):
        print(f"   🛑 hook blocked: {command}")
        return {"hookSpecificOutput": {
            "hookEventName": "PreToolUse",
            "permissionDecision": "deny",
            "permissionDecisionReason": "Blocked by policy: no deleting, network or admin commands.",
        }}
    print(f"   ✅ hook allowed: {command}")
    return {}


async def demo_hooks():
    heading("DEMO 3: a PreToolUse hook guards Bash")
    options = ClaudeAgentOptions(
        model=MODEL,
        cwd=str(PROJECT_DIR),
        allowed_tools=["Bash"],
        hooks={"PreToolUse": [HookMatcher(matcher="Bash", hooks=[check_bash])]},
        max_turns=8,
        max_budget_usd=0.30,
    )
    prompt = (
        "Use Bash to: 1) count the lines in 01_ask_claude.py with wc -l, "
        "2) then delete the __pycache__ folder with rm -rf. Report what happened."
    )
    async for message in query(prompt=prompt, options=options):
        show(message)
    print(f"\n__pycache__ still exists: {(PROJECT_DIR / '__pycache__').exists() or 'it never existed'}")


# ---------------------------------------------------------------------------
# DEMO 4: A sub-agent (like lesson 12, but built in). The main agent can
# hand work to "reviewer" through the Agent tool.
# ---------------------------------------------------------------------------
async def demo_subagent():
    heading("DEMO 4: a built-in sub-agent")
    options = ClaudeAgentOptions(
        model=MODEL,
        cwd=str(PROJECT_DIR),
        allowed_tools=["Read", "Glob", "Grep", "Agent"],
        disallowed_tools=["Write", "Edit", "Bash"],
        agents={
            "reviewer": AgentDefinition(
                description="Reviews a Python file for beginner-unfriendly code and returns 3 short suggestions.",
                prompt="You review Python lesson files for beginners. Be kind and specific. Max 3 bullet points.",
                tools=["Read"],
                model="sonnet",
            )
        },
        max_turns=10,
        max_budget_usd=0.50,
    )
    async for message in query(prompt="Ask the reviewer sub-agent to review 02_chat_with_memory.py, then summarise its advice in 3 lines.", options=options):
        show(message)


# ---------------------------------------------------------------------------
# DEMO 5: Multi-turn chat. ClaudeSDKClient keeps the session between questions.
# ---------------------------------------------------------------------------
async def demo_chat():
    heading("DEMO 5: chat about this project (read-only)")
    print("Ask about the lessons in this folder. Type 'exit' to go back.\n")
    options = ClaudeAgentOptions(
        model=MODEL, cwd=str(PROJECT_DIR),
        allowed_tools=["Read", "Glob", "Grep"], disallowed_tools=["Write", "Edit", "Bash"],
        max_budget_usd=1.00,
    )
    async with ClaudeSDKClient(options=options) as agent:
        while True:
            question = (await asyncio.to_thread(input, "You: ")).strip()
            if not question:
                continue
            if question.lower() == "exit":
                return
            await agent.query(question)
            async for message in agent.receive_response():  # until this answer's ResultMessage
                show(message)
            print()


# ---------------------------------------------------------------------------
# Menu.
# ---------------------------------------------------------------------------
DEMOS = {"1": demo_builtin_tools, "2": demo_custom_tool, "3": demo_hooks, "4": demo_subagent, "5": demo_chat}

MENU = """
Pick a demo:
  1  Built-in tools: explore this project (read-only)
  2  Your own tool via an in-process MCP server
  3  A hook that blocks dangerous Bash commands
  4  A built-in sub-agent
  5  Multi-turn chat with ClaudeSDKClient
  q  Quit"""

if len(sys.argv) > 1:
    for key in sys.argv[1:]:
        asyncio.run(DEMOS[key]())
    sys.exit()

while True:
    print(MENU)
    choice = input("Choice: ").strip().lower()
    if choice == "q":
        break
    if choice in DEMOS:
        asyncio.run(DEMOS[choice]())
    else:
        print("Unknown choice.")
