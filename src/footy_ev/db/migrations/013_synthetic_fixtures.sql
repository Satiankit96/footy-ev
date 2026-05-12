-- =========================================================================
-- Migration 013: synthetic_fixtures table for Kalshi-derived fixtures.
--
-- When the bootstrap script (scripts/bootstrap_kalshi_aliases.py) ticker-parses
-- a Kalshi event and resolves both teams, but no warehouse fixture matches
-- (e.g. the current-season football-data.co.uk CSV has not refreshed yet),
-- it inserts a synthetic row here.
--
-- v_fixtures_epl (defined in views/020_v_fixtures_epl.sql) is amended in this
-- migration's companion view-bump to UNION ALL these rows. Downstream consumers
-- (paper-trader, dashboard) need no changes — they continue to query the view.
--
-- fixture_id convention: 'KXFIX-<event_ticker>' so synthetic rows are
-- distinguishable from real raw_match_results-derived ones (which use the
-- composite 'EPL|2025-2026|home|away|YYYY-MM-DD' key).
--
-- All rows here have status='scheduled' on insert; settlement is out of scope
-- (no scores). When a real fixtures-ingestion source is wired the operator can
-- DELETE rows whose teams+date now match a raw_match_results row.
--
-- Idempotent: PRIMARY KEY on fixture_id.
-- =========================================================================

CREATE TABLE IF NOT EXISTS synthetic_fixtures (
    fixture_id      VARCHAR PRIMARY KEY,
    league          VARCHAR NOT NULL,
    season          VARCHAR NOT NULL,
    home_team_id    VARCHAR NOT NULL,
    away_team_id    VARCHAR NOT NULL,
    match_date      DATE    NOT NULL,
    kickoff_utc     TIMESTAMP NOT NULL,
    event_ticker    VARCHAR NOT NULL,
    status          VARCHAR NOT NULL DEFAULT 'scheduled',
    ingested_at     TIMESTAMP NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_synthetic_fixtures_teams_date
    ON synthetic_fixtures (home_team_id, away_team_id, match_date);
