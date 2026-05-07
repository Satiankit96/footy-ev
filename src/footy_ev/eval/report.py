"""Markdown report writer for evaluate_run output.

The structured summary dict is the canonical machine-readable output;
this module renders it to a Markdown file at reports/run_<run_id>.md so
the operator can read it without querying DuckDB.

Graceful degradation: if n_evaluated == 0 (run has no predictions, or no
Pinnacle coverage), emits a brief "no data" report rather than crashing
on missing keys / NaN formatting.
"""

from __future__ import annotations

import math
from pathlib import Path
from typing import Any

import polars as pl

POST_LANDING_SEQUENCE = """## How to produce the canonical go/no-go run

After this evaluator code lands, the operator's go/no-go evaluation is:

1. Run a wide backtest against the live warehouse (covers Pinnacle coverage window 2012-13 onward; defaults expand training fold-by-fold):
   ```
   .\\make.ps1 backtest-epl -TrainMinSeasons 12 -StepDays 7
   ```
2. Evaluate that run against Pinnacle close:
   ```
   .\\make.ps1 evaluate-run -RunId <uuid-from-step-1>
   ```
3. Read the GO / NO_GO / MARGINAL_SIGNAL / PRELIMINARY_SIGNAL / INSUFFICIENT_SAMPLE verdict in `reports/run_<uuid>.md`.

Verdict thresholds:
- INSUFFICIENT_SAMPLE: n_evaluated < 1000
- PRELIMINARY_SIGNAL:  1000 <= n_evaluated < 2000 (signal exists, below canonical thesis sample)
- NO_GO:             n_evaluated >= 2000 AND mean_edge_winners <= 0  (foundational thesis fails)
- MARGINAL_SIGNAL:   n_evaluated >= 2000 AND mean_edge_winners > 0 AND bootstrap 95% CI lower bound <= 0
- GO:                n_evaluated >= 2000 AND mean_edge_winners > 0 AND bootstrap 95% CI lower bound > 0

Note: HANDOFF.md historically cites a 1000-bet sample as the Phase 1 success criterion; that threshold is reused here as the live-trading bankroll-discipline gate (PROJECT_INSTRUCTIONS §3), distinct from the 2000-bet thesis go/no-go.
"""


def _fmt(x: Any) -> str:
    if x is None:
        return "—"
    if isinstance(x, float):
        if math.isnan(x):
            return "—"
        return f"{x:+.4f}"
    return str(x)


def _fmt_count(x: Any) -> str:
    return "—" if x is None else f"{x:,}"


def _fmt_pvalue(x: Any) -> str:
    """Format a p-value to 3 decimal places; '—' for None/nan."""
    if x is None:
        return "—"
    if isinstance(x, float) and math.isnan(x):
        return "—"
    return f"{x:.3f}"


