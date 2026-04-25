-- Migration 001: raw match results from football-data.co.uk, teams placeholder,
-- schema drift log.
--
-- Storage pattern (per BLUE_MAP.md §6.1 + decision 2026-04-24):
--   DuckDB tables are the mutable write surface (ON CONFLICT upsert semantics matter
--   for bug-fix-and-rerun cycles). Nightly COPY ... TO 'data/warehouse/**/*.parquet'
--   PARTITION_BY (league, season) archives them. Downstream code queries unified v_*
--   views joining the live DuckDB tables + parquet_scan() over the archive.
-- This pattern is shared across all ingestion modules (odds_snapshots, events_ledger, ...).

-- =========================================================================
-- raw_match_results: one row per match, columns mirror football-data.co.uk CSV.
-- All stat/odds columns are NULLABLE because column coverage varies across ~25 seasons.
-- =========================================================================
CREATE TABLE IF NOT EXISTS raw_match_results (
    -- Ingestion metadata
    league            VARCHAR NOT NULL,           -- canonical code: EPL, LaLiga, SerieA, Bundesliga, Ligue1
    season            VARCHAR NOT NULL,           -- "2024-2025" (NOT the URL code "2425")
    source_code       VARCHAR NOT NULL,           -- football-data.co.uk file code: E0, D1, SP1, I1, F1
    source_url        VARCHAR NOT NULL,
    ingested_at       TIMESTAMP NOT NULL,
    source_row_hash   VARCHAR NOT NULL,           -- sha256 of raw CSV line; used to skip no-op upserts

    -- Core match (required every season)
    div               VARCHAR NOT NULL,           -- source col Div
    match_date        DATE    NOT NULL,           -- parsed from source Date (dd/mm/yyyy or dd/mm/yy + century pivot)
    match_time        TIME,                       -- source col Time (present from ~2019 onward)
    home_team         VARCHAR NOT NULL,           -- source HomeTeam (NOT yet canonicalized; see teams table)
    away_team         VARCHAR NOT NULL,           -- source AwayTeam
    fthg              INTEGER,                    -- full-time home goals
    ftag              INTEGER,                    -- full-time away goals
    ftr               VARCHAR,                    -- full-time result: H / D / A
    hthg              INTEGER,                    -- half-time home goals (absent in some early seasons)
    htag              INTEGER,
    htr               VARCHAR,
    referee           VARCHAR,

    -- Match stats (oldest seasons frequently missing these)
    hs                INTEGER,                    -- home shots total
    as_               INTEGER,                    -- away shots total ("AS" is a SQL reserved word; canonical is as_)
    hst               INTEGER,                    -- home shots on target
    ast               INTEGER,                    -- away shots on target
    hf                INTEGER,                    -- home fouls committed
    af                INTEGER,                    -- away fouls committed
    hc                INTEGER,                    -- home corners
    ac                INTEGER,                    -- away corners
    hy                INTEGER,                    -- home yellow cards
    ay                INTEGER,                    -- away yellow cards
    hr                INTEGER,                    -- home red cards
    ar                INTEGER,                    -- away red cards

    -- 1X2 decimal odds per bookmaker (all nullable; books come and go across eras)
    b365h DOUBLE, b365d DOUBLE, b365a DOUBLE,     -- Bet365
    bwh   DOUBLE, bwd   DOUBLE, bwa   DOUBLE,     -- Betway
    iwh   DOUBLE, iwd   DOUBLE, iwa   DOUBLE,     -- Interwetten
    psh   DOUBLE, psd   DOUBLE, psa   DOUBLE,     -- Pinnacle (HISTORICAL ONLY; live Pinnacle API banned per CLAUDE.md)
    whh   DOUBLE, whd   DOUBLE, wha   DOUBLE,     -- William Hill
    vch   DOUBLE, vcd   DOUBLE, vca   DOUBLE,     -- VC Bet
    maxh  DOUBLE, maxd  DOUBLE, maxa  DOUBLE,     -- max across books
    avgh  DOUBLE, avgd  DOUBLE, avga  DOUBLE,     -- avg across books
    bfeh  DOUBLE, bfed  DOUBLE, bfea  DOUBLE,     -- Betfair Exchange back odds (newer seasons only)

    -- Over/Under 2.5 goals
    b365_over_25  DOUBLE, b365_under_25  DOUBLE,
    p_over_25     DOUBLE, p_under_25     DOUBLE,  -- Pinnacle O/U — same historical-only caveat as PSH/D/A
    max_over_25   DOUBLE, max_under_25   DOUBLE,
    avg_over_25   DOUBLE, avg_under_25   DOUBLE,

    -- Asian handicap
    ah_line       DOUBLE,                          -- source AHh: handicap applied to home team
    b365_ah_home  DOUBLE, b365_ah_away  DOUBLE,
    p_ah_home     DOUBLE, p_ah_away     DOUBLE,

    -- Drift-safe catchall. Any source column not in the column registry (see
    -- src/footy_ev/ingestion/football_data/columns.py) is preserved here verbatim:
    -- key = original CSV column name, value = stringified cell. Zero data loss on
    -- unexpected new source columns.
    extras        MAP(VARCHAR, VARCHAR),

    -- Natural-key PRIMARY KEY.
    -- Assumption: (league, season, match_date, home_team, away_team) uniquely
    -- identifies a match. This holds for the five top-division leagues we target
    -- (EPL, La Liga, Serie A, Bundesliga, Ligue 1). It BREAKS for cup competitions
    -- with replays (FA Cup, Coppa Italia) and for lower-division double-headers.
    -- If we ever ingest those sources, this PK must move to a surrogate match_id
    -- (e.g. sha256(league|season|date|home|away|replay_seq)).
    PRIMARY KEY (league, season, match_date, home_team, away_team)
);

CREATE INDEX IF NOT EXISTS idx_raw_match_results_date
    ON raw_match_results (match_date);

-- =========================================================================
-- teams: canonical team registry. Empty on creation — populated by a later
-- entity-resolution step. Included in this migration so downstream code has
-- a stable schema target to join against (home_team / away_team source strings
-- like 'Man United' / 'Manchester United' resolve to a single team_id via aliases).
-- =========================================================================
CREATE TABLE IF NOT EXISTS teams (
    team_id     VARCHAR PRIMARY KEY,
    team_name   VARCHAR NOT NULL,
    country     VARCHAR NOT NULL,
    aliases     VARCHAR[],                        -- raw source strings seen for this team
    ingested_at TIMESTAMP NOT NULL
);

-- =========================================================================
-- schema_drift_log: every unknown source column we observe during ingestion
-- gets a row here with sample values. Operator reviews WHERE NOT resolved
-- periodically and either (a) extends the column registry to promote the
-- column to a typed field, or (b) marks the row resolved = TRUE (intentional
-- drop, noise column, etc.). Unresolved drift rows are technical debt — see
-- TODO at the top of loader.py.
-- =========================================================================
CREATE TABLE IF NOT EXISTS schema_drift_log (
    observed_at   TIMESTAMP NOT NULL,
    league        VARCHAR NOT NULL,
    season        VARCHAR NOT NULL,
    source_code   VARCHAR NOT NULL,
    column_name   VARCHAR NOT NULL,
    sample_values VARCHAR[] NOT NULL,
    resolved      BOOLEAN NOT NULL DEFAULT FALSE
);
CREATE INDEX IF NOT EXISTS idx_schema_drift_unresolved
    ON schema_drift_log (resolved, observed_at);
