"""Altair chart constructors for the Streamlit dashboard.

All functions accept a Polars DataFrame and return an altair.Chart.
No matplotlib. No plotly. Color palette mirrors the eval CLI verdicts.
"""

from __future__ import annotations

import altair as alt
import polars as pl

# ---------------------------------------------------------------------------
# Color palette
# ---------------------------------------------------------------------------

VERDICT_COLORS = {
    "GO": "#22c55e",  # green-500
    "MARGINAL_SIGNAL": "#f59e0b",  # amber-500
    "NO_GO": "#ef4444",  # red-500
    "PRELIMINARY_SIGNAL": "#94a3b8",  # slate-400
    "INSUFFICIENT_SAMPLE": "#94a3b8",
}

_SIGNAL_COLOR = "#22c55e"  # green  (below null = signal)
_NOISE_COLOR = "#ef4444"  # red    (above null = noise)
_NEUTRAL_COLOR = "#94a3b8"  # slate  (null unknown)


# ---------------------------------------------------------------------------
# Edge by season bar chart
# ---------------------------------------------------------------------------


def edge_by_season_bar(df: pl.DataFrame) -> alt.Chart:
    """Horizontal bar chart: season on y-axis, mean_edge on x-axis.

    Bars colored green (positive) or red (negative).
    """
    if df.height == 0:
        return alt.Chart(alt.Data(values=[])).mark_bar()

    pdf = df.to_pandas()
    pdf["color"] = pdf["mean_edge"].apply(lambda x: _SIGNAL_COLOR if x > 0 else _NOISE_COLOR)
    chart = (
        alt.Chart(pdf)
        .mark_bar()
        .encode(
            x=alt.X("mean_edge:Q", title="Mean edge at close", axis=alt.Axis(format="+.3f")),
            y=alt.Y("season:N", sort="-x", title="Season"),
            color=alt.Color("color:N", scale=None),
            tooltip=[
                alt.Tooltip("season:N"),
                alt.Tooltip("mean_edge:Q", format="+.4f", title="Mean edge"),
                alt.Tooltip("n_predictions:Q", format=",", title="n"),
            ],
        )
        .properties(title="Edge at close by season", height=max(120, df.height * 28))
    )
    rule = (
        alt.Chart({"values": [{"x": 0}]})
        .mark_rule(color="white", strokeDash=[4, 4])
        .encode(x=alt.X("x:Q"))
    )
    return chart + rule


# ---------------------------------------------------------------------------
# Reliability scatter
# ---------------------------------------------------------------------------


def reliability_scatter(
    df: pl.DataFrame,
    market: str,
    selection: str,
) -> alt.Chart:
    """Scatter of mean_pred vs frac_pos with diagonal reference line.

    Point size = n_in_bin. Color = pass (green) / fail (red).
    Only plots non-empty bins (n_in_bin > 0).
    """
    sub = df.filter(
        (pl.col("market") == market) & (pl.col("selection") == selection) & (pl.col("n_in_bin") > 0)
    )
    if sub.height == 0:
        return alt.Chart(alt.Data(values=[])).mark_point()

    pdf = sub.to_pandas()
    pdf["pass_label"] = pdf["passes_2pp"].apply(lambda x: "PASS" if x else "FAIL")

    points = (
        alt.Chart(pdf)
        .mark_circle()
        .encode(
            x=alt.X("mean_pred:Q", scale=alt.Scale(domain=[0, 1]), title="Mean predicted prob"),
            y=alt.Y("frac_pos:Q", scale=alt.Scale(domain=[0, 1]), title="Fraction positive"),
            size=alt.Size("n_in_bin:Q", title="n in bin", scale=alt.Scale(range=[40, 400])),
            color=alt.Color(
                "pass_label:N",
                scale=alt.Scale(
                    domain=["PASS", "FAIL"],
                    range=[_SIGNAL_COLOR, _NOISE_COLOR],
                ),
                title="±2pp",
            ),
            tooltip=[
                alt.Tooltip("bin_lower:Q", format=".2f"),
                alt.Tooltip("bin_upper:Q", format=".2f"),
                alt.Tooltip("n_in_bin:Q", format=","),
                alt.Tooltip("mean_pred:Q", format=".3f"),
                alt.Tooltip("frac_pos:Q", format=".3f"),
                alt.Tooltip("pass_label:N", title="±2pp"),
            ],
        )
    )
    diag_data = {"values": [{"x": 0, "y": 0}, {"x": 1, "y": 1}]}
    diagonal = (
        alt.Chart(diag_data)
        .mark_line(color="gray", strokeDash=[4, 4], opacity=0.6)
        .encode(x="x:Q", y="y:Q")
    )
    return (diagonal + points).properties(
        title=f"Reliability — {selection} [{market}]",
        width=340,
        height=300,
    )


