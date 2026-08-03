"""
Transformation Rules API.

Scrum 4: GET /rules, GET /rules/{code}, POST /rules/execute
Scrum 5: Agent-ready catalog (parameters, version, status filter)
Scrum 6: Tags, usages, and ?tag= filter
Scrum 8: POST /rules/execute-selected (exact agent-selected list)
Scrum 9: Hardening + GET /rules/logs
"""

from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from config.database import get_db
from models.transformation_rules import (
    TransformationLogicLog,
    TransformationRule,
    TransformationRuleDependency,
    TransformationRuleParameter,
    TransformationRuleTag,
    TransformationRuleTagMap,
    TransformationRuleUsage,
)
from transformation_rules.dependency import DependencyError, DependencyManager
from transformation_rules.executor import RuleExecutionError
from transformation_rules.registry import (
    RuleInactiveError,
    RuleLoadError,
    RuleNotFoundError,
    RuleRegistry,
)
from transformation_rules.resolver import SelectedRulesError
from transformation_rules.service import TransformationRulesService
from transformation_rules.validation import ParamValidationError

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/rules", tags=["Transformation Rules"])


# ---------- Schemas ----------

class DependencyInfo(BaseModel):
    depends_on_rule_code: str
    dependency_type: str
    description: str | None = None


class ParameterInfo(BaseModel):
    """Parameter definition for MCP / agent catalog consumers."""

    param_name: str
    data_type: str
    is_required: str
    default_value: str | None = None
    description: str | None = None


class TagInfo(BaseModel):
    tag_name: str
    description: str | None = None


class UsageInfo(BaseModel):
    used_in_service: str
    used_in_method: str | None = None
    description: str | None = None


class RuleListItem(BaseModel):
    rule_id: int
    rule_code: str
    rule_name: str
    description: str | None = None
    status: str
    is_system_rule: str
    version_no: str | None = None
    method_path: str | None = None
    dependencies: list[DependencyInfo] = []
    parameters: list[ParameterInfo] = []
    tags: list[TagInfo] = []
    usages: list[UsageInfo] = []


class RuleListResponse(BaseModel):
    count: int
    status_filter: str
    tag_filter: str | None = None
    rules: list[RuleListItem]


class RuleDetailResponse(BaseModel):
    rule_id: int
    rule_code: str
    rule_name: str
    description: str | None = None
    status: str
    is_system_rule: str
    version_no: str | None = None
    dependencies: list[DependencyInfo] = []
    execution_order_preview: list[str] = []
    method_path: str | None = None
    parameters: list[ParameterInfo] = []
    params: dict[str, Any] = Field(
        default_factory=dict,
        description="Resolved default parameter values for execution",
    )
    tags: list[TagInfo] = []
    usages: list[UsageInfo] = []


class ExecuteRuleRequest(BaseModel):
    rule_code: str = Field(..., examples=["TR_010"])
    data: dict[str, Any] = Field(
        ...,
        examples=[{"text": "  apple  ", "amount": 100, "tax": 10}],
    )
    include_soft: bool = Field(
        True,
        description="Include soft dependencies in the pipeline",
    )
    param_overrides: dict[str, dict[str, Any]] | None = Field(
        default=None,
        description='Per-rule param overrides, e.g. {"TR_002": {"column_name": "text"}}',
        examples=[{"TR_001": {"column_name": "text"}, "TR_002": {"column_name": "text"}}],
    )


class ExecuteStep(BaseModel):
    rule_code: str
    status: str
    data_after: dict[str, Any] | None = None
    error: str | None = None


class ExecuteRuleResponse(BaseModel):
    request_id: str
    requested_rule: str
    execution_order: list[str]
    status: str
    data: dict[str, Any]
    steps: list[ExecuteStep]
    log_id: int | None = None


