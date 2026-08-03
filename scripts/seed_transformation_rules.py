"""
Seed Transformation Rules sample metadata (Scrum 1 + Scrum 6 tags/usages).

Sample rules:
  TR_001 Uppercase Text
  TR_002 Trim Whitespace
  TR_010 Calculate Total  (depends on TR_002 hard, TR_001 soft)

Usage (from project root):
  python scripts/seed_transformation_rules.py
"""

import sys
from pathlib import Path

# Allow importing project packages when run as a script
ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from sqlalchemy.orm import Session

from config.database import session_with_retry, engine, Base, check_connection
from models.transformation_rules import (
    TransformationCategory,
    TransformationRule,
    TransformationRuleDependency,
    TransformationRuleVersion,
    TransformationRuleMethod,
    TransformationRuleParameter,
    TransformationRuleTag,
    TransformationRuleTagMap,
    TransformationRuleUsage,
)


def ensure_tables() -> None:
    import models.transformation_rules  # noqa: F401

    if not check_connection(retries=3, delay_seconds=2.0):
        raise RuntimeError("Database not reachable — cannot create tables")
    Base.metadata.create_all(bind=engine)


def _get_or_create_tag(db: Session, tag_name: str, description: str) -> TransformationRuleTag:
    tag = db.query(TransformationRuleTag).filter_by(tag_name=tag_name).first()
    if tag:
        return tag
    tag = TransformationRuleTag(tag_name=tag_name, description=description)
    db.add(tag)
    db.flush()
    return tag


def seed_tags_and_usages(db: Session) -> None:
    """Idempotent tags/usages for existing sample rules (Scrum 6)."""
    rules = {
        r.rule_code: r
        for r in db.query(TransformationRule)
        .filter(TransformationRule.rule_code.in_(["TR_001", "TR_002", "TR_010"]))
        .all()
    }
    if len(rules) < 3:
        print("Tags/usages seed skipped — sample rules not found yet.")
        return

    tag_silver = _get_or_create_tag(db, "silver-zone", "Used in Silver Zone")
    tag_dynamic = _get_or_create_tag(db, "dynamic", "Dynamically loadable rule")
    tag_text = _get_or_create_tag(db, "text", "Text transformation")
    tag_numeric = _get_or_create_tag(db, "numeric", "Numeric calculation")

    rule_tag_plan = {
        "TR_001": [tag_silver, tag_dynamic, tag_text],
        "TR_002": [tag_silver, tag_dynamic, tag_text],
        "TR_010": [tag_silver, tag_dynamic, tag_numeric],
    }
    for code, tags in rule_tag_plan.items():
        rule = rules[code]
        for tag in tags:
            exists = (
                db.query(TransformationRuleTagMap)
                .filter_by(rule_id=rule.rule_id, tag_id=tag.tag_id)
                .first()
            )
            if not exists:
                db.add(
                    TransformationRuleTagMap(rule_id=rule.rule_id, tag_id=tag.tag_id)
                )

    usage_plan = [
        ("TR_001", "API", "POST /rules/execute", "Triggered by Transformation Rules API"),
        ("TR_002", "API", "POST /rules/execute", "Triggered by Transformation Rules API"),
        ("TR_010", "API", "POST /rules/execute", "Calculate total via API"),
        ("TR_010", "Agent", "POST /rules/execute-selected", "Selected by MCP agent"),
    ]
    for code, service, method, desc in usage_plan:
        rule = rules[code]
        exists = (
            db.query(TransformationRuleUsage)
            .filter_by(
                rule_id=rule.rule_id,
                used_in_service=service,
                used_in_method=method,
            )
            .first()
        )
        if not exists:
            db.add(
                TransformationRuleUsage(
                    rule_id=rule.rule_id,
                    used_in_service=service,
                    used_in_method=method,
                    description=desc,
                )
            )

    db.commit()
    print("Tags/usages seed completed.")
    print("  Tags: silver-zone, dynamic, text, numeric")
    print("  Mapped to TR_001, TR_002, TR_010")


