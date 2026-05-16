"""Audit router — /api/v1/audit/*."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query

from footy_ev_api.adapters.audit import (
    list_decisions,
    list_model_versions,
    list_operator_actions,
)
from footy_ev_api.auth import get_current_operator
from footy_ev_api.schemas.audit import (
    DecisionRow,
    DecisionsResponse,
    ModelVersionRow,
    ModelVersionsResponse,
    OperatorActionRow,
    OperatorActionsResponse,
)

router = APIRouter(tags=["audit"])

_AUTH = [Depends(get_current_operator)]


@router.get(
    "/audit/operator-actions",
    response_model=OperatorActionsResponse,
    dependencies=_AUTH,
)
def route_operator_actions(
    action_type: str | None = Query(default=None),
    since: str | None = Query(default=None, description="ISO timestamp lower bound"),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
) -> OperatorActionsResponse:
    """Paginated operator action log."""
    data = list_operator_actions(
        action_type=action_type,
        since=since,
        limit=limit,
        offset=offset,
    )
    return OperatorActionsResponse(
        actions=[OperatorActionRow(**a) for a in data["actions"]],
        total=data["total"],
    )


@router.get(
    "/audit/model-versions",
    response_model=ModelVersionsResponse,
    dependencies=_AUTH,
)
def route_model_versions() -> ModelVersionsResponse:
    """All model versions registered in model_predictions."""
    data = list_model_versions()
    return ModelVersionsResponse(
        versions=[ModelVersionRow(**v) for v in data["versions"]],
    )


@router.get(
    "/audit/decisions",
    response_model=DecisionsResponse,
    dependencies=_AUTH,
)
def route_decisions(
    since: str | None = Query(default=None, description="ISO timestamp lower bound"),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
) -> DecisionsResponse:
    """Paper bet decision audit trail."""
    data = list_decisions(since=since, limit=limit, offset=offset)
    return DecisionsResponse(
        decisions=[DecisionRow(**d) for d in data["decisions"]],
        total=data["total"],
    )
