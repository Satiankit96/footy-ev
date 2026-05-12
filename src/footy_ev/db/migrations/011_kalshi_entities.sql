-- =========================================================================
-- Migration 011: Kalshi entity-resolution tables + paper_bets.venue column.
--
-- Entity-resolution policy (CLAUDE.md invariant): resolution is a
-- deterministic SQL join at query time. Bootstrap data is produced by
-- scripts/bootstrap_kalshi_aliases.py (--from-fixture mode), never by
-- runtime code.
--
-- Tables:
--   kalshi_event_aliases      — Kalshi event ticker → warehouse fixture_id
--   kalshi_contract_resolutions — runtime resolution cache
--
-- paper_bets gets a venue column (DEFAULT 'kalshi') so every recorded bet
-- carries its originating venue. Rows written before this migration receive
-- the default; Betfair rows from prior sessions can be back-filled manually.
--
-- All DDL is idempotent (CREATE TABLE IF NOT EXISTS, ADD COLUMN IF NOT EXISTS).
-- =========================================================================

-- -------------------------------------------------------------------------
-- kalshi_event_aliases — operator-reviewed mapping from Kalshi event ticker
-- to warehouse fixture_id.  Bootstrap data comes from
-- scripts/bootstrap_kalshi_aliases.py --from-fixture.
-- -------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS kalshi_event_aliases (
    event_ticker    VARCHAR PRIMARY KEY,
    fixture_id      VARCHAR NOT NULL,
    confidence      DOUBLE  NOT NULL DEFAULT 1.0,
    resolved_by     VARCHAR NOT NULL DEFAULT 'manual',
    resolved_at     TIMESTAMP NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_kalshi_event_aliases_fixture
    ON kalshi_event_aliases (fixture_id);

-- -------------------------------------------------------------------------
-- kalshi_contract_resolutions — runtime cache written by the scraper node
-- after each successful / failed resolve_kalshi_market() call.
-- Status ∈ {resolved, ambiguous, unresolved}.
-- -------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS kalshi_contract_resolutions (
    event_ticker    VARCHAR PRIMARY KEY,
    fixture_id      VARCHAR,
    confidence      DOUBLE,
    resolved_at     TIMESTAMP NOT NULL,
    status          VARCHAR NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_kalshi_contract_resolutions_fixture
    ON kalshi_contract_resolutions (fixture_id);

-- -------------------------------------------------------------------------
-- paper_bets.venue — which execution venue produced this bet record.
-- DuckDB ADD COLUMN IF NOT EXISTS is idempotent (0.8.0+).
-- -------------------------------------------------------------------------
ALTER TABLE paper_bets ADD COLUMN IF NOT EXISTS venue VARCHAR DEFAULT 'kalshi';
