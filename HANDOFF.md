# Handoff — end of Phase 2 step 1 (XGBoost O/U 2.5 infrastructure landed)

> Created **2026-05-06** at the close of Phase 2 step 1. Read this in full before doing anything else, then `CLAUDE.md`, then dive into the codebase. The previous `HANDOFF.md` (Phase 0 step 2 era — Understat ingestion + alias view) is not archived separately; its content has been compressed into §6 below.

---

## 1. Status banner

We are at the **end of Phase 2 step 1**, ~45% through the overall project plan.

**Test suite: 138 unit passed / 10 integration passed / 2 skipped (network-gated) / 1 xfailed (Cat-G/H bookmaker columns, expected, unchanged since Phase 0).**

### Phase 1 — CLOSED

Dixon-Coles 1X2 is **dead** (NO_GO verdict on CLV vs Pinnacle close; mean edge on realized winners ≤ 0 at canonical sample). xG-Skellam O/U 2.5 is the live baseline, confirmed at **MARGINAL_SIGNAL** (mean edge > 0, bootstrap 95% CI crosses zero, p = 0.038). The project accepted this as an operational green-light because all 7 seasons are individually positive and the CI crossing zero is a sample-size artefact, not a structural contradiction.

**Locked Phase 1 config:**
- Model: `xg_skellam_v1`
- `xi_decay = 0.0` (uniform weighting — decay weakened signal in all diagnostics)
- `no_calibrate = True` (isotonic calibration broke CLV in both DC and xG-Skellam; isotonic is suspended; future calibration approach is an open question)
- Baseline run in live warehouse: `run_id = 034bb631-83e8-4fdf-a7f5-1189bd107df6`
- Verdict: MARGINAL_SIGNAL, p = 0.038, all 7 seasons (2018-19 → 2024-25) positive

### Phase 2 step 1 — CLOSED (infrastructure only)

XGBoost binary classifier (O/U 2.5, `xgb_ou25_v1`) fully wired:
- 15 SQL features (rolling team form + xG) + 1 stacked feature (xg_skellam_p_over) + 1 audit_noise canary = 16 features total
- PIT (walk-forward window functions) and snapshot (GROUP BY) modes in `features/assembler.py`
- `features.md` written with domain rationale before training code was invoked
- Permutation importance gate fires per-fold; writes to `xgb_feature_importances` keyed by `fit_id`
- Migration 007 (`xgb_fits` + `xgb_feature_importances`) applied
- `make.ps1` wired: `.\make.ps1 backtest-epl -ModelVersion xgb_ou25_v1 -XgSkellamRunId <run_id>`

**The canonical XGBoost backtest has NOT been run yet.** That is the immediate next operator action in the new chat session.

---

## 2. Key file locations

| Path | Purpose |
|---|---|
| `src/footy_ev/features/assembler.py` | `build_feature_matrix(con, fixture_ids, as_of, xg_skellam_run_id, *, mode)` — 15 SQL features; PIT + snapshot modes |
| `src/footy_ev/features/__init__.py` | Exports `FEATURE_NAMES` (15 items, no audit_noise) and `build_feature_matrix` |
| `features.md` | Domain rationale for all 16 features; PIT argument for stacked feature |
| `src/footy_ev/models/xgboost_ou25.py` | `XGBoostOU25Fit`, `fit(feature_df, labels, *, as_of, xg_skellam_run_id)`, `predict_ou25(fitted, feat_row)` |
| `src/footy_ev/eval/feature_audit.py` | `permutation_importance_gate(fitted, test_features, test_labels, *, n_null=100, rng_seed=0)` |
| `src/footy_ev/backtest/walkforward.py` | Walk-forward harness with `xgb_ou25_v1` path; XGBoost registry entry has `needs_features=True` |
| `src/footy_ev/db/migrations/007_xgb_artifacts.sql` | `xgb_fits` + `xgb_feature_importances` tables |
| `src/footy_ev/eval/cli.py` | `evaluate_run(con, run_id, *, devig_method, reports_dir, no_calibrate)` |
| `src/footy_ev/eval/bootstrap.py` | `bootstrap_edge_ci(con, run_id, *, n_resamples, alpha, rng_seed)` — percentile bootstrap on winners |
| `reports/` | Markdown reports from `evaluate_run`; one per run_id |
| `data/warehouse/footy_ev.duckdb` | Live warehouse; mutable write surface |

