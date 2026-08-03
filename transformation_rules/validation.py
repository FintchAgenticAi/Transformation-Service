"""
Pre-execution validation for agent / MCP payloads (Scrum 9).
"""

from __future__ import annotations

from typing import Any

from sqlalchemy.orm import Session

from models.transformation_rules import TransformationRuleParameter


class ParamValidationError(Exception):
    """Required params missing or overrides invalid."""

    def __init__(self, message: str, *, rule_code: str | None = None):
        self.rule_code = rule_code
        super().__init__(message)


def validate_param_overrides(
    param_overrides: dict[str, dict[str, Any]] | None,
    pipeline_codes: list[str],
) -> None:
    """Reject override keys that are not in the resolved execution pipeline."""
    if not param_overrides:
        return
    if not isinstance(param_overrides, dict):
        raise ParamValidationError("param_overrides must be an object/dict")

    allowed = set(pipeline_codes)
    for code, overrides in param_overrides.items():
        if code not in allowed:
            raise ParamValidationError(
                f"Unknown rule_code in param_overrides: {code}",
                rule_code=code,
            )
        if not isinstance(overrides, dict):
            raise ParamValidationError(
                f"param_overrides for {code} must be an object/dict",
                rule_code=code,
            )


def validate_pipeline_params(
    db: Session, pipeline: list[dict[str, Any]]
) -> None:
    """
    Ensure every required parameter has a non-empty value after defaults/overrides.
    """
    for item in pipeline:
        rule_code = item["rule_code"]
        method = item["method"]
        params = item.get("params") or {}

        rows = (
            db.query(TransformationRuleParameter)
            .filter(TransformationRuleParameter.method_id == method.method_id)
            .all()
        )
        for row in rows:
            if row.is_required != "Y":
                continue
            value = params.get(row.param_name)
            if value is None:
                raise ParamValidationError(
                    f"Missing required param '{row.param_name}' for rule {rule_code}",
                    rule_code=rule_code,
                )
            if isinstance(value, str) and value.strip() == "":
                raise ParamValidationError(
                    f"Required param '{row.param_name}' for rule {rule_code} is empty",
                    rule_code=rule_code,
                )


def validate_input_data(data: Any) -> None:
    if not isinstance(data, dict):
        raise ParamValidationError("data must be a JSON object")
