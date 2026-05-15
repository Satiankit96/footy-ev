"""Kalshi endpoint response schemas."""

from __future__ import annotations

from pydantic import BaseModel


class KalshiHealthResponse(BaseModel):
    """GET /api/v1/kalshi/health response."""

    ok: bool
    latency_ms: float | None
    clock_skew_s: float | None
    base_url: str
    error: str | None = None


class KalshiCredentialsResponse(BaseModel):
    """GET /api/v1/kalshi/credentials/status response."""

    configured: bool
    key_id_present: bool
    private_key_present: bool
    base_url: str
    is_demo: bool


class KalshiEventResponse(BaseModel):
    """Single Kalshi event in a list or detail view."""

    event_ticker: str
    series_ticker: str
    title: str
    sub_title: str | None = None
    category: str | None = None
    alias_status: str | None = None
    fixture_id: str | None = None


class KalshiEventListResponse(BaseModel):
    """GET /api/v1/kalshi/events response."""

    events: list[KalshiEventResponse]
    total: int


class KalshiMarketResponse(BaseModel):
    """Single Kalshi market with current pricing."""

    ticker: str
    event_ticker: str
    floor_strike: str
    yes_bid: str
    no_bid: str
    yes_ask: str | None = None
    no_ask: str | None = None
    yes_bid_size: float | None = None
    yes_ask_size: float | None = None
    decimal_odds: str | None = None
    implied_probability: str | None = None


class KalshiEventDetailResponse(BaseModel):
    """GET /api/v1/kalshi/events/{event_ticker} response."""

    event: KalshiEventResponse
    markets: list[KalshiMarketResponse]


class KalshiMarketDetailResponse(BaseModel):
    """GET /api/v1/kalshi/markets/{ticker} response."""

    market: KalshiMarketResponse
    recent_snapshots: list[dict[str, object]]


class KalshiSeriesResponse(BaseModel):
    """Single series entry."""

    series_ticker: str
    title: str
    category: str | None = None


class KalshiSeriesListResponse(BaseModel):
    """GET /api/v1/kalshi/series response."""

    series: list[KalshiSeriesResponse]
