"""Diagnostics router — /api/v1/diagnostics/*."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query

from footy_ev_api.adapters.diagnostics import (
    check_env,
    do_circuit_breaker_reset,
    get_circuit_breaker,
    get_logs,
    list_migrations,
)
from footy_ev_api.auth import get_current_operator
from footy_ev_api.schemas.diagnostics import (
    CircuitBreakerState,
    EnvCheckResponse,
    LogsResponse,
    MigrationListResponse,
)

router = APIRouter(tags=["diagnostics"])

_AUTH = [Depends(get_current_operator)]


@router.get(
    "/diagnostics/circuit-breaker",
    response_model=CircuitBreakerState,
    dependencies=_AUTH,
)
def route_get_circuit_breaker() -> CircuitBreakerState:
    """Current circuit breaker state."""
    return CircuitBreakerState.model_validate(get_circuit_breaker())


@router.post(
    "/diagnostics/circuit-breaker/reset",
    response_model=CircuitBreakerState,
    dependencies=_AUTH,
)
def route_reset_circuit_breaker() -> CircuitBreakerState:
    """Manually reset the circuit breaker. This action is audit-logged."""
    return CircuitBreakerState.model_validate(do_circuit_breaker_reset())


@router.get(
    "/diagnostics/logs",
    response_model=LogsResponse,
    dependencies=_AUTH,
)
def route_get_logs(
    level: str | None = Query(
        default=None, description="Filter by log level (DEBUG/INFO/WARNING/ERROR)"
    ),
    since: str | None = Query(default=None, description="ISO timestamp lower bound"),
    limit: int = Query(default=100, ge=1, le=500),
) -> LogsResponse:
    """Tail recent log entries from the in-memory buffer."""
    return LogsResponse(**get_logs(level=level, since=since, limit=limit))


@router.get(
    "/diagnostics/migrations",
    response_model=MigrationListResponse,
    dependencies=_AUTH,
)
def route_list_migrations() -> MigrationListResponse:
    """List all migration files with applied status."""
    return MigrationListResponse(**list_migrations())


@router.get(
    "/diagnostics/env",
    response_model=EnvCheckResponse,
    dependencies=_AUTH,
)
def route_check_env() -> EnvCheckResponse:
    """Env var presence check. Never returns values — set/unset only."""
    return EnvCheckResponse(**check_env())
