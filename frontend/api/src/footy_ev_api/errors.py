"""Consistent error envelope for all API errors."""

from __future__ import annotations

import uuid

from fastapi import Request
from fastapi.responses import JSONResponse


class AppError(Exception):
    """Structured application error with code, message, and HTTP status."""

    def __init__(
        self,
        code: str,
        message: str,
        status_code: int = 400,
        details: dict[str, object] | None = None,
    ) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.status_code = status_code
        self.details: dict[str, object] = details or {}


async def app_error_handler(request: Request, exc: AppError) -> JSONResponse:
    """Convert AppError into a JSON envelope with request-id correlation."""
    request_id = request.headers.get("x-request-id", str(uuid.uuid4()))
    return JSONResponse(
        status_code=exc.status_code,
        content={
            "error": {
                "code": exc.code,
                "message": exc.message,
                "details": exc.details,
                "request_id": request_id,
            }
        },
    )
