"""Frozen-header regression test for football-data.co.uk EPL 2024-2025.

The fixture ``E0_2425_header.txt`` is captured from a successful integration run
and locked to disk. This test asserts that the column registry covers every
column in that captured header — i.e. ``registry-supported ⊇ frozen header``.

Today's reality: the 2024-2025 header has many columns the registry does not
yet know about (closing-odds variants, 1xBet, Betfair non-Exchange, etc.). Those
columns currently flow through the ``extras`` MAP. Migration 002 will promote
them to typed columns; until then this test is **expected to fail** and is
marked ``xfail(strict=True)`` so the suite stays green AND the test goes red
the day someone removes the ``xfail`` decorator after migration 002 lands.

When migration 002 is complete and the registry has been extended, drop the
``xfail`` decorator. If the test then fails for a real reason (registry missing
a column the source still has), that's the regression behavior we want.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from footy_ev.ingestion.football_data.columns import SOURCE_NAMES

FROZEN_HEADER_PATH = (
    Path(__file__).resolve().parent.parent / "fixtures" / "football_data" / "E0_2425_header.txt"
)


def _read_frozen_header() -> list[str]:
    text = FROZEN_HEADER_PATH.read_text(encoding="utf-8-sig").rstrip("\r\n")
    return text.split(",")


def test_frozen_header_file_exists_and_is_nonempty() -> None:
    """Sanity check on the fixture itself."""
    assert FROZEN_HEADER_PATH.exists()
    cols = _read_frozen_header()
    assert len(cols) > 50, f"frozen header looks too short: {len(cols)} columns"
    # First column is always Div on football-data.co.uk top-five-league CSVs.
    assert cols[0] == "Div"


@pytest.mark.xfail(  # type: ignore[misc]
    strict=True,
    reason="migration 002 pending: registry does not yet cover all 2024-2025 source columns",
)
def test_registry_covers_frozen_header() -> None:
    """``registry-supported ⊇ frozen header``: every header column is in the registry.

    Fails loudly when football-data.co.uk adds a column we haven't registered.
    """
    header_cols = set(_read_frozen_header())
    missing_from_registry = header_cols - SOURCE_NAMES
    assert not missing_from_registry, (
        f"{len(missing_from_registry)} columns in 2024-2025 header are not in the "
        f"registry: {sorted(missing_from_registry)}"
    )
