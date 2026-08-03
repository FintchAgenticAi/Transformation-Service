"""
Transformation Rules DB models (Scrum 1 — core tables).

Matches docs/diagrams/transformation_rules_db.sql (dependency-oriented ERD).
"""

from sqlalchemy import (
    Column,
    Integer,
    String,
    DateTime,
    Text,
    ForeignKey,
    UniqueConstraint,
    CheckConstraint,
)
from sqlalchemy.sql import func
from config.database import Base


class TransformationCategory(Base):
    __tablename__ = "transformation_categories"

    category_id = Column(Integer, primary_key=True, index=True)
    category_name = Column(String(100), nullable=False, unique=True)
    description = Column(String(255), nullable=True)


class TransformationRule(Base):
    __tablename__ = "transformation_rules"

    rule_id = Column(Integer, primary_key=True, index=True)
    rule_code = Column(String(50), nullable=False, unique=True)  # e.g. TR_001
    rule_name = Column(String(150), nullable=False)
    description = Column(String(500), nullable=True)
    category_id = Column(
        Integer,
        ForeignKey("transformation_categories.category_id"),
        nullable=True,
    )
    status = Column(String(20), nullable=False, default="active")  # active | inactive
    is_system_rule = Column(String(1), nullable=False, default="N")  # Y | N
    created_by = Column(String(100), nullable=True)
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())


class TransformationRuleDependency(Base):
    __tablename__ = "transformation_rule_dependencies"
    __table_args__ = (
        UniqueConstraint("rule_id", "depends_on_rule_id", name="uq_rule_dependency"),
        CheckConstraint("rule_id <> depends_on_rule_id", name="chk_no_self_dependency"),
    )

    dependency_id = Column(Integer, primary_key=True, index=True)
    rule_id = Column(
        Integer,
        ForeignKey("transformation_rules.rule_id", ondelete="CASCADE"),
        nullable=False,
    )
    depends_on_rule_id = Column(
        Integer,
        ForeignKey("transformation_rules.rule_id", ondelete="CASCADE"),
        nullable=False,
    )
    dependency_type = Column(String(10), nullable=False, default="hard")  # hard | soft
    description = Column(String(255), nullable=True)


class TransformationRuleVersion(Base):
    __tablename__ = "transformation_rule_versions"
    __table_args__ = (
        UniqueConstraint("rule_id", "version_no", name="uq_rule_version"),
    )

    version_id = Column(Integer, primary_key=True, index=True)
    rule_id = Column(
        Integer,
        ForeignKey("transformation_rules.rule_id", ondelete="CASCADE"),
        nullable=False,
    )
    version_no = Column(String(20), nullable=False)  # e.g. v1
    effective_from = Column(DateTime, nullable=True)
    effective_to = Column(DateTime, nullable=True)
    status = Column(String(20), nullable=False, default="draft")  # draft | active | retired
    change_log = Column(Text, nullable=True)
    created_by = Column(String(100), nullable=True)
    created_at = Column(DateTime, server_default=func.now())


class TransformationRuleMethod(Base):
    __tablename__ = "transformation_rule_methods"

    method_id = Column(Integer, primary_key=True, index=True)
    version_id = Column(
        Integer,
        ForeignKey("transformation_rule_versions.version_id", ondelete="CASCADE"),
        nullable=False,
    )
    method_name = Column(String(150), nullable=False)  # e.g. apply
    method_path = Column(String(255), nullable=False)  # e.g. rules.TR_010_calculate_total.apply
    entry_point = Column(String(100), nullable=True)
    description = Column(String(255), nullable=True)


class TransformationRuleParameter(Base):
    __tablename__ = "transformation_rule_parameters"
    __table_args__ = (
        UniqueConstraint("method_id", "param_name", name="uq_method_param"),
    )

    param_id = Column(Integer, primary_key=True, index=True)
    method_id = Column(
        Integer,
        ForeignKey("transformation_rule_methods.method_id", ondelete="CASCADE"),
        nullable=False,
    )
    param_name = Column(String(100), nullable=False)
    data_type = Column(String(50), nullable=False)  # string, int, float, bool, json
    is_required = Column(String(1), nullable=False, default="N")  # Y | N
    default_value = Column(String(255), nullable=True)
    description = Column(String(255), nullable=True)


class TransformationRuleTag(Base):
    """Catalog tags for agent filtering (Scrum 6)."""

    __tablename__ = "transformation_rule_tags"

    tag_id = Column(Integer, primary_key=True, index=True)
    tag_name = Column(String(100), nullable=False, unique=True)
    description = Column(String(255), nullable=True)


class TransformationRuleTagMap(Base):
    """M:N map between rules and tags (Scrum 6)."""

    __tablename__ = "transformation_rule_tag_map"
    __table_args__ = (
        UniqueConstraint("rule_id", "tag_id", name="uq_rule_tag_map"),
    )

    rule_id = Column(
        Integer,
        ForeignKey("transformation_rules.rule_id", ondelete="CASCADE"),
        primary_key=True,
    )
    tag_id = Column(
        Integer,
        ForeignKey("transformation_rule_tags.tag_id", ondelete="CASCADE"),
        primary_key=True,
    )


class TransformationRuleUsage(Base):
    """Where a rule is used — API / Pipeline / Job (Scrum 6)."""

    __tablename__ = "transformation_rule_usages"

    usage_id = Column(Integer, primary_key=True, index=True)
    rule_id = Column(
        Integer,
        ForeignKey("transformation_rules.rule_id", ondelete="CASCADE"),
        nullable=False,
    )
    used_in_service = Column(String(100), nullable=False)  # API, Pipeline, Job
    used_in_method = Column(String(150), nullable=True)
    description = Column(String(255), nullable=True)


class TransformationLogicLog(Base):
    """Execution / monitoring log (Scrum 4)."""

    __tablename__ = "transformation_logic_logs"

    log_id = Column(Integer, primary_key=True, index=True)
    rule_id = Column(
        Integer,
        ForeignKey("transformation_rules.rule_id"),
        nullable=True,
    )
    method_id = Column(
        Integer,
        ForeignKey("transformation_rule_methods.method_id"),
        nullable=True,
    )
    version_id = Column(
        Integer,
        ForeignKey("transformation_rule_versions.version_id"),
        nullable=True,
    )
    request_id = Column(String(100), nullable=True)
    input_record_count = Column(Integer, nullable=True)
    output_record_count = Column(Integer, nullable=True)
    status = Column(String(20), nullable=False)  # success | failed | partial
    started_at = Column(DateTime, server_default=func.now())
    ended_at = Column(DateTime, nullable=True)
    error_message = Column(Text, nullable=True)
    triggered_by = Column(String(20), nullable=False, default="api")  # manual | api | system
