# Transformation Service Rules

Silver Zone Transformation Rules service (Scrums 1–6 + 8–10).

Your scope: **rule catalog + APIs + execute selected rules + logs**.  
Partner (Sunali) scope: **MCP tools + agent that selects rules** — or use the included **`mcp_server`** package (stdio) in this repo.

## Run

```powershell
.\venv\Scripts\Activate.ps1
python scripts/seed_transformation_rules.py
uvicorn main:app --reload
```

Swagger: http://127.0.0.1:8000/docs

## For MCP / Agent partner

Call these HTTP APIs only (no direct DB access).

### Base URL

`http://127.0.0.1:8000` (local) — replace with deployed host later.

### Integration flow

```text
Sunali MCP / agent                     Your Transformation Rules Service
---------------------------------      ---------------------------------
1. GET /rules                      →   return catalog (codes, params, tags)
2. Agent picks rule_codes
3. POST /rules/execute-selected    →   run exact list, log, return data
4. GET /rules/logs (optional)      →   debug recent runs together
```

### Suggested MCP tool mapping

| MCP tool | HTTP call |
|----------|-----------|
| `list_rules` | `GET /rules` |
| `get_rule` | `GET /rules/{rule_code}` |
| `execute_selected` | `POST /rules/execute-selected` |
| `list_logs` | `GET /rules/logs` |

---

### GET /rules

List rules for selection.

| Query param | Default | Values |
|-------------|---------|--------|
| `status` | `active` | `active`, `inactive`, `all` |
| `tag` | _(none)_ | e.g. `numeric`, `text` |

Example response (shape):

```json
{
  "count": 3,
  "status_filter": "active",
  "tag_filter": null,
  "rules": [
    {
      "rule_code": "TR_010",
      "rule_name": "Calculate Total",
      "description": "...",
      "status": "active",
      "version_no": "1.0",
      "method_path": "transformation_rules.rules.TR_010_calculate_total.apply",
      "dependencies": [
        { "depends_on_rule_code": "TR_002", "dependency_type": "hard" }
      ],
      "parameters": [
        {
          "param_name": "amount_field",
          "data_type": "string",
          "is_required": "Y",
          "default_value": "amount"
        }
      ],
      "tags": [{ "tag_name": "numeric" }],
      "usages": [{ "used_in_service": "Agent", "used_in_method": "POST /rules/execute-selected" }]
    }
  ]
}
```

### GET /rules/{rule_code}

Same catalog fields for one rule, plus:

- `execution_order_preview`
- `params` (resolved defaults)

### POST /rules/execute-selected (agent handshake)

Request:

```json
{
  "rule_ids": [2, 1, 3],
  "execution_order": [2, 1, 3],
  "data": { "text": "  apple  ", "amount": "100", "tax": "10" },
  "param_overrides": {
    "1": { "column_name": "text" },
    "2": { "column_name": "text" }
  },
  "strict": true
}
```

| Field | Meaning |
|-------|---------|
| `rule_ids` | Selected rules pool (`rule_id` from `GET /rules`) |
| `execution_order` | Rule IDs in the exact order they must run |
| `data` | One input record (row) to transform |
| `param_overrides` | Optional per-rule overrides (key by `rule_id` or `rule_code`) |
| `strict` | `true`: exact `execution_order`. `false`: insert missing hard deps |

Example success response (shape):

```json
{
  "request_id": "uuid...",
  "requested_rule_ids": [2, 1, 3],
  "execution_order_ids": [2, 1, 3],
  "requested_rules": ["TR_002", "TR_001", "TR_010"],
  "execution_order": ["TR_002", "TR_001", "TR_010"],
  "strict": true,
  "status": "success",
  "data": { "text": "APPLE", "amount": 100.0, "tax": 10.0, "total": 110.0 },
  "steps": [
    { "rule_id": 2, "rule_code": "TR_002", "status": "success", "attributes": [] },
    { "rule_id": 1, "rule_code": "TR_001", "status": "success", "attributes": [] },
    { "rule_id": 3, "rule_code": "TR_010", "status": "success", "attributes": [] }
  ],
  "log_id": 42
}
```

### POST /rules/execute

Demo / single-root mode: runs one rule plus its dependency graph.

### Hardening errors (Scrum 9)

```json
{
  "detail": {
    "error": "param_validation_failed",
    "message": "Missing required param 'column_name' for rule TR_002",
    "failed_rule": "TR_002",
    "request_id": "...",
    "log_id": 42
  }
}
```

| Case | HTTP | `detail.error` |
|------|------|----------------|
| Empty `rule_ids` / `execution_order` | `400` | `empty_selection` / `empty_execution_order` |
| `execution_order` not in `rule_ids` | `400` | `invalid_execution_order` |
| Duplicate rule IDs | `400` | `duplicate_rule` |
| Unknown rule | `404` | `rule_not_found` |
| Inactive rule | `400` | `inactive_rule` |
| Missing/bad params or overrides | `400` | `param_validation_failed` |
| Rule apply() failed | `400` | `rule_execution_failed` (+ `steps`) |

### GET /rules/logs

| Query param | Default | Notes |
|-------------|---------|--------|
| `limit` | `20` | 1–100 |
| `status` | _(none)_ | `success` / `failed` / `partial` |
| `rule_code` | _(none)_ | filter by linked rule |

Example: `GET /rules/logs?status=failed&limit=10`

---

## Handoff / demo (Scrum 10)

Prove your side **without MCP** (you act as the agent):

```powershell
python scripts/demo_agent_handshake.py
```

This runs: catalog → pick `TR_002/TR_001/TR_010` → execute-selected → logs.

Mentor checklist: [`docs/Scrum10_Mentor_Handoff_Checklist.md`](docs/Scrum10_Mentor_Handoff_Checklist.md)

### Smoke tests

```powershell
python scripts/test_rules_api.py
```

## Current sample rules

| Code | Name | Notes |
|------|------|--------|
| `TR_001` | Uppercase Text | text |
| `TR_002` | Trim Whitespace | text |
| `TR_010` | Calculate Total | numeric; hard dep on `TR_002`, soft dep on `TR_001` |

Larger real-dataset rule library (Scrum 7) can be added later without changing this handshake.

---

## MCP server (AI layer adapter)

Separate process that exposes your `/rules` APIs as **MCP tools** (stdio). Full guide: [`docs/MCP_Server.md`](docs/MCP_Server.md)

```powershell
# Terminal 1
uvicorn main:app --reload

# Terminal 2
pip install -r requirements.txt
python -m mcp_server
```

| MCP tool | REST API |
|----------|----------|
| `list_rules` | `GET /rules` |
| `get_rule` | `GET /rules/{rule_code}` |
| `execute_selected` | `POST /rules/execute-selected` |
| `execute_rule` | `POST /rules/execute` |
| `list_logs` | `GET /rules/logs` |

Env: `TRANSFORMATION_API_BASE_URL=http://127.0.0.1:8000`

Smoke test (HTTP client only, no Cursor):

```powershell
python scripts/test_mcp_api_client.py
```

Cursor config example: `docs/mcp_cursor_config.example.json`