# ---------------------------------------------------------------------------
# Feature importance heatmap
# ---------------------------------------------------------------------------


def feature_importance_heatmap(df: pl.DataFrame) -> alt.Chart:
    """Heatmap: rows=features, cols=fold_rank, color=below_null_baseline.

    Green = signal (below null = good). Red = noise (above null = bad).
    Gray = unknown (below_null_baseline is NULL).
    """
    if df.height == 0:
        return alt.Chart(alt.Data(values=[])).mark_rect()

    pdf = df.to_pandas()
    pdf["status"] = pdf["below_null_baseline"].apply(
        lambda x: "signal" if x is True else ("noise" if x is False else "unknown")
    )
    return (
        alt.Chart(pdf)
        .mark_rect()
        .encode(
            x=alt.X("fold_rank:O", title="Fold"),
            y=alt.Y(
                "feature_name:N",
                title="Feature",
                sort=alt.EncodingSortField("permutation_importance", op="mean", order="descending"),
            ),
            color=alt.Color(
                "status:N",
                scale=alt.Scale(
                    domain=["signal", "noise", "unknown"],
                    range=[_SIGNAL_COLOR, _NOISE_COLOR, _NEUTRAL_COLOR],
                ),
                title="vs null baseline",
            ),
            tooltip=[
                alt.Tooltip("feature_name:N"),
                alt.Tooltip("fold_rank:O"),
                alt.Tooltip("permutation_importance:Q", format=".4f"),
                alt.Tooltip("status:N"),
            ],
        )
        .properties(
            title="Feature importance per fold (green=signal, red=noise)",
            height=max(200, len(pdf["feature_name"].unique()) * 20),
        )
    )


# ---------------------------------------------------------------------------
# Feature stability line chart
# ---------------------------------------------------------------------------


# ---------------------------------------------------------------------------
# Kelly sizing charts
# ---------------------------------------------------------------------------


def stake_histogram(df: pl.DataFrame) -> alt.Chart:
    """Histogram of Kelly-sized stakes (stake_gbp column)."""
    if df.height == 0:
        return alt.Chart(alt.Data(values=[])).mark_bar()

    pdf = df.filter(pl.col("stake_gbp") > 0).to_pandas()
    return (
        alt.Chart(pdf)
        .mark_bar(color=_SIGNAL_COLOR, opacity=0.8)
        .encode(
            x=alt.X("stake_gbp:Q", bin=alt.Bin(maxbins=30), title="Stake (£)"),
            y=alt.Y("count()", title="Count"),
            tooltip=[
                alt.Tooltip("stake_gbp:Q", bin=True, title="Stake range"),
                alt.Tooltip("count()", title="n bets"),
            ],
        )
        .properties(title="Kelly stake distribution (would-have-bet subset)", height=260)
    )


def ruin_terminal_histogram(dist: list[float]) -> alt.Chart:
    """Histogram of terminal bankrolls from ruin simulation."""
    if not dist:
        return alt.Chart(alt.Data(values=[])).mark_bar()

    import pandas as pd

    pdf = pd.DataFrame({"final_bankroll": dist})
    return (
        alt.Chart(pdf)
        .mark_bar(opacity=0.75)
        .encode(
            x=alt.X(
                "final_bankroll:Q", bin=alt.Bin(maxbins=40), title="Terminal bankroll (start=1.0)"
            ),
            y=alt.Y("count()", title="Simulations"),
            color=alt.condition(
                alt.datum.final_bankroll < 0.5,
                alt.value(_NOISE_COLOR),
                alt.value(_SIGNAL_COLOR),
            ),
        )
        .properties(title="Ruin sim: terminal bankroll distribution", height=260)
    )


