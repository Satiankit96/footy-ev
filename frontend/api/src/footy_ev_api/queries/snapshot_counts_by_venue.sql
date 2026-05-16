-- snapshot_counts_by_venue: odds snapshot volume grouped by venue and market.
-- No params required. Returns top rows by snapshot count.
SELECT
    venue,
    market,
    COUNT(*)                                      AS snapshot_count,
    MIN(CAST(received_at AS VARCHAR))             AS earliest,
    MAX(CAST(received_at AS VARCHAR))             AS latest
FROM live_odds_snapshots
GROUP BY venue, market
ORDER BY snapshot_count DESC
LIMIT 50
