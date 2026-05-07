"""CLI for risk/Kelly sizing utilities.

Subcommands:
    kelly          — compute a single Kelly stake given p, sigma, odds, bankroll
    simulate-ruin  — run Monte Carlo ruin simulation and report key metrics

Invocation:
    uv run python -m footy_ev.risk.cli kelly --p-hat 0.55 --sigma-p 0.02 --odds 2.10 --bankroll 1000
    uv run python -m footy_ev.risk.cli simulate-ruin --edge-pct 0.0108 --edge-se 0.005 --kelly-fraction 0.25
"""

from __future__ import annotations

import typer

from footy_ev.risk.kelly import kelly_fraction_used, kelly_stake
from footy_ev.risk.ruin import simulate_ruin as _simulate_ruin

app = typer.Typer(add_completion=False, help="footy-ev Kelly sizing utilities.")


@app.callback()  # type: ignore[misc]
def _callback() -> None:
    """Force Typer into subcommand-dispatch mode."""


@app.command("kelly")  # type: ignore[misc]
def kelly_cmd(
    p_hat: float = typer.Option(..., "--p-hat", help="Calibrated win probability"),
    sigma_p: float = typer.Option(0.0, "--sigma-p", help="Bootstrap SE of p_hat"),
    odds: float = typer.Option(..., "--odds", help="Decimal odds"),
    bankroll: float = typer.Option(..., "--bankroll", help="Current bankroll (£)"),
    base_fraction: float = typer.Option(0.25, "--base-fraction"),
    uncertainty_k: float = typer.Option(1.0, "--uncertainty-k"),
    per_bet_cap_pct: float = typer.Option(0.02, "--per-bet-cap-pct"),
    recent_clv_pct: float = typer.Option(0.0, "--recent-clv-pct"),
) -> None:
    """Compute fractional Kelly stake for a single bet."""
    stake = kelly_stake(
        p_hat,
        sigma_p,
        odds,
        bankroll,
        base_fraction=base_fraction,
        uncertainty_k=uncertainty_k,
        per_bet_cap_pct=per_bet_cap_pct,
        recent_clv_pct=recent_clv_pct,
    )
    fraction = kelly_fraction_used(
        p_hat,
        sigma_p,
        odds,
        base_fraction=base_fraction,
        uncertainty_k=uncertainty_k,
        per_bet_cap_pct=per_bet_cap_pct,
        recent_clv_pct=recent_clv_pct,
    )
    b = odds - 1.0
    p_lb = max(0.0, p_hat - uncertainty_k * sigma_p)
    q = 1.0 - p_lb
    f_full = (b * p_lb - q) / b if (b > 0 and p_lb > 0) else 0.0
    edge_pct = (p_hat * odds - 1.0) * 100

    typer.echo(f"p_hat            = {p_hat:.4f}")
    typer.echo(f"sigma_p          = {sigma_p:.4f}")
    typer.echo(f"p_lb (1σ)        = {p_lb:.4f}")
    typer.echo(f"edge at odds     = {edge_pct:+.2f}%")
    typer.echo(f"full Kelly f*    = {f_full:.4f} ({f_full * 100:.2f}% of bankroll)")
    typer.echo(f"fraction used    = {fraction:.4f} ({fraction * 100:.2f}% of bankroll)")
    typer.echo(f"stake (B={bankroll:.0f})   = £{stake}")


@app.command("simulate-ruin")  # type: ignore[misc]
def simulate_ruin_cmd(
    edge_pct: float = typer.Option(..., "--edge-pct", help="Mean edge, e.g. 0.0108"),
    edge_se: float = typer.Option(..., "--edge-se", help="Standard error of edge"),
    kelly_fraction: float = typer.Option(0.25, "--kelly-fraction"),
    n_bets: int = typer.Option(1000, "--n-bets"),
    n_sims: int = typer.Option(10_000, "--n-sims"),
    rng_seed: int = typer.Option(0, "--rng-seed"),
) -> None:
    """Run Monte Carlo ruin simulation and report key metrics."""
    typer.echo(
        f"Simulating {n_sims:,} paths × {n_bets:,} bets "
        f"(edge={edge_pct:+.4f} ± {edge_se:.4f}, f={kelly_fraction:.2f})…"
    )
    result = _simulate_ruin(
        edge_pct,
        edge_se,
        kelly_fraction,
        n_bets=n_bets,
        n_sims=n_sims,
        rng_seed=rng_seed,
    )
    typer.echo("")
    typer.echo(
        f"P(50% drawdown touched)      = {result['p_50pct_drawdown']:.3f}  "
        f"{'⚠ ABOVE THRESHOLD' if result['p_50pct_drawdown'] > 0.05 else '✓'}"
    )
    typer.echo(
        f"P(bankroll < 50% after {n_bets}) = {result['p_below_50pct_after_1000']:.3f}  "
        f"{'⚠ ABOVE THRESHOLD' if result['p_below_50pct_after_1000'] > 0.05 else '✓'}"
    )
    typer.echo(f"Max drawdown p95             = {result['max_drawdown_p95']:.3f}")
    typer.echo("")
    typer.echo("Final bankroll (start=1.0):")
    typer.echo(f"  p10 = {result['final_bankroll_p10']:.3f}")
    typer.echo(f"  p50 = {result['final_bankroll_p50']:.3f}")
    typer.echo(f"  p90 = {result['final_bankroll_p90']:.3f}")
    typer.echo(f"  mean= {result['final_bankroll_mean']:.3f}")

    if result["p_50pct_drawdown"] > 0.05 or result["p_below_50pct_after_1000"] > 0.05:
        typer.echo("")
        typer.echo(
            "⚠  Ruin probability exceeds 5% threshold. "
            f"Reduce kelly_fraction below {kelly_fraction:.2f} before going live."
        )


if __name__ == "__main__":
    app()
