"""LangGraph StateGraph assembly for the paper-trading pipeline.

Topology (BLUE_MAP s2.3):
    START -> [scraper, news] (parallel, fan-in via add reducer)
          -> analyst -> pricing -> risk -> execution -> END

The graph is checkpointed to a SQLite file (default
data/langgraph_checkpoints.sqlite). Cyclical re-runs (s2.4) are
deferred to Phase 3 step 2.
"""

from __future__ import annotations

import sqlite3
from collections.abc import Callable
from functools import partial
from pathlib import Path
from typing import Any

import duckdb
from langgraph.checkpoint.sqlite import SqliteSaver
from langgraph.graph import END, START, StateGraph

from footy_ev.orchestration.nodes import (
    analyst_node,
    execution_node,
    news_node,
    pricing_node,
    risk_node,
    scraper_node,
)
from footy_ev.orchestration.state import BettingState
from footy_ev.venues import BetfairClient

DEFAULT_CHECKPOINT_PATH = Path("data/langgraph_checkpoints.sqlite")


def build_graph(
    *,
    betfair: BetfairClient,
    market_id_map: dict[str, list[str]] | None,
    event_meta_map: dict[str, dict[str, Any]] | None = None,
    score_fn: Callable[..., list[dict[str, Any]]] | None,
    warehouse_con: duckdb.DuckDBPyConnection | None,
) -> Any:
    """Compile the StateGraph with the required runtime dependencies bound.

    The dependencies (Betfair client, score function, warehouse connection)
    are partial-applied to the node callables here so the graph itself
    sees plain `state -> dict` functions and LangGraph's typing is happy.

    Args:
        betfair: authenticated BetfairClient.
        market_id_map: Betfair event ID → list of market IDs.
        event_meta_map: Betfair event ID → event metadata dict (name, openDate,
            countryCode). Passed to the scraper for entity resolution.
        score_fn: callable to score fixtures; injected into analyst node.
        warehouse_con: open DuckDB connection for DB reads/writes in nodes.
    """
    g: StateGraph = StateGraph(BettingState)

    g.add_node(
        "scraper",
        partial(
            scraper_node,
            client=betfair,
            market_id_map=market_id_map,
            event_meta_map=event_meta_map,
            con=warehouse_con,
        ),
    )
    g.add_node("news", news_node)
    g.add_node("analyst", partial(analyst_node, score_fn=score_fn))
    g.add_node("pricing", pricing_node)
    g.add_node("risk", risk_node)
    g.add_node("execution", partial(execution_node, con=warehouse_con))

    g.add_edge(START, "scraper")
    g.add_edge(START, "news")
    g.add_edge("scraper", "analyst")
    g.add_edge("news", "analyst")
    g.add_edge("analyst", "pricing")
    g.add_edge("pricing", "risk")
    g.add_edge("risk", "execution")
    g.add_edge("execution", END)

    return g


def compile_graph(
    g: Any,
    *,
    checkpoint_path: Path = DEFAULT_CHECKPOINT_PATH,
) -> tuple[Any, sqlite3.Connection]:
    """Compile with a SqliteSaver bound to the given file.

    Returns (compiled_graph, sqlite_conn). The caller owns the sqlite
    connection's lifetime and must close it after the graph invocation
    completes (we deliberately do not use the from_conn_string context
    manager because we need the connection to outlive that scope).
    """
    checkpoint_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(checkpoint_path), check_same_thread=False)
    saver = SqliteSaver(conn)
    compiled = g.compile(checkpointer=saver)
    return compiled, conn
