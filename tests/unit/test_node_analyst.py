"""Unit tests for orchestration.nodes.analyst."""

from __future__ import annotations

from datetime import UTC, datetime

from footy_ev.orchestration.nodes.analyst import analyst_node


def test_analyst_short_circuits_when_breaker_tripped() -> None:
    out = analyst_node({"circuit_breaker_tripped": True})
    assert out == {"model_probs": []}


def test_analyst_returns_empty_without_score_fn() -> None:
    out = analyst_node({"fixtures_to_process": ["x"], "as_of": datetime.now(tz=UTC)})
    assert out == {"model_probs": []}


def test_analyst_invokes_score_fn_and_wraps_results() -> None:
    def fake_score(fixtures, as_of):
        return [
            {
                "fixture_id": "ARS-LIV",
                "market": "ou_2.5",
                "selection": "over",
                "p_calibrated": 0.55,
                "p_raw": 0.55,
                "sigma_p": 0.02,
                "model_version": "xgb_ou25_v1",
                "run_id": "r1",
            }
        ]

    out = analyst_node(
        {"fixtures_to_process": ["ARS-LIV"], "as_of": datetime.now(tz=UTC)},
        score_fn=fake_score,
    )
    assert len(out["model_probs"]) == 1
    p = out["model_probs"][0]
    assert p.fixture_id == "ARS-LIV"
    assert p.p_calibrated == 0.55
    assert p.run_id == "r1"
    assert len(p.features_hash) == 16  # truncated sha256
