-- odds_movement: time-series odds for a fixture+market (for chart rendering).
-- Params: $fixture_id (VARCHAR), $market (VARCHAR, '' for all)
SELECT
    CAST(received_at AS VARCHAR)  AS received_at,
    venue,
    market,
    selection,
    odds_decimal
FROM live_odds_snapshots
WHERE fixture_id = $fixture_id
  AND ($market = '' OR market = $market)
ORDER BY received_at ASC
LIMIT 500
