"""Unit tests for KalshiClient RSA-PSS/SHA256 signing (Phase 3 step 5b).

All tests are offline — no network access. A fresh 2048-bit RSA keypair is
generated in-memory per test using the cryptography library. The operator's
production PEM is never touched.

Covers:
  - _sign_request produces correct-length base64 output (344 chars for 2048-bit)
  - Corrupted PEM raises _KalshiSigningError
  - Non-RSA key (EC) raises _KalshiSigningError
  - _signing_headers returns the three required Kalshi auth keys
  - KALSHI-ACCESS-TIMESTAMP is a numeric string
  - KALSHI-ACCESS-SIGNATURE is valid base64 of correct length
  - KALSHI-ACCESS-KEY matches api_key_id
  - Signing is deterministic-ish: different calls produce different signatures
    (salted PSS — each signing uses a random salt, so same message ≠ same sig)
"""

from __future__ import annotations

import base64
import os
from pathlib import Path

import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import ec, rsa

from footy_ev.venues.kalshi import (
    KalshiClient,
    _KalshiSigningError,
)

# ---------------------------------------------------------------------------
# Test key generation helpers
# ---------------------------------------------------------------------------


def _make_rsa_pem(key_size: int = 2048) -> bytes:
    """Generate a fresh RSA private key and return it as a PEM bytes."""
    key = rsa.generate_private_key(public_exponent=65537, key_size=key_size)
    return key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption(),
    )


def _make_ec_pem() -> bytes:
    """Generate a fresh EC private key and return it as PEM bytes."""
    key = ec.generate_private_key(ec.SECP256R1())
    return key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption(),
    )


def _make_client(pem: bytes, api_key_id: str = "test-key-id-abc") -> KalshiClient:
    """Construct a KalshiClient from raw PEM bytes without touching the filesystem."""
    return KalshiClient(api_key_id=api_key_id, private_key_pem=pem)


# ---------------------------------------------------------------------------
# _sign_request output length
# ---------------------------------------------------------------------------


def test_sign_request_output_is_base64_of_expected_length() -> None:
    """2048-bit RSA → 256-byte signature → ~344-char base64 string."""
    pem = _make_rsa_pem(2048)
    client = _make_client(pem)
    sig = client._sign_request("GET", "/trade-api/v2/events", 1_700_000_000_000)
    # Must be valid base64
    raw = base64.b64decode(sig)
    assert len(raw) == 256, f"Expected 256 raw bytes, got {len(raw)}"
    # Base64 encoding of 256 bytes = ceil(256/3)*4 = 344 chars
    assert len(sig) == 344, f"Expected 344 base64 chars, got {len(sig)}"


def test_sign_request_4096_bit_produces_512_byte_sig() -> None:
    """4096-bit RSA → 512-byte raw signature → 684-char base64."""
    pem = _make_rsa_pem(4096)
    client = _make_client(pem)
    sig = client._sign_request("GET", "/trade-api/v2/events", 1_700_000_000_001)
    raw = base64.b64decode(sig)
    assert len(raw) == 512
    assert len(sig) == 684


# ---------------------------------------------------------------------------
# Error paths
# ---------------------------------------------------------------------------


def test_corrupted_pem_raises_signing_error() -> None:
    """Non-PEM bytes cause _KalshiSigningError on first sign call."""
    client = _make_client(b"this-is-not-a-pem")
    with pytest.raises(_KalshiSigningError, match="Cannot load RSA private key"):
        client._sign_request("GET", "/trade-api/v2/events", 1_700_000_000_000)


def test_empty_pem_raises_signing_error() -> None:
    """Empty PEM bytes cause _KalshiSigningError."""
    client = _make_client(b"")
    with pytest.raises(_KalshiSigningError, match="empty"):
        client._sign_request("GET", "/trade-api/v2/events", 1_700_000_000_000)


def test_non_rsa_key_raises_signing_error() -> None:
    """EC key causes _KalshiSigningError (Kalshi requires RSA)."""
    ec_pem = _make_ec_pem()
    client = _make_client(ec_pem)
    with pytest.raises(_KalshiSigningError, match="not RSA"):
        client._sign_request("GET", "/trade-api/v2/events", 1_700_000_000_000)


# ---------------------------------------------------------------------------
# Key caching — loading happens only once
# ---------------------------------------------------------------------------


