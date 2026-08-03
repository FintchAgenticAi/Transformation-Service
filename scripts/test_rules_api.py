"""
Scrum 4 + 5 + 6 + 8 + 9 smoke test using FastAPI TestClient.

Usage (venv active):
  python scripts/test_rules_api.py
"""

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from fastapi.testclient import TestClient

from main import app


def main() -> None:
    client = TestClient(app)

    # GET /rules (Scrum 5 catalog)
    r = client.get("/rules")
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["count"] >= 3
    assert body["status_filter"] == "active"
    codes = {item["rule_code"] for item in body["rules"]}
    assert {"TR_001", "TR_002", "TR_010"}.issubset(codes)

    by_code = {item["rule_code"]: item for item in body["rules"]}
    tr010 = by_code["TR_010"]
    assert tr010.get("method_path"), "list catalog must include method_path"
    assert tr010.get("version_no"), "list catalog must include version_no"
    assert isinstance(tr010.get("parameters"), list), "list catalog must include parameters"
    assert any(p.get("param_name") for p in tr010["parameters"]), "TR_010 should expose params"
    assert isinstance(tr010.get("tags"), list) and len(tr010["tags"]) >= 1, "TR_010 must have tags"
    tag_names = {t["tag_name"] for t in tr010["tags"]}
    assert "numeric" in tag_names or "silver-zone" in tag_names
    assert isinstance(tr010.get("usages"), list) and len(tr010["usages"]) >= 1
    print("OK GET /rules:", body["count"], "rules (params + tags + usages)")
    print("  TR_010 tags:", sorted(tag_names))

    # GET /rules?status=all
    r = client.get("/rules", params={"status": "all"})
    assert r.status_code == 200, r.text
    assert r.json()["status_filter"] == "all"
    print("OK GET /rules?status=all")

    # GET /rules?tag=numeric (Scrum 6)
    r = client.get("/rules", params={"tag": "numeric"})
    assert r.status_code == 200, r.text
    tagged = r.json()
    assert tagged["tag_filter"] == "numeric"
    assert tagged["count"] >= 1
    assert all(
        any(t["tag_name"] == "numeric" for t in item["tags"])
        for item in tagged["rules"]
    )
    print("OK GET /rules?tag=numeric:", tagged["count"], "rule(s)")

    # GET /rules?tag=text
    r = client.get("/rules", params={"tag": "text"})
    assert r.status_code == 200, r.text
    text_rules = {item["rule_code"] for item in r.json()["rules"]}
    assert {"TR_001", "TR_002"}.issubset(text_rules)
    print("OK GET /rules?tag=text:", sorted(text_rules))

    # GET /rules/TR_010
    r = client.get("/rules/TR_010")
    assert r.status_code == 200, r.text
    detail = r.json()
    assert detail["rule_code"] == "TR_010"
    assert detail["execution_order_preview"][-1] == "TR_010"
    assert detail["method_path"]
    assert detail.get("version_no")
    assert isinstance(detail.get("parameters"), list) and len(detail["parameters"]) >= 1
    assert isinstance(detail.get("params"), dict)
    assert isinstance(detail.get("tags"), list) and len(detail["tags"]) >= 1
    assert isinstance(detail.get("usages"), list) and len(detail["usages"]) >= 1
    print("OK GET /rules/TR_010 order:", detail["execution_order_preview"])
    print("  parameters:", [p["param_name"] for p in detail["parameters"]])
    print("  tags:", [t["tag_name"] for t in detail["tags"]])

    # POST /rules/execute
    payload = {
        "rule_code": "TR_010",
        "data": {"text": "  apple  ", "amount": 100, "tax": 10},
        "include_soft": True,
        "param_overrides": {
            "TR_001": {"column_name": "text"},
            "TR_002": {"column_name": "text"},
        },
    }
    r = client.post("/rules/execute", json=payload)
    assert r.status_code == 200, r.text
    result = r.json()
    assert result["status"] == "success"
    assert result["data"]["total"] == 110
    assert result["log_id"] is not None
    print("OK POST /rules/execute:", result["data"])
    print("  log_id:", result["log_id"])
    print("  execution_order:", result["execution_order"])

    # 404 for unknown rule
    r = client.get("/rules/TR_999")
    assert r.status_code == 404
    print("OK GET unknown rule -> 404")

    # POST /rules/execute-selected (Scrum 8) — exact agent order
    selected_payload = {
        "rule_codes": ["TR_002", "TR_001", "TR_010"],
        "data": {"text": "  mango  ", "amount": 50, "tax": 5},
        "param_overrides": {
            "TR_001": {"column_name": "text"},
            "TR_002": {"column_name": "text"},
        },
        "strict": True,
    }
    r = client.post("/rules/execute-selected", json=selected_payload)
    assert r.status_code == 200, r.text
    selected = r.json()
    assert selected["status"] == "success"
    assert selected["strict"] is True
    assert selected["requested_rules"] == ["TR_002", "TR_001", "TR_010"]
    assert selected["execution_order"] == ["TR_002", "TR_001", "TR_010"]
    assert selected["data"]["text"] == "MANGO"
    assert selected["data"]["total"] == 55
    assert selected["log_id"] is not None
    assert len(selected["steps"]) == 3
    print("OK POST /rules/execute-selected (strict):", selected["data"])
    print("  execution_order:", selected["execution_order"])
    print("  log_id:", selected["log_id"])

    # strict=false inserts hard deps (TR_002) before TR_010; soft TR_001 not auto-added
    r = client.post(
        "/rules/execute-selected",
        json={
            "rule_codes": ["TR_010"],
            "data": {"amount": 20, "tax": 3},
            "param_overrides": {"TR_002": {"column_name": "text"}},
            "strict": False,
        },
    )
    assert r.status_code == 200, r.text
    soft = r.json()
    assert soft["execution_order"][0] == "TR_002"
    assert soft["execution_order"][-1] == "TR_010"
    assert "TR_001" not in soft["execution_order"]
    assert soft["data"]["total"] == 23
    print("OK POST /rules/execute-selected (strict=false):", soft["execution_order"])

    # empty list -> 400
    r = client.post(
        "/rules/execute-selected",
        json={"rule_codes": [], "data": {"amount": 1, "tax": 1}},
    )
    assert r.status_code == 400, r.text
    print("OK POST /rules/execute-selected empty -> 400")

    # unknown code -> 404
    r = client.post(
        "/rules/execute-selected",
        json={"rule_codes": ["TR_999"], "data": {"amount": 1, "tax": 1}},
    )
    assert r.status_code == 404, r.text
    print("OK POST /rules/execute-selected unknown -> 404")

    # duplicate codes -> 400
    r = client.post(
        "/rules/execute-selected",
        json={
            "rule_codes": ["TR_002", "TR_002"],
            "data": {"text": "x"},
            "param_overrides": {"TR_002": {"column_name": "text"}},
        },
    )
    assert r.status_code == 400, r.text
    assert r.json()["detail"]["error"] == "duplicate_rule"
    print("OK POST /rules/execute-selected duplicate -> 400")

    # Scrum 9: missing required param -> 400 structured
    r = client.post(
        "/rules/execute-selected",
        json={
            "rule_codes": ["TR_002"],
            "data": {"text": "  hello  "},
            "strict": True,
        },
    )
    assert r.status_code == 400, r.text
    detail = r.json()["detail"]
    assert detail["error"] == "param_validation_failed"
    assert detail["failed_rule"] == "TR_002"
    assert "column_name" in detail["message"]
    print("OK missing required param -> 400", detail["error"])

    # Scrum 9: bad param_overrides key -> 400
    r = client.post(
        "/rules/execute-selected",
        json={
            "rule_codes": ["TR_010"],
            "data": {"amount": 1, "tax": 1},
            "param_overrides": {"TR_999": {"column_name": "text"}},
            "strict": True,
        },
    )
    assert r.status_code == 400, r.text
    assert r.json()["detail"]["error"] == "param_validation_failed"
    print("OK bad param_overrides -> 400")

    # Scrum 9: runtime failure includes per-step status
    r = client.post(
        "/rules/execute-selected",
        json={
            "rule_codes": ["TR_010"],
            "data": {"tax": 5},
            "strict": True,
        },
    )
    assert r.status_code == 400, r.text
    detail = r.json()["detail"]
    assert detail["error"] == "rule_execution_failed"
    assert detail["failed_rule"] == "TR_010"
    assert isinstance(detail.get("steps"), list) and len(detail["steps"]) >= 1
    assert detail["steps"][-1]["status"] == "failed"
    print("OK runtime failure steps:", detail["failed_rule"])

    # Scrum 9: GET /rules/logs
    r = client.get("/rules/logs", params={"limit": 10})
    assert r.status_code == 200, r.text
    logs_body = r.json()
    assert logs_body["count"] >= 1
    assert isinstance(logs_body["logs"], list)
    assert "log_id" in logs_body["logs"][0]
    print("OK GET /rules/logs:", logs_body["count"], "recent")

    r = client.get("/rules/logs", params={"status": "failed", "limit": 5})
    assert r.status_code == 200, r.text
    assert all(item["status"] == "failed" for item in r.json()["logs"])
    print("OK GET /rules/logs?status=failed")

    print()
    print("Scrum 4+5+6+8+9 PASSED - Hardening + logs API works.")
    print("Scrum 10 demo: python scripts/demo_agent_handshake.py")
    print("Swagger UI: http://127.0.0.1:8000/docs")


if __name__ == "__main__":
    main()