def seed(db: Session) -> None:
    # Idempotent: skip core sample if already seeded
    existing = db.query(TransformationRule).filter_by(rule_code="TR_010").first()
    if existing:
        print("Sample rules already exist. Skipping core seed.")
        print(f"  Found: {existing.rule_code} — {existing.rule_name}")
        seed_tags_and_usages(db)
        return

    # 1) Categories
    cat_text = TransformationCategory(
        category_name="Text",
        description="Text transformation rules",
    )
    cat_numeric = TransformationCategory(
        category_name="Numeric",
        description="Numeric / calculation rules",
    )
    cat_enrichment = TransformationCategory(
        category_name="Enrichment",
        description="Data enrichment rules",
    )
    db.add_all([cat_text, cat_numeric, cat_enrichment])
    db.flush()

    # 2) Rules
    rule_001 = TransformationRule(
        rule_code="TR_001",
        rule_name="Uppercase Text",
        description="Convert text to uppercase",
        category_id=cat_text.category_id,
        status="active",
        is_system_rule="Y",
        created_by="system",
    )
    rule_002 = TransformationRule(
        rule_code="TR_002",
        rule_name="Trim Whitespace",
        description="Trim leading/trailing spaces",
        category_id=cat_text.category_id,
        status="active",
        is_system_rule="Y",
        created_by="system",
    )
    rule_010 = TransformationRule(
        rule_code="TR_010",
        rule_name="Calculate Total",
        description="A + B = C (amount + tax = total)",
        category_id=cat_numeric.category_id,
        status="active",
        is_system_rule="N",
        created_by="architect",
    )
    db.add_all([rule_001, rule_002, rule_010])
    db.flush()

    # 3) Dependencies: TR_010 depends on TR_001 (soft) and TR_002 (hard)
    db.add_all(
        [
            TransformationRuleDependency(
                rule_id=rule_010.rule_id,
                depends_on_rule_id=rule_001.rule_id,
                dependency_type="soft",
                description="Optional text prep before calculate",
            ),
            TransformationRuleDependency(
                rule_id=rule_010.rule_id,
                depends_on_rule_id=rule_002.rule_id,
                dependency_type="hard",
                description="Must trim before calculate",
            ),
        ]
    )

    # 4) Versions (v1 active for each)
    v001 = TransformationRuleVersion(
        rule_id=rule_001.rule_id,
        version_no="v1",
        status="active",
        change_log="Initial uppercase rule",
        created_by="system",
    )
    v002 = TransformationRuleVersion(
        rule_id=rule_002.rule_id,
        version_no="v1",
        status="active",
        change_log="Initial trim rule",
        created_by="system",
    )
    v010 = TransformationRuleVersion(
        rule_id=rule_010.rule_id,
        version_no="v1",
        status="active",
        change_log="Initial calculate total rule",
        created_by="architect",
    )
    db.add_all([v001, v002, v010])
    db.flush()

    # 5) Methods (Python path for Registry — Scrum 2)
    m001 = TransformationRuleMethod(
        version_id=v001.version_id,
        method_name="apply",
        method_path="transformation_rules.rules.TR_001_uppercase_text.apply",
        entry_point="apply",
        description="Uppercase transform method",
    )
    m002 = TransformationRuleMethod(
        version_id=v002.version_id,
        method_name="apply",
        method_path="transformation_rules.rules.TR_002_trim_whitespace.apply",
        entry_point="apply",
        description="Trim transform method",
    )
    m010 = TransformationRuleMethod(
        version_id=v010.version_id,
        method_name="apply",
        method_path="transformation_rules.rules.TR_010_calculate_total.apply",
        entry_point="apply",
        description="Calculate total method",
    )
    db.add_all([m001, m002, m010])
    db.flush()

    # 6) Parameters
    db.add_all(
        [
            TransformationRuleParameter(
                method_id=m001.method_id,
                param_name="column_name",
                data_type="string",
                is_required="Y",
                default_value=None,
                description="Target text column",
            ),
            TransformationRuleParameter(
                method_id=m002.method_id,
                param_name="column_name",
                data_type="string",
                is_required="Y",
                default_value=None,
                description="Target text column",
            ),
            TransformationRuleParameter(
                method_id=m010.method_id,
                param_name="amount_field",
                data_type="string",
                is_required="Y",
                default_value="amount",
                description="Input field A",
            ),
            TransformationRuleParameter(
                method_id=m010.method_id,
                param_name="tax_field",
                data_type="string",
                is_required="Y",
                default_value="tax",
                description="Input field B",
            ),
            TransformationRuleParameter(
                method_id=m010.method_id,
                param_name="total_field",
                data_type="string",
                is_required="Y",
                default_value="total",
                description="Output field C",
            ),
        ]
    )

    db.commit()
    print("Seed completed successfully.")
    print("  Categories: Text, Numeric, Enrichment")
    print("  Rules: TR_001, TR_002, TR_010")
    print("  Dependencies: TR_010 → TR_001 (soft), TR_010 → TR_002 (hard)")
    print("  Versions/methods/parameters: inserted")

    seed_tags_and_usages(db)


def main() -> None:
    ensure_tables()
    db = session_with_retry(retries=3, delay_seconds=2.0)
    try:
        seed(db)
    except Exception as e:
        db.rollback()
        print(f"Seed failed: {e}")
        raise
    finally:
        db.close()


if __name__ == "__main__":
    main()