def test_signing_key_is_cached_after_first_call() -> None:
    """_signing_key is None before first sign, non-None after."""
    pem = _make_rsa_pem()
    client = _make_client(pem)
    assert client._signing_key is None
    client._sign_request("GET", "/trade-api/v2/events", 1_700_000_000_000)
    assert client._signing_key is not None


# ---------------------------------------------------------------------------
# _signing_headers
# ---------------------------------------------------------------------------


def test_signing_headers_has_required_kalshi_keys() -> None:
    """_signing_headers returns the three required Kalshi auth headers."""
    pem = _make_rsa_pem()
    client = _make_client(pem, api_key_id="my-key-uuid")
    headers = client._signing_headers("GET", "/trade-api/v2/series")
    assert "KALSHI-ACCESS-KEY" in headers
    assert "KALSHI-ACCESS-TIMESTAMP" in headers
    assert "KALSHI-ACCESS-SIGNATURE" in headers


def test_signing_headers_key_matches_api_key_id() -> None:
    """KALSHI-ACCESS-KEY equals the api_key_id passed at construction."""
    pem = _make_rsa_pem()
    client = _make_client(pem, api_key_id="my-unique-key-id-9999")
    headers = client._signing_headers("GET", "/trade-api/v2/series")
    assert headers["KALSHI-ACCESS-KEY"] == "my-unique-key-id-9999"


def test_signing_headers_timestamp_is_numeric() -> None:
    """KALSHI-ACCESS-TIMESTAMP must be a millisecond epoch integer string."""
    pem = _make_rsa_pem()
    client = _make_client(pem)
    headers = client._signing_headers("GET", "/trade-api/v2/series")
    ts_str = headers["KALSHI-ACCESS-TIMESTAMP"]
    assert ts_str.isdigit(), f"Timestamp not numeric: {ts_str!r}"
    ts_ms = int(ts_str)
    # Should be roughly now in milliseconds (between year 2020 and 2100)
    assert 1_580_000_000_000 < ts_ms < 4_000_000_000_000, f"Timestamp out of range: {ts_ms}"


def test_signing_headers_signature_is_valid_base64() -> None:
    """KALSHI-ACCESS-SIGNATURE must be valid base64 of correct RSA length."""
    pem = _make_rsa_pem(2048)
    client = _make_client(pem)
    headers = client._signing_headers("GET", "/trade-api/v2/series")
    sig = headers["KALSHI-ACCESS-SIGNATURE"]
    raw = base64.b64decode(sig)
    assert len(raw) == 256, f"Expected 256 raw bytes, got {len(raw)}"


def test_signing_headers_pss_salt_produces_different_sigs_per_call() -> None:
    """PSS uses a random salt so two calls on the same message produce different sigs."""
    pem = _make_rsa_pem()
    client = _make_client(pem)
    sig1 = client._sign_request("GET", "/trade-api/v2/events", 1_700_000_000_000)
    sig2 = client._sign_request("GET", "/trade-api/v2/events", 1_700_000_000_000)
    assert sig1 != sig2, "PSS should produce different sigs on repeated calls (random salt)"


# ---------------------------------------------------------------------------
# Optional live demo test (gated on FOOTY_EV_KALSHI_DEMO=1)
# ---------------------------------------------------------------------------

_DEMO_GATE = "FOOTY_EV_KALSHI_DEMO"


@pytest.mark.skipif(
    os.environ.get(_DEMO_GATE) != "1",
    reason=(
        f"set {_DEMO_GATE}=1 and KALSHI_API_KEY_ID + data/kalshi_private_key.pem "
        "to run the live demo signing verification"
    ),
)
def test_signing_headers_accepted_by_demo_endpoint(tmp_path: Path) -> None:
    """Verify signing headers produce HTTP 200 (not 401) on demo /series endpoint."""
    import httpx as _httpx

    from footy_ev.venues.kalshi import DEMO_BASE_URL, _KalshiCredentialError

    try:
        client = KalshiClient.from_env(base_url=DEMO_BASE_URL)
    except _KalshiCredentialError as exc:
        pytest.skip(f"Kalshi credentials not configured: {exc}")

    path = "/trade-api/v2/series"
    headers = client._signing_headers("GET", path)
    url = DEMO_BASE_URL.rstrip("/") + "/series"
    resp = _httpx.get(url, headers=headers, timeout=15.0)
    assert resp.status_code == 200, (
        f"Demo endpoint returned {resp.status_code}. Body: {resp.text[:300]}"
    )
