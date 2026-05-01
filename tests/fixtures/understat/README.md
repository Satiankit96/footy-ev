# Understat fixtures

Frozen captures of Understat's league/season AJAX JSON payload, used by the
parse-layer regression tests at `tests/unit/test_understat_parse.py`. They pin
the wire shape so a silent change to the upstream payload trips the test suite
instead of slipping through to the production loader.

## Files

| File | Capture date | Season | Purpose |
|---|---|---|---|
| `EPL_2023.json` | 2026-04-26 | 2023-2024 (completed) | Every match has `isResult=true`, populated `goals`/`xG`/`forecast`. Pins the happy path. |
| `EPL_2025.json` | 2026-04-26 | 2025-2026 (in-progress) | Mix of played + unplayed matches. Pins null-handling for `goals`/`xG` (nested dicts with `null` values for unplayed) AND the absence of the `forecast` key on unplayed matches. |

## Endpoint

```
GET https://understat.com/getLeagueData/EPL/<year>
Headers:
  User-Agent: footy-ev/<version> (+<repo>)
  X-Requested-With: XMLHttpRequest
```

`<year>` is the season-start year (`2023` for the 2023-24 season, `2025` for
the 2025-26 season).

The endpoint was discovered by reading
[understatapi v0.7.1](https://github.com/collinb9/understatAPI) source — see
the commit `Fix: use AJAX endpoints instead of HTML parsing` (2025-12-17).
Understat's older inline-JSON pattern (`var datesData = JSON.parse('...')`)
was deprecated sometime in 2025; this AJAX endpoint is public-by-convention
but undocumented. If it breaks, check understatapi's GitHub for the current
pattern before reverse-engineering.

## Refresh procedure

When fixtures need re-capturing — e.g., after Understat shifts shape and we
have to recalibrate the parser:

1. Honor the `>=2s` rate limit between fetches (CLAUDE.md hard rule).
2. Use the project User-Agent (`footy-ev/<version> (+<repo>)`) and the
   `X-Requested-With: XMLHttpRequest` header. Without that header,
   Understat returns a stripped HTML shell, not the JSON payload.
3. Save the response pretty-printed with
   `json.dumps(payload, sort_keys=True, indent=2)` to the same filename.
   Diff vs the prior file should be small except where live data has shifted
   (added matches, late updates, etc.). A large diff is signal — review it.
4. Run the parse-layer test suite:
   `uv run pytest tests/unit/test_understat_parse.py -v`. Any failure
   indicates either a parser bug or an upstream shape change. The
   `MIN_EXPECTED_MATCHES_PER_SEASON` floor in `parse.py` is the first tripwire
   for "regex matched the wrong thing" / "endpoint shape changed" failures.
