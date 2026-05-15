"""FastAPI app factory and uvicorn entry point."""

from __future__ import annotations

from fastapi import FastAPI, WebSocket
from fastapi.middleware.cors import CORSMiddleware

from footy_ev_api.errors import AppError, app_error_handler
from footy_ev_api.jobs.manager import JobManager
from footy_ev_api.routers.aliases import router as aliases_router
from footy_ev_api.routers.auth import router as auth_router
from footy_ev_api.routers.bootstrap import router as bootstrap_router
from footy_ev_api.routers.health import router as health_router
from footy_ev_api.routers.kalshi import router as kalshi_router
from footy_ev_api.routers.pipeline import router as pipeline_router
from footy_ev_api.routers.shell import router as shell_router
from footy_ev_api.ws.jobs import ws_job
from footy_ev_api.ws.pipeline import sync_broadcast, ws_freshness, ws_pipeline


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
    app.add_exception_handler(AppError, app_error_handler)  # type: ignore[arg-type]
    app.include_router(health_router, prefix="/api/v1")
    app.include_router(auth_router, prefix="/api/v1/auth")
    app.include_router(shell_router, prefix="/api/v1")
    app.include_router(pipeline_router, prefix="/api/v1")
    app.include_router(kalshi_router, prefix="/api/v1")
    app.include_router(aliases_router, prefix="/api/v1")
    app.include_router(bootstrap_router, prefix="/api/v1")

    app.websocket("/ws/v1/pipeline")(ws_pipeline)
    app.websocket("/ws/v1/freshness")(ws_freshness)

    @app.websocket("/ws/v1/jobs/{job_id}")
    async def _ws_job(websocket: WebSocket, job_id: str) -> None:
        await ws_job(websocket, job_id)

    mgr = JobManager()
    mgr.set_broadcast(sync_broadcast)

    return app


app = create_app()
