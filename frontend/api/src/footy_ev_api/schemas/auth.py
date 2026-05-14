"""Auth endpoint request/response schemas."""

from __future__ import annotations

from pydantic import BaseModel


class LoginRequest(BaseModel):
    """POST /api/v1/auth/login request body."""

    token: str


class LoginResponse(BaseModel):
    """POST /api/v1/auth/login response."""

    ok: bool


class LogoutResponse(BaseModel):
    """POST /api/v1/auth/logout response."""

    ok: bool


class MeResponse(BaseModel):
    """GET /api/v1/auth/me response."""

    operator: str
    session_started_at: str | None
