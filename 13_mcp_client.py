"""
Lesson 13 (part 2): Use an MCP server from your own agent.

KEY IDEA: Our agent doesn't define the shop tools any more. It STARTS the
MCP server (13_mcp_server.py), ASKS it which tools it has, and gives those to
Claude. When Claude calls one, the call is forwarded to the server.

    our agent (MCP client) --stdio--> 13_mcp_server.py (MCP server)
        1. session.list_tools()    -> tool names + schemas
        2. convert them for the Claude API (async_mcp_tool)
        3. tool runner (lesson 11b) runs the loop; each tool call goes
           session.call_tool(...) -> server -> result back to Claude

The anthropic SDK has helpers that convert MCP things to API things
(pip install "anthropic[mcp]"; the plain `mcp` package is enough here):
    async_mcp_tool(tool, session)     MCP tool      -> runnable tool for the tool runner
    mcp_message(prompt_message)       MCP prompt    -> a message
    mcp_resource_to_content(resource) MCP resource  -> a content block

MCP is ASYNC (async/await). Lesson 17 explains async properly; here just
notice `async def`, `await` and `async with`.

Other ways to use MCP servers:
    - Claude Code:   claude mcp add shop -- <venv python> <path>/13_mcp_server.py
    - Remote servers (a URL): the API can connect for you, no client code:
          client.beta.messages.create(..., betas=["mcp-client-2025-11-20"],
              mcp_servers=[{"type": "url", "url": "https://.../mcp", "name": "x"}],
              tools=[{"type": "mcp_toolset", "mcp_server_name": "x"}])
    - Many ready-made servers exist (GitHub, Slack, Postgres, filesystem...):
      https://github.com/modelcontextprotocol/servers
      Only connect servers you trust: their tool descriptions and results go
      straight into Claude's context (see lesson 15b, prompt injection).

Run:
    python 13_mcp_client.py          (menu)
    python 13_mcp_client.py 1        (one demo)
"""

import asyncio
import os
import sys
from pathlib import Path

import anthropic
from anthropic.lib.tools.mcp import async_mcp_tool, mcp_message, mcp_resource_to_content
from dotenv import find_dotenv, load_dotenv
from mcp import ClientSession
from mcp.client.stdio import StdioServerParameters, stdio_client

MODEL = "claude-opus-5-5"
SERVER_SCRIPT = Path(__file__).resolve().parent / "13_mcp_server.py"

load_dotenv(find_dotenv())
api_key = os.getenv("ANTHROPIC_API_KEY")
if not api_key:
    raise SystemExit("ANTHROPIC_API_KEY not found. Add it to your .env file.")

client = None  # async client (MCP is async); made fresh per asyncio.run() in run_demo()

# Start the server with the SAME Python (our venv), so it finds the mcp package.
SERVER = StdioServerParameters(command=sys.executable, args=[str(SERVER_SCRIPT)])


def heading(title: str) -> None:
    print(f"\n{'=' * 70}\n{title}\n{'=' * 70}")


def answer_text(message) -> str:
    return "".join(b.text for b in message.content if b.type == "text").strip()


async def run_agent(session: ClientSession, messages: list) -> str:
    """Tool runner (lesson 11b) with the server's tools. Mirrors turns into `messages`."""
    tools = (await session.list_tools()).tools
    runner = client.beta.messages.tool_runner(
        model=MODEL,
        max_tokens=8000,
        output_config={"effort": "low"},
        tools=[async_mcp_tool(t, session) for t in tools],
        messages=messages,
    )
    last = None
    async for message in runner:
        last = message
        for block in message.content:
            if block.type == "tool_use":
                print(f"   🔌 MCP tool: {block.name}({block.input})")
        messages.append({"role": "assistant", "content": message.content})
        tool_response = await runner.generate_tool_call_response()
        if tool_response:
            messages.append(tool_response)
    return answer_text(last)


# ---------------------------------------------------------------------------
# DEMO 1: Connect, list what the server offers, ask one question.
# ---------------------------------------------------------------------------
async def demo_discover():
    heading("DEMO 1: connect to the server and use its tools")
    async with stdio_client(SERVER) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            print("Tools:", [t.name for t in (await session.list_tools()).tools])
            print("Resources:", [str(r.uri) for r in (await session.list_resources()).resources])
            print("Prompts:", [p.name for p in (await session.list_prompts()).prompts])

            question = "Which city brings in the most money, and is anything almost out of stock?"
            print(f"\nQ: {question}")
            answer = await run_agent(session, [{"role": "user", "content": question}])
            print(f"A: {answer}")


# ---------------------------------------------------------------------------
# DEMO 2: Use the server's PROMPT and RESOURCE too.
# ---------------------------------------------------------------------------
async def demo_prompt_resource():
    heading("DEMO 2: a prompt template + a resource from the server")
    async with stdio_client(SERVER) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()

            prompt = await session.get_prompt("weekly_report", {"audience": "shop owner"})
            policy = await session.read_resource("shop://policies")
            print(f"Prompt from server: {prompt.messages[0].content.text}\n")

            first = mcp_message(prompt.messages[0])  # -> {"role": "user", "content": [text block]}
            messages = [{
                "role": "user",
                "content": [
                    mcp_resource_to_content(policy),  # the policy text, as a document block
                    *first["content"],                # the prompt template's text
                    {"type": "text", "text": "End with one line reminding the owner of the free-delivery threshold."},
                ],
            }]
            print(await run_agent(session, messages))


# ---------------------------------------------------------------------------
# DEMO 3: Chat with the shop through MCP.
# ---------------------------------------------------------------------------
async def demo_chat():
    heading("DEMO 3: chat (tools come from the MCP server)")
    print("Ask about products, stock or sales. Type 'exit' to go back.\n")
    async with stdio_client(SERVER) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            messages = []
            while True:
                question = (await asyncio.to_thread(input, "You: ")).strip()
                if not question:
                    continue
                if question.lower() == "exit":
                    return
                messages.append({"role": "user", "content": question})
                print(f"Claude: {await run_agent(session, messages)}\n")


# ---------------------------------------------------------------------------
# Menu. An async client belongs to ONE event loop, and every asyncio.run()
# starts a new one, so each demo gets a fresh client (lesson 17).
# ---------------------------------------------------------------------------
async def run_demo(demo) -> None:
    global client
    async with anthropic.AsyncAnthropic(api_key=api_key) as client:
        await demo()


DEMOS = {"1": demo_discover, "2": demo_prompt_resource, "3": demo_chat}

MENU = """
Pick a demo:
  1  Connect, list, use the server's tools
  2  Use the server's prompt + resource
  3  Chat through MCP
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
