-- team_form_last_n: last N completed fixtures for a team.
-- Params: $team_id (VARCHAR), $n (INTEGER, default 5)
SELECT
    fixture_id,
    CAST(match_date AS VARCHAR)                                              AS date,
    CASE WHEN home_team_id = $team_id THEN away_team_id
         ELSE home_team_id END                                               AS opponent_id,
    CASE WHEN home_team_id = $team_id THEN 'home' ELSE 'away' END           AS home_away,
    CASE WHEN home_score_ft IS NOT NULL AND away_score_ft IS NOT NULL
         THEN CAST(home_score_ft AS VARCHAR) || ' - ' || CAST(away_score_ft AS VARCHAR)
         ELSE NULL END                                                       AS score,
    CASE WHEN home_team_id = $team_id AND result_ft = 'H' THEN 'W'
         WHEN away_team_id = $team_id AND result_ft = 'A' THEN 'W'
         WHEN result_ft = 'D'                              THEN 'D'
         WHEN result_ft IS NOT NULL                        THEN 'L'
         ELSE NULL END                                                       AS result,
    CAST(home_xg AS VARCHAR)                                                 AS home_xg,
    CAST(away_xg AS VARCHAR)                                                 AS away_xg
FROM v_fixtures_epl
WHERE (home_team_id = $team_id OR away_team_id = $team_id)
  AND status = 'final'
ORDER BY match_date DESC
LIMIT $n
