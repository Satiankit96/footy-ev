"""Settings router — /api/v1/settings."""

from __future__ import annotations

from fastapi import APIRouter, Depends

from footy_ev_api.adapters.settings import get_settings, save_settings
from footy_ev_api.auth import get_current_operator
from footy_ev_api.schemas.settings import OperatorSettings, SettingsResponse

router = APIRouter(tags=["settings"])

_AUTH = [Depends(get_current_operator)]


@router.get("/settings", response_model=SettingsResponse, dependencies=_AUTH)
def route_get_settings() -> SettingsResponse:
    """Return persisted operator UI settings, falling back to defaults."""
    data = get_settings()
    return SettingsResponse(settings=OperatorSettings(**data))


@router.put("/settings", response_model=SettingsResponse, dependencies=_AUTH)
def route_save_settings(body: OperatorSettings) -> SettingsResponse:
    """Persist operator UI settings and return the saved values."""
    saved = save_settings(body.model_dump())
    return SettingsResponse(settings=OperatorSettings(**saved))
