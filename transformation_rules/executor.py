"""
Rule Executor — run resolved pipeline in dependency order (Scrum 3 / 9).
"""

from __future__ import annotations

from typing import Any


class RuleExecutionError(Exception):
    """Raised when a rule fails; carries per-step status for agent debugging."""

    def __init__(
        self,
        rule_code: str,
        message: str,
        *,
        steps: list[dict[str, Any]] | None = None,
        data: dict[str, Any] | None = None,
        execution_order: list[str] | None = None,
    ):
        self.rule_code = rule_code
        self.message = message
        self.steps = steps or []
        self.data = data or {}
        self.execution_order = execution_order or []
        super().__init__(f"[{rule_code}] {message}")


class RuleExecutor:
    def execute(
        self,
        pipeline: list[dict[str, Any]],
        data: dict,
    ) -> dict[str, Any]:
        """
        Run each rule's apply(data, params) in order.
        Returns:
          {
            "data": final_data,
            "steps": [{ rule_code, status, data_after }, ...]
          }
        """
        working = dict(data)
        steps: list[dict[str, Any]] = []
        order = [item["rule_code"] for item in pipeline]

        for item in pipeline:
            rule_code = item["rule_code"]
            fn = item["callable"]
            params = item["params"]
            try:
                working = fn(working, params)
                steps.append(
                    {
                        "rule_code": rule_code,
                        "status": "success",
                        "data_after": dict(working),
                    }
                )
            except Exception as e:
                steps.append(
                    {
                        "rule_code": rule_code,
                        "status": "failed",
                        "error": str(e),
                        "data_after": dict(working),
                    }
                )
                raise RuleExecutionError(
                    rule_code,
                    str(e),
                    steps=steps,
                    data=dict(working),
                    execution_order=order,
                ) from e

        return {"data": working, "steps": steps}
