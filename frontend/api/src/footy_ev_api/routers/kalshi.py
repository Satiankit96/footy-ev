"""Kalshi integration endpoints: health, credentials, events, markets."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

import duckdb
from fastapi import APIRouter, Depends, Query

from footy_ev_api.adapters.kalshi import (
    check_health,
    compute_decimal_odds,
    compute_implied_probability,
    credentials_status,
    get_kalshi_client,
    get_market,
    list_events,
    list_markets,
)
from footy_ev_api.auth import get_current_operator
from footy_ev_api.schemas.kalshi import (
    KalshiCredentialsResponse,
    KalshiEventDetailResponse,
    KalshiEventListResponse,
    KalshiEventResponse,
    KalshiHealthResponse,
    KalshiMarketDetailResponse,
    KalshiMarketResponse,
    KalshiSeriesListResponse,
    KalshiSeriesResponse,
)
from footy_ev_api.settings import Settings

_LOG = logging.getLogger(__name__)

router = APIRouter(prefix="/kalshi", tags=["kalshi"])


def _warehouse_path() -> Path:
    settings = Settings()
    return Path(settings.warehouse_path)


def _query_aliases(event_tickers: list[str]) -> dict[str, dict[str, str | None]]:
    """Query kalshi_event_aliases for resolved fixture IDs."""
    db_path = _warehouse_path()
    if not db_path.exists():
        return {}
    try:
        con = duckdb.connect(str(db_path), read_only=True)
        try:
            placeholders = ", ".join(["?"] * len(event_tickers))
            rows = con.execute(
                f"SELECT event_ticker, fixture_id FROM kalshi_event_aliases WHERE event_ticker IN ({placeholders})",  # noqa: S608
                event_tickers,
            ).fetchall()
            return {row[0]: {"alias_status": "resolved", "fixture_id": row[1]} for row in rows}
        except duckdb.CatalogException:
            return {}
        finally:
            con.close()
    except Exception:
        _LOG.debug("Warehouse query failed", exc_info=True)
        return {}


def _query_snapshots(market_ticker: str) -> list[dict[str, object]]:
    """Query recent odds_snapshots for a market (last 24h)."""
    db_path = _warehouse_path()
    if not db_path.exists():
        return []
    try:
        con = duckdb.connect(str(db_path), read_only=True)
        try:
            rows = con.execute(
                "SELECT * FROM odds_snapshots WHERE ticker = ? AND snapshot_ts > now() - INTERVAL '24 hours' ORDER BY snapshot_ts DESC LIMIT 100",
                [market_ticker],
            ).fetchdf()
            return rows.to_dict(orient="records")  # type: ignore[no-any-return]
        except (duckdb.CatalogException, Exception):
            return []
        finally:
            con.close()
    except Exception:
        return []


def _market_to_response(m: Any) -> KalshiMarketResponse:
    """Convert a KalshiMarket model to our response schema."""
    yes_bid = m.yes_bid_dollars
    no_bid = m.no_bid_dollars
    return KalshiMarketResponse(
        ticker=m.ticker,
        event_ticker=m.event_ticker,
        floor_strike=str(m.floor_strike),
        yes_bid=str(yes_bid),
        no_bid=str(no_bid),
        yes_ask=str(m.yes_ask_dollars) if m.yes_ask_dollars else None,
        no_ask=str(m.no_ask_dollars) if m.no_ask_dollars else None,
        yes_bid_size=m.yes_bid_size_fp if m.yes_bid_size_fp else None,
        yes_ask_size=m.yes_ask_size_fp if m.yes_ask_size_fp else None,
        decimal_odds=compute_decimal_odds(yes_bid),
        implied_probability=compute_implied_probability(yes_bid),
    )


@router.get("/credentials/status", response_model=KalshiCredentialsResponse)
async def kalshi_credentials(
    _operator: str = Depends(get_current_operator),
) -> KalshiCredentialsResponse:
    """Check credential configuration without exposing secrets."""
    data = credentials_status()
    return KalshiCredentialsResponse(**data)


@router.get("/health", response_model=KalshiHealthResponse)
async def kalshi_health(
    _operator: str = Depends(get_current_operator),
) -> KalshiHealthResponse:
    """Ping Kalshi API and report latency + clock skew."""
    client = get_kalshi_client()
    data = check_health(client)
    return KalshiHealthResponse(**data)


@router.get("/series", response_model=KalshiSeriesListResponse)
async def kalshi_series(
    _operator: str = Depends(get_current_operator),
) -> KalshiSeriesListResponse:
    """List available series. Returns a static list for now."""
    return KalshiSeriesListResponse(
        series=[
            KalshiSeriesResponse(
                series_ticker="KXEPLTOTAL",
                title="EPL Total Goals",
                category="football",
            ),
        ],
    )


@router.get("/events", response_model=KalshiEventListResponse)
async def kalshi_events(
    _operator: str = Depends(get_current_operator),
    series: str = Query(default="KXEPLTOTAL"),
    status: str = Query(default="open"),
    limit: int = Query(default=100, ge=1, le=500),
) -> KalshiEventListResponse:
    """List events for a Kalshi series with alias status from warehouse."""
    client = get_kalshi_client()
    raw_events = list_events(client, series_ticker=series, status=status, limit=limit)

    tickers = [e.event_ticker for e in raw_events]
    aliases = _query_aliases(tickers) if tickers else {}

    events = []
    for e in raw_events:
        alias_info = aliases.get(e.event_ticker, {})
        events.append(
            KalshiEventResponse(
                event_ticker=e.event_ticker,
                series_ticker=e.series_ticker,
                title=e.title,
                sub_title=e.sub_title or None,
                category=e.category or None,
                alias_status=alias_info.get("alias_status"),
                fixture_id=alias_info.get("fixture_id"),
            )
        )

    return KalshiEventListResponse(events=events, total=len(events))


@router.get("/events/{event_ticker}", response_model=KalshiEventDetailResponse)
async def kalshi_event_detail(
    event_ticker: str,
    _operator: str = Depends(get_current_operator),
) -> KalshiEventDetailResponse:
    """Event detail with all markets under it."""
    client = get_kalshi_client()

    raw_events = list_events(
        client, series_ticker=event_ticker.split("-")[0], status="open", limit=200
    )
    event_data = next((e for e in raw_events if e.event_ticker == event_ticker), None)

    aliases = _query_aliases([event_ticker])
    alias_info = aliases.get(event_ticker, {})

    if event_data:
        event = KalshiEventResponse(
            event_ticker=event_data.event_ticker,
            series_ticker=event_data.series_ticker,
            title=event_data.title,
            sub_title=event_data.sub_title or None,
            category=event_data.category or None,
            alias_status=alias_info.get("alias_status"),
            fixture_id=alias_info.get("fixture_id"),
        )
    else:
        event = KalshiEventResponse(
            event_ticker=event_ticker,
            series_ticker=event_ticker.split("-")[0],
            title=event_ticker,
            alias_status=alias_info.get("alias_status"),
            fixture_id=alias_info.get("fixture_id"),
        )

    raw_markets = list_markets(client, event_ticker=event_ticker)
    markets = [_market_to_response(m) for m in raw_markets]

    return KalshiEventDetailResponse(event=event, markets=markets)


@router.get("/markets/{ticker}", response_model=KalshiMarketDetailResponse)
async def kalshi_market_detail(
    ticker: str,
    _operator: str = Depends(get_current_operator),
) -> KalshiMarketDetailResponse:
    """Single market detail with current prices and recent snapshots."""
    client = get_kalshi_client()
    raw_market = get_market(client, ticker)
    market = _market_to_response(raw_market)
    snapshots = _query_snapshots(ticker)
    return KalshiMarketDetailResponse(market=market, recent_snapshots=snapshots)