class ExecuteSelectedRequest(BaseModel):
    """Agent / MCP handshake: run an exact selected list of rules."""

    rule_codes: list[str] = Field(
        ...,
        examples=[["TR_002", "TR_001", "TR_010"]],
        description="Ordered rule codes selected by the agent",
    )
    data: dict[str, Any] = Field(
        ...,
        examples=[{"text": "  apple  ", "amount": 100, "tax": 10}],
    )
    param_overrides: dict[str, dict[str, Any]] | None = Field(
        default=None,
        description='Per-rule param overrides, e.g. {"TR_002": {"column_name": "text"}}',
        examples=[{"TR_001": {"column_name": "text"}, "TR_002": {"column_name": "text"}}],
    )
    strict: bool = Field(
        True,
        description=(
            "If true, run exactly rule_codes in the given order "
            "(no dependency auto-insert). If false, insert missing hard deps."
        ),
    )


class ExecuteSelectedResponse(BaseModel):
    request_id: str
    requested_rules: list[str]
    execution_order: list[str]
    strict: bool
    status: str
    data: dict[str, Any]
    steps: list[ExecuteStep]
    log_id: int | None = None


class LogicLogItem(BaseModel):
    log_id: int
    request_id: str | None = None
    rule_id: int | None = None
    rule_code: str | None = None
    status: str
    started_at: datetime | None = None
    ended_at: datetime | None = None
    error_message: str | None = None
    triggered_by: str
    input_record_count: int | None = None
    output_record_count: int | None = None


class LogicLogListResponse(BaseModel):
    count: int
    limit: int
    logs: list[LogicLogItem]


# ---------- Helpers ----------


def _api_error(
    status_code: int,
    *,
    error: str,
    message: str,
    request_id: str | None = None,
    log_id: int | None = None,
    failed_rule: str | None = None,
    **extra: Any,
) -> None:
    """Raise a structured HTTP error (never a vague string-only 500 for agent cases)."""
    detail: dict[str, Any] = {"error": error, "message": message}
    if request_id is not None:
        detail["request_id"] = request_id
    if log_id is not None:
        detail["log_id"] = log_id
    if failed_rule is not None:
        detail["failed_rule"] = failed_rule
    detail.update(extra)
    raise HTTPException(status_code=status_code, detail=detail)


def _status_for_selection_error(exc: SelectedRulesError) -> int:
    if getattr(exc, "error_code", "") == "rule_not_found":
        return 404
    if "not found" in str(exc).lower():
        return 404
    return 400

def _deps_for_rule(db: Session, rule_id: int) -> list[DependencyInfo]:
    rows = (
        db.query(TransformationRuleDependency)
        .filter(TransformationRuleDependency.rule_id == rule_id)
        .all()
    )
    result: list[DependencyInfo] = []
    for row in rows:
        parent = (
            db.query(TransformationRule)
            .filter(TransformationRule.rule_id == row.depends_on_rule_id)
            .first()
        )
        if parent:
            result.append(
                DependencyInfo(
                    depends_on_rule_code=parent.rule_code,
                    dependency_type=row.dependency_type,
                    description=row.description,
                )
            )
    return result


def _parameter_infos(db: Session, method_id: int) -> list[ParameterInfo]:
    rows = (
        db.query(TransformationRuleParameter)
        .filter(TransformationRuleParameter.method_id == method_id)
        .order_by(TransformationRuleParameter.param_name)
        .all()
    )
    return [
        ParameterInfo(
            param_name=row.param_name,
            data_type=row.data_type,
            is_required=row.is_required,
            default_value=row.default_value,
            description=row.description,
        )
        for row in rows
    ]


def _tags_for_rule(db: Session, rule_id: int) -> list[TagInfo]:
    rows = (
        db.query(TransformationRuleTag)
        .join(
            TransformationRuleTagMap,
            TransformationRuleTagMap.tag_id == TransformationRuleTag.tag_id,
        )
        .filter(TransformationRuleTagMap.rule_id == rule_id)
        .order_by(TransformationRuleTag.tag_name)
        .all()
    )
    return [
        TagInfo(tag_name=row.tag_name, description=row.description) for row in rows
    ]


def _usages_for_rule(db: Session, rule_id: int) -> list[UsageInfo]:
    rows = (
        db.query(TransformationRuleUsage)
        .filter(TransformationRuleUsage.rule_id == rule_id)
        .order_by(TransformationRuleUsage.usage_id)
        .all()
    )
    return [
        UsageInfo(
            used_in_service=row.used_in_service,
            used_in_method=row.used_in_method,
            description=row.description,
        )
        for row in rows
    ]