def write_markdown_report(
    summary: dict[str, Any],
    reliability_dfs: dict[str, pl.DataFrame],
    out_path: Path,
) -> None:
    """Write the evaluation Markdown report.

    Args:
        summary: structured dict from evaluate_run.
        reliability_dfs: per-selection reliability bin DataFrames.
        out_path: destination path. Parent dir must exist (caller's job).
    """
    out_path.parent.mkdir(parents=True, exist_ok=True)
    lines: list[str] = []
    run_id = summary.get("run_id", "<unknown>")
    lines.append(f"# Backtest evaluation: run `{run_id}`")
    lines.append("")

    n_eval = summary.get("n_evaluated", 0)
    if n_eval == 0:
        lines.append("**No data — n_evaluated = 0.**")
        lines.append("")
        n_skipped = summary.get("n_skipped_no_pinnacle", 0)
        n_pred = summary.get("n_predictions", 0)
        lines.append(f"- model_predictions for run: {_fmt_count(n_pred)}")
        lines.append(f"- skipped (missing Pinnacle close): {_fmt_count(n_skipped)}")
        lines.append("")
        lines.append(f"**Verdict: {summary.get('go_no_go_verdict', 'INSUFFICIENT_SAMPLE')}**")
        lines.append("")
        lines.append(POST_LANDING_SEQUENCE)
        out_path.write_text("\n".join(lines), encoding="utf-8")
        return

    lines.append(f"- League: `{summary.get('league', '?')}`")
    lines.append(f"- Model version: `{summary.get('model_version', '?')}`")
    lines.append(f"- Folds: {_fmt_count(summary.get('n_folds'))}")
    lines.append(f"- Predictions in run: {_fmt_count(summary.get('n_predictions'))}")
    lines.append(f"- Evaluations written: {_fmt_count(n_eval)}")
    lines.append(
        f"- Skipped (no Pinnacle close): {_fmt_count(summary.get('n_skipped_no_pinnacle', 0))}"
    )
    lines.append(f"- Would have bet (edge > 3%): {_fmt_count(summary.get('n_would_have_bet', 0))}")
    lines.append(f"- De-vig method: `{summary.get('devig_method', 'shin')}`")
    lines.append("")

    lines.append("## Edge at close")
    lines.append("")
    lines.append("| Subset | Mean | Median |")
    lines.append("|---|---|---|")
    lines.append(
        f"| All predictions | {_fmt(summary.get('mean_edge_all'))} | {_fmt(summary.get('median_edge_all'))} |"
    )
    lines.append(
        f"| Realized winners (canonical thesis test) | {_fmt(summary.get('mean_edge_winners'))} | {_fmt(summary.get('median_edge_winners'))} |"
    )
    lines.append(
        f"| Would have bet (edge > 3%) | {_fmt(summary.get('mean_edge_would_have_bet'))} | — |"
    )
    lines.append("")

    # Bootstrap CI on mean edge (winners) — placed directly after Edge at close.
    boot_n = summary.get("bootstrap_n_winners")
    if boot_n is not None:
        lines.append("## Bootstrap CI on mean edge (winners)")
        lines.append("")
        lines.append("| Metric | Value |")
        lines.append("|---|---|")
        lines.append(f"| Winners resampled | {_fmt_count(boot_n)} |")
        lines.append(f"| Resamples | {_fmt_count(summary.get('bootstrap_n_resamples'))} |")
        lines.append(f"| Mean | {_fmt(summary.get('bootstrap_mean'))} |")
        lines.append(
            f"| 95% CI | [{_fmt(summary.get('bootstrap_ci_low'))}, {_fmt(summary.get('bootstrap_ci_high'))}] |"
        )
        lines.append(
            f"| p-value (H₀: μ ≤ 0) | {_fmt_pvalue(summary.get('bootstrap_p_value_above_zero'))} |"
        )
        lines.append("")

    by_season = summary.get("edge_by_season") or {}
    if by_season:
        lines.append("## Edge by season (all predictions)")
        lines.append("")
        lines.append("| Season | Mean edge |")
        lines.append("|---|---|")
        for season in sorted(by_season):
            lines.append(f"| {season} | {_fmt(by_season[season])} |")
        lines.append("")

    brier_raw = summary.get("brier_raw_by_selection") or {}
    brier_cal = summary.get("brier_calibrated_by_selection") or {}
    if brier_raw or brier_cal:
        all_sels = sorted(set(brier_raw) | set(brier_cal))
        lines.append("## Brier scores (per selection)")
        lines.append("")
        lines.append("| Selection | Brier (raw) | Brier (calibrated) |")
        lines.append("|---|---|---|")
        for sel in all_sels:
            br = brier_raw.get(sel)
            bc = brier_cal.get(sel)
            br_s = "—" if br is None else f"{br:.4f}"
            bc_s = "—" if bc is None else f"{bc:.4f}"
            lines.append(f"| {sel} | {br_s} | {bc_s} |")
        lines.append("")

    rel_pass = summary.get("reliability_pass_pct_by_selection") or {}
    if reliability_dfs:
        lines.append("## Reliability bins (15 bins, ±2pp acceptance per BLUE_MAP §7.5)")
        # Keys are "<market>:<selection>"; group by market for readable sections.
        markets_seen: dict[str, list[str]] = {}
        for key in sorted(reliability_dfs):
            market, sel = key.split(":", 1)
            markets_seen.setdefault(market, []).append(sel)
        for market in sorted(markets_seen):
            for sel in markets_seen[market]:
                key = f"{market}:{sel}"
                df = reliability_dfs.get(key)
                if df is None or df.height == 0:
                    continue
                pct = rel_pass.get(key, 0.0)
                lines.append("")
                lines.append(f"### {sel} [{market}] ({pct:.1f}% populated bins pass)")
                lines.append("")
                lines.append("| range | n | mean_pred | frac_pos | pass |")
                lines.append("|---|---|---|---|---|")
                for r in df.iter_rows(named=True):
                    lo, hi = r["bin_lower"], r["bin_upper"]
                    n = r["n_in_bin"]
                    if n == 0:
                        lines.append(f"| {lo:.2f}-{hi:.2f} | 0 | — | — | — |")
                    else:
                        p_str = "PASS" if r["passes_2pp"] else "FAIL"
                        lines.append(
                            f"| {lo:.2f}-{hi:.2f} | {n} | {r['mean_pred']:.3f} | {r['frac_pos']:.3f} | {p_str} |"
                        )
        lines.append("")

    lines.append("## Day-14 go/no-go verdict")
    lines.append("")
    verdict = summary.get("go_no_go_verdict", "INSUFFICIENT_SAMPLE")
    lines.append(f"**{verdict}**")
    lines.append("")
    lines.append(_verdict_explanation(verdict, n_eval, summary))
    lines.append("")
    lines.append(POST_LANDING_SEQUENCE)
    out_path.write_text("\n".join(lines), encoding="utf-8")


