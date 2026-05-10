"""Streamlit dashboard — footy-ev read-only warehouse UI.

Pages (sidebar nav):
  Overview        — list all backtest runs, click to drilldown
  Run Detail      — verdict card, edge by season, reliability, feature heatmap, bet table
  CLV Explorer    — cross-run aggregated CLV with filters
  Feature Stability — per-feature permutation importance trajectory across folds

Launch:
    uv run streamlit run dashboard/app.py
Or via make.ps1:
    .\\make.ps1 dashboard
"""

from __future__ import annotations

import sys
from pathlib import Path

# Streamlit runs this file as a script and puts only `dashboard/` on sys.path,
# so `from dashboard import ...` would fail. Prepend the project root so the
# package is importable regardless of how the script is invoked.
_PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------
# Resolve relative to this file so the dashboard works regardless of cwd
# (Streamlit does not chdir into the script's directory). An override path
# can be set via the FOOTY_EV_DUCKDB env var.
import os  # noqa: E402

import duckdb  # noqa: E402  -- import after sys.path tweak above
import polars as pl  # noqa: E402
import streamlit as st  # noqa: E402

from dashboard import charts, queries  # noqa: E402

_DEFAULT_DB_PATH = _PROJECT_ROOT / "data" / "warehouse" / "footy_ev.duckdb"
DB_PATH = Path(os.environ.get("FOOTY_EV_DUCKDB") or _DEFAULT_DB_PATH).resolve()

st.set_page_config(
    page_title="footy-ev dashboard",
    page_icon="⚽",
    layout="wide",
)

VERDICT_BADGE = {
    "GO": "🟢 GO",
    "MARGINAL_SIGNAL": "🟡 MARGINAL_SIGNAL",
    "NO_GO": "🔴 NO_GO",
    "PRELIMINARY_SIGNAL": "⚪ PRELIMINARY_SIGNAL",
    "INSUFFICIENT_SAMPLE": "⚪ INSUFFICIENT_SAMPLE",
}

VERDICT_COLORS = charts.VERDICT_COLORS


# ---------------------------------------------------------------------------
# DB connection (read-only, cached for the session)
# ---------------------------------------------------------------------------


@st.cache_resource
def _get_con() -> duckdb.DuckDBPyConnection:
    if not DB_PATH.exists():
        st.error(f"Warehouse not found at {DB_PATH}. Run a backtest first.")
        st.stop()

    # Apply pending migrations once with a writable handle (idempotent —
    # every migration uses CREATE TABLE IF NOT EXISTS). This handles the
    # case where the warehouse was created before a new migration landed
    # (e.g. migration 009 paper_trading on a pre-Phase-3 warehouse).
    # If another process holds the file we silently fall through; the
    # read-only handle still works for already-applied tables and
    # surfaces a clear DuckDB error for any missing table.
    try:
        from footy_ev.db import apply_migrations, apply_views

        write_con = duckdb.connect(str(DB_PATH))
        try:
            apply_migrations(write_con)
            apply_views(write_con)
        finally:
            write_con.close()
    except duckdb.IOException:
        pass

    return duckdb.connect(str(DB_PATH), read_only=True)


def get_con() -> duckdb.DuckDBPyConnection:
    return _get_con()


# ---------------------------------------------------------------------------
# Cached query wrappers
# ---------------------------------------------------------------------------


@st.cache_data(ttl=60)
def _runs_list() -> pl.DataFrame:
    return queries.runs_list(get_con())


@st.cache_data(ttl=60)
def _run_meta(run_id: str) -> dict | None:
    return queries.run_meta(get_con(), run_id)


@st.cache_data(ttl=300)
def _clv_agg(run_id: str) -> dict:
    return queries.clv_agg(get_con(), run_id)


@st.cache_data(ttl=300)
def _edge_by_season(run_id: str) -> pl.DataFrame:
    return queries.edge_by_season(get_con(), run_id)


@st.cache_data(ttl=300)
def _reliability_bins(run_id: str) -> pl.DataFrame:
    return queries.reliability_bins_df(get_con(), run_id)


@st.cache_data(ttl=300)
def _feature_importances(run_id: str) -> pl.DataFrame:
    return queries.feature_importances_df(get_con(), run_id)


@st.cache_data(ttl=300)
def _feature_stability(run_id: str) -> pl.DataFrame:
    return queries.feature_stability_df(get_con(), run_id)


@st.cache_data(ttl=300)
def _kelly_sizing(run_id: str, bankroll: float) -> pl.DataFrame:
    return queries.kelly_sizing_df(get_con(), run_id, bankroll=bankroll)


