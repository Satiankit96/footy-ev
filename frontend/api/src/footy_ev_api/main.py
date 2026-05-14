"""FastAPI app factory and uvicorn entry point."""

from __future__ import annotations

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from footy_ev_api.routers.auth import router as auth_router
from footy_ev_api.routers.health import router as health_router
from footy_ev_api.routers.shell import router as shell_router


def create_app() -> FastAPI:
    """Build and configure the FastAPI application."""
    app = FastAPI(
        title="footy-ev API",
        version="0.1.0",
        docs_url="/docs",
        redoc_url="/redoc",
        openapi_url="/api/v1/openapi.json",
    )
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["http://localhost:3000"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.include_router(health_router, prefix="/api/v1")
    app.include_router(auth_router, prefix="/api/v1/auth")
    app.include_router(shell_router, prefix="/api/v1")
    return app


app = create_app()
