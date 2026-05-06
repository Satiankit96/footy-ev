-- =========================================================================
-- 005_clv_calibration_artifacts.sql
--
-- Phase 1 step 2: closing-line edge (CLV proxy) + isotonic calibration +
-- reliability evaluation storage.
--
-- Tables created (all idempotent via IF NOT EXISTS):
--   clv_evaluations    one row per (run_id, prediction_id) — i.e. 3 per
--                      fixture for 1X2 markets. edge_at_close is the
--                      closing-line edge, NOT the strict-CLV
--                      bet_decisions.clv_pct (which requires odds_taken
--                      from a placed bet — distinct semantic). Column
--                      named edge_at_close to keep them disjoint.
--   calibration_fits   one row per (run_id, selection). Stores the FINAL
--                      end-of-run isotonic mapping (full prediction set
--                      per selection). iso_x / iso_y are the breakpoints
--                      from sklearn IsotonicRegression. Walk-forward
--                      per-fold fits are NOT persisted; the in-run
--                      calibrated values land in clv_evaluations.p_calibrated.
--   reliability_bins   per (run_id, selection, bin_idx). 15 uniform bins
--                      on [0, 1]. n_in_bin can be 0 (empty bin); in that
--                      case frac_pos / mean_pred / passes_2pp are NULL.
--
-- All idempotent. No FK constraints (matches convention from 001-004).
-- =========================================================================

CREATE TABLE IF NOT EXISTS clv_evaluations (
    evaluation_id           VARCHAR PRIMARY KEY,
    run_id                  VARCHAR NOT NULL,
    prediction_id           VARCHAR NOT NULL,
    fixture_id              VARCHAR NOT NULL,
    selection               VARCHAR NOT NULL,
    p_raw                   DOUBLE NOT NULL,
    p_calibrated            DOUBLE NOT NULL,
    pinnacle_close_decimal  DOUBLE NOT NULL,
    pinnacle_q_devigged     DOUBLE NOT NULL,
    devig_method            VARCHAR NOT NULL,
    edge_at_close           DOUBLE NOT NULL,
    is_winner               BOOLEAN NOT NULL,
    would_have_bet          BOOLEAN NOT NULL,
    evaluated_at            TIMESTAMP NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_clv_evaluations_run
    ON clv_evaluations (run_id);

CREATE INDEX IF NOT EXISTS idx_clv_evaluations_run_fixture
    ON clv_evaluations (run_id, fixture_id);

CREATE INDEX IF NOT EXISTS idx_clv_evaluations_run_winner
    ON clv_evaluations (run_id, is_winner);

CREATE TABLE IF NOT EXISTS calibration_fits (
    fit_id              VARCHAR PRIMARY KEY,
    run_id              VARCHAR NOT NULL,
    selection           VARCHAR NOT NULL,
    iso_x               DOUBLE[] NOT NULL,
    iso_y               DOUBLE[] NOT NULL,
    n_train             INTEGER NOT NULL,
    n_test              INTEGER NOT NULL,
    brier_raw           DOUBLE,
    brier_calibrated    DOUBLE,
    fitted_at           TIMESTAMP NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_calibration_fits_run
    ON calibration_fits (run_id);

CREATE TABLE IF NOT EXISTS reliability_bins (
    run_id      VARCHAR NOT NULL,
    selection   VARCHAR NOT NULL,
    bin_idx     INTEGER NOT NULL,
    bin_lower   DOUBLE NOT NULL,
    bin_upper   DOUBLE NOT NULL,
    n_in_bin    INTEGER NOT NULL,
    frac_pos    DOUBLE,
    mean_pred   DOUBLE,
    passes_2pp  BOOLEAN,
    PRIMARY KEY (run_id, selection, bin_idx)
);
