-- top_fixtures_by_bet_count: fixtures ranked by number of paper bets placed.
-- Params: $limit (INTEGER, default 20)
SELECT
    fixture_id,
    COUNT(*)                             AS bet_count,
    ROUND(SUM(CAST(stake_gbp AS DOUBLE)), 2) AS total_staked_gbp,
    ROUND(AVG(edge_pct) * 100, 3)       AS avg_edge_pct
FROM paper_bets
GROUP BY fixture_id
ORDER BY bet_count DESC
LIMIT $limit