---

## 3. Architectural invariants

Load-bearing. Break these and the project fails in subtle ways.

1. **CLV vs Pinnacle close (and eventually Betfair SP) is the North Star metric.** Raw P&L is secondary. Any backtest report missing CLV is incomplete. (PROJECT_INSTRUCTIONS §6, BLUE_MAP §1.1)
2. **Walk-forward only on time-series. K-fold CV is banned.** (CLAUDE.md, BLUE_MAP §1.5, §7)
3. **Point-in-time correctness is mandatory at every feature computation boundary.** Training features use `kickoff_utc < train_cutoff`. Stacked features (xg_skellam → XGBoost) use `mp.as_of < train_cutoff`, `ROW_NUMBER() … ORDER BY as_of DESC` to pick the most recent fold, never a future fold. (BLUE_MAP §6.1, §8)
4. **Append-only ledgers for odds and events.** No updates, no deletes on historical match rows except via `source_row_hash` upsert pattern.
5. **Raw downloaded data is immutable.** `data/raw/` is the archive. Never modify a cached file in place.
6. **DuckDB tables are the mutable write surface; Parquet archive nightly; `v_*` views join both.** Downstream code queries `v_*` views and is agnostic to which side data came from.
7. **Migrations are append-only and idempotent.** Every migration uses `CREATE TABLE IF NOT EXISTS` / `CREATE INDEX IF NOT EXISTS`. Currently 7 applied (001–007).
8. **Entity resolution happens at QUERY time, not ingest time.** `team_aliases.(source, raw_name) → team_id` joined inside `v_*` views. Fuzzy matching at ingest is banned.
9. **Pinnacle: historical closing-odds allowed, live API banned.** `PSC{H,D,A}` in football-data CSVs is the 14-season CLV training label. Live Pinnacle API shut down July 2025; permanently off-limits.
10. **Real-money trading gated on `LIVE_TRADING=true` AND bankroll discipline conditions in PROJECT_INSTRUCTIONS §3.** Default is paper-only.
11. **Calibration layer is currently disabled.** Isotonic broke CLV in all DC and xG-Skellam diagnostic runs (calibrated Brier improved but CLV edge degraded). `no_calibrate=True` is the production config until a better calibration approach is identified (Platt? Beta? Skip entirely?). Do not re-enable isotonic without a fresh diagnostic.
12. **XGBoost feature audit fires per-fold.** `permutation_importance_gate` is called inside the fold loop after each XGBoost fit, writing 16 rows to `xgb_feature_importances` keyed by `fit_id`. The `audit_noise` random uniform column is a deliberate canary — if it appears above the null baseline CI in any fold, that is a bug signal (data leakage or overfit), not a real feature.
13. **Stacked feature PIT contract.** `xg_skellam_p_over` uses `WHERE mp.as_of < train_cutoff` (strict less-than) with `ROW_NUMBER() OVER (PARTITION BY fixture_id ORDER BY as_of DESC) = 1` to pick the most-recent pre-cutoff Skellam prediction. Fixtures with no qualifying row get `COALESCE(…, 0.5)`. This is belt-and-suspenders PIT.
14. **`audit_noise` is added by the walkforward harness, never by the assembler.** `FEATURE_NAMES` (15 items) does not include `audit_noise`. The harness adds it after calling `build_feature_matrix`. Train RNG: `np.random.default_rng(fold_idx)`; test RNG: `np.random.default_rng(fold_idx + 1_000_000)`.
15. **No mocking the database in integration tests.** Use real (in-memory or temp-file) DuckDB.
16. **No f-string SQL with user/source-derived values.** View/table names from internal code (not user input) are OK in f-strings. All data values must be parameterized.

---

## 4. What's next, ordered

### Immediate: canonical XGBoost backtest (first move in new chat session)

```powershell
.\make.ps1 backtest-epl `
    -ModelVersion xgb_ou25_v1 `
    -XgSkellamRunId 034bb631-83e8-4fdf-a7f5-1189bd107df6 `
    -TrainMinSeasons 3 `
    -StepDays 7
```

Then evaluate:
```powershell
.\make.ps1 evaluate-run -RunId <uuid-from-above> -NoCalibrate
```

