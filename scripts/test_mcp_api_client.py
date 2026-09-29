"""
Smoke test: MCP HTTP client (no MCP host required).

Requires: uvicorn main:app running.

Usage:
  python scripts/test_mcp_api_client.py
"""

import asyncio
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from mcp_server.client import TransformationApiClient
from mcp_server.config import get_settings


async def main() -> None:
    settings = get_settings()
    client = TransformationApiClient(
        settings.api_base_url,
        timeout_seconds=settings.request_timeout_seconds,
    )
    catalog = await client.list_rules(status="active")
    print("list_rules count:", catalog["count"])
    codes = {r["rule_code"]: r["rule_id"] for r in catalog["rules"]}
    assert "TR_010" in codes
    detail = await client.get_rule("TR_010")
    print("get_rule:", detail["rule_code"], detail.get("execution_order_preview"))
    result = await client.execute_selected(
        {
            "rule_codes": ["TR_002", "TR_001", "TR_010"],
            "data": {"text": "  apple  ", "amount": 100, "tax": 10},
            "param_overrides": {
                "TR_001": {"column_name": "text"},
                "TR_002": {"column_name": "text"},
            },
            "strict": True,
        }
    )
    assert result["data"]["text"] == "APPLE"
    print("execute_selected OK:", result["data"])
    print("MCP API client smoke test PASSED")


if __name__ == "__main__":
    asyncio.run(main())
