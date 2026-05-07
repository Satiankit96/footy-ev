# XGBoost O/U 2.5 Feature Set — Domain Rationale

Phase 2 step 1. Feature matrix for `xgb_ou25_v1`. All features are
point-in-time (PIT) correct: training features for a fixture at time T use
only matches with kickoff_utc < T; test features use only matches before
`as_of` (the train_cutoff of the fold).

---

## Rolling team form features (14 features)

All rolling windows use `ROWS BETWEEN N PRECEDING AND 1 PRECEDING` in PIT mode
(window functions ordered by kickoff_utc within each team). In snapshot mode,
the last-N matches up to `as_of` are used (GROUP BY aggregation).

Fixtures with fewer than the window size of prior matches yield NULL for that
feature. XGBoost treats NULL as missing and handles it natively via its
split-finding algorithm.

### xG-based (8 features, 5-match window)

| Feature | Rationale |
|---|---|
| `home_xg_for_5` | Home team's attacking output: expected goals scored per game. Better signal than actual goals (less variance). |
| `away_xg_for_5` | Away team's attacking output. |
| `home_xg_against_5` | Home team's defensive exposure: expected goals conceded per game. |
| `away_xg_against_5` | Away team's defensive exposure. |
| `home_goals_for_5` | Actual goals scored (complement to xG; captures finishing variance and set-piece prowess). |
| `away_goals_for_5` | Actual goals scored by the away team. |
| `home_goals_against_5` | Goals conceded (GK performance, set-piece defense). |
| `away_goals_against_5` | Goals conceded by the away team. |

5-match window: short enough to be recent, long enough to reduce single-game noise.
The 5-match window is team-centric (home or away fixtures combined), not split by
venue, to preserve sample size.

### Results-based (6 features, 10-match window)

| Feature | Rationale |
|---|---|
| `home_win_rate_10` | Win rate over last 10: captures form momentum beyond goal counts. |
| `away_win_rate_10` | Away team win rate. |
| `home_draw_rate_10` | Draw propensity: high-draw teams suppress total goals. |
| `away_draw_rate_10` | Away team draw propensity. |
| `home_ppg_10` | Points per game (normalised to [0,1] range by dividing by 3) — composite form metric. |
| `away_ppg_10` | Away team PPG. |

10-match window for results: results are noisier than xG so a longer window
reduces variance. Win/draw rates are direct O/U 2.5 proxies: defensive teams
with high draw rates produce fewer than 2.5 goals.

---

## Stacked model feature (1 feature)

### `xg_skellam_p_over` — xG-Skellam baseline probability

The O/U 2.5 over probability from the locked xG-Skellam baseline run
(`xi_decay=0.0, no isotonic`, run_id from Phase 1 diagnostic).

**PIT argument**: the stacked feature uses only xG-Skellam predictions where
`model_predictions.as_of < train_cutoff`, taking the most recent prediction
per fixture via `ROW_NUMBER() OVER (PARTITION BY fixture_id ORDER BY as_of DESC)`.
This guarantees that for each training fixture at time T, the stacked feature
came from a xG-Skellam fit trained on data before T. No future leakage.

**Domain rationale**: the xG-Skellam model already encodes team-level xG rates
via Poisson MLE. Including it as a feature lets XGBoost learn when the Skellam
baseline is trustworthy and when the rolling form features override it. Fixtures
with no xG-Skellam prediction (e.g., before the baseline run's warmup window)
default to 0.5 (maximum uncertainty).

---

## Audit / canary feature (1 feature, not in FEATURE_NAMES)

### `audit_noise`

`np.random.default_rng(fold_seed).uniform(size=n_train)` — pure uniform noise,
re-sampled per fold with a deterministic seed derived from the fold index.

This feature has variance but zero signal. It exists to validate the permutation
importance gate: a correctly functioning `permutation_importance_gate` must find
`audit_noise` with `below_null_baseline=True`. If audit_noise is flagged as
important, there is a data-leakage or implementation bug in the audit.

The null CI in `permutation_importance_gate` is derived by permuting audit_noise
`n_null=100` times and computing the 5th–95th percentile of the resulting
importance distribution. Any feature with permutation importance ≤ `perm_ci_high`
is flagged `below_null_baseline=True`.

---

## Summary table

| # | Feature | Type | Window |
|---|---|---|---|
| 1 | `home_xg_for_5` | xG (attack) | 5 matches |
| 2 | `away_xg_for_5` | xG (attack) | 5 matches |
| 3 | `home_xg_against_5` | xG (defense) | 5 matches |
| 4 | `away_xg_against_5` | xG (defense) | 5 matches |
| 5 | `home_goals_for_5` | goals (attack) | 5 matches |
| 6 | `away_goals_for_5` | goals (attack) | 5 matches |
| 7 | `home_goals_against_5` | goals (defense) | 5 matches |
| 8 | `away_goals_against_5` | goals (defense) | 5 matches |
| 9 | `home_win_rate_10` | results | 10 matches |
| 10 | `away_win_rate_10` | results | 10 matches |
| 11 | `home_draw_rate_10` | results | 10 matches |
| 12 | `away_draw_rate_10` | results | 10 matches |
| 13 | `home_ppg_10` | results | 10 matches |
| 14 | `away_ppg_10` | results | 10 matches |
| 15 | `xg_skellam_p_over` | stacked model | — |
| 16 | `audit_noise` *(canary)* | noise | per-fold |
