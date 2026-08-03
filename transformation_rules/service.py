"""
Transformation Rules Service — orchestrates resolve + execute (Scrum 3 / 8 / 9).
"""

from __future__ import annotations

from typing import Any

from sqlalchemy.orm import Session

from transformation_rules.executor import RuleExecutor
from transformation_rules.resolver import RuleResolver
from transformation_rules.validation import (
    ParamValidationError,
    validate_input_data,
    validate_param_overrides,
    validate_pipeline_params,
)


class TransformationRulesService:
    def __init__(self, db: Session):
        self.db = db
        self.resolver = RuleResolver(db)
        self.executor = RuleExecutor()

    def _prepare_and_run(
        self,
        pipeline: list[dict[str, Any]],
        data: dict,
        param_overrides: dict[str, dict[str, Any]] | None,
    ) -> dict[str, Any]:
        validate_input_data(data)
        order = [item["rule_code"] for item in pipeline]
        validate_param_overrides(param_overrides, order)
        validate_pipeline_params(self.db, pipeline)
        return self.executor.execute(pipeline, data)

    def execute_rule(
        self,
        rule_code: str,
        data: dict,
        *,
        include_soft: bool = True,
        param_overrides: dict[str, dict[str, Any]] | None = None,
    ) -> dict[str, Any]:
        """
        Execute rule_code with all DB dependencies in topological order.

        Returns:
          {
            "requested_rule": "TR_010",
            "execution_order": ["TR_002", "TR_001", "TR_010"],
            "status": "success",
            "data": {...},
            "steps": [...]
          }
        """
        code = (rule_code or "").strip()
        if not code:
            raise ParamValidationError("rule_code must not be empty")

        pipeline = self.resolver.resolve_pipeline(
            code,
            include_soft=include_soft,
            param_overrides=param_overrides,
        )
        order = [item["rule_code"] for item in pipeline]
        result = self._prepare_and_run(pipeline, data, param_overrides)
        return {
            "requested_rule": code,
            "execution_order": order,
            "status": "success",
            "data": result["data"],
            "steps": result["steps"],
        }

    def execute_selected(
        self,
        rule_codes: list[str],
        data: dict,
        *,
        strict: bool = True,
        param_overrides: dict[str, dict[str, Any]] | None = None,
    ) -> dict[str, Any]:
        """
        Execute an agent-selected list of rules (Scrum 8 / 9).

        strict=True runs exactly the given codes in the given order.
        strict=False inserts missing hard dependencies before each selected rule.
        """
        requested = self.resolver.normalize_selected_codes(rule_codes)
        pipeline = self.resolver.resolve_selected_pipeline(
            requested,
            strict=strict,
            param_overrides=param_overrides,
        )
        order = [item["rule_code"] for item in pipeline]
        result = self._prepare_and_run(pipeline, data, param_overrides)
        return {
            "requested_rules": requested,
            "execution_order": order,
            "strict": strict,
            "status": "success",
            "data": result["data"],
            "steps": result["steps"],
        }
