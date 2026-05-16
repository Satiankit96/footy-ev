"""Schemas for operator settings endpoints."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel


class OperatorSettings(BaseModel):
    """Persisted UI preferences for the operator."""

    theme: Literal["dark", "light", "system"] = "system"
    density: Literal["comfortable", "compact"] = "comfortable"
    default_page_size: Literal[25, 50, 100] = 50
    default_time_range_days: Literal[7, 14, 30, 90] = 30


class SettingsResponse(BaseModel):
    """Wrapper returned by GET and PUT /api/v1/settings."""

    settings: OperatorSettings
