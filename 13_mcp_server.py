"""
Lesson 13 (part 1): Build your own MCP server.

KEY IDEA: MCP (Model Context Protocol) is a STANDARD PLUG for tools.
Until now our tools lived inside each agent script. With MCP, tools live in a
separate program (an MCP SERVER). Any MCP CLIENT can connect to it and use
its tools: our own agent (13_mcp_client.py), Claude Code, Claude Desktop,
and many other apps. Write the tool once, use it everywhere.

An MCP server can offer three things:
    TOOLS      functions the model can call          (@mcp.tool())
    RESOURCES  read-only data, addressed by a URI     (@mcp.resource("shop://policies"))
    PROMPTS    ready-made prompt templates            (@mcp.prompt())

Transports (how client and server talk):
    stdio             the client STARTS the server as a child process and talks
                      through stdin/stdout. Simple, local, no network. (used here)
    streamable-http   the server runs as a web service; clients connect by URL.
                      Use this to share a server with other people / machines.

This server wraps the shop database from lesson 6c (read-only).

IMPORTANT for stdio servers: never print() to stdout. stdout carries the
protocol messages; a stray print breaks the connection. Log to stderr.

Setup (one time):
    pip install mcp                 (this lesson uses mcp 2.x: MCPServer, not FastMCP)

You don't run this file yourself; a client starts it. To try it:
    python 13_mcp_client.py                       our own agent
    claude mcp add shop -- <full path to venv python> <full path to this file>
                                                  then ask Claude Code about the shop
    pip install "mcp[cli]" && mcp dev 13_mcp_server.py
                                                  the MCP Inspector: click tools in a web page
"""

import json
import sqlite3
import sys
from pathlib import Path
from typing import Literal

from mcp.server.mcpserver import MCPServer

DB_PATH = Path(__file__).resolve().parent / "lesson_data" / "shop.db"

mcp = MCPServer(
    name="shop",
    instructions="Tools for the sample shop: products, stock and orders. All data is read-only.",
)


def run_query(sql: str, params: tuple = ()) -> list[dict]:
    if not DB_PATH.exists():
        raise RuntimeError("shop.db not found. Run 06c_real_tools.py once to create it.")
    db = sqlite3.connect(f"file:{DB_PATH}?mode=ro", uri=True)  # read-only, as in lesson 6c
    db.row_factory = sqlite3.Row
    try:
        return [dict(row) for row in db.execute(sql, params).fetchall()]
    finally:
        db.close()


# ---------------------------------------------------------------------------
# TOOLS. Type hints + docstring become the tool's schema and description,
# like @beta_tool in lesson 11b. Our code builds the SQL, so the model can't
# run arbitrary queries: safer than a general query_database tool.
# ---------------------------------------------------------------------------
@mcp.tool()
def list_products(category: str | None = None) -> str:
    """List products with price (INR) and stock. Optionally filter by category
    (Clothing, Electronics, Grocery, Home)."""
    if category:
        rows = run_query("SELECT id, name, category, price_inr, stock FROM products WHERE category = ? COLLATE NOCASE", (category,))
    else:
        rows = run_query("SELECT id, name, category, price_inr, stock FROM products")
    return json.dumps(rows)


@mcp.tool()
def low_stock(threshold: int = 20) -> str:
    """Products whose stock is below the threshold, lowest first."""
    return json.dumps(run_query("SELECT name, stock FROM products WHERE stock < ? ORDER BY stock", (threshold,)))


@mcp.tool()
def sales_summary(group_by: Literal["category", "city", "product"] = "category") -> str:
    """Revenue (quantity x price, INR) and number of orders, grouped by 'category', 'city' or 'product'."""
    columns = {"category": "p.category", "city": "o.city", "product": "p.name"}
    if group_by not in columns:
        raise ValueError("group_by must be 'category', 'city' or 'product'.")
    col = columns[group_by]  # chosen from our own dict, never pasted from the input
    return json.dumps(run_query(
        f"SELECT {col} AS {group_by}, SUM(o.quantity * p.price_inr) AS revenue_inr, COUNT(*) AS orders "
        f"FROM orders o JOIN products p ON p.id = o.product_id GROUP BY {col} ORDER BY revenue_inr DESC"
    ))


# ---------------------------------------------------------------------------
# RESOURCE: read-only text the client can load into the context.
# ---------------------------------------------------------------------------
@mcp.resource("shop://policies")
def policies() -> str:
    """The shop's delivery and returns policy."""
    return (
        "Free delivery on orders of Rs 999 or more, otherwise Rs 49. "
        "Unopened items can be returned within 7 days. Refunds take 5 working days."
    )


# ---------------------------------------------------------------------------
# PROMPT: a reusable prompt template the client can fetch and send.
# ---------------------------------------------------------------------------
@mcp.prompt()
def weekly_report(audience: str = "shop owner") -> str:
    """A prompt asking for a short weekly sales report."""
    return (
        f"Write a short weekly sales report for the {audience}. Use the shop tools to get revenue by "
        "category and city, and list products low on stock. Under 120 words."
    )


if __name__ == "__main__":
    print("shop MCP server starting (stdio)", file=sys.stderr)  # stderr, never stdout
    mcp.run()  # default transport: stdio
