"""
MCP server — exposes Transformation Rules REST APIs as MCP tools (stdio).

Start FastAPI first: uvicorn main:app --reload
Then: python -m mcp_server
"""

from __future__ import annotations

import json
from typing import Any

from mcp.server.fastmcp import FastMCP

from mcp_server.client import TransformationApiClient, TransformationApiError
from mcp_server.config import get_settings

INSTRUCTIONS = """
You are connected to the Silver Zone Transformation Rules service.

Workflow:
1. Call list_rules to discover rule_id, rule_code, parameters, tags, and dependencies.
2. Call get_rule for full detail on one rule (execution_order_preview, params).
3. Call execute_selected to transform one data record (one JSON row of attributes).
   - Preferred: rule_ids + execution_order (IDs from list_rules).
   - Legacy: rule_codes (ordered list; same order as execution).
4. Call list_logs to debug recent runs.

Data is one record (object), not a full table. Rules validate and transform attributes individually.
""".strip()

mcp = FastMCP(
    "transformation-rules",
    instructions=INSTRUCTIONS,
)


def _client() -> TransformationApiClient:
    settings = get_settings()
    return TransformationApiClient(
        settings.api_base_url,
        timeout_seconds=settings.request_timeout_seconds,
    )


def _json(data: Any) -> str:
    return json.dumps(data, indent=2, default=str)


@mcp.tool()
async def list_rules(status: str = "active", tag: str | None = None) -> str:
    """
    List transformation rules from the catalog.

    Args:
        status: active (default), inactive, or all
        tag: optional filter, e.g. numeric or text

    Returns rule_id, rule_code, parameters, dependencies, tags — use rule_id for execute_selected.
    """
    try:
        result = await _client().list_rules(status=status, tag=tag)
        return _json(result)
    except TransformationApiError as e:
        return _json({"error": str(e), "status_code": e.status_code, "body": e.body})


@mcp.tool()
async def get_rule(rule_code: str) -> str:
    """
    Get one rule by code (e.g. TR_010): parameters, dependencies, execution_order_preview.
    """
    try:
        result = await _client().get_rule(rule_code)
        return _json(result)
    except TransformationApiError as e:
        return _json({"error": str(e), "status_code": e.status_code, "body": e.body})


@mcp.tool()
async def execute_selected(
    data_json: str,
    rule_ids_json: str | None = None,
    execution_order_json: str | None = None,
    rule_codes_json: str | None = None,
    param_overrides_json: str | None = None,
    strict: bool = True,
) -> str:
    """
    Execute selected transformation rules on one data record.

    Args:
        data_json: JSON object — one row, e.g. {"text":"  apple  ","amount":"100","tax":"10"}
        rule_ids_json: JSON array of rule IDs from list_rules, e.g. [2,1,3]
        execution_order_json: JSON array of rule IDs in run order, e.g. [2,1,3]
        rule_codes_json: Legacy JSON array of codes in order, e.g. ["TR_002","TR_001","TR_010"]
        param_overrides_json: optional JSON object keyed by rule_id or rule_code
        strict: if true, run exact order; if false, insert missing hard dependencies

    Provide either (rule_ids + execution_order) OR rule_codes, not both.
    """
    try:
        data = json.loads(data_json)
        if not isinstance(data, dict):
            raise ValueError("data_json must be a JSON object")

        payload: dict[str, Any] = {"data": data, "strict": strict}

        if rule_codes_json:
            codes = json.loads(rule_codes_json)
            if not isinstance(codes, list):
                raise ValueError("rule_codes_json must be a JSON array")
            payload["rule_codes"] = codes
        else:
            if not rule_ids_json or not execution_order_json:
                raise ValueError(
                    "Provide rule_ids_json and execution_order_json, or rule_codes_json"
                )
            rule_ids = json.loads(rule_ids_json)
            execution_order = json.loads(execution_order_json)
            if not isinstance(rule_ids, list) or not isinstance(execution_order, list):
                raise ValueError("rule_ids and execution_order must be JSON arrays")
            payload["rule_ids"] = rule_ids
            payload["execution_order"] = execution_order

        if param_overrides_json:
            overrides = json.loads(param_overrides_json)
            if not isinstance(overrides, dict):
                raise ValueError("param_overrides_json must be a JSON object")
            payload["param_overrides"] = overrides

        result = await _client().execute_selected(payload)
        return _json(result)
    except (json.JSONDecodeError, ValueError) as e:
        return _json({"error": "invalid_input", "message": str(e)})
    except TransformationApiError as e:
        return _json({"error": str(e), "status_code": e.status_code, "body": e.body})


@mcp.tool()
async def execute_rule(
    rule_code: str,
    data_json: str,
    include_soft: bool = True,
    param_overrides_json: str | None = None,
) -> str:
    """
    Execute one root rule plus its dependency graph (POST /rules/execute).

    Args:
        rule_code: e.g. TR_010
        data_json: JSON object — one input record
        include_soft: include soft dependencies in pipeline order
        param_overrides_json: optional per-rule param overrides
    """
    try:
        data = json.loads(data_json)
        if not isinstance(data, dict):
            raise ValueError("data_json must be a JSON object")
        payload: dict[str, Any] = {
            "rule_code": rule_code.strip(),
            "data": data,
            "include_soft": include_soft,
        }
        if param_overrides_json:
            payload["param_overrides"] = json.loads(param_overrides_json)
        result = await _client().execute_rule(payload)
        return _json(result)
    except (json.JSONDecodeError, ValueError) as e:
        return _json({"error": "invalid_input", "message": str(e)})
    except TransformationApiError as e:
        return _json({"error": str(e), "status_code": e.status_code, "body": e.body})


@mcp.tool()
async def list_logs(
    limit: int = 20,
    status: str | None = None,
    rule_code: str | None = None,
) -> str:
    """List recent transformation execution logs (debugging)."""
    try:
        result = await _client().list_logs(
            limit=limit,
            status=status,
            rule_code=rule_code,
        )
        return _json(result)
    except TransformationApiError as e:
        return _json({"error": str(e), "status_code": e.status_code, "body": e.body})


def main() -> None:
    """Run MCP server on stdio (Cursor / Claude Desktop)."""
    mcp.run(transport="stdio")


if __name__ == "__main__":
    main()
