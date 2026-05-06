-- =========================================================================
-- v_pinnacle_close_epl: long-form Pinnacle closing odds for EPL.
--
-- Emits one row per (fixture_id, market, selection). Two markets:
--   1x2      — home / draw / away (psch / pscd / psca columns)
--   ou_2.5   — over / under       (pc_over_25 / pc_under_25 columns)
--
-- 1x2 rows are filtered to fixtures where all three prices are present.
-- O/U rows are filtered to fixtures where both pc_over_25 and pc_under_25
-- are present (independent of whether 1x2 prices exist).
--
-- is_winner:
--   1x2  home  → result_ft = 'H'
--   1x2  draw  → result_ft = 'D'
--   1x2  away  → result_ft = 'A'
--   ou_2.5 over  → home_score_ft + away_score_ft > 2
--   ou_2.5 under → home_score_ft + away_score_ft <= 2
--
-- Numeric prefix 030_ continues the dependency-safe ordering: 010_ creates
-- v_understat_matches; 020_ creates v_fixtures_epl (which this view joins);
-- 030_ runs after both.
-- =========================================================================

CREATE OR REPLACE VIEW v_pinnacle_close_epl AS
WITH base AS (
    SELECT
        f.fixture_id,
        f.match_date,
        f.season,
        f.result_ft,
        f.home_score_ft,
        f.away_score_ft,
        r.psch,
        r.pscd,
        r.psca,
        r.pc_over_25,
        r.pc_under_25
    FROM v_fixtures_epl f
    JOIN raw_match_results r
        ON r.league = f.league
       AND r.season = f.season
       AND r.match_date = f.match_date
       AND r.home_team = f.home_team_raw
       AND r.away_team = f.away_team_raw
    WHERE f.home_team_id IS NOT NULL
      AND f.away_team_id IS NOT NULL
      AND f.status = 'final'
)
SELECT fixture_id, match_date, season,
       '1x2'  AS market,
       'home' AS selection,
       psch   AS pinnacle_close_decimal,
       (result_ft = 'H') AS is_winner
FROM base
WHERE psch IS NOT NULL AND pscd IS NOT NULL AND psca IS NOT NULL

UNION ALL
SELECT fixture_id, match_date, season,
       '1x2'  AS market,
       'draw' AS selection,
       pscd   AS pinnacle_close_decimal,
       (result_ft = 'D') AS is_winner
FROM base
WHERE psch IS NOT NULL AND pscd IS NOT NULL AND psca IS NOT NULL

UNION ALL
SELECT fixture_id, match_date, season,
       '1x2'  AS market,
       'away' AS selection,
       psca   AS pinnacle_close_decimal,
       (result_ft = 'A') AS is_winner
FROM base
WHERE psch IS NOT NULL AND pscd IS NOT NULL AND psca IS NOT NULL

UNION ALL
SELECT fixture_id, match_date, season,
       'ou_2.5' AS market,
       'over'   AS selection,
       pc_over_25 AS pinnacle_close_decimal,
       ((home_score_ft + away_score_ft) > 2) AS is_winner
FROM base
WHERE pc_over_25 IS NOT NULL AND pc_under_25 IS NOT NULL

UNION ALL
SELECT fixture_id, match_date, season,
       'ou_2.5' AS market,
       'under'  AS selection,
       pc_under_25 AS pinnacle_close_decimal,
       ((home_score_ft + away_score_ft) <= 2) AS is_winner
FROM base
WHERE pc_over_25 IS NOT NULL AND pc_under_25 IS NOT NULL;
