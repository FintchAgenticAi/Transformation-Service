# Transformation Rules MCP Server

Separate **MCP adapter** that exposes your existing FastAPI `/rules` APIs as MCP tools for the AI layer.

## Architecture

```text
AI host (Cursor / Claude)  --stdio MCP-->  mcp_server  --HTTP-->  FastAPI (main.py)
```

The MCP process does **not** connect to PostgreSQL. It only calls HTTP.

## Tools

| MCP tool | HTTP API |
|----------|----------|
| `list_rules` | `GET /rules` |
| `get_rule` | `GET /rules/{rule_code}` |
| `execute_selected` | `POST /rules/execute-selected` |
| `execute_rule` | `POST /rules/execute` |
| `list_logs` | `GET /rules/logs` |

## Run locally

Terminal 1 — API:

```powershell
cd C:\Users\HP\Desktop\ai-financial-platform
.\venv\Scripts\Activate.ps1
python scripts\seed_transformation_rules.py
uvicorn main:app --reload
```

Terminal 2 — MCP (stdio; used by Cursor):

```powershell
.\venv\Scripts\Activate.ps1
python -m mcp_server
```

## Environment

| Variable | Default | Meaning |
|----------|---------|---------|
| `TRANSFORMATION_API_BASE_URL` | `http://127.0.0.1:8000` | FastAPI base URL |
| `TRANSFORMATION_API_TIMEOUT` | `60` | HTTP timeout (seconds) |

## Cursor configuration

Copy `docs/mcp_cursor_config.example.json` into your Cursor MCP settings and fix paths to your machine.

Or in Cursor: **Settings → MCP → Add server**:

- Command: `...\venv\Scripts\python.exe`
- Args: `-m`, `mcp_server`
- Cwd: project root
- Env: `TRANSFORMATION_API_BASE_URL=http://127.0.0.1:8000`

## Example agent flow

1. `list_rules` → read `rule_id` for TR_002, TR_001, TR_010
2. `execute_selected` with `rule_codes_json`: `["TR_002","TR_001","TR_010"]` and `data_json` for one row
3. `list_logs` → verify `log_id`