def feature_stability_lines(df: pl.DataFrame) -> alt.Chart:
    """Line chart: permutation_importance over fold_rank for each feature.

    The audit_noise canary is drawn as a dashed gray reference.
    Other features are drawn as colored lines.
    """
    if df.height == 0:
        return alt.Chart(alt.Data(values=[])).mark_line()

    pdf = df.to_pandas()
    # Separate audit_noise from real features
    noise_df = pdf[pdf["feature_name"] == "audit_noise"]
    feature_df = pdf[pdf["feature_name"] != "audit_noise"]

    feature_lines = (
        alt.Chart(feature_df)
        .mark_line(opacity=0.8)
        .encode(
            x=alt.X("fold_rank:Q", title="Fold"),
            y=alt.Y("permutation_importance:Q", title="Permutation importance"),
            color=alt.Color("feature_name:N", title="Feature"),
            tooltip=[
                alt.Tooltip("fold_rank:Q"),
                alt.Tooltip("feature_name:N"),
                alt.Tooltip("permutation_importance:Q", format=".4f"),
            ],
        )
    )

    if noise_df.empty:
        return feature_lines.properties(
            title="Feature permutation importance across folds",
            height=350,
        )

    noise_line = (
        alt.Chart(noise_df)
        .mark_line(strokeDash=[6, 3], color="gray", opacity=0.9)
        .encode(
            x=alt.X("fold_rank:Q"),
            y=alt.Y("permutation_importance:Q"),
            tooltip=[
                alt.Tooltip("fold_rank:Q"),
                alt.Tooltip(
                    "permutation_importance:Q", format=".4f", title="audit_noise (null baseline)"
                ),
            ],
        )
    )

    return (feature_lines + noise_line).properties(
        title="Feature stability: permutation importance across folds (gray dashed = audit_noise)",
        height=350,
    )


# ---------------------------------------------------------------------------
# Paper Trading page (Phase 3 step 1)
# ---------------------------------------------------------------------------


def paper_edge_histogram(df: pl.DataFrame) -> alt.Chart:
    """Histogram of edge_pct across the most recent N paper bets."""
    if df.is_empty():
        return alt.Chart(pl.DataFrame({"edge_pct": [0.0]}).to_pandas()).mark_text(
            text="No paper bets yet."
        )
    return (
        alt.Chart(df.to_pandas())
        .mark_bar()
        .encode(
            x=alt.X("edge_pct:Q", bin=alt.Bin(maxbins=20), title="Edge %"),
            y=alt.Y("count()", title="Paper bets"),
            tooltip=["count()"],
        )
        .properties(title="Edge distribution (last paper bets)", height=220)
    )


def freshness_gauge(df: pl.DataFrame, limit_sec: int = 300) -> alt.Chart:
    """Per-source freshness bars; red when over the staleness limit."""
    if df.is_empty():
        return alt.Chart(pl.DataFrame({"x": [0]}).to_pandas()).mark_text(
            text="No live odds snapshots yet."
        )
    pdf = df.to_pandas()
    pdf["status"] = pdf["max_staleness_sec"].apply(
        lambda s: "stale" if s and s > limit_sec else "fresh"
    )
    return (
        alt.Chart(pdf)
        .mark_bar()
        .encode(
            x=alt.X("max_staleness_sec:Q", title=f"Staleness (s); limit={limit_sec}"),
            y=alt.Y("fixture_id:N", title="Fixture"),
            color=alt.Color(
                "status:N",
                scale=alt.Scale(
                    domain=["fresh", "stale"],
                    range=[VERDICT_COLORS["GO"], VERDICT_COLORS["NO_GO"]],
                ),
                legend=alt.Legend(title="Freshness"),
            ),
            tooltip=["venue", "fixture_id", "max_staleness_sec", "latest_received_at"],
        )
        .properties(title="Live-odds freshness per fixture", height=220)
    )
