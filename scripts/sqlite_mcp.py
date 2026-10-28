"""
Pure-Python, zero-dependency SQLite Model Context Protocol (MCP) server for Tradng-Ai.
Runs seamlessly on both Windows and Linux (including Oracle Cloud VMs).
"""

import json
import sqlite3
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_DB = ROOT / "data" / "trader.db"


def get_db_path():
    if len(sys.argv) > 1 and sys.argv[1]:
        p = Path(sys.argv[1])
        return p if p.is_absolute() else ROOT / p
    return DEFAULT_DB


def get_conn():
    db_path = get_db_path()
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(db_path), timeout=30.0)
    conn.row_factory = sqlite3.Row
    return conn


TOOLS = [
    {
        "name": "read_query",
        "description": "Execute a read-only SQL SELECT query against the Tradng-Ai SQLite database.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "The SQL SELECT query to execute"}
            },
            "required": ["query"],
        },
    },
    {
        "name": "list_tables",
        "description": "List all tables and views available in the Tradng-Ai SQLite database.",
        "inputSchema": {
            "type": "object",
            "properties": {},
        },
    },
    {
        "name": "describe_table",
        "description": "Get column definitions and schema for a specific table in Tradng-Ai.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "table_name": {"type": "string", "description": "Name of the table to inspect"}
            },
            "required": ["table_name"],
        },
    },
]


def handle_call_tool(name, arguments):
    conn = get_conn()
    try:
        if name == "read_query":
            query = arguments.get("query", "").strip()
            # Safety gate: read-only
            first_word = query.split()[0].upper() if query else ""
            if first_word not in ("SELECT", "PRAGMA", "EXPLAIN"):
                return {"isError": True, "content": [{"type": "text", "text": "Only read-only queries (SELECT, PRAGMA) are allowed."}]}
            
            cur = conn.cursor()
            cur.execute(query)
            rows = cur.fetchall()
            if not rows:
                return {"content": [{"type": "text", "text": "No rows returned."}]}
            
            cols = [col[0] for col in cur.description] if cur.description else []
            data = [dict(zip(cols, row)) for row in rows]
            return {"content": [{"type": "text", "text": json.dumps(data, default=str, indent=2)}]}

        elif name == "list_tables":
            cur = conn.cursor()
            cur.execute("SELECT type, name FROM sqlite_master WHERE type IN ('table', 'view') AND name NOT LIKE 'sqlite_%' ORDER BY name")
            tables = [dict(row) for row in cur.fetchall()]
            return {"content": [{"type": "text", "text": json.dumps(tables, indent=2)}]}

        elif name == "describe_table":
            table_name = arguments.get("table_name", "").strip()
            cur = conn.cursor()
            cur.execute(f"PRAGMA table_info({table_name})")
            columns = [dict(row) for row in cur.fetchall()]
            return {"content": [{"type": "text", "text": json.dumps(columns, indent=2)}]}

        else:
            return {"isError": True, "content": [{"type": "text", "text": f"Unknown tool: {name}"}]}
    finally:
        conn.close()


def main():
    while True:
        line = sys.stdin.readline()
        if not line:
            break
        line = line.strip()
        if not line:
            continue
        try:
            req = json.loads(line)
        except Exception:
            continue

        req_id = req.get("id")
        method = req.get("method")
        params = req.get("params", {})

        if method == "initialize":
            res = {
                "jsonrpc": "2.0",
                "id": req_id,
                "result": {
                    "protocolVersion": "2024-11-05",
                    "capabilities": {"tools": {}},
                    "serverInfo": {"name": "tradng-sqlite-mcp", "version": "1.0.0"},
                },
            }
        elif method == "notifications/initialized":
            continue
        elif method == "tools/list":
            res = {
                "jsonrpc": "2.0",
                "id": req_id,
                "result": {"tools": TOOLS},
            }
        elif method == "tools/call":
            tool_name = params.get("name")
            tool_args = params.get("arguments", {})
            try:
                call_res = handle_call_tool(tool_name, tool_args)
                res = {"jsonrpc": "2.0", "id": req_id, "result": call_res}
            except Exception as e:
                res = {
                    "jsonrpc": "2.0",
                    "id": req_id,
                    "result": {"isError": True, "content": [{"type": "text", "text": str(e)}]},
                }
        elif method == "ping":
            res = {"jsonrpc": "2.0", "id": req_id, "result": {}}
        else:
            if req_id is not None:
                res = {
                    "jsonrpc": "2.0",
                    "id": req_id,
                    "error": {"code": -32601, "message": f"Method {method} not found"},
                }
            else:
                continue

        sys.stdout.write(json.dumps(res) + "\n")
        sys.stdout.flush()


if __name__ == "__main__":
    main()
