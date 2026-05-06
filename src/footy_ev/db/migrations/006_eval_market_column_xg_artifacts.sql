-- =========================================================================
-- 006_eval_market_column_xg_artifacts.sql
--
-- Phase 1 step 3: add market column to CLV/calibration/reliability tables;
-- create xg_fits and xg_team_params for the xG-Skellam O/U model.
--
-- All changes are idempotent (IF NOT EXISTS / IF NOT EXISTS guard on ALTER).
-- =========================================================================

-- Add market column to step-2 tables so multi-market runs can coexist.
-- Existing rows (all from dc_v1 / 1x2) get backfilled to '1x2'.

ALTER TABLE clv_evaluations  ADD COLUMN IF NOT EXISTS market VARCHAR;
ALTER TABLE calibration_fits ADD COLUMN IF NOT EXISTS market VARCHAR;
ALTER TABLE reliability_bins ADD COLUMN IF NOT EXISTS market VARCHAR;

UPDATE clv_evaluations  SET market = '1x2' WHERE market IS NULL;
UPDATE calibration_fits SET market = '1x2' WHERE market IS NULL;
UPDATE reliability_bins SET market = '1x2' WHERE market IS NULL;

-- xG-Skellam model fit metadata (mirrors dc_fits structure but no rho_tau).
CREATE TABLE IF NOT EXISTS xg_fits (
    fit_id              VARCHAR PRIMARY KEY,
    league              VARCHAR NOT NULL,
    as_of               TIMESTAMP NOT NULL,
    gamma_home_adv      DOUBLE NOT NULL,
    xi_decay            DOUBLE NOT NULL,
    n_train_matches     INTEGER NOT NULL,
    log_likelihood      DOUBLE NOT NULL,
    optimizer_status    VARCHAR NOT NULL,
    fit_seconds         DOUBLE NOT NULL,
    model_version       VARCHAR NOT NULL,
    fitted_at           TIMESTAMP NOT NULL
);

-- Per-team xG attack/defense parameters (mirrors dc_team_params).
CREATE TABLE IF NOT EXISTS xg_team_params (
    fit_id          VARCHAR NOT NULL,
    team_id         VARCHAR NOT NULL,
    alpha_attack    DOUBLE NOT NULL,
    beta_defense    DOUBLE NOT NULL,
    PRIMARY KEY (fit_id, team_id)
);
