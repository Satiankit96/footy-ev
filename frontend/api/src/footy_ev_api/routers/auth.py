"""Auth endpoints: login, logout, me."""

from __future__ import annotations

from datetime import UTC, datetime

from fastapi import APIRouter, Cookie, Depends, Response

from footy_ev_api.auth import (
    create_session_jwt,
    decode_session_jwt,
    get_current_operator,
    verify_operator_token,
)
from footy_ev_api.errors import AppError
from footy_ev_api.schemas.auth import (
    LoginRequest,
    LoginResponse,
    LogoutResponse,
    MeResponse,
)
from footy_ev_api.settings import Settings

router = APIRouter(tags=["auth"])


@router.post("/login", response_model=LoginResponse)
async def login(body: LoginRequest, response: Response) -> LoginResponse:
    """Validate operator token. Sets HttpOnly session cookie on success."""
    settings = Settings()
    if not settings.ui_operator_token:
        raise AppError("INVALID_TOKEN", "Invalid token", 401)

    if not verify_operator_token(body.token, settings):
        raise AppError("INVALID_TOKEN", "Invalid token", 401)

    token, exp = create_session_jwt(settings)
    response.set_cookie(
        key="session",
        value=token,
        httponly=True,
        samesite="strict",
        secure=False,
        expires=int(exp.timestamp()),
        path="/",
    )
    return LoginResponse(ok=True)


@router.post("/logout", response_model=LogoutResponse)
async def logout(response: Response) -> LogoutResponse:
    """Clear the session cookie.  Always succeeds."""
    response.delete_cookie(key="session", path="/")
    return LogoutResponse(ok=True)


@router.get("/me", response_model=MeResponse)
async def me(
    _operator: str = Depends(get_current_operator),
    session: str | None = Cookie(default=None),
) -> MeResponse:
    """Return current operator info from the session JWT."""
    started_at: str | None = None
    if session:
        settings = Settings()
        payload = decode_session_jwt(session, settings)
        iat = payload.get("iat")
        if isinstance(iat, int | float):
            started_at = datetime.fromtimestamp(iat, tz=UTC).isoformat()
    return MeResponse(operator="operator", session_started_at=started_at)
