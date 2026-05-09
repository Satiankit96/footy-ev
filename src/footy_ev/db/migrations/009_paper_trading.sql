-- 009_paper_trading.sql
-- Phase 3 step 1: paper-trading runtime tables.
--
-- - paper_bets: append-only ledger of every approved-but-not-placed bet
--   decision produced by the LangGraph orchestrator. Includes the full
--   audit trail (model inputs hash, kelly fraction, odds at decision,
--   features hash) so any decision can be reproduced after the fact.
-- - live_odds_snapshots: append-only odds ticker for live data (Betfair
--   Exchange Delayed feed). Mirrors the historical odds_snapshots schema
--   but keyed on a (venue, fixture, market, selection, received_at) hash
--   for idempotency on retries.
-- - langgraph_checkpoint_summaries: one row per StateGraph invocation
--   (sqlite checkpoint blobs live in data/langgraph_checkpoints.sqlite).
-- - circuit_breaker_log: every staleness/auth/rate-limit trip with
--   reason and recovery time, surfaced on the dashboard.
--
-- All tables are append-only; settlement/recovery is recorded by writing
-- a new row or by setting a settlement_status column, never by mutating
-- the original audit row.

CREATE TABLE IF NOT EXISTS paper_bets (
    decision_id          VARCHAR PRIMARY KEY,
    run_id               VARCHAR,
    fixture_id           VARCHAR NOT NULL,
    market               VARCHAR NOT NULL,
    selection            VARCHAR NOT NULL,
    p_calibrated         DOUBLE NOT NULL,
    sigma_p              DOUBLE,
    odds_at_decision     DOUBLE NOT NULL,
    venue                VARCHAR NOT NULL,
    edge_pct             DOUBLE NOT NULL,
    kelly_fraction_used  DOUBLE NOT NULL,
    stake_gbp            DECIMAL(18, 2) NOT NULL,
    bankroll_used        DECIMAL(18, 2) NOT NULL,
    features_hash        VARCHAR NOT NULL,
    decided_at           TIMESTAMP NOT NULL,
    settlement_status    VARCHAR DEFAULT 'pending',
    settled_at           TIMESTAMP,
    pnl_gbp              DECIMAL(18, 2),
    closing_odds         DOUBLE,
    clv_pct              DOUBLE
);

CREATE INDEX IF NOT EXISTS idx_paper_bets_fixture
    ON paper_bets(fixture_id, decided_at DESC);

CREATE TABLE IF NOT EXISTS live_odds_snapshots (
    snapshot_id          VARCHAR PRIMARY KEY,
    venue                VARCHAR NOT NULL,
    fixture_id           VARCHAR NOT NULL,
    market               VARCHAR NOT NULL,
    selection            VARCHAR NOT NULL,
    odds_decimal         DOUBLE NOT NULL,
    liquidity_gbp        DOUBLE,
    received_at          TIMESTAMP NOT NULL,
    source_timestamp     TIMESTAMP,
    staleness_seconds    INTEGER
);

CREATE INDEX IF NOT EXISTS idx_live_odds_fixture_market
    ON live_odds_snapshots(fixture_id, market, received_at DESC);

CREATE TABLE IF NOT EXISTS langgraph_checkpoint_summaries (
    invocation_id        VARCHAR PRIMARY KEY,
    fixture_ids          VARCHAR[] NOT NULL,
    started_at           TIMESTAMP NOT NULL,
    completed_at         TIMESTAMP,
    final_node           VARCHAR,
    n_candidate_bets     INTEGER DEFAULT 0,
    n_approved_bets      INTEGER DEFAULT 0,
    breaker_tripped      BOOLEAN DEFAULT FALSE,
    breaker_reason       VARCHAR,
    last_error           VARCHAR,
    sqlite_thread_id     VARCHAR
);

CREATE TABLE IF NOT EXISTS circuit_breaker_log (
    event_id             VARCHAR PRIMARY KEY,
    tripped_at           TIMESTAMP NOT NULL,
    reason               VARCHAR NOT NULL,
    affected_source      VARCHAR NOT NULL,
    max_staleness_sec    INTEGER,
    auto_recovered       BOOLEAN DEFAULT FALSE,
    recovered_at         TIMESTAMP
);
