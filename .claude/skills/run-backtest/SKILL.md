---
name: run-backtest
description: Run a walk-forward backtest for a given league and season range. Use when the operator asks to backtest, evaluate model performance, or compute CLV.
---

# Run a walk-forward backtest

When invoked, do the following:

1. Confirm the league code (EPL, LL, SA, BL, L1) and season range (e.g. 2018-2019 through 2024-2025).
2. Verify the data exists: `uv run python -c "from footy_ev.db import quick_check; quick_check('$LEAGUE', '$START_SEASON', '$END_SEASON')"`
3. If data is missing, STOP and tell the operator which seasons need ingestion. Do not silently proceed.
4. Run the backtest: `make backtest SEASON=$END_SEASON LEAGUE=$LEAGUE`
5. After completion, parse the report at `reports/backtest_$LEAGUE_$END_SEASON.json` and report:
   - Total bets placed
   - Mean CLV (%)
   - ROI (%)
   - Max drawdown
   - Reliability plot deviation (bins where |actual - predicted| > 2pp)
6. If reliability deviation is bad in any bin, recommend re-fitting the calibration layer.
7. If CLV is negative, do NOT recommend changes to thresholds. Negative CLV means the model has no edge; chasing thresholds is fitting to variance.

Never modify the backtest harness inline. If the harness has bugs, raise them as a separate task.