Inspect `reports/run_<uuid>.md` for verdict. Also query:
```sql
SELECT feature_name, AVG(importance_gain), AVG(permutation_importance),
       SUM(below_null_baseline::INT) AS n_below_null
FROM xgb_feature_importances
JOIN xgb_fits USING (fit_id)
WHERE model_version = 'xgb_ou25_v1'
GROUP BY feature_name
ORDER BY AVG(importance_gain) DESC;
```
This is the fold-stability check (BLUE_MAP §7.3).

### Short-term: Phase 2 step 2 (after canonical run)

- **Hyperparameter sweep** (grid or Bayesian) for XGBoost: n_estimators, max_depth, learning_rate, subsample. Currently fixed at {400, 4, 0.05, 0.8}.
- **Kelly sizing**: fractional Kelly on `edge = p_model - p_market`; per-bet cap at `max(0.02 * bankroll, kelly_fraction * 0.5)`; PROJECT_INSTRUCTIONS §10.
- **Calibration revisit**: Platt scaling or beta calibration as an alternative to isotonic. Validate on holdout that CLV edge is preserved after calibration.

### Medium-term: Phase 2 step 3 onward

- Multi-market extension: 1X2 XGBoost (if DC is revived as a stacked input), Asian handicap.
- LangGraph orchestration + Betfair Exchange Delayed key + paper-trading loop (Phase 3).
- Real-money deployment gated on PROJECT_INSTRUCTIONS §3 bankroll discipline (Phase 4+).

### Parked / open questions

- **Dixon-Coles 1X2**: sits dead (NO_GO verdict). Does it get revived as a XGBoost stacked feature in a later step? Or stay parked? No decision yet.
- **Better calibration approach**: Platt? Beta calibration? Skip entirely until exchange pricing makes it necessary? Open.
- **Multi-league extension**: La Liga, Serie A, Bundesliga, Ligue 1. Ingestion code is league-agnostic. Add when EPL XGBoost canonical run is stable. Priority: Bundesliga > Serie A > Ligue 1 on Betfair Exchange volume.
- **Active position management / hedging engine**: flagged as Phase 5+ idea. Not in current plan.

---

## 5. Outstanding TODOs / known debt

### Operator-side
- **Ambient `VIRTUAL_ENV` warning** (`VIRTUAL_ENV=c:\MY_Projects\venv` does not match `.venv`): cosmetic, outputs correct. Fix: unset `VIRTUAL_ENV` in the parent shell or PowerShell profile.
- **`uv` PATH**: sessions may need `$env:PATH = "$env:USERPROFILE\.local\bin;$env:PATH"` prepended. Persistent fix is a Windows User PATH config.

### Code-side
- **`.bootstrap_backup/` still tracked in git** from the original session. Safe to delete.
- **Trailing-blank-line skip in `_read_rows_lenient`** causes 1-reject in the 2014-15 football-data CSV. ~5-line cleanup.
- **mypy `# type: ignore[misc]`** on `@decorator` lines for typer/tenacity/pytest fixtures. Fix: extend `.pre-commit-config.yaml` `additional_dependencies`.
- **Cat-G/H bookmakers** (1xBet, BMGM, BV, CL, BFD): deferred migration 008 until they appear in a second season. Currently only 2024-25. Wait one more season.
- **`teams` table is empty.** `team_aliases.team_id` is de-facto canonical. Phase 2 step 2 will need team metadata if we add league/country filtering. Bootstrap seed deferred.
- **`addendum.md`** at project root: "Operator Vision Addendum" not yet merged into BLUE_MAP / PROJECT_INSTRUCTIONS. Operator's call.
- **Typer deprecation warning**: `is_flag=True` in `typer.Option()` for `--no-calibrate`. Cosmetic; tests pass with 1 warning. Fix in the next Typer upgrade.
- **`LEARNING_LOG.md` does not exist.** Operator plans to create it. Sections 3 and 6 of this file are interim canon.

### Test gaps
- **`_do_ingest_league` / `_do_ingest_understat_league` CLI loop behavior** not unit-tested. Low priority.
- **XGBoost integration test uses 180-day step** to bound wall-time; fold-level permutation audit therefore covers fewer folds than the canonical 7-day run. Acceptable.