def _catalog_meta(db: Session, rule: TransformationRule) -> dict[str, Any]:
    """
    Version / method / parameter catalog for one rule.
    Does not import Python callables (safe for list endpoint).
    """
    registry = RuleRegistry(db)
    try:
        version = registry.get_active_version(rule.rule_id)
        method = registry.get_method(version.version_id)
        return {
            "version_no": version.version_no,
            "method_path": method.method_path,
            "parameters": _parameter_infos(db, method.method_id),
            "params": registry.get_params(method.method_id),
        }
    except RuleNotFoundError:
        return {
            "version_no": None,
            "method_path": None,
            "parameters": [],
            "params": {},
        }


def _save_log(
    db: Session,
    *,
    rule: TransformationRule | None,
    method_id: int | None,
    version_id: int | None,
    request_id: str,
    status_value: str,
    started_at: datetime,
    error_message: str | None = None,
    input_count: int = 1,
    output_count: int = 1,
) -> TransformationLogicLog:
    log = TransformationLogicLog(
        rule_id=rule.rule_id if rule else None,
        method_id=method_id,
        version_id=version_id,
        request_id=request_id,
        input_record_count=input_count,
        output_record_count=output_count,
        status=status_value,
        started_at=started_at,
        ended_at=datetime.now(timezone.utc).replace(tzinfo=None),
        error_message=error_message,
        triggered_by="api",
    )
    db.add(log)
    db.commit()
    db.refresh(log)
    return log


# ---------- Endpoints ----------

@router.get("", response_model=RuleListResponse)
def list_rules(
    status: str = Query(
        "active",
        description='Filter by status: "active" (default), "inactive", or "all"',
        examples=["active"],
    ),
    tag: str | None = Query(
        None,
        description='Optional tag filter, e.g. "numeric" or "text"',
        examples=["numeric"],
    ),
    db: Session = Depends(get_db),
):
    """
    List transformation rules (agent / MCP catalog).

    Includes dependencies, parameters, tags, and usages so an agent can choose rules.
    """
    query = db.query(TransformationRule)
    status_filter = (status or "active").strip().lower()
    if status_filter != "all":
        query = query.filter(TransformationRule.status == status_filter)

    tag_filter = tag.strip().lower() if tag else None
    if tag_filter:
        query = (
            query.join(
                TransformationRuleTagMap,
                TransformationRuleTagMap.rule_id == TransformationRule.rule_id,
            )
            .join(
                TransformationRuleTag,
                TransformationRuleTag.tag_id == TransformationRuleTagMap.tag_id,
            )
            .filter(TransformationRuleTag.tag_name == tag_filter)
            .distinct()
        )

    rules = query.order_by(TransformationRule.rule_code).all()
    items: list[RuleListItem] = []
    for r in rules:
        meta = _catalog_meta(db, r)
        items.append(
            RuleListItem(
                rule_id=r.rule_id,
                rule_code=r.rule_code,
                rule_name=r.rule_name,
                description=r.description,
                status=r.status,
                is_system_rule=r.is_system_rule,
                version_no=meta["version_no"],
                method_path=meta["method_path"],
                dependencies=_deps_for_rule(db, r.rule_id),
                parameters=meta["parameters"],
                tags=_tags_for_rule(db, r.rule_id),
                usages=_usages_for_rule(db, r.rule_id),
            )
        )
    return RuleListResponse(
        count=len(items),
        status_filter=status_filter,
        tag_filter=tag_filter,
        rules=items,
    )


