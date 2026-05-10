-- =========================================================================
-- Migration 010: Betfair entity-resolution tables.
--
-- Entity-resolution policy (CLAUDE.md invariant): resolution is a
-- deterministic SQL join at query time. Bootstrap data is produced by
-- scripts/bootstrap_betfair_aliases.py (fuzzy match + manual review),
-- never by runtime code.
--
-- Tables:
--   betfair_team_aliases      — Betfair team name → canonical team_id
--   betfair_market_aliases    — Betfair market type code → internal market
--   betfair_selection_aliases — (internal_market, Betfair runner name) → internal selection
--   betfair_event_resolutions — runtime resolution cache; Betfair event ID → fixture_id
--
-- betfair_market_aliases and betfair_selection_aliases are seeded here
-- with the handful of football market/selection types that matter.
--
-- All tables are idempotent (CREATE TABLE IF NOT EXISTS).
-- =========================================================================

CREATE TABLE IF NOT EXISTS betfair_team_aliases (
    betfair_team_name   VARCHAR PRIMARY KEY,
    team_id             VARCHAR NOT NULL,
    confidence          DOUBLE  NOT NULL DEFAULT 1.0,
    resolved_by         VARCHAR NOT NULL DEFAULT 'manual',
    resolved_at         TIMESTAMP NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_betfair_team_aliases_team_id
    ON betfair_team_aliases (team_id);

-- -------------------------------------------------------------------------
-- betfair_market_aliases — small static lookup (only ~5 market types matter)
-- -------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS betfair_market_aliases (
    betfair_market_type VARCHAR PRIMARY KEY,
    internal_market     VARCHAR NOT NULL
);

INSERT INTO betfair_market_aliases (betfair_market_type, internal_market)
VALUES
    ('MATCH_ODDS',       '1x2'),
    ('OVER_UNDER_25',    'ou_2.5'),
    ('OVER_UNDER_35',    'ou_3.5'),
    ('BOTH_TEAMS_TO_SCORE', 'btts'),
    ('ASIAN_HANDICAP',   'asian_handicap')
ON CONFLICT DO NOTHING;

-- -------------------------------------------------------------------------
-- betfair_selection_aliases — (market, Betfair runner name) → selection key
-- -------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS betfair_selection_aliases (
    internal_market         VARCHAR NOT NULL,
    betfair_runner_name     VARCHAR NOT NULL,
    internal_selection      VARCHAR NOT NULL,
    PRIMARY KEY (internal_market, betfair_runner_name)
);

INSERT INTO betfair_selection_aliases
    (internal_market, betfair_runner_name, internal_selection)
VALUES
    -- Over/Under 2.5 Goals
    ('ou_2.5', 'Over 2.5 Goals',  'over'),
    ('ou_2.5', 'Under 2.5 Goals', 'under'),
    -- Over/Under 3.5 Goals
    ('ou_3.5', 'Over 3.5 Goals',  'over'),
    ('ou_3.5', 'Under 3.5 Goals', 'under'),
    -- Both Teams to Score
    ('btts', 'Yes', 'yes'),
    ('btts', 'No',  'no'),
    -- Match Odds (1X2) — runner names are the actual team names; these are
    -- resolved dynamically via betfair_team_aliases, not via this table.
    -- Draw is static.
    ('1x2', 'The Draw', 'draw')
ON CONFLICT DO NOTHING;

-- -------------------------------------------------------------------------
-- betfair_event_resolutions — runtime cache of resolved Betfair event IDs.
-- Written by the scraper node after a successful resolve_event() call.
-- Status ∈ {resolved, ambiguous, unresolved}.
-- -------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS betfair_event_resolutions (
    betfair_event_id    VARCHAR PRIMARY KEY,
    fixture_id          VARCHAR,
    confidence          DOUBLE,
    resolved_at         TIMESTAMP NOT NULL,
    status              VARCHAR NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_betfair_event_resolutions_fixture
    ON betfair_event_resolutions (fixture_id);
