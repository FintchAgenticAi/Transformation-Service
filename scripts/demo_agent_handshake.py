"""
Scrum 10 demo — prove your Transformation Rules service without MCP.

Flow (you play the agent):
  1) GET /rules              → catalog
  2) Pick 2–3 rule_codes
  3) POST /rules/execute-selected
  4) GET /rules/logs         → show recent log for the run

Usage (venv active, DB reachable):
  python scripts/demo_agent_handshake.py

Optional: start Swagger in another terminal for live mentor demo:
  uvicorn main:app --reload
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from fastapi.testclient import TestClient

from main import app


def _print_json(label: str, payload: object) -> None:
    print()
    print("=" * 60)
    print(label)
    print("=" * 60)
    print(json.dumps(payload, indent=2, default=str))


def main() -> None:
    client = TestClient(app)

    print("Scrum 10 - Agent handshake demo (no MCP required)")
    print("Service owns: catalog + execute-selected + logs")
    print("Partner owns: MCP tools + agent selection logic")

    # 1) Catalog
    r = client.get("/rules", params={"status": "active"})
    assert r.status_code == 200, r.text
    catalog = r.json()
    assert catalog["count"] >= 1, "Catalog is empty — run seed script first"
    codes = [item["rule_code"] for item in catalog["rules"]]
    _print_json(
        "1) GET /rules - catalog available to MCP",
        {
            "count": catalog["count"],
            "rule_codes": codes,
            "sample_rule": catalog["rules"][0],
        },
    )

    # 2) Manual selection (stand-in for Sunali's agent)
    selected = ["TR_002", "TR_001", "TR_010"]
    for code in selected:
        assert code in codes, f"Selected rule missing from catalog: {code}"
    print()
    print("2) Agent selection (manual stand-in):", selected)

    # 3) Execute selected
    payload = {
        "rule_codes": selected,
        "data": {"text": "  apple  ", "amount": 100, "tax": 10},
        "param_overrides": {
            "TR_001": {"column_name": "text"},
            "TR_002": {"column_name": "text"},
        },
        "strict": True,
    }
    r = client.post("/rules/execute-selected", json=payload)
    assert r.status_code == 200, r.text
    result = r.json()
    _print_json(
        "3) POST /rules/execute-selected - run selected rules",
        {
            "request_id": result["request_id"],
            "log_id": result["log_id"],
            "requested_rules": result["requested_rules"],
            "execution_order": result["execution_order"],
            "status": result["status"],
            "data": result["data"],
            "steps": [
                {"rule_code": s["rule_code"], "status": s["status"]}
                for s in result["steps"]
            ],
        },
    )
    assert result["status"] == "success"
    assert result["data"]["text"] == "APPLE"
    assert result["data"]["total"] == 110
    assert result["log_id"] is not None

    # 4) Logs
    r = client.get("/rules/logs", params={"limit": 5})
    assert r.status_code == 200, r.text
    logs = r.json()
    matching = [
        row
        for row in logs["logs"]
        if row.get("log_id") == result["log_id"]
        or row.get("request_id") == result["request_id"]
    ]
    _print_json(
        "4) GET /rules/logs - recent executions (debug with partner)",
        {
            "returned": logs["count"],
            "this_run": matching[0] if matching else logs["logs"][0],
        },
    )

    print()
    print("Scrum 10 DEMO PASSED")
    print("Mentor story: catalog ready -> selection executed -> logs visible.")
    print("Swagger UI: http://127.0.0.1:8000/docs")


if __name__ == "__main__":
    main()