@st.cache_data(ttl=600)
def _ruin_sim(edge_pct: float, edge_se: float, kelly_fraction: float) -> dict:
    return queries.ruin_sim_results(edge_pct, edge_se, kelly_fraction, n_bets=1000, n_sims=5000)


@st.cache_data(ttl=60)
def _cross_run_clv(
    model_versions_key: str,
    season: str | None,
    market: str | None,
    would_have_bet: bool | None,
) -> pl.DataFrame:
    mvs = model_versions_key.split(",") if model_versions_key else None
    return queries.cross_run_clv(
        get_con(),
        model_versions=mvs,
        season=season,
        market=market,
        would_have_bet=would_have_bet,
    )


@st.cache_data(ttl=300)
def _available_seasons() -> list[str]:
    return queries.available_seasons(get_con())


@st.cache_data(ttl=300)
def _available_markets() -> list[str]:
    return queries.available_markets(get_con())


@st.cache_data(ttl=300)
def _available_model_versions() -> list[str]:
    return queries.available_model_versions(get_con())


# ---------------------------------------------------------------------------
# Sidebar navigation + run picker
# ---------------------------------------------------------------------------


def _sidebar() -> tuple[str, str | None]:
    """Returns (page_name, selected_run_id)."""
    st.sidebar.title("footy-ev")
    page = st.sidebar.radio(
        "Navigate",
        [
            "Overview",
            "Run Detail",
            "CLV Explorer",
            "Feature Stability",
            "Kelly Sizing",
            "Paper Trading",
        ],
    )

    run_id: str | None = None
    if page in ("Run Detail", "Feature Stability", "Kelly Sizing"):
        runs = _runs_list()
        if runs.height == 0:
            st.sidebar.info("No runs yet.")
        else:
            options = runs["run_id"].to_list()
            labels = {
                r["run_id"]: (f"{r['run_id'][:8]}… {r['model_version']} ({r['status']})")
                for r in runs.iter_rows(named=True)
            }
            selected = st.sidebar.selectbox(
                "Run",
                options=options,
                format_func=lambda x: labels.get(x, x),
            )
            run_id = selected
    return page, run_id


# ---------------------------------------------------------------------------
# Page: Overview
# ---------------------------------------------------------------------------


def _page_overview() -> None:
    st.title("Backtest Runs")
    runs = _runs_list()
    if runs.height == 0:
        st.info("No backtest runs found. Run `make.ps1 backtest-epl` first.")
        return

    display = runs.with_columns(
        [
            pl.col("run_id").str.slice(0, 8).alias("run_id_short"),
        ]
    ).select(
        [
            "run_id_short",
            "model_version",
            "league",
            "status",
            "n_folds",
            "n_predictions",
            "started_at",
            "completed_at",
        ]
    )

    st.dataframe(
        display.to_pandas(),
        use_container_width=True,
        column_config={
            "run_id_short": "Run ID",
            "model_version": "Model",
            "league": "League",
            "status": "Status",
            "n_folds": st.column_config.NumberColumn("Folds", format="%d"),
            "n_predictions": st.column_config.NumberColumn("Predictions", format="%d"),
            "started_at": st.column_config.DatetimeColumn("Started"),
            "completed_at": st.column_config.DatetimeColumn("Completed"),
        },
    )
    st.caption(
        f"{runs.height} runs. Select **Run Detail** or **Feature Stability** "
        "in the sidebar to drill into a specific run."
    )


# ---------------------------------------------------------------------------
# Page: Run Detail
# ---------------------------------------------------------------------------


def _verdict_badge(verdict: str) -> str:
    return VERDICT_BADGE.get(verdict, verdict)


