"""
Scrum 3 smoke test: dependency order + full pipeline execution.

Usage (venv active, from project root):
  python scripts/test_rule_execution.py
"""

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from config.database import session_with_retry
from transformation_rules.dependency import DependencyManager
from transformation_rules.service import TransformationRulesService


def main() -> None:
    db = session_with_retry(retries=3, delay_seconds=2.0)
    try:
        deps = DependencyManager(db)

        # 1) Dependency order for TR_010
        order = deps.resolve_order("TR_010", include_soft=True)
        print("Execution order (with soft):", order)
        assert order.index("TR_002") < order.index("TR_010")
        assert order.index("TR_001") < order.index("TR_010")
        assert order[-1] == "TR_010"
        print("OK dependency order")

        hard_only = deps.resolve_order("TR_010", include_soft=False)
        print("Execution order (hard only):", hard_only)
        assert "TR_002" in hard_only
        assert "TR_001" not in hard_only
        assert hard_only[-1] == "TR_010"
        print("OK hard-only order")

        # 2) Full service pipeline
        service = TransformationRulesService(db)
        result = service.execute_rule(
            "TR_010",
            data={"text": "  apple  ", "amount": 100, "tax": 10},
            include_soft=True,
            param_overrides={
                "TR_001": {"column_name": "text"},
                "TR_002": {"column_name": "text"},
            },
        )
        print("Pipeline result:", result)
        assert result["status"] == "success"
        assert result["data"]["total"] == 110
        assert result["data"]["text"] == "APPLE"  # trim then upper
        assert result["execution_order"][-1] == "TR_010"
        print()
        print("Scrum 3 PASSED — dependency resolve + executor pipeline works.")
    finally:
        db.close()


if __name__ == "__main__":
    main()
