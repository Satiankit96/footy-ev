-- =========================================================================
-- v_fixtures_epl: unified fixture view for EPL, BLUE_MAP §6.2 fixtures shape.
--
-- Projects raw_match_results (football-data.co.uk) into the canonical
-- fixtures contract, joining team_aliases (source='football_data') for
-- canonical team_ids and LEFT JOINing v_understat_matches for xG.
--
-- fixture_id is a deterministic composite key (league|season|home_team_id|
-- away_team_id|match_date). Stable across re-applications. Long but
-- human-readable.
--
-- kickoff_utc simplification (Phase 1 step 1):
--   Day-level granularity only — kickoff_utc is CAST(match_date AS TIMESTAMP),
--   i.e. midnight on match day. match_time is nullable in older seasons
--   anyway. Walk-forward step is weekly (step_days=7), so sub-day precision
--   is irrelevant at this stage. Refine to true UTC alignment when CLV
--   computation against intra-day SP snapshots needs it.
--
-- Failure mode: any unmapped raw_name yields NULL home_team_id /
-- away_team_id. Downstream consumers (the walk-forward harness) MUST filter
-- on team_id IS NOT NULL before fitting.
--
-- Idempotent: CREATE OR REPLACE VIEW. Lexical apply order: applied AFTER
-- v_understat_matches (lex order in views/ dir).
-- =========================================================================

CREATE OR REPLACE VIEW v_fixtures_epl AS
WITH base AS (
    SELECT
        r.league,
        r.season,
        r.match_date,
        r.home_team       AS home_team_raw,
        r.away_team       AS away_team_raw,
        ha.team_id        AS home_team_id,
        aa.team_id        AS away_team_id,
        r.fthg            AS home_score_ft,
        r.ftag            AS away_score_ft,
        r.ftr             AS result_ft,
        CAST(r.match_date AS TIMESTAMP) AS kickoff_utc,
        CASE
            WHEN r.fthg IS NOT NULL AND r.ftag IS NOT NULL THEN 'final'
            ELSE 'scheduled'
        END AS status
    FROM raw_match_results r
    LEFT JOIN team_aliases ha
        ON ha.source = 'football_data'
       AND ha.raw_name = r.home_team
       AND CAST(r.match_date AS TIMESTAMP)
           BETWEEN COALESCE(ha.active_from, '1900-01-01'::TIMESTAMP)
               AND COALESCE(ha.active_to,   '9999-12-31'::TIMESTAMP)
    LEFT JOIN team_aliases aa
        ON aa.source = 'football_data'
       AND aa.raw_name = r.away_team
       AND CAST(r.match_date AS TIMESTAMP)
           BETWEEN COALESCE(aa.active_from, '1900-01-01'::TIMESTAMP)
               AND COALESCE(aa.active_to,   '9999-12-31'::TIMESTAMP)
    WHERE r.league = 'EPL'
)
SELECT
    concat_ws(
        '|',
        b.league,
        b.season,
        COALESCE(b.home_team_id, '<UNMAPPED:' || b.home_team_raw || '>'),
        COALESCE(b.away_team_id, '<UNMAPPED:' || b.away_team_raw || '>'),
        CAST(b.match_date AS VARCHAR)
    ) AS fixture_id,
    b.league,
    b.season,
    b.home_team_id,
    b.away_team_id,
    b.home_team_raw,
    b.away_team_raw,
    b.match_date,
    b.kickoff_utc,
    b.home_score_ft,
    b.away_score_ft,
    b.result_ft,
    u.home_xg,
    u.away_xg,
    b.status
FROM base b
LEFT JOIN v_understat_matches u
    ON CAST(u.kickoff_local AS DATE) = b.match_date
   AND u.home_team_id = b.home_team_id
   AND u.away_team_id = b.away_team_id

UNION ALL

-- Synthetic fixtures derived from Kalshi events (see migration 013).
-- Inserted by scripts/bootstrap_kalshi_aliases.py when ticker+team resolution
-- succeeds but no raw_match_results row matches yet.
SELECT
    s.fixture_id,
    s.league,
    s.season,
    s.home_team_id,
    s.away_team_id,
    NULL                  AS home_team_raw,
    NULL                  AS away_team_raw,
    s.match_date,
    s.kickoff_utc,
    NULL                  AS home_score_ft,
    NULL                  AS away_score_ft,
    NULL                  AS result_ft,
    NULL                  AS home_xg,
    NULL                  AS away_xg,
    s.status
FROM synthetic_fixtures s;