@router.get("/logs", response_model=LogicLogListResponse)
def list_execution_logs(
    limit: int = Query(20, ge=1, le=100, description="Max recent logs to return"),
    status: str | None = Query(
        None,
        description='Optional filter: "success", "failed", or "partial"',
        examples=["failed"],
    ),
    rule_code: str | None = Query(
        None,
        description="Optional filter by rule_code linked on the log row",
        examples=["TR_010"],
    ),
    db: Session = Depends(get_db),
):
    """
    Recent transformation execution logs (Scrum 9).

    Use this with Sunali to debug catalog → execute-selected failures.
    """
    query = db.query(TransformationLogicLog)
    status_filter = (status or "").strip().lower() or None
    if status_filter:
        query = query.filter(TransformationLogicLog.status == status_filter)

    code_filter = (rule_code or "").strip() or None
    if code_filter:
        rule = (
            db.query(TransformationRule)
            .filter(TransformationRule.rule_code == code_filter)
            .first()
        )
        if not rule:
            _api_error(
                404,
                error="rule_not_found",
                message=f"Rule not found: {code_filter}",
            )
        query = query.filter(TransformationLogicLog.rule_id == rule.rule_id)

    rows = (
        query.order_by(TransformationLogicLog.log_id.desc()).limit(limit).all()
    )
    rule_ids = {row.rule_id for row in rows if row.rule_id is not None}
    code_by_id: dict[int, str] = {}
    if rule_ids:
        for r in (
            db.query(TransformationRule)
            .filter(TransformationRule.rule_id.in_(rule_ids))
            .all()
        ):
            code_by_id[r.rule_id] = r.rule_code

    items = [
        LogicLogItem(
            log_id=row.log_id,
            request_id=row.request_id,
            rule_id=row.rule_id,
            rule_code=code_by_id.get(row.rule_id) if row.rule_id else None,
            status=row.status,
            started_at=row.started_at,
            ended_at=row.ended_at,
            error_message=row.error_message,
            triggered_by=row.triggered_by,
            input_record_count=row.input_record_count,
            output_record_count=row.output_record_count,
        )
        for row in rows
    ]
    return LogicLogListResponse(count=len(items), limit=limit, logs=items)


@router.post("/execute-selected", response_model=ExecuteSelectedResponse)
def execute_selected_rules(
    payload: ExecuteSelectedRequest, db: Session = Depends(get_db)
):
    """
    Execute an agent-selected list of rules (Scrum 8 / 9).

    With strict=true (default), runs exactly `rule_codes` in the given order.
    With strict=false, inserts missing hard dependencies before each selected rule.
    """
    request_id = str(uuid.uuid4())
    started_at = datetime.now(timezone.utc).replace(tzinfo=None)
    service = TransformationRulesService(db)

    rule = None
    method_id = None
    version_id = None
    try:
        requested = [
            (c or "").strip() for c in (payload.rule_codes or []) if (c or "").strip()
        ]
        if not requested:
            raise SelectedRulesError(
                "rule_codes must not be empty", error_code="empty_selection"
            )

        registry = RuleRegistry(db)
        first = registry.resolve(requested[0])
        rule = first["rule"]
        method_id = first["method"].method_id
        version_id = first["version"].version_id

        result = service.execute_selected(
            payload.rule_codes,
            payload.data,
            strict=payload.strict,
            param_overrides=payload.param_overrides,
        )

        log = _save_log(
            db,
            rule=rule,
            method_id=method_id,
            version_id=version_id,
            request_id=request_id,
            status_value="success",
            started_at=started_at,
        )
        return ExecuteSelectedResponse(
            request_id=request_id,
            requested_rules=result["requested_rules"],
            execution_order=result["execution_order"],
            strict=result["strict"],
            status=result["status"],
            data=result["data"],
            steps=[ExecuteStep(**s) for s in result["steps"]],
            log_id=log.log_id,
        )
    except SelectedRulesError as e:
        message = str(e)
        log = _save_log(
            db,
            rule=rule,
            method_id=method_id,
            version_id=version_id,
            request_id=request_id,
            status_value="failed",
            started_at=started_at,
            error_message=message,
            output_count=0,
        )
        _api_error(
            _status_for_selection_error(e),
            error=getattr(e, "error_code", "invalid_selection"),
            message=message,
            request_id=request_id,
            log_id=log.log_id,
        )
    except RuleInactiveError as e:
        log = _save_log(
            db,
            rule=rule,
            method_id=method_id,
            version_id=version_id,
            request_id=request_id,
            status_value="failed",
            started_at=started_at,
            error_message=str(e),
            output_count=0,
        )
        _api_error(
            400,
            error="inactive_rule",
            message=str(e),
            request_id=request_id,
            log_id=log.log_id,
        )
    except RuleNotFoundError as e:
        log = _save_log(
            db,
            rule=rule,
            method_id=method_id,
            version_id=version_id,
            request_id=request_id,
            status_value="failed",
            started_at=started_at,
            error_message=str(e),
            output_count=0,
        )
        _api_error(
            404,
            error="rule_not_found",
            message=str(e),
            request_id=request_id,
            log_id=log.log_id,
        )
    except ParamValidationError as e:
        log = _save_log(
            db,
            rule=rule,
            method_id=method_id,
            version_id=version_id,
            request_id=request_id,
            status_value="failed",
            started_at=started_at,
            error_message=str(e),
            output_count=0,
        )
        _api_error(
            400,
            error="param_validation_failed",
            message=str(e),
            request_id=request_id,
            log_id=log.log_id,
            failed_rule=e.rule_code,
        )
    except RuleExecutionError as e:
        log = _save_log(
            db,
            rule=rule,
            method_id=method_id,
            version_id=version_id,
            request_id=request_id,
            status_value="failed",
            started_at=started_at,
            error_message=str(e),
            output_count=0,
        )
        _api_error(
            400,
            error="rule_execution_failed",
            message=str(e),
            request_id=request_id,
            log_id=log.log_id,
            failed_rule=e.rule_code,
            execution_order=e.execution_order,
            steps=e.steps,
            data=e.data,
        )
    except (DependencyError, RuleLoadError) as e:
        message = str(e)
        status_code = 404 if "not found" in message.lower() else 400
        error_code = (
            "rule_not_found"
            if status_code == 404
            else ("inactive_rule" if "inactive" in message.lower() else "dependency_error")
        )
        log = _save_log(
            db,
            rule=rule,
            method_id=method_id,
            version_id=version_id,
            request_id=request_id,
            status_value="failed",
            started_at=started_at,
            error_message=message,
            output_count=0,
        )
        _api_error(
            status_code,
            error=error_code,
            message=message,
            request_id=request_id,
            log_id=log.log_id,
        )
    except Exception as e:
        logger.exception("Unexpected execute-selected error")
        db.rollback()
        log_id = None
        try:
            log = _save_log(
                db,
                rule=rule,
                method_id=method_id,
                version_id=version_id,
                request_id=request_id,
                status_value="failed",
                started_at=started_at,
                error_message=str(e),
                output_count=0,
            )
            log_id = log.log_id
        except Exception:
            db.rollback()
        _api_error(
            500,
            error="internal_error",
            message="Failed to execute selected rules",
            request_id=request_id,
            log_id=log_id,
        )


