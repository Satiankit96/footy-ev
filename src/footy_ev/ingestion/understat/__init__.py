"""Understat per-match xG ingestion.

Pipeline mirrors ``ingestion/football_data``:

    source.py   →  fetch the league/season HTML page; immutable disk cache.
    parse.py    →  Pydantic models + regex extraction of the embedded JSON
                   blob + UTC kickoff conversion.
    loader.py   →  upsert into ``raw_understat_matches``; log drift.

Public surface kept minimal — exceptions live here so callers don't depend on
internal module layout.
"""

from __future__ import annotations


class UnderstatFetchError(Exception):
    """Raised when an Understat HTML fetch cannot complete after retries.

    Wraps transient network errors and permanent HTTP failures (4xx). Cache hits
    do NOT raise this — they short-circuit before the network attempt.
    """


class UnderstatParseError(Exception):
    """Raised when the Understat HTML payload doesn't contain the expected shape.

    Covers: regex miss for the ``var datesData = JSON.parse('...')`` block, JSON
    decode failure on the unquoted blob, and the post-parse sanity check
    (parsed value not a list, or fewer than ``MIN_EXPECTED_MATCHES_PER_SEASON``
    matches). All three usually indicate Understat changed their HTML — the
    frozen-fixture test is the primary tripwire for this.
    """


__all__ = ["UnderstatFetchError", "UnderstatParseError"]
