"""Venue adapters: per-source clients that produce OddsSnapshot records.

Phase 3 step 1 ships the Betfair Exchange Delayed-API client only; future
steps add sharp-fixed-odds and soft-book adapters per BLUE_MAP §5.
"""

from footy_ev.venues.betfair import BetfairClient, BetfairResponse
from footy_ev.venues.exceptions import BetfairAuthError, StaleResponseError

__all__ = [
    "BetfairAuthError",
    "BetfairClient",
    "BetfairResponse",
    "StaleResponseError",
]