@router.get("/{rule_code}", response_model=RuleDetailResponse)
def get_rule(rule_code: str, db: Session = Depends(get_db)):
    """Get one rule: dependencies, parameters, tags, usages, method path, order preview."""
    try:
        registry = RuleRegistry(db)
        resolved = registry.resolve(rule_code)
        deps_mgr = DependencyManager(db)
        order = deps_mgr.resolve_order(rule_code, include_soft=True)
    except RuleNotFoundError as e:
        _api_error(404, error="rule_not_found", message=str(e))
    except RuleInactiveError as e:
        _api_error(400, error="inactive_rule", message=str(e))
    except (DependencyError, RuleLoadError) as e:
        message = str(e)
        if "inactive" in message.lower():
            _api_error(400, error="inactive_rule", message=message)
        if "not found" in message.lower():
            _api_error(404, error="rule_not_found", message=message)
        _api_error(400, error="dependency_error", message=message)

    rule = resolved["rule"]
    version = resolved["version"]
    method = resolved["method"]
    return RuleDetailResponse(
        rule_id=rule.rule_id,
        rule_code=rule.rule_code,
        rule_name=rule.rule_name,
        description=rule.description,
        status=rule.status,
        is_system_rule=rule.is_system_rule,
        version_no=version.version_no,
        dependencies=_deps_for_rule(db, rule.rule_id),
        execution_order_preview=order,
        method_path=method.method_path,
        parameters=_parameter_infos(db, method.method_id),
        params=resolved["params"],
        tags=_tags_for_rule(db, rule.rule_id),
        usages=_usages_for_rule(db, rule.rule_id),
    )