def _verdict_explanation(verdict: str, n_eval: int, summary: dict[str, Any]) -> str:
    mean_win = summary.get("mean_edge_winners", float("nan"))
    ci_low = summary.get("bootstrap_ci_low", float("nan"))
    ci_high = summary.get("bootstrap_ci_high", float("nan"))
    if verdict == "GO":
        return (
            f"Foundational thesis confirmed: {n_eval:,} evaluated predictions, "
            f"mean edge on realized winners {mean_win:+.4f}, "
            f"bootstrap 95% CI [{ci_low:+.4f}, {ci_high:+.4f}] fully above zero. "
            "Proceed to Phase 2 (XGBoost ensemble + Kelly sizing) per PROJECT_INSTRUCTIONS §10."
        )
    if verdict == "MARGINAL_SIGNAL":
        return (
            f"Marginal signal: {n_eval:,} evaluated predictions, "
            f"mean edge on realized winners {mean_win:+.4f} (positive), "
            f"but bootstrap 95% CI [{ci_low:+.4f}, {ci_high:+.4f}] crosses zero. "
            "The edge exists in-sample but is not statistically separable from noise at this sample size. "
            "Run additional diagnostic backtests (--no-calibrate, xi_decay=0.0) to confirm the signal "
            "is structural before proceeding to Phase 2."
        )
    if verdict == "NO_GO":
        return (
            f"Foundational thesis fails: {n_eval:,} evaluated predictions, "
            f"mean edge on realized winners {mean_win:+.4f} (≤ 0). "
            "Per BLUE_MAP §8 Day 14: skip the multi-agent build, or pivot to "
            "arbitrage / promo extraction (different game, less modeling-heavy)."
        )
    if verdict == "PRELIMINARY_SIGNAL":
        return (
            f"Preliminary signal: {n_eval:,} evaluations, below the 2000-bet "
            "canonical thesis threshold but above the 1000-bet inference floor. "
            f"Mean edge on realized winners: {mean_win:+.4f}. Expand the "
            "backtest window before committing to GO."
        )
    return (
        f"Insufficient sample: {n_eval:,} evaluations, below the 1000-bet "
        "minimum to draw any inference. Run a larger backtest (e.g. lower "
        "TrainMinSeasons or smaller StepDays) before re-evaluating."
    )
