-- =========================================================================
-- 004_phase1_model_artifacts.sql
--
-- Phase 1 step 1: Dixon-Coles fit + walk-forward harness storage.
--
-- Tables created (all idempotent via IF NOT EXISTS):
--   model_predictions   per-match model outputs. Mirrors BLUE_MAP §6.2 with
--                       ONE EXTENSION: a nullable `run_id` column (not in
--                       §6.2) groups predictions by harness invocation.
--                       sigma_p is NULLABLE (relaxed from §6.2 NOT NULL)
--                       because bootstrap SE is deferred to a later step.
--   dc_fits             one row per (league, as_of) Dixon-Coles fit.
--   dc_team_params      per-team alpha (attack) / beta (defense), keyed to
--                       a fit_id from dc_fits.
--   backtest_runs       run-level metadata for walk-forward invocations.
--                       n_folds / n_predictions / completed_at are nullable
--                       and filled in on completion; status transitions
--                       running -> complete | failed.
--
-- The `teams` table from BLUE_MAP §6.2 already exists in the warehouse
-- (created earlier and currently empty). It is NOT touched here; population
-- is a one-time operator bootstrap via scripts/seed_teams.sql.
--
-- No data writes. No FK constraints (matches the convention from
-- migrations 001-003).
-- =========================================================================

CREATE TABLE IF NOT EXISTS model_predictions (
    prediction_id    VARCHAR PRIMARY KEY,
    fixture_id       VARCHAR NOT NULL,
    market           VARCHAR NOT NULL,
    selection        VARCHAR NOT NULL,
    p_raw            DOUBLE NOT NULL,
    p_calibrated     DOUBLE NOT NULL,
    sigma_p          DOUBLE,
    model_version    VARCHAR NOT NULL,
    features_hash    VARCHAR NOT NULL,
    as_of            TIMESTAMP NOT NULL,
    generated_at     TIMESTAMP NOT NULL,
    run_id           VARCHAR
);

CREATE INDEX IF NOT EXISTS idx_model_predictions_fixture_market
    ON model_predictions (fixture_id, market, selection);

CREATE INDEX IF NOT EXISTS idx_model_predictions_run
    ON model_predictions (run_id);

CREATE TABLE IF NOT EXISTS dc_fits (
    fit_id            VARCHAR PRIMARY KEY,
    league            VARCHAR NOT NULL,
    as_of             TIMESTAMP NOT NULL,
    gamma_home_adv    DOUBLE NOT NULL,
    rho_tau           DOUBLE NOT NULL,
    xi_decay          DOUBLE NOT NULL,
    n_train_matches   INTEGER NOT NULL,
    log_likelihood    DOUBLE NOT NULL,
    optimizer_status  VARCHAR NOT NULL,
    fit_seconds       DOUBLE NOT NULL,
    model_version     VARCHAR NOT NULL,
    fitted_at         TIMESTAMP NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_dc_fits_league_asof
    ON dc_fits (league, as_of);

CREATE TABLE IF NOT EXISTS dc_team_params (
    fit_id           VARCHAR NOT NULL,
    team_id          VARCHAR NOT NULL,
    alpha_attack     DOUBLE NOT NULL,
    beta_defense     DOUBLE NOT NULL,
    PRIMARY KEY (fit_id, team_id)
);

CREATE TABLE IF NOT EXISTS backtest_runs (
    run_id             VARCHAR PRIMARY KEY,
    model_version      VARCHAR NOT NULL,
    league             VARCHAR NOT NULL,
    train_min_seasons  INTEGER NOT NULL,
    step_days          INTEGER NOT NULL,
    started_at         TIMESTAMP NOT NULL,
    completed_at       TIMESTAMP,
    n_folds            INTEGER,
    n_predictions      INTEGER,
    status             VARCHAR NOT NULL,
    notes              VARCHAR
);