---

## 6. Recent decisions log (compressed)

Episodes 4–12 are from Phase 0 step 2 (Understat era). Compressed to one-liners here; full context is in the old HANDOFF.md (committed 2026-05-01).

**Ep 4** Migration 002 empty-string false-positive fix — `extras[KEY] <> ''` guard added.
**Ep 5** Closing-odds coverage diagnostic — Pinnacle starts 2012-13, B365 starts 2019-20.
**Ep 6** Plan-mode guard rails saved hours — Understat's HTML page no longer embeds inline JSON.
**Ep 7** `team_aliases` temporal columns (`active_from`/`active_to`) added for rebrand future-proofing.
**Ep 8** `kickoff_local` + `kickoff_utc` dual storage; TZ via `zoneinfo`.
**Ep 9/10** Understat AJAX endpoint discovered from `understatapi` v0.7.1 source; HTML scraping dead.
**Ep 11** `forecast_*_pct` is post-match attribution, not pre-match prediction — data leakage trap. Stored with warning docstring. Do NOT use as a feature.
**Ep 12** Temporal-alias-join test uses two-raw-name-same-team variant (schema-compatible with `(source, raw_name)` PK).

---

**Episode 13 — Phase 1 diagnostic battery (2026-05-04/05).** Four diagnostic runs in sequence:

1. `dc_v1` calibrated → **NO_GO**. Mean edge on winners: −0.0021. DC 1X2 model is dead.
2. `xg_skellam_v1` calibrated → initial GO, but bootstrap CI crossed zero when scrutinised → downgraded to MARGINAL_SIGNAL.
3. `dc_v1` no-calibrate → **NO_GO** (confirms isotonic wasn't the DC problem).
4. `xg_skellam_v1` no-calibrate, `xi_decay=0.0` → **MARGINAL_SIGNAL, p=0.038**, all 7 seasons positive.

Key learning: isotonic calibration consistently degrades CLV edge in both models. `xi_decay=0.0` (uniform weighting) outperforms decay in xG-Skellam. Locked config: `xi_decay=0.0, no_calibrate=True`.

---

**Episode 14 — Bootstrap CI + MARGINAL_SIGNAL tier (2026-05-05).** Added `bootstrap_edge_ci` (percentile bootstrap, resampling `is_winner=TRUE` rows, 10 000 resamples, `p_value_above_zero = mean(resample_means <= 0)`). Added `MARGINAL_SIGNAL` verdict tier: `n_eval ≥ 2000 AND mean > 0 AND ci_low ≤ 0`. Verdict ladder (5 tiers):

- `INSUFFICIENT_SAMPLE`: n_eval < 1000
- `PRELIMINARY_SIGNAL`: 1000 ≤ n_eval < 2000
- `NO_GO`: n_eval ≥ 2000 AND mean_edge_winners ≤ 0
- `MARGINAL_SIGNAL`: n_eval ≥ 2000 AND mean > 0 AND ci_low ≤ 0
- `GO`: n_eval ≥ 2000 AND mean > 0 AND ci_low > 0

xG-Skellam (xi_decay=0.0, no-calibrate) lands at MARGINAL_SIGNAL. Operator accepted this as operational green-light for Phase 2 given the season-level consistency.

---

**Episode 15 — XGBoost O/U 2.5 infrastructure (Phase 2 step 1, 2026-05-06).** Full feature engineering pipeline + model + audit gate:

- `features/assembler.py`: 15 SQL features (8 xG-rolling/5-match + 6 results-rolling/10-match + 1 xg_skellam_p_over stacked feature). PIT mode: `ROWS BETWEEN N PRECEDING AND 1 PRECEDING` window functions. Snapshot mode: `ROW_NUMBER() … ORDER BY kickoff_utc DESC` + GROUP BY.
- `features.md`: domain rationale written before training code invoked (per §10 Phase 2 requirement).
- `models/xgboost_ou25.py`: `XGBoostOU25Fit` dataclass; fixed XGB params (n_estimators=400, max_depth=4, lr=0.05, subsample=0.8); `MIN_XGB_TRAIN_MATCHES=500`.
- `eval/feature_audit.py`: null CI from permuting `audit_noise` 100 times; per-feature perm importance vs null CI; `below_null_baseline` flag.
- `walkforward.py`: `needs_features=True` registry key; XGBoost path builds PIT train features → aligns labels via inner join → appends audit_noise (fold_idx seed) → fits → snapshot test features → perm audit → persist importances. Standard path (DC, xG-Skellam) unchanged.
- `007_xgb_artifacts.sql`: `xgb_fits` (one row per fold fit) + `xgb_feature_importances` (16 rows per fit).
- `make.ps1`: `$XgSkellamRunId` param → `--xg-skellam-run-id` CLI arg.
- Test counts: 138 unit / 10 integration (all green).

---

## 7. How to resume

1. **Read in this order** (small → large): `CLAUDE.md` (always-on), this `HANDOFF.md`, then `BLUE_MAP.md` §7.3–§7.4 (XGBoost fold stability + feature audit) if the task touches Phase 2. Skip the rest of BLUE_MAP unless a section is cited directly.

2. **Confirm test suite is green:**
   ```powershell
   .\make.ps1 test
   # expect: 138 passed, 1 xfailed
   $env:FOOTY_EV_INTEGRATION_DB = "1"
   .\make.ps1 test-integration
   # expect: 10 passed, 2 skipped
   ```

3. **Confirm warehouse state:**
   ```sql
   SELECT COUNT(*) FROM raw_match_results;       -- 9832 (EPL 2000-01 → 2025-26)
   SELECT COUNT(*) FROM raw_understat_matches;   -- 4560 (EPL 2014-15 → 2025-26)
   SELECT COUNT(*) FROM team_aliases;            -- 70
   SELECT run_id, model_version, status, n_predictions
   FROM backtest_runs ORDER BY started_at DESC LIMIT 5;
   -- should show the locked xg_skellam run_id = 034bb631-83e8-4fdf-a7f5-1189bd107df6
   ```

4. **First move in the new chat:** Run the canonical XGBoost backtest (see §4 above). Operator pastes this HANDOFF.md + CLAUDE.md + PROJECT_INSTRUCTIONS.md + BLUE_MAP.md into the new session, says "Phase 2 step 1 landed, canonical XGBoost run pending — should I run it or do you want to inspect anything first?" Claude responds with the operator command from §4.

5. **Environment quirks (operator-side, not code-fixable):**
   - `VIRTUAL_ENV` mismatch warning is cosmetic; ignore.
   - `uv` may not be on default PATH; prepend `$env:USERPROFILE\.local\bin` if needed.

---

## 8. What NOT to do

Abbreviated banned-paths reminder (full detail in `PROJECT_INSTRUCTIONS.md` §5 and `CLAUDE.md` "Banned paths"):

- **No multi-account / "ghost execution" / human-mimicking bet sequencers.** Route volume through Betfair Exchange.
- **No k-fold CV on time-series data.** Walk-forward only.
- **No Pinnacle as a live odds API source.** Historical CSV closing-odds data IS allowed.
- **No Transformer / DeepAR / RNN architectures for in-play in Phase 1 or 2.**
- **No local 4–8B LLMs as the "Analyst" producing probability estimates.** They parse text; they do not predict.
- **No paid services as if they're necessary.** The system must work end-to-end on free tooling.
- **No real-money bet placement until PROJECT_INSTRUCTIONS §3 bankroll conditions are met.**
- **No mocking the database in integration tests.** Use real DuckDB.
- **No fuzzy entity resolution at ingest time.** Raw names go in verbatim.
- **No f-string SQL with user/source-derived values.**
- **No business logic in notebooks.** Exploration only; reusable code moves to `src/footy_ev/`.
- **Don't use `forecast_*_pct` as a pre-match feature.** It is post-match attribution (Episode 11).
- **Don't re-enable isotonic calibration without a fresh diagnostic.** Isotonic consistently degraded CLV in all Phase 1 runs (Episode 13). `no_calibrate=True` is the production config.
- **Don't run the XGBoost backtest without passing `--xg-skellam-run-id`.** The stacked feature will default to 0.5 for all fixtures and the model degrades silently.
- **Don't trust audit_noise as a real feature.** It is a deliberate canary. `below_null_baseline=True` on audit_noise is the expected and correct outcome. If it appears ABOVE the null baseline, that is a bug signal.

If a request violates any of these, push back and cite this file or the upstream source.
