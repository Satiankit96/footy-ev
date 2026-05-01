-- Migration 003: raw Understat per-match xG ledger + cross-source team alias table.
--
-- Storage pattern is the same as migration 001 (DuckDB tables as the mutable write
-- surface, Parquet archive nightly, unified v_* views joining live + archive).
--
-- This migration introduces TWO tables:
--   1. raw_understat_matches — one row per Understat match (top-of-page datesData JSON).
--   2. team_aliases          — cross-source canonical-name registry for entity resolution.
--
-- Entity-resolution policy (per Phase 0 step 2 plan):
--   We do NOT resolve team identity at ingest time. raw_understat_matches stores raw
--   Understat team strings verbatim. The downstream view v_understat_matches (lives
--   under src/footy_ev/db/views/, NOT in this migration) joins team_aliases to produce
--   canonical team_id columns. Any unmapped raw_name surfaces as NULL through that
--   view and is reported by the understat-detect-unmapped CLI.

-- =========================================================================
-- raw_understat_matches: one row per match scraped from understat.com.
-- Source page is https://understat.com/league/<EPL|...>/<YYYY> which embeds a
-- `var datesData = JSON.parse('...')` blob containing the season's matches.
-- All goal/xG columns are NULLABLE because in-progress seasons have unplayed
-- matches with isResult=False.
-- =========================================================================
CREATE TABLE IF NOT EXISTS raw_understat_matches (
    -- Ingestion metadata
    league               VARCHAR NOT NULL,            -- canonical code: EPL, LaLiga, SerieA, Bundesliga, Ligue1
    season               VARCHAR NOT NULL,            -- "2024-2025" (NOT the URL year code "2024")
    source_code          VARCHAR NOT NULL,            -- always 'understat' for this table
    source_url           VARCHAR NOT NULL,
    ingested_at          TIMESTAMP NOT NULL,
    source_row_hash      VARCHAR NOT NULL,            -- sha256 of canonical-JSON-encoded match dict; used to skip no-op upserts

    -- Natural keys (raw, NOT entity-resolved — see team_aliases below)
    understat_match_id   VARCHAR NOT NULL,            -- stable Understat ID, e.g. '14048'
    understat_home_id    VARCHAR NOT NULL,
    understat_away_id    VARCHAR NOT NULL,
    home_team_raw        VARCHAR NOT NULL,            -- Understat-spelled name, e.g. 'Manchester United'
    away_team_raw        VARCHAR NOT NULL,

    -- Match facts
    -- kickoff_local: as-scraped, league-local TZ. Audit/debug only — do NOT use in
    -- downstream queries. kickoff_utc is the canonical time column.
    kickoff_local        TIMESTAMP NOT NULL,
    kickoff_utc          TIMESTAMP NOT NULL,
    is_result            BOOLEAN  NOT NULL,
    home_goals           INTEGER,                     -- NULL for unplayed matches
    away_goals           INTEGER,
    home_xg              DOUBLE,                      -- NULL for unplayed matches
    away_xg              DOUBLE,

    -- Understat's own pre-match win-probability forecast. Informational only;
    -- do NOT use as a model input — it's a feature, not a label.
    forecast_home_pct    DOUBLE,
    forecast_draw_pct    DOUBLE,
    forecast_away_pct    DOUBLE,

    -- Drift-safe catchall. Any JSON key returned by Understat that is NOT covered by
    -- the Pydantic model lands here verbatim (key = JSON path, value = stringified).
    extras               MAP(VARCHAR, VARCHAR),

    -- Single-column PK. Understat IDs are stable per match.
    -- A future migration may add UNIQUE (league, season, kickoff_utc, home_team_raw,
    -- away_team_raw) as a tripwire constraint (Option C from the plan); the loader's
    -- ON CONFLICT clause targets understat_match_id by name precisely so adding that
    -- constraint later is non-breaking.
    PRIMARY KEY (understat_match_id)
);

CREATE INDEX IF NOT EXISTS idx_raw_understat_kickoff_utc
    ON raw_understat_matches (kickoff_utc);
CREATE INDEX IF NOT EXISTS idx_raw_understat_league_season
    ON raw_understat_matches (league, season);

-- =========================================================================
-- team_aliases: maps a (source, raw_name) pair to a canonical team_id.
-- Bootstrapped manually via scripts/seed_team_aliases.sql; rows are NOT
-- created by ingestion. Unmapped raw_names surface as NULL through
-- v_understat_matches and are reported by the understat-detect-unmapped CLI.
--
-- Temporal columns (active_from, active_to):
--   Future-proofing against mid-history team rebrands (e.g. a club renames itself
--   between seasons; same canonical team_id, two distinct raw_names with disjoint
--   validity windows). On bootstrap both columns are NULL — interpreted as "valid
--   forever" by the v_understat_matches join, which uses
--     COALESCE(active_from, '1900-01-01'::TIMESTAMP) AND COALESCE(active_to, '9999-12-31'::TIMESTAMP).
-- =========================================================================
CREATE TABLE IF NOT EXISTS team_aliases (
    source        VARCHAR   NOT NULL,                 -- 'football_data' | 'understat'
    raw_name      VARCHAR   NOT NULL,                 -- as it appears on the source
    team_id       VARCHAR   NOT NULL,                 -- canonical id, e.g. 'man_united'
    confidence    VARCHAR   NOT NULL,                 -- 'manual' | 'exact_match'
    resolved_at   TIMESTAMP NOT NULL,
    active_from   TIMESTAMP,                          -- NULL = valid from beginning of time
    active_to     TIMESTAMP,                          -- NULL = valid forever
    notes         VARCHAR,
    -- PK is (source, raw_name). Mid-history rebrands typically produce a NEW
    -- raw_name, so a single (source, raw_name) row is sufficient per era. Same
    -- raw_name reassigned to a different team across eras is currently
    -- unsupported; if that ever surfaces, escalate to a surrogate alias_id PK.
    PRIMARY KEY (source, raw_name)
);

CREATE INDEX IF NOT EXISTS idx_team_aliases_team_id
    ON team_aliases (team_id);
