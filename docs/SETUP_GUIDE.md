# Setup Guide

Operator-facing setup steps that aren't fully automated by the code.

## Kalshi Exchange (PRIMARY VENUE — Phase 3 step 5a+)

The operator is US-based (NY). Kalshi is a CFTC-regulated prediction market
exchange and the only legal venue for EPL total-goals contracts in the US.
Betfair Exchange is not accessible from the US; see the deprecated Betfair
section below if you need it for reference.

**Current status:** Phase 3 step 5b complete. RSA-PSS/SHA256 auth is wired.
`KalshiClient.list_events()`, `list_markets()`, and `get_market()` are fully
implemented with Pydantic-validated response models and tenacity retry.
The paper-trader can now fetch real odds from Kalshi demo / production.

### 1. Create a Kalshi account

1. Go to [kalshi.com](https://kalshi.com/) and register. The account is free.
   No deposit is required for paper trading.
2. Complete identity verification (KYC) — required for all CFTC-regulated
   exchanges even without depositing.

### 2. Generate an API keypair

1. Sign in → **Settings** → **API Keys** → **Create API Key**.
2. Select RSA key type. Kalshi generates a keypair; download the private key
   PEM file immediately (it is not stored server-side).
3. Copy the **Key ID** (UUID format, e.g. `a1b2c3d4-...`).

### 3. Store credentials

```powershell
# Place the private key PEM in the gitignored/claudeignored path:
Copy-Item "~/Downloads/kalshi_private_key.pem" "data/kalshi_private_key.pem"
```

In `.env` (copy from `.env.example`):
```env
KALSHI_API_KEY_ID=<paste-your-key-id-uuid-here>
```

Confirm the key is not tracked by git:
```powershell
git check-ignore data/kalshi_private_key.pem
# should print: data/kalshi_private_key.pem
```

### 4. Demo environment (recommended first)

Kalshi provides a demo environment at `demo-api.kalshi.co` for testing
without real money. The `KalshiClient` accepts a `base_url` parameter:

```python
from footy_ev.venues.kalshi import KalshiClient, DEMO_BASE_URL
client = KalshiClient.from_env(base_url=DEMO_BASE_URL)
```

### 5. Live integration test

```powershell
$env:FOOTY_EV_KALSHI_DEMO = "1"
.\make.ps1 test-integration
# tests/integration/test_kalshi_live.py runs read-only list_events and
# list_markets calls. Skips cleanly if FOOTY_EV_KALSHI_DEMO or
# KALSHI_API_KEY_ID are unset.
```

### 5b. Shape discovery probe (completed — 2026-05-12)

The discovery probe (`scripts/probe_kalshi_demo.py`) was run against the
Kalshi demo API. Key findings locked into the implementation:

- **Event tickers:** `KXEPLTOTAL-26MAY24WHULEE` (series + date + TEAMTEAM)
- **Market tickers:** `KXEPLTOTAL-26MAY24WHULEE-2` (event + sequential int)
- **`floor_strike`:** float in JSON (e.g. `2.5`) — OU 2.5 filter uses exact Decimal comparison
- **Price fields:** 4-decimal strings, e.g. `"0.5500"` / `"0.0000"` (no-bid)
- **Size fields:** strings, e.g. `"50.00"` (coerced to float by Pydantic)
- **Events endpoint:** does NOT embed markets — markets must be fetched separately

Re-run the probe at any time to verify field shapes still match:

```powershell
$env:KALSHI_API_BASE_URL = "https://demo-api.kalshi.co/trade-api/v2"
$env:KALSHI_API_KEY_ID   = "<your-key-id-uuid>"
uv run python scripts/probe_kalshi_demo.py
```

### 6. Start the paper trader (Kalshi)

```powershell
python run.py paper-trade --once
python run.py paper-trade --fixtures-ahead-days 7
```

---

## Betfair Exchange — REMOVED

Betfair is not US-legal (operator is NY-based) and has been fully removed
from this codebase. Do not configure Betfair for any setup.

Retained for reference only. The operator is NY-based; Betfair is not
US-legal. Do not configure Betfair for new setups.

The paper-trading runtime in [`runtime/paper_trader.py`](../src/footy_ev/runtime/paper_trader.py)
needs three things from Betfair: an account (free), a Delayed Application
Key (free, instant), and your username/password. No deposit, no real-money
betting in this phase.

### 1. Open a Betfair Exchange account

1. Go to [betfair.com](https://www.betfair.com/) and register a real
   account. You will need to confirm an email and possibly do a basic
   identity check (passport / address). This is mandated for any
   regulated UK gambling site even if you never deposit.
2. **Do not deposit money.** Real-money betting is gated on PROJECT_INSTRUCTIONS §3
   bankroll discipline, which we are not at yet.

### 2. Request a Delayed Application Key

1. Sign in at [developer-docs.betfair.com](https://developer-docs.betfair.com/).
2. Open the **Application Keys** tool (left sidebar).
3. Click **Create Application Key**, give it a name (e.g. `footy-ev-paper`),
   and select **Delayed**. The Delayed key is free and rate-limited; data
   is approximately 60 seconds behind the live exchange. That latency is
   fine for paper trading and CLV measurement; it is not fine for
   in-running arbitrage (which we are not doing).
4. Copy the resulting key (32-char hex string).

### 3. Populate `.env`

```env
BETFAIR_APP_KEY=<your delayed key>
BETFAIR_USERNAME=<your betfair login email>
BETFAIR_PASSWORD=<your betfair password>
# BETFAIR_CERT_PATH is optional. The Delayed-key flow uses simple
# username/password login. Cert login only matters once you upgrade
# to a Live key, which is Phase 4+.
```

`.env` is gitignored. Confirm with `git check-ignore .env`. Never commit
this file or paste credentials into an LLM session.

### 4. Verify the credentials work

```powershell
$env:FOOTY_EV_BETFAIR_LIVE = "1"
.\make.ps1 test-integration
# tests/integration/test_betfair_live.py runs a single read-only listEvents
# call against the real Delayed API. Skips with a clear message if either
# the env var or any BETFAIR_* var is missing.
```

A passing live test confirms login + the three calls (`listEvents`,
`listMarketCatalogue`, `listMarketBook`) reach Betfair successfully.

### 5. Start the paper trader

```powershell
python run.py paper-trade --once
# Single-pass smoke test: pulls upcoming EPL fixtures, runs the LangGraph
# once per fixture, writes any approved bets to paper_bets.

python run.py paper-trade --fixtures-ahead-days 7
# Continuous mode: polls every 5 minutes, ctrl-C to stop. Safe to resume;
# state is checkpointed to data/langgraph_checkpoints.sqlite.

python run.py paper-status
# Prints latest invocation, recent paper bets, breaker status.
```

## What if I don't have a Betfair account yet?

The implementation works without one. All unit and graph integration
tests use mocked Betfair responses. Only `test_betfair_live.py` requires
the real account — and it skips cleanly when `FOOTY_EV_BETFAIR_LIVE` is
unset or any `BETFAIR_*` env var is empty. The paper-trade runtime will
fail at startup with a clear "missing BETFAIR_APP_KEY" message; once the
key is added it just works.
