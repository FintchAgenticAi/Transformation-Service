"""
Rule Resolver — build full executable plan for a requested rule (Scrum 3)
and for an agent-selected list (Scrum 8).
"""

from __future__ import annotations

from typing import Any

from sqlalchemy.orm import Session

from transformation_rules.dependency import DependencyError, DependencyManager
from transformation_rules.registry import (
    RuleInactiveError,
    RuleNotFoundError,
    RuleRegistry,
)


class SelectedRulesError(Exception):
    """Invalid selected rule list for execute-selected."""

    def __init__(self, message: str, *, error_code: str = "invalid_selection"):
        self.error_code = error_code
        super().__init__(message)


class RuleResolver:
    def __init__(self, db: Session):
        self.db = db
        self.registry = RuleRegistry(db)
        self.dependencies = DependencyManager(db)

    def _build_pipeline(
        self,
        order: list[str],
        param_overrides: dict[str, dict[str, Any]] | None = None,
    ) -> list[dict[str, Any]]:
        param_overrides = param_overrides or {}
        pipeline: list[dict[str, Any]] = []
        for code in order:
            resolved = self.registry.resolve(code)
            params = dict(resolved["params"])
            if code in param_overrides:
                params.update(param_overrides[code])
            pipeline.append(
                {
                    "rule_code": code,
                    "rule": resolved["rule"],
                    "version": resolved["version"],
                    "method": resolved["method"],
                    "params": params,
                    "callable": resolved["callable"],
                }
            )
        return pipeline

    def resolve_pipeline(
        self,
        rule_code: str,
        *,
        include_soft: bool = True,
        param_overrides: dict[str, dict[str, Any]] | None = None,
    ) -> list[dict[str, Any]]:
        """
        Return ordered list of resolved rule specs:
          [{ rule_code, rule, version, method, params, callable }, ...]
        """
        order = self.dependencies.resolve_order(
            rule_code, include_soft=include_soft
        )
        return self._build_pipeline(order, param_overrides)

    def normalize_selected_codes(self, rule_codes: list[str]) -> list[str]:
        """Normalize, reject empty/blank and duplicate codes."""
        if not rule_codes:
            raise SelectedRulesError(
                "rule_codes must not be empty", error_code="empty_selection"
            )

        normalized: list[str] = []
        seen: set[str] = set()
        for raw in rule_codes:
            code = (raw or "").strip()
            if not code:
                raise SelectedRulesError(
                    "rule_codes contains an empty value",
                    error_code="empty_selection",
                )
            if code in seen:
                raise SelectedRulesError(
                    f"Duplicate rule_code in selection: {code}",
                    error_code="duplicate_rule",
                )
            seen.add(code)
            normalized.append(code)
        return normalized

    def resolve_selected_order(
        self,
        rule_codes: list[str],
        *,
        strict: bool = True,
    ) -> list[str]:
        """
        Build execution order for an agent-selected list.

        strict=True  → run exactly the given codes in the given order
                       (no dependency auto-insert; agent already chose).
        strict=False → insert missing hard dependencies before each selected rule,
                       preserving selection order for the selected codes.
        """
        codes = self.normalize_selected_codes(rule_codes)

        # Validate every selected code exists and is active up front.
        for code in codes:
            try:
                self.registry.get_rule(code)
            except RuleInactiveError as e:
                raise SelectedRulesError(str(e), error_code="inactive_rule") from e
            except RuleNotFoundError as e:
                raise SelectedRulesError(str(e), error_code="rule_not_found") from e

        if strict:
            return codes

        order: list[str] = []
        seen: set[str] = set()
        for code in codes:
            try:
                hard_order = self.dependencies.resolve_order(
                    code, include_soft=False
                )
            except DependencyError as e:
                raise SelectedRulesError(str(e)) from e
            for dep_code in hard_order:
                if dep_code not in seen:
                    order.append(dep_code)
                    seen.add(dep_code)
        return order

    def resolve_selected_pipeline(
        self,
        rule_codes: list[str],
        *,
        strict: bool = True,
        param_overrides: dict[str, dict[str, Any]] | None = None,
    ) -> list[dict[str, Any]]:
        """Resolve callables/params for an agent-selected rule list (Scrum 8)."""
        order = self.resolve_selected_order(rule_codes, strict=strict)
        return self._build_pipeline(order, param_overrides)
