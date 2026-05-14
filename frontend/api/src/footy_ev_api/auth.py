"""Operator authentication: JWT session tokens, constant-time comparison."""

from __future__ import annotations

import hashlib
import hmac
import os
from datetime import UTC, datetime, timedelta
from typing import Any

from fastapi import Cookie, HTTPException, status
from jose import JWTError, jwt

from footy_ev_api.settings import Settings

_ALGORITHM = "HS256"
_SESSION_LIFETIME = timedelta(days=7)


def _get_jwt_secret(settings: Settings) -> str:
    # Derive the JWT signing key from the operator token so the JWT secret
    # is never the raw token itself.  A proper KDF (e.g. HKDF) would be
    # better in production — acceptable for single-operator local use.
    return hashlib.sha256(settings.ui_operator_token.encode()).hexdigest()


def verify_operator_token(candidate: str, settings: Settings) -> bool:
    """Constant-time comparison of candidate token against the configured value."""
    return hmac.compare_digest(candidate, settings.ui_operator_token)


def create_session_jwt(settings: Settings) -> tuple[str, datetime]:
    """Return (encoded_jwt, expiry_datetime)."""
    now = datetime.now(UTC)
    exp = now + _SESSION_LIFETIME
    payload: dict[str, Any] = {
        "sub": "operator",
        "iat": now,
        "exp": exp,
    }
    token: str = jwt.encode(payload, _get_jwt_secret(settings), algorithm=_ALGORITHM)
    return token, exp


def decode_session_jwt(token: str, settings: Settings) -> dict[str, Any]:
    """Validate and decode a session JWT.  Raises HTTPException(401) on failure."""
    try:
        payload: dict[str, Any] = jwt.decode(
            token,
            _get_jwt_secret(settings),
            algorithms=[_ALGORITHM],
        )
        return payload
    except JWTError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired session",
        ) from exc


def get_current_operator(
    session: str | None = Cookie(default=None),
) -> str:
    """FastAPI dependency: validates the session cookie and returns the operator id."""
    if session is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Not authenticated",
        )
    settings = Settings()
    payload = decode_session_jwt(session, settings)
    op: str = payload.get("sub", "operator")
    return op


def get_kalshi_base_url() -> str:
    """Read the Kalshi API base URL from the environment (main project .env)."""
    return os.environ.get("KALSHI_API_BASE_URL", "")
