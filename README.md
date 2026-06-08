# Select AI + SQLcl MCP + Oracle 26ai Autonomous Database — in one Python file

Connect to your Autonomous Database through the **SQLcl MCP Server**, set up **Select AI**
(a database credential + an AI profile), and ask one question in **plain English** — the
database turns it into SQL and answers. The LLM call happens inside Oracle; your code never
touches the model. All in a single self-contained script: `select_ai_mcp.py`.

## What the script does
1. Opens an MCP session to the saved SQLcl connection (no password in code).
2. Creates a tiny `sales` demo table.
3. Creates a `DBMS_CLOUD.CREATE_CREDENTIAL` (your LLM key) + `DBMS_CLOUD_AI.CREATE_PROFILE`.
4. Asks `QUESTION` via `DBMS_CLOUD_AI.GENERATE` (showsql / runsql / narrate).

## Prerequisites
- Oracle 26ai **Autonomous Database**; **SQLcl 25.2+** with a saved connection
  (`conn -save DEBATE -savepwd <user>@<adb-tns-alias>`); Python 3.10+; an OpenAI key.
- **One-time admin grant** so the DB can reach the LLM endpoint (the script prints it):
  ```sql
  BEGIN
    DBMS_NETWORK_ACL_ADMIN.APPEND_HOST_ACE(
      host => 'api.openai.com',
      ace  => xs$ace_type(privilege_list => xs$name_list('http'),
                          principal_name => 'DEBATE', principal_type => xs_acl.ptype_db));
  END;
  /
  ```

## Run
```powershell
pip install -r requirements.txt
copy .env.example .env          # OPENAI_API_KEY + ORACLE_MCP_CONNECTION
python select_ai_mcp.py
```

> ⚠️ A learning demo. The OpenAI key is stored as a database credential in your own ADB.
