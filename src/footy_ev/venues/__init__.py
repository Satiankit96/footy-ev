"""Venue adapters: per-source clients that produce OddsSnapshot records.

Primary venue: Kalshi (US-legal, CFTC-regulated, NY operator).
"""

from footy_ev.venues.exceptions import StaleResponseError
from footy_ev.venues.kalshi import (
    KalshiClient,
    KalshiResponse,
    decimal_odds_to_price,
    price_to_decimal_odds,
)
from footy_ev.venues.resolution import (
    KalshiMarketResolution,
    cache_kalshi_resolution,
    resolve_kalshi_market,
)

__all__ = [
    "KalshiClient",
    "KalshiMarketResolution",
    "KalshiResponse",
    "StaleResponseError",
    "cache_kalshi_resolution",
    "decimal_odds_to_price",
    "price_to_decimal_odds",
    "resolve_kalshi_market",
]
