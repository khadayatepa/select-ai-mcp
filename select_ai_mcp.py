"""
Select AI + SQLcl MCP + Oracle 26ai Autonomous Database — in ONE Python file.

What it does, end to end:
  1. Connects to your Autonomous Database through the SQLcl MCP Server (no password
     in code — it uses a saved SQLcl connection).
  2. Creates a tiny demo table so there's something to ask about.
  3. Sets up Select AI: a database CREDENTIAL holding your LLM key, and an AI PROFILE
     that points Select AI at your table.
  4. Asks ONE natural-language question and lets the database turn it into SQL and
     answer it — the LLM call happens *inside* Oracle via DBMS_CLOUD_AI.

Run:  python select_ai_mcp.py

Prereq (one-time, by your DB admin): allow the database to reach the LLM endpoint.
This script prints the exact grant if it's missing.
"""
from __future__ import annotations

import asyncio
import os
import sys

for _s in (sys.stdout, sys.stderr):  # Windows consoles default to cp1252
    try:
        _s.reconfigure(encoding="utf-8", errors="replace")  # type: ignore[union-attr]
    except Exception:
        pass

from dotenv import load_dotenv
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

load_dotenv()
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")
MODEL = os.getenv("SELECT_AI_MODEL", "gpt-4o")
CONNECTION = os.getenv("ORACLE_MCP_CONNECTION", "DEBATE")
SQLCL = os.getenv("SQLCL_COMMAND", "sql")
QUESTION = os.getenv("QUESTION", "What are the total sales by region?")
CRED = "OPENAI_CRED"
PROFILE = "SALES_AI"


def _text(result) -> str:
    return "\n".join(t for i in (result.content or []) if (t := getattr(i, "text", None)) is not None).strip()


class MCP:
    """Minimal SQLcl MCP client: connect once, run SQL."""

    def __init__(self, command: str, connection: str):
        self.command, self.connection = command, connection
        self._stack = None

    async def __aenter__(self):
        import contextlib
        self._stack = contextlib.AsyncExitStack()
        params = StdioServerParameters(command=self.command, args=["-mcp"], env=dict(os.environ))
        read, write = await self._stack.enter_async_context(stdio_client(params))
        self.s = await self._stack.enter_async_context(ClientSession(read, write))
        await self.s.initialize()
        meta = {"mcp_client": "select-ai-mcp/0.1", "model": MODEL}
        try:
            await self.s.call_tool("connect", {"connection_name": self.connection, **meta})
        except Exception:
            pass  # SQLcl 'connect' can throw yet still connect; verified by the first query
        self._meta = meta
        return self

    async def __aexit__(self, *exc):
        await self._stack.aclose()

    async def sql(self, statement: str) -> str:
        return _text(await self.s.call_tool("run-sql", {"sql": statement, **self._meta}))


SETUP_TABLE = [
    "BEGIN EXECUTE IMMEDIATE 'DROP TABLE sales CASCADE CONSTRAINTS'; EXCEPTION WHEN OTHERS THEN NULL; END;",
    "CREATE TABLE sales (region VARCHAR2(20), product VARCHAR2(30), amount NUMBER, sale_date DATE)",
    "INSERT ALL "
    "INTO sales VALUES ('West','Widget',1200,DATE '2026-01-10') "
    "INTO sales VALUES ('East','Gadget',900,DATE '2026-02-05') "
    "INTO sales VALUES ('West','Gadget',700,DATE '2026-02-20') "
    "INTO sales VALUES ('North','Widget',1500,DATE '2026-03-01') "
    "INTO sales VALUES ('East','Widget',1100,DATE '2026-03-12') SELECT 1 FROM DUAL",
    "COMMIT",
]


def credential_block(key: str) -> str:
    return ("BEGIN "
            f"BEGIN DBMS_CLOUD.DROP_CREDENTIAL('{CRED}'); EXCEPTION WHEN OTHERS THEN NULL; END; "
            f"DBMS_CLOUD.CREATE_CREDENTIAL(credential_name => '{CRED}', username => 'OPENAI', "
            f"password => '{key}'); END;")


def profile_block(owner: str) -> str:
    attrs = ('{"provider":"openai","credential_name":"' + CRED + '",'
             '"object_list":[{"owner":"' + owner + '","name":"SALES"}],'
             '"model":"' + MODEL + '"}')
    return ("BEGIN "
            f"BEGIN DBMS_CLOUD_AI.DROP_PROFILE('{PROFILE}'); EXCEPTION WHEN OTHERS THEN NULL; END; "
            f"DBMS_CLOUD_AI.CREATE_PROFILE(profile_name => '{PROFILE}', attributes => '{attrs}'); "
            f"DBMS_CLOUD_AI.SET_PROFILE('{PROFILE}'); END;")


def generate(prompt: str, action: str) -> str:
    p = prompt.replace("'", "''")
    return (f"SELECT DBMS_CLOUD_AI.GENERATE(prompt => '{p}', profile_name => '{PROFILE}', "
            f"action => '{action}') AS result FROM dual")


def _ok(out: str) -> bool:
    return "ORA-" not in out and "Error" not in out


async def main() -> None:
    print("\n=== Select AI + SQLcl MCP + Oracle 26ai ===\n")
    async with MCP(SQLCL, CONNECTION) as mcp:
        user = (await mcp.sql("SELECT USER FROM dual")).splitlines()[-1].strip().strip('"')
        print(f"Connected to Autonomous DB as {user} (via SQLcl MCP).\n")

        print("1) Creating a small demo table 'sales'...")
        for s in SETUP_TABLE:
            await mcp.sql(s)
        print("   ok\n")

        print("2) Creating the Select AI credential + profile...")
        if not OPENAI_API_KEY:
            print("   ! OPENAI_API_KEY is empty — set it in .env"); return
        c = await mcp.sql(credential_block(OPENAI_API_KEY))
        p = await mcp.sql(profile_block(user))
        print(f"   credential: {'ok' if _ok(c) else c.splitlines()[0]}")
        print(f"   profile:    {'ok' if _ok(p) else p.splitlines()[0]}\n")

        print(f"3) Asking Select AI:  \"{QUESTION}\"\n")
        showsql = await mcp.sql(generate(QUESTION, "showsql"))
        if "ORA-24247" in showsql:
            print("   ⚠ The database can't reach the LLM endpoint yet. One-time admin grant:\n")
            print("     -- run as ADMIN --")
            print("     BEGIN")
            print("       DBMS_NETWORK_ACL_ADMIN.APPEND_HOST_ACE(")
            print("         host => 'api.openai.com',")
            print("         ace  => xs$ace_type(privilege_list => xs$name_list('http'),")
            print(f"                            principal_name => '{user}',")
            print("                            principal_type => xs_acl.ptype_db));")
            print("     END;\n     /\n")
            print("   Then re-run this script.")
            return

        print("   Generated SQL:")
        print("   " + showsql.replace("\n", "\n   "))
        print("\n   Answer:")
        answer = await mcp.sql(generate(QUESTION, "runsql"))
        print("   " + answer.replace("\n", "\n   "))
        print("\n   In words:")
        narrate = await mcp.sql(generate(QUESTION, "narrate"))
        print("   " + narrate.replace("\n", "\n   "))


if __name__ == "__main__":
    asyncio.run(main())
