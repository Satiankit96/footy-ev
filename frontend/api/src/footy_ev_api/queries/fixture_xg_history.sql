-- fixture_xg_history: full result and xG data for a specific fixture.
-- Params: $fixture_id (VARCHAR)
SELECT
    fixture_id,
    CAST(match_date AS VARCHAR)      AS date,
    home_team_id,
    away_team_id,
    home_score_ft,
    away_score_ft,
    result_ft,
    CAST(home_xg AS VARCHAR)         AS home_xg,
    CAST(away_xg AS VARCHAR)         AS away_xg,
    status
FROM v_fixtures_epl
WHERE fixture_id = $fixture_id
