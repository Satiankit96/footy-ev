"""Venue adapters: per-source clients that produce OddsSnapshot records.

Phase 3 step 1 ships the Betfair Exchange Delayed-API client only; future
steps add sharp-fixed-odds and soft-book adapters per BLUE_MAP §5.
Phase 3 step 3 adds query-time entity resolution (Betfair → warehouse).
"""

from footy_ev.venues.betfair import BetfairClient, BetfairResponse
from footy_ev.venues.exceptions import BetfairAuthError, StaleResponseError
from footy_ev.venues.resolution import (
    EventResolution,
    cache_resolution,
    parse_betfair_event_name,
    parse_betfair_opendate,
    resolve_event,
    resolve_event_from_meta,
    resolve_market,
    resolve_selection,
)

__all__ = [
    "BetfairAuthError",
    "BetfairClient",
    "BetfairResponse",
    "EventResolution",
    "StaleResponseError",
    "cache_resolution",
    "parse_betfair_event_name",
    "parse_betfair_opendate",
    "resolve_event",
    "resolve_event_from_meta",
    "resolve_market",
    "resolve_selection",
]
