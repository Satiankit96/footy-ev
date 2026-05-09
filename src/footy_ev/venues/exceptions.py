"""Venue-specific exception hierarchy."""

from __future__ import annotations


class VenueError(Exception):
    """Base for all venue/adapter failures."""


class BetfairAuthError(VenueError):
    """Login or session-token refresh failed."""


class StaleResponseError(VenueError):
    """Venue response exceeded the staleness limit (BLUE_MAP §1.3)."""
