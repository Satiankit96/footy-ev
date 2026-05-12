"""Venue adapters: per-source clients that produce OddsSnapshot records.

Phase 3 step 5a adds Kalshi as the primary venue (US-legal, operator is
NY-based). Betfair remains importable but is deprecated — see betfair.py.
Phase 3 step 5b will complete KalshiClient by wiring RSA-PSS/SHA256 auth.
"""

from footy_ev.venues.betfair import BetfairClient, BetfairResponse
from footy_ev.venues.exceptions import BetfairAuthError, StaleResponseError
from footy_ev.venues.kalshi import (
    KalshiClient,
    KalshiResponse,
    decimal_odds_to_price,
    price_to_decimal_odds,
)
from footy_ev.venues.resolution import (
    EventResolution,
    KalshiMarketResolution,
    cache_kalshi_resolution,
    cache_resolution,
    parse_betfair_event_name,
    parse_betfair_opendate,
    resolve_event,
    resolve_event_from_meta,
    resolve_kalshi_market,
    resolve_market,
    resolve_selection,
)

__all__ = [
    "BetfairAuthError",
    "BetfairClient",
    "BetfairResponse",
    "EventResolution",
    "KalshiClient",
    "KalshiMarketResolution",
    "KalshiResponse",
    "StaleResponseError",
    "cache_kalshi_resolution",
    "cache_resolution",
    "decimal_odds_to_price",
    "parse_betfair_event_name",
    "parse_betfair_opendate",
    "price_to_decimal_odds",
    "resolve_event",
    "resolve_event_from_meta",
    "resolve_kalshi_market",
    "resolve_market",
    "resolve_selection",
]
