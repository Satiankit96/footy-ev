"""Unit tests for KalshiClient stub and price helpers.

All tests are offline — no network access, no real RSA keys.
Covers:
  - price_to_decimal_odds / decimal_odds_to_price round-trips
  - _KalshiCredentialError raised at init when env vars missing or PEM unreadable
  - KalshiClient.from_env() path errors
  - get_events / get_markets / get_market_orderbook all raise NotImplementedError
"""

from __future__ import annotations

from pathlib import Path

import pytest

from footy_ev.venues.kalshi import (
    KalshiClient,
    KalshiResponse,
    _KalshiCredentialError,
    decimal_odds_to_price,
    price_to_decimal_odds,
)

# ---------------------------------------------------------------------------
# Price helpers
# ---------------------------------------------------------------------------


def test_price_to_decimal_odds_basic() -> None:
    odds = price_to_decimal_odds(0.5)
    assert abs(odds - 2.0) < 1e-9


def test_price_to_decimal_odds_55_cents() -> None:
    odds = price_to_decimal_odds(0.55)
    assert abs(odds - (1.0 / 0.55)) < 1e-9


def test_price_to_decimal_odds_rejects_zero() -> None:
    with pytest.raises(ValueError, match="must be in"):
        price_to_decimal_odds(0.0)


def test_price_to_decimal_odds_rejects_one() -> None:
    with pytest.raises(ValueError, match="must be in"):
        price_to_decimal_odds(1.0)


def test_price_to_decimal_odds_rejects_above_one() -> None:
    with pytest.raises(ValueError, match="must be in"):
        price_to_decimal_odds(1.5)


def test_decimal_odds_to_price_roundtrip() -> None:
    for p in [0.30, 0.45, 0.55, 0.70, 0.80]:
        odds = price_to_decimal_odds(p)
        back = decimal_odds_to_price(odds)
        assert abs(back - p) < 0.01, f"roundtrip failed for p={p}"


def test_decimal_odds_to_price_clamps_to_range() -> None:
    # odds=1.001 → price would be ~0.999, should clamp to 0.99
    assert decimal_odds_to_price(1.001) == 0.99
    # odds=100 → price would be 0.01, clamp holds
    assert decimal_odds_to_price(100.0) == 0.01


def test_decimal_odds_to_price_rejects_lte_one() -> None:
    with pytest.raises(ValueError, match="must be > 1.0"):
        decimal_odds_to_price(1.0)


# ---------------------------------------------------------------------------
# Credential error
# ---------------------------------------------------------------------------


def test_from_env_raises_credential_error_no_key_id(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv("KALSHI_API_KEY_ID", raising=False)
    pem = tmp_path / "key.pem"
    pem.write_bytes(b"fake_pem")
    with pytest.raises(_KalshiCredentialError, match="KALSHI_API_KEY_ID"):
        KalshiClient.from_env(pem_path=pem)


def test_from_env_raises_credential_error_missing_pem(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setenv("KALSHI_API_KEY_ID", "test-key-id")
    missing_pem = tmp_path / "nonexistent.pem"
    with pytest.raises(_KalshiCredentialError, match="Cannot read"):
        KalshiClient.from_env(pem_path=missing_pem)


# ---------------------------------------------------------------------------
# Stub raises NotImplementedError
# ---------------------------------------------------------------------------


@pytest.fixture
def stub_client(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> KalshiClient:
    monkeypatch.setenv("KALSHI_API_KEY_ID", "test-key-id")
    pem = tmp_path / "key.pem"
    pem.write_bytes(b"fake_pem_bytes")
    return KalshiClient.from_env(pem_path=pem)


def test_get_events_raises_not_implemented(stub_client: KalshiClient) -> None:
    with pytest.raises(NotImplementedError, match="RSA"):
        stub_client.get_events()


def test_get_markets_raises_not_implemented(stub_client: KalshiClient) -> None:
    with pytest.raises(NotImplementedError, match="RSA"):
        stub_client.get_markets(event_ticker="KXEPLTOTAL-26MAY01LEEBUR")


def test_get_market_orderbook_raises_not_implemented(stub_client: KalshiClient) -> None:
    with pytest.raises(NotImplementedError, match="RSA"):
        stub_client.get_market_orderbook(ticker="KXEPLTOTAL-26MAY01LEEBUR-T2.5")


# ---------------------------------------------------------------------------
# KalshiResponse dataclass
# ---------------------------------------------------------------------------


def test_kalshi_response_is_frozen() -> None:
    from datetime import UTC, datetime

    r = KalshiResponse(payload={"foo": "bar"}, received_at=datetime.now(tz=UTC))
    with pytest.raises((AttributeError, TypeError)):
        r.payload = "mutated"  # type: ignore[misc]
