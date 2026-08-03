"""
Scrum 2 smoke test: Registry loads rules from DB method_path and runs apply().

Usage (from project root, with venv active):
  python scripts/test_rule_registry.py
"""

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from config.database import session_with_retry
from transformation_rules.registry import RuleRegistry


def main() -> None:
    db = session_with_retry(retries=3, delay_seconds=2.0)
    try:
        registry = RuleRegistry(db)

        # --- TR_002 Trim ---
        trim = registry.resolve("TR_002")
        trim_params = {**trim["params"], "column_name": "text"}
        after_trim = trim["callable"]({"text": "  hello  ", "amount": 100, "tax": 10}, trim_params)
        assert after_trim["text"] == "hello", after_trim
        print("OK TR_002 trim:", after_trim)

        # --- TR_001 Uppercase ---
        upper = registry.resolve("TR_001")
        upper_params = {**upper["params"], "column_name": "text"}
        after_upper = upper["callable"](after_trim, upper_params)
        assert after_upper["text"] == "HELLO", after_upper
        print("OK TR_001 uppercase:", after_upper)

        # --- TR_010 Calculate Total (A + B = C) ---
        calc = registry.resolve("TR_010")
        after_total = calc["callable"](after_upper, calc["params"])
        assert after_total["total"] == 110, after_total
        print("OK TR_010 calculate total:", after_total)

        print()
        print("Scrum 2 PASSED — Registry loaded all rules from DB method_path.")
        print("  TR_010 method_path:", calc["method"].method_path)
    finally:
        db.close()


if __name__ == "__main__":
    main()
