"""
Dependency Manager — resolve rule run order from DB graph (Scrum 3).

Uses transformation_rule_dependencies (no flat execution_order column).
"""

from __future__ import annotations

from collections import defaultdict, deque

from sqlalchemy.orm import Session

from models.transformation_rules import (
    TransformationRule,
    TransformationRuleDependency,
)


class DependencyError(Exception):
    pass


class DependencyManager:
    def __init__(self, db: Session):
        self.db = db

    def _rule_by_id(self, rule_id: int) -> TransformationRule | None:
        return (
            self.db.query(TransformationRule)
            .filter(TransformationRule.rule_id == rule_id)
            .first()
        )

    def _rule_by_code(self, rule_code: str) -> TransformationRule:
        rule = (
            self.db.query(TransformationRule)
            .filter(TransformationRule.rule_code == rule_code)
            .first()
        )
        if not rule:
            raise DependencyError(f"Rule not found: {rule_code}")
        if rule.status != "active":
            raise DependencyError(
                f"Rule is inactive: {rule_code} (status={rule.status})"
            )
        return rule

    def get_direct_dependencies(
        self,
        rule_id: int,
        *,
        include_soft: bool = True,
    ) -> list[TransformationRuleDependency]:
        q = self.db.query(TransformationRuleDependency).filter(
            TransformationRuleDependency.rule_id == rule_id
        )
        rows = q.all()
        if include_soft:
            return rows
        return [r for r in rows if r.dependency_type == "hard"]

    def collect_dependency_closure(
        self,
        rule_code: str,
        *,
        include_soft: bool = True,
    ) -> set[int]:
        """
        Return set of rule_ids that must be considered:
        target rule + all recursive prerequisites.
        """
        target = self._rule_by_code(rule_code)
        needed: set[int] = set()
        stack = [target.rule_id]

        while stack:
            current_id = stack.pop()
            if current_id in needed:
                continue
            needed.add(current_id)
            for dep in self.get_direct_dependencies(
                current_id, include_soft=include_soft
            ):
                parent = self._rule_by_id(dep.depends_on_rule_id)
                if not parent:
                    raise DependencyError(
                        f"Missing depends_on_rule_id={dep.depends_on_rule_id}"
                    )
                if parent.status != "active":
                    if dep.dependency_type == "hard":
                        raise DependencyError(
                            f"Hard dependency inactive: {parent.rule_code}"
                        )
                    continue
                if parent.rule_id not in needed:
                    stack.append(parent.rule_id)

        return needed

    def resolve_order(
        self,
        rule_code: str,
        *,
        include_soft: bool = True,
    ) -> list[str]:
        """
        Topological sort of dependency graph for rule_code.
        Parents (depends_on) run before the dependent rule.
        Returns ordered list of rule_code strings.
        """
        needed_ids = self.collect_dependency_closure(
            rule_code, include_soft=include_soft
        )

        # Build adjacency: parent -> children (parent must run first)
        # Edge: depends_on_rule_id  -->  rule_id
        children: dict[int, list[int]] = defaultdict(list)
        indegree: dict[int, int] = {rid: 0 for rid in needed_ids}

        deps = (
            self.db.query(TransformationRuleDependency)
            .filter(TransformationRuleDependency.rule_id.in_(needed_ids))
            .all()
        )
        for dep in deps:
            if dep.depends_on_rule_id not in needed_ids:
                continue
            if not include_soft and dep.dependency_type != "hard":
                continue
            # parent must come before child
            parent_id = dep.depends_on_rule_id
            child_id = dep.rule_id
            children[parent_id].append(child_id)
            indegree[child_id] += 1

        queue = deque(sorted([rid for rid, deg in indegree.items() if deg == 0]))
        ordered_ids: list[int] = []

        while queue:
            node = queue.popleft()
            ordered_ids.append(node)
            for child in sorted(children[node]):
                indegree[child] -= 1
                if indegree[child] == 0:
                    queue.append(child)

        if len(ordered_ids) != len(needed_ids):
            raise DependencyError(
                f"Circular dependency detected while resolving {rule_code}"
            )

        id_to_code = {
            r.rule_id: r.rule_code
            for r in self.db.query(TransformationRule)
            .filter(TransformationRule.rule_id.in_(ordered_ids))
            .all()
        }
        return [id_to_code[rid] for rid in ordered_ids]
