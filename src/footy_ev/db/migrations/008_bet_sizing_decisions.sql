-- =========================================================================
-- Migration 008: Kelly-sized bet sizing decisions.
--
-- bet_sizing_decisions records one row per prediction where Kelly sizing
-- was computed (Phase 2 step 4). This table is write-once at evaluation
-- time; actual bet execution (bet_decisions) comes in Phase 3.
--
-- Idempotent (CREATE TABLE IF NOT EXISTS).
-- =========================================================================

CREATE TABLE IF NOT EXISTS bet_sizing_decisions (
    decision_id         VARCHAR PRIMARY KEY,
    prediction_id       VARCHAR NOT NULL,
    run_id              VARCHAR NOT NULL,
    fixture_id          VARCHAR NOT NULL,
    market              VARCHAR NOT NULL,
    selection           VARCHAR NOT NULL,
    p_hat               DOUBLE NOT NULL,
    sigma_p             DOUBLE,
    odds_decimal        DOUBLE NOT NULL,
    bankroll_used       DECIMAL(18,2) NOT NULL,
    kelly_fraction_used DOUBLE NOT NULL,
    stake_gbp           DECIMAL(18,2) NOT NULL,
    per_bet_cap_hit     BOOLEAN NOT NULL DEFAULT FALSE,
    portfolio_cap_hit   BOOLEAN NOT NULL DEFAULT FALSE,
    decided_at          TIMESTAMP NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_bet_sizing_run
    ON bet_sizing_decisions (run_id);

CREATE INDEX IF NOT EXISTS idx_bet_sizing_prediction
    ON bet_sizing_decisions (prediction_id);