def _page_run_detail(run_id: str) -> None:
    meta = _run_meta(run_id)
    if meta is None:
        st.error(f"run_id not found: {run_id}")
        return

    st.title(f"Run Detail: `{run_id[:12]}…`")

    # --- Header card ---
    agg = _clv_agg(run_id)
    verdict = agg["verdict"]
    VERDICT_COLORS.get(verdict, "#94a3b8")

    col1, col2, col3, col4, col5 = st.columns(5)
    col1.metric("Verdict", _verdict_badge(verdict))
    col2.metric("Model", meta["model_version"])
    col3.metric("n evaluated", f"{agg['n_evaluated']:,}")
    col4.metric(
        "Mean edge (winners)",
        f"{agg['mean_edge_winners']:+.4f}" if agg["mean_edge_winners"] is not None else "—",
    )
    if agg["ci_low"] is not None:
        col5.metric(
            "95% CI",
            f"[{agg['ci_low']:+.4f}, {agg['ci_high']:+.4f}]",
        )
    else:
        col5.metric("95% CI", "—")

    p_val = agg["p_value"]
    st.markdown(f"**p-value (H₀: μ ≤ 0):** {p_val:.3f}" if p_val is not None else "**p-value:** —")
    st.markdown(
        f"League: `{meta['league']}` · Folds: {meta['n_folds']} · "
        f"Predictions: {meta['n_predictions']:,}"
    )

    st.divider()

    # --- Edge by season ---
    st.subheader("Edge by season")
    season_df = _edge_by_season(run_id)
    if season_df.height > 0:
        st.altair_chart(charts.edge_by_season_bar(season_df), use_container_width=True)
    else:
        st.info("No CLV data for season breakdown.")

    st.divider()

    # --- Reliability plots ---
    rel_df = _reliability_bins(run_id)
    if rel_df.height > 0:
        st.subheader("Reliability")
        pairs = (
            rel_df.select(["market", "selection"])
            .unique()
            .sort(["market", "selection"])
            .iter_rows()
        )
        cols_iter = st.columns(2)
        for col_idx, (market, selection) in enumerate(pairs):
            with cols_iter[col_idx % 2]:
                chart = charts.reliability_scatter(rel_df, market, selection)
                st.altair_chart(chart, use_container_width=True)
        st.divider()

    # --- Feature importance heatmap (XGBoost runs only) ---
    if "xgb" in meta["model_version"]:
        fi_df = _feature_importances(run_id)
        if fi_df.height > 0:
            st.subheader("Feature importance per fold")
            st.altair_chart(
                charts.feature_importance_heatmap(fi_df),
                use_container_width=True,
            )
            st.caption("Green = below null baseline (signal). Red = above (noise).")
            st.divider()

    # --- Would-have-bet table ---
    st.subheader("Would-have-bet subset")
    whb_only = st.checkbox("Filter to would_have_bet=True", value=True, key="whb_filter")
    total = queries.clv_bets_count(get_con(), run_id, would_have_bet_only=whb_only)
    page_size = 50

    if total == 0:
        st.info("No rows match the filter.")
    else:
        page = st.number_input(
            f"Page (50 rows, {total:,} total)",
            min_value=0,
            max_value=max(0, (total - 1) // page_size),
            value=0,
            step=1,
            key="bet_page",
        )
        bet_df = queries.clv_bets_df(
            get_con(),
            run_id,
            would_have_bet_only=whb_only,
            page=int(page),
            page_size=page_size,
        )
        st.dataframe(bet_df.to_pandas(), use_container_width=True)


# ---------------------------------------------------------------------------
# Page: CLV Explorer
# ---------------------------------------------------------------------------


def _page_clv_explorer() -> None:
    st.title("CLV Explorer")
    st.caption("Cross-run aggregated CLV statistics.")

    all_mvs = _available_model_versions()
    all_seasons = ["(all)"] + _available_seasons()
    all_markets = ["(all)"] + _available_markets()

    col1, col2, col3, col4 = st.columns(4)
    with col1:
        sel_mv = st.multiselect("Model version", all_mvs, default=all_mvs)
    with col2:
        sel_season = st.selectbox("Season", all_seasons)
    with col3:
        sel_market = st.selectbox("Market", all_markets)
    with col4:
        whb_opt = st.selectbox("Would have bet", ["(all)", "True", "False"])

    season_param = None if sel_season == "(all)" else sel_season
    market_param = None if sel_market == "(all)" else sel_market
    whb_param: bool | None = None
    if whb_opt == "True":
        whb_param = True
    elif whb_opt == "False":
        whb_param = False

    mv_key = ",".join(sorted(sel_mv)) if sel_mv else ""
    df = _cross_run_clv(mv_key, season_param, market_param, whb_param)

    if df.height == 0:
        st.info("No data matches the current filters.")
        return

    display = df.with_columns(
        [
            pl.col("run_id").str.slice(0, 8).alias("run_id_short"),
            pl.col("mean_edge_all").round(4),
            pl.col("mean_edge_winners").round(4),
            pl.col("mean_edge_whb").round(4),
        ]
    ).select(
        [
            "run_id_short",
            "model_version",
            "league",
            "n_evaluated",
            "mean_edge_all",
            "mean_edge_winners",
            "n_would_have_bet",
            "mean_edge_whb",
        ]
    )
    st.dataframe(display.to_pandas(), use_container_width=True)


# ---------------------------------------------------------------------------
# Page: Feature Stability
# ---------------------------------------------------------------------------


def _page_feature_stability(run_id: str) -> None:
    meta = _run_meta(run_id)
    if meta is None:
        st.error(f"run_id not found: {run_id}")
        return
    if "xgb" not in meta["model_version"]:
        st.info(
            f"Feature stability is only available for XGBoost runs (model: {meta['model_version']})."
        )
        return

    st.title(f"Feature Stability: `{run_id[:12]}…`")
    st.caption(
        f"Model: {meta['model_version']} · League: {meta['league']} · Folds: {meta['n_folds']}"
    )

    stab_df = _feature_stability(run_id)
    if stab_df.height == 0:
        st.info("No xgb_feature_importances rows found for this run.")
        return

    # Feature selector
    all_features = sorted(stab_df["feature_name"].unique().to_list())
    selected_features = st.multiselect(
        "Features to show (all shown by default)",
        options=all_features,
        default=all_features,
    )
    if selected_features:
        filtered = stab_df.filter(pl.col("feature_name").is_in(selected_features))
    else:
        filtered = stab_df

    st.altair_chart(
        charts.feature_stability_lines(filtered),
        use_container_width=True,
    )
    st.caption(
        "Gray dashed = `audit_noise` canary (random uniform column). "
        "Features consistently below the canary line are indistinguishable from noise."
    )

    # Summary table: mean importance + fraction of folds below null
    summary = (
        stab_df.group_by("feature_name")
        .agg(
            [
                pl.col("permutation_importance").mean().alias("mean_perm_imp"),
                pl.col("below_null_baseline").cast(pl.Int32).mean().alias("frac_above_null"),
            ]
        )
        .with_columns((1 - pl.col("frac_above_null")).alias("frac_below_null"))
        .sort("mean_perm_imp", descending=True)
    )
    st.subheader("Summary across all folds")
    st.dataframe(summary.to_pandas(), use_container_width=True)


# ---------------------------------------------------------------------------
# Page: Kelly Sizing
# ---------------------------------------------------------------------------


def _page_kelly_sizing(run_id: str) -> None:
    meta = _run_meta(run_id)
    if meta is None:
        st.error(f"run_id not found: {run_id}")
        return

    st.title(f"Kelly Sizing: `{run_id[:12]}…`")
    st.caption(f"Model: {meta['model_version']} · League: {meta['league']}")

    bankroll = st.number_input(
        "Placeholder bankroll (£)",
        min_value=100.0,
        max_value=100_000.0,
        value=1000.0,
        step=100.0,
        key="kelly_bankroll",
    )

    sizing_df = _kelly_sizing(run_id, float(bankroll))

    if sizing_df.height == 0:
        st.info("No would_have_bet rows with Pinnacle closing odds for this run.")
        return

    nonzero = sizing_df.filter(pl.col("stake_gbp") > 0)
    total_turnover = float(sizing_df["stake_gbp"].sum())
    n_sized = sizing_df.height
    n_nonzero = nonzero.height

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Sized bets", f"{n_sized:,}")
    c2.metric("Non-zero stakes", f"{n_nonzero:,}")
    c3.metric("Simulated turnover", f"£{total_turnover:,.2f}")
    c4.metric(
        "Mean stake",
        f"£{float(nonzero['stake_gbp'].mean()):.2f}" if n_nonzero else "—",
    )

    st.altair_chart(charts.stake_histogram(sizing_df), use_container_width=True)

    st.subheader("Sample bet sizing table")
    display = sizing_df.select(
        [
            "fixture_id",
            "market",
            "selection",
            pl.col("p_hat").round(4),
            pl.col("sigma_p").round(4),
            pl.col("odds").round(3),
            pl.col("kelly_fraction").round(5),
            pl.col("stake_gbp").round(2),
            "edge_at_close",
            "is_winner",
        ]
    ).head(100)
    st.dataframe(display.to_pandas(), use_container_width=True)

    st.divider()
    st.subheader("Ruin simulation")
    st.caption(
        "Uses mean edge from CLV evaluations ± bootstrap SE. "
        "Even-money model (odds=2.0). BLUE_MAP §4.3 threshold: both metrics < 5%."
    )

    agg = _clv_agg(run_id)
    default_edge = agg.get("mean_edge_winners") or 0.01
    default_se = abs((agg.get("ci_high") or default_edge) - (agg.get("ci_low") or 0.0)) / (2 * 1.96)

    col1, col2, col3 = st.columns(3)
    with col1:
        edge_pct = st.number_input(
            "Edge pct", value=round(default_edge, 4), step=0.001, format="%.4f", key="ruin_edge"
        )
    with col2:
        edge_se = st.number_input(
            "Edge SE",
            value=round(max(default_se, 0.001), 4),
            step=0.001,
            format="%.4f",
            key="ruin_se",
        )
    with col3:
        kf = st.number_input(
            "Kelly fraction", value=0.25, step=0.05, min_value=0.05, max_value=1.0, key="ruin_kf"
        )

    if st.button("Run simulation (5,000 paths)"):
        with st.spinner("Simulating…"):
            result = _ruin_sim(float(edge_pct), float(edge_se), float(kf))

        r1, r2, r3 = st.columns(3)
        p50 = result["p_50pct_drawdown"]
        pb50 = result["p_below_50pct_after_1000"]
        r1.metric(
            "P(50% drawdown)",
            f"{p50:.3f}",
            delta="⚠ above 5% threshold" if p50 > 0.05 else "✓ below threshold",
            delta_color="inverse",
        )
        r2.metric(
            "P(below 50% @ 1000)",
            f"{pb50:.3f}",
            delta="⚠ above 5% threshold" if pb50 > 0.05 else "✓ below threshold",
            delta_color="inverse",
        )
        r3.metric("Max DD p95", f"{result['max_drawdown_p95']:.3f}")

        fc1, fc2, fc3 = st.columns(3)
        fc1.metric("Final B p10", f"{result['final_bankroll_p10']:.3f}")
        fc2.metric("Final B p50", f"{result['final_bankroll_p50']:.3f}")
        fc3.metric("Final B p90", f"{result['final_bankroll_p90']:.3f}")

        st.altair_chart(
            charts.ruin_terminal_histogram(result["final_bankroll_dist"]),
            use_container_width=True,
        )


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def main() -> None:
    page, run_id = _sidebar()

    if page == "Overview":
        _page_overview()
    elif page == "Run Detail":
        if run_id:
            _page_run_detail(run_id)
        else:
            st.info("Select a run from the sidebar.")
    elif page == "CLV Explorer":
        _page_clv_explorer()
    elif page == "Feature Stability":
        if run_id:
            _page_feature_stability(run_id)
        else:
            st.info("Select a run from the sidebar.")
    elif page == "Kelly Sizing":
        if run_id:
            _page_kelly_sizing(run_id)
        else:
            st.info("Select a run from the sidebar.")
    elif page == "Paper Trading":
        _page_paper_trading()


def _page_paper_trading() -> None:
    """Phase 3 step 1: live paper-trading state."""
    st.title("Paper Trading")

    breaker = queries.circuit_breaker_status(get_con())
    badge = "🔴 TRIPPED" if breaker["is_tripped"] else "🟢 OK"
    cols = st.columns(4)
    cols[0].metric("Circuit breaker", badge)
    cols[1].metric("Total paper bets", queries.paper_bets_total(get_con()))

    queue = queries.fixture_queue(get_con())
    cols[2].metric("Fixtures in latest tick", int(queue.height))

    last_event = breaker.get("last_event")
    if last_event:
        cols[3].caption(
            f"Last breaker: {last_event.get('reason', '?')} "
            f"({last_event.get('affected_source', '?')})"
        )

    st.divider()

    st.subheader("Live odds freshness per fixture")
    fresh = queries.freshness_per_source(get_con())
    st.altair_chart(charts.freshness_gauge(fresh), use_container_width=True)

    st.divider()

    st.subheader("Recent paper bets")
    recent = queries.paper_bets_recent(get_con(), limit=50)
    if recent.is_empty():
        st.info("No paper bets yet. Start the runtime: `python run.py paper-trade`.")
    else:
        st.dataframe(
            recent.to_pandas(),
            use_container_width=True,
            column_config={
                "edge_pct": st.column_config.NumberColumn("Edge", format="%.2f%%"),
                "stake_gbp": st.column_config.NumberColumn("Stake", format="£%.2f"),
                "odds_at_decision": st.column_config.NumberColumn("Odds", format="%.2f"),
            },
        )

    st.divider()

    st.subheader("Edge distribution (last 100 paper bets)")
    dist = queries.edge_distribution_paper(get_con(), n=100)
    st.altair_chart(charts.paper_edge_histogram(dist), use_container_width=True)


if __name__ == "__main__":
    main()