@router.post("/execute", response_model=ExecuteRuleResponse)
def execute_rule(payload: ExecuteRuleRequest, db: Session = Depends(get_db)):
    """
    Execute a rule with its dependency graph.

    Example: POST TR_010 with amount/tax → runs TR_001/TR_002 first if soft/hard deps apply.
    """
    request_id = str(uuid.uuid4())
    started_at = datetime.now(timezone.utc).replace(tzinfo=None)
    service = TransformationRulesService(db)

    rule = None
    method_id = None
    version_id = None
    try:
        registry = RuleRegistry(db)
        resolved = registry.resolve(payload.rule_code)
        rule = resolved["rule"]
        method_id = resolved["method"].method_id
        version_id = resolved["version"].version_id

        result = service.execute_rule(
            payload.rule_code,
            payload.data,
            include_soft=payload.include_soft,
            param_overrides=payload.param_overrides,
        )

        log = _save_log(
            db,
            rule=rule,
            method_id=method_id,
            version_id=version_id,
            request_id=request_id,
            status_value="success",
            started_at=started_at,
        )
        return ExecuteRuleResponse(
            request_id=request_id,
            requested_rule=result["requested_rule"],
            execution_order=result["execution_order"],
            status=result["status"],
            data=result["data"],
            steps=[ExecuteStep(**s) for s in result["steps"]],
            log_id=log.log_id,
        )
    except RuleInactiveError as e:
        log = _save_log(
            db,
            rule=rule,
            method_id=method_id,
            version_id=version_id,
            request_id=request_id,
            status_value="failed",
            started_at=started_at,
            error_message=str(e),
            output_count=0,
        )
        _api_error(
            400,
            error="inactive_rule",
            message=str(e),
            request_id=request_id,
            log_id=log.log_id,
        )
    except RuleNotFoundError as e:
        log = _save_log(
            db,
            rule=rule,
            method_id=method_id,
            version_id=version_id,
            request_id=request_id,
            status_value="failed",
            started_at=started_at,
            error_message=str(e),
            output_count=0,
        )
        _api_error(
            404,
            error="rule_not_found",
            message=str(e),
            request_id=request_id,
            log_id=log.log_id,
        )
    except ParamValidationError as e:
        log = _save_log(
            db,
            rule=rule,
            method_id=method_id,
            version_id=version_id,
            request_id=request_id,
            status_value="failed",
            started_at=started_at,
            error_message=str(e),
            output_count=0,
        )
        _api_error(
            400,
            error="param_validation_failed",
            message=str(e),
            request_id=request_id,
            log_id=log.log_id,
            failed_rule=e.rule_code,
        )
    except RuleExecutionError as e:
        log = _save_log(
            db,
            rule=rule,
            method_id=method_id,
            version_id=version_id,
            request_id=request_id,
            status_value="failed",
            started_at=started_at,
            error_message=str(e),
            output_count=0,
        )
        _api_error(
            400,
            error="rule_execution_failed",
            message=str(e),
            request_id=request_id,
            log_id=log.log_id,
            failed_rule=e.rule_code,
            execution_order=e.execution_order,
            steps=e.steps,
            data=e.data,
        )
    except (DependencyError, RuleLoadError) as e:
        message = str(e)
        status_code = 404 if "not found" in message.lower() else 400
        error_code = (
            "rule_not_found"
            if status_code == 404
            else ("inactive_rule" if "inactive" in message.lower() else "dependency_error")
        )
        log = _save_log(
            db,
            rule=rule,
            method_id=method_id,
            version_id=version_id,
            request_id=request_id,
            status_value="failed",
            started_at=started_at,
            error_message=message,
            output_count=0,
        )
        _api_error(
            status_code,
            error=error_code,
            message=message,
            request_id=request_id,
            log_id=log.log_id,
        )
    except Exception as e:
        logger.exception("Unexpected execute error")
        db.rollback()
        log_id = None
        try:
            log = _save_log(
                db,
                rule=rule,
                method_id=method_id,
                version_id=version_id,
                request_id=request_id,
                status_value="failed",
                started_at=started_at,
                error_message=str(e),
                output_count=0,
            )
            log_id = log.log_id
        except Exception:
            db.rollback()
        _api_error(
            500,
            error="internal_error",
            message="Failed to execute rule",
            request_id=request_id,
            log_id=log_id,
        )
