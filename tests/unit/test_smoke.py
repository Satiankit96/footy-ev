"""Smoke test to verify the package imports."""

import footy_ev


def test_version() -> None:
    assert footy_ev.__version__ == "0.0.1"
