"""
Rule Registry — load Python rule callables from DB method_path (Scrum 2).

Example method_path:
  transformation_rules.rules.TR_010_calculate_total.apply
"""

from __future__ import annotations

import importlib
from typing import Any, Callable

from sqlalchemy.orm import Session

from models.transformation_rules import (
    TransformationRule,
    TransformationRuleMethod,
    TransformationRuleParameter,
    TransformationRuleVersion,
)

ApplyFn = Callable[[dict, dict], dict]


class RuleNotFoundError(Exception):
    pass


class RuleInactiveError(Exception):
    """Rule exists in catalog but status is not active."""


class RuleLoadError(Exception):
    pass


def _split_method_path(method_path: str) -> tuple[str, str]:
    """
    Split 'package.module.function' into (module_path, function_name).
    """
    if "." not in method_path:
        raise RuleLoadError(f"Invalid method_path (no dot): {method_path}")
    module_path, function_name = method_path.rsplit(".", 1)
    if not module_path or not function_name:
        raise RuleLoadError(f"Invalid method_path: {method_path}")
    return module_path, function_name


def load_callable_from_path(method_path: str) -> ApplyFn:
    """Dynamically import and return the apply function for a method_path."""
    module_path, function_name = _split_method_path(method_path)
    try:
        module = importlib.import_module(module_path)
    except ImportError as e:
        raise RuleLoadError(f"Cannot import module '{module_path}': {e}") from e

    fn = getattr(module, function_name, None)
    if fn is None or not callable(fn):
        raise RuleLoadError(
            f"Function '{function_name}' not found in module '{module_path}'"
        )
    return fn


class RuleRegistry:
    """Resolve rule_code → callable + params from Transformation Rules DB."""

    def __init__(self, db: Session):
        self.db = db

    def get_rule(self, rule_code: str) -> TransformationRule:
        """Return an active rule, or raise not-found / inactive with clear messages."""
        rule = (
            self.db.query(TransformationRule)
            .filter(TransformationRule.rule_code == rule_code)
            .first()
        )
        if not rule:
            raise RuleNotFoundError(f"Rule not found: {rule_code}")
        if rule.status != "active":
            raise RuleInactiveError(
                f"Rule is inactive: {rule_code} (status={rule.status})"
            )
        return rule

    def get_active_version(self, rule_id: int) -> TransformationRuleVersion:
        version = (
            self.db.query(TransformationRuleVersion)
            .filter(
                TransformationRuleVersion.rule_id == rule_id,
                TransformationRuleVersion.status == "active",
            )
            .order_by(TransformationRuleVersion.version_id.desc())
            .first()
        )
        if not version:
            raise RuleNotFoundError(f"No active version for rule_id={rule_id}")
        return version

    def get_method(self, version_id: int) -> TransformationRuleMethod:
        method = (
            self.db.query(TransformationRuleMethod)
            .filter(TransformationRuleMethod.version_id == version_id)
            .first()
        )
        if not method:
            raise RuleNotFoundError(f"No method for version_id={version_id}")
        return method

    def get_params(self, method_id: int) -> dict[str, Any]:
        """Build params dict from transformation_rule_parameters."""
        rows = (
            self.db.query(TransformationRuleParameter)
            .filter(TransformationRuleParameter.method_id == method_id)
            .all()
        )
        params: dict[str, Any] = {}
        for row in rows:
            if row.default_value is not None:
                params[row.param_name] = row.default_value
            elif row.is_required == "Y":
                # required but no default — caller must supply later
                params[row.param_name] = None
        return params

    def get_callable(self, rule_code: str) -> ApplyFn:
        """Load apply() for rule_code using DB method_path (no hardcoding)."""
        rule = self.get_rule(rule_code)
        version = self.get_active_version(rule.rule_id)
        method = self.get_method(version.version_id)
        return load_callable_from_path(method.method_path)

    def resolve(self, rule_code: str) -> dict[str, Any]:
        """
        Full resolve for one rule:
          { rule, version, method, params, callable }
        """
        rule = self.get_rule(rule_code)
        version = self.get_active_version(rule.rule_id)
        method = self.get_method(version.version_id)
        params = self.get_params(method.method_id)
        fn = load_callable_from_path(method.method_path)
        return {
            "rule": rule,
            "version": version,
            "method": method,
            "params": params,
            "callable": fn,
        }
