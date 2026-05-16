"""Pydantic schemas for diagnostics endpoints."""

from __future__ import annotations

from pydantic import BaseModel


class CircuitBreakerState(BaseModel):
    state: str
    last_tripped_at: str | None = None
    reason: str | None = None


class MigrationInfo(BaseModel):
    name: str
    applied: bool
    applied_at: str | None = None


class MigrationListResponse(BaseModel):
    migrations: list[MigrationInfo]


class EnvVarInfo(BaseModel):
    name: str
    is_set: bool
    required: bool


class EnvCheckResponse(BaseModel):
    vars: list[EnvVarInfo]


class LogEntry(BaseModel):
    timestamp: str
    level: str
    logger: str
    message: str


class LogsResponse(BaseModel):
    entries: list[LogEntry]
    total: int
