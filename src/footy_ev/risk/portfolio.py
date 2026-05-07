"""Portfolio-level bet caps per BLUE_MAP §4.2.

Applies three caps to a list of candidate bets:
  1. Per-day exposure cap (default 10% of bankroll).
  2. Per-fixture exposure cap (default 3% of bankroll across all markets).
  3. Correlated-bet collapsing: bets on the same fixture within
     `correlation_threshold` are treated as one position for cap purposes.

Input/output: list of candidate dicts. Each dict must contain at minimum:
    fixture_id   str
    market       str
    selection    str
    stake_gbp    Decimal
    odds_quoted  float

Returns the approved subset with stakes possibly downsized, preserving all
other keys from the input dicts.
"""

from __future__ import annotations

from decimal import ROUND_HALF_UP, Decimal
from typing import Any

_PENNY = Decimal("0.01")


def _scale_stake(stake: Decimal, scale: float) -> Decimal:
    if scale >= 1.0:
        return stake
    scaled = Decimal(str(float(stake) * scale))
    return scaled.quantize(_PENNY, rounding=ROUND_HALF_UP)


def portfolio_caps(
    candidates: list[dict[str, Any]],
    bankroll: float,
    *,
    per_day_cap_pct: float = 0.10,
    per_fixture_cap_pct: float = 0.03,
    correlation_threshold: float = 0.7,
) -> list[dict[str, Any]]:
    """Apply portfolio-level exposure caps to a list of candidate bets.

    Args:
        candidates: list of candidate dicts, each with fixture_id, market,
            selection, stake_gbp (Decimal), odds_quoted. Sorted by expected
            value descending (caller's responsibility) so highest-EV bets
            consume cap budget first.
        bankroll: current bankroll in currency units.
        per_day_cap_pct: maximum total daily exposure as fraction of bankroll.
        per_fixture_cap_pct: maximum exposure on any single fixture as
            fraction of bankroll.
        correlation_threshold: fraction at which two bets on the same fixture
            are considered correlated and collapsed into one position.
            Currently implemented as: any two bets on the SAME fixture_id
            are treated as correlated (conservative; §4.2 example).

    Returns:
        Approved bets with stakes adjusted downward where caps bind.
        Zero-stake bets are excluded from the output.
    """
    day_cap = Decimal(str(bankroll * per_day_cap_pct)).quantize(_PENNY, rounding=ROUND_HALF_UP)
    fixture_cap = Decimal(str(bankroll * per_fixture_cap_pct)).quantize(
        _PENNY, rounding=ROUND_HALF_UP
    )

    day_spent = Decimal("0.00")
    fixture_spent: dict[str, Decimal] = {}

    approved: list[dict[str, Any]] = []

    for candidate in candidates:
        fixture_id: str = candidate["fixture_id"]
        raw_stake: Decimal = candidate["stake_gbp"]

        if raw_stake <= Decimal("0.00"):
            continue

        already_on_fixture = fixture_spent.get(fixture_id, Decimal("0.00"))
        day_remaining = day_cap - day_spent
        fixture_remaining = fixture_cap - already_on_fixture

        # Correlated: bets on the same fixture count against the same
        # fixture cap bucket, regardless of market/selection.
        headroom = min(day_remaining, fixture_remaining)

        if headroom <= Decimal("0.00"):
            continue

        actual_stake = min(raw_stake, headroom)
        if actual_stake <= Decimal("0.00"):
            continue

        out = dict(candidate)
        out["stake_gbp"] = actual_stake
        out["per_bet_cap_hit"] = actual_stake < raw_stake
        out["portfolio_cap_hit"] = actual_stake < raw_stake

        approved.append(out)
        day_spent += actual_stake
        fixture_spent[fixture_id] = already_on_fixture + actual_stake

    return approved


if __name__ == "__main__":
    from decimal import Decimal

    bets = [
        {
            "fixture_id": "f1",
            "market": "ou_2.5",
            "selection": "over",
            "stake_gbp": Decimal("30.00"),
            "odds_quoted": 2.1,
        },
        {
            "fixture_id": "f1",
            "market": "btts",
            "selection": "yes",
            "stake_gbp": Decimal("30.00"),
            "odds_quoted": 1.8,
        },
        {
            "fixture_id": "f2",
            "market": "ou_2.5",
            "selection": "over",
            "stake_gbp": Decimal("20.00"),
            "odds_quoted": 2.0,
        },
    ]
    result = portfolio_caps(bets, bankroll=1000.0)
    for b in result:
        print(b["fixture_id"], b["market"], b["stake_gbp"], b.get("portfolio_cap_hit"))
    print("smoke: OK")
