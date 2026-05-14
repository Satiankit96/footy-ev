"""Auth endpoints: login, logout, me."""

from __future__ import annotations

from datetime import UTC, datetime

from fastapi import APIRouter, Cookie, Depends, Response
from pydantic import BaseModel

from footy_ev_api.auth import (
    create_session_jwt,
    decode_session_jwt,
    get_current_operator,
    verify_operator_token,
)
from footy_ev_api.settings import Settings

router = APIRouter(tags=["auth"])


class LoginRequest(BaseModel):
    """Operator token submission."""

    token: str


@router.post("/login")
async def login(body: LoginRequest, response: Response) -> dict[str, bool]:
    """Validate operator token. Sets HttpOnly session cookie on success."""
    settings = Settings()
    if not settings.ui_operator_token:
        response.status_code = 401
        return {"ok": False}

    if not verify_operator_token(body.token, settings):
        response.status_code = 401
        return {"ok": False}

    token, exp = create_session_jwt(settings)
    response.set_cookie(
        key="session",
        value=token,
        httponly=True,
        samesite="strict",
        secure=False,  # localhost dev; enable for HTTPS in production
        expires=int(exp.timestamp()),
        path="/",
    )
    return {"ok": True}


@router.post("/logout")
async def logout(response: Response) -> dict[str, bool]:
    """Clear the session cookie.  Always succeeds."""
    response.delete_cookie(key="session", path="/")
    return {"ok": True}


@router.get("/me")
async def me(
    _operator: str = Depends(get_current_operator),
    session: str | None = Cookie(default=None),
) -> dict[str, str | None]:
    """Return current operator info from the session JWT."""
    started_at: str | None = None
    if session:
        settings = Settings()
        payload = decode_session_jwt(session, settings)
        iat = payload.get("iat")
        if isinstance(iat, int | float):
            started_at = datetime.fromtimestamp(iat, tz=UTC).isoformat()
    return {"operator": "operator", "session_started_at": started_at}
