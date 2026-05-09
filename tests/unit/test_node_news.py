"""Unit test for the news-node stub (Phase 3 step 1 ships a no-op)."""

from __future__ import annotations

from footy_ev.orchestration.nodes.news import news_node


def test_news_node_returns_empty_deltas() -> None:
    assert news_node({}) == {"news_deltas": []}
