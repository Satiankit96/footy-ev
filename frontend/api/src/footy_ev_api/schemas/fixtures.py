"""Fixture endpoint schemas."""

from __future__ import annotations

from pydantic import BaseModel


class FixtureAliasInfo(BaseModel):
    """Alias info embedded in fixture detail."""

    event_ticker: str
    confidence: float
    resolved_by: str
    resolved_at: str | None = None


class FixtureResponse(BaseModel):
    """Single fixture record."""

    fixture_id: str
    league: str
    season: str
    home_team_id: str | None = None
    away_team_id: str | None = None
    home_team_raw: str | None = None
    away_team_raw: str | None = None
    match_date: str | None = None
    kickoff_utc: str | None = None
    home_score_ft: int | None = None
    away_score_ft: int | None = None
    result_ft: str | None = None
    home_xg: str | None = None
    away_xg: str | None = None
    status: str
    alias_count: int = 0


class FixtureDetailResponse(FixtureResponse):
    """Fixture detail with linked aliases and counts."""

    aliases: list[FixtureAliasInfo] = []
    prediction_count: int = 0
    bet_count: int = 0


class FixtureListResponse(BaseModel):
    """GET /api/v1/fixtures response."""

    fixtures: list[FixtureResponse]
    total: int
