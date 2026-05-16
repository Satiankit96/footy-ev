import { test, expect, type Page } from "@playwright/test";

// ── Helpers ────────────────────────────────────────────────────────────────────

async function setSessionCookie(page: Page) {
  await page.context().addCookies([
    {
      name: "session",
      value: "e2e-test-token",
      domain: "localhost",
      path: "/",
    },
  ]);
}

async function mockCommonEndpoints(page: Page) {
  await page.route("**/api/v1/auth/me", (route) =>
    route.fulfill({ json: { operator: "e2e-operator" } }),
  );
  await page.route("**/api/v1/shell", (route) =>
    route.fulfill({
      json: {
        operator: "e2e-operator",
        venue: { name: "kalshi", is_active: true, is_demo: false },
        circuit_breaker: { state: "ok", last_tripped_at: null, reason: null },
        pipeline: { status: "idle", last_cycle_at: null, last_cycle_duration_s: null },
      },
    }),
  );
  await page.route("**/api/v1/settings", (route) =>
    route.fulfill({
      json: {
        settings: {
          theme: "system",
          density: "comfortable",
          default_page_size: 50,
          default_time_range_days: 30,
        },
      },
    }),
  );
}

// ── Flow 1: Login → Dashboard ─────────────────────────────────────────────────

test("login → dashboard: successful login redirects to dashboard", async ({ page }) => {
  await page.route("**/api/v1/auth/login", (route) =>
    route.fulfill({ status: 200, json: { ok: true } }),
  );
  await mockCommonEndpoints(page);
  await page.route("**/api/v1/pipeline/status", (route) =>
    route.fulfill({
      json: {
        last_cycle_at: null,
        last_cycle_duration_s: null,
        circuit_breaker: { state: "ok", last_tripped_at: null, reason: null },
        loop: { running: false, interval_min: 15 },
        freshness: {},
      },
    }),
  );

  await page.goto("/login");
  await expect(page.getByPlaceholder("Operator token")).toBeVisible();

  await page.getByPlaceholder("Operator token").fill("test-token");
  await page.getByRole("button", { name: /sign in/i }).click();

  // After successful login, the page navigates to "/" (dashboard)
  await expect(page).toHaveURL("/");
});

// ── Flow 2: Pipeline cycle ─────────────────────────────────────────────────────

test("pipeline: start cycle button triggers API call", async ({ page }) => {
  await setSessionCookie(page);
  await mockCommonEndpoints(page);

  await page.route("**/api/v1/pipeline/status", (route) =>
    route.fulfill({
      json: {
        last_cycle_at: null,
        last_cycle_duration_s: null,
        circuit_breaker: { state: "ok", last_tripped_at: null, reason: null },
        loop: { running: false, interval_min: 15 },
        freshness: {},
      },
    }),
  );
  await page.route("**/api/v1/pipeline/jobs*", (route) =>
    route.fulfill({ json: { jobs: [], total: 0 } }),
  );

  let cycleRequested = false;
  await page.route("**/api/v1/pipeline/cycle", (route) => {
    cycleRequested = true;
    return route.fulfill({
      json: { job_id: "job-001", status: "queued", started_at: new Date().toISOString() },
    });
  });

  await page.goto("/pipeline");
  await expect(page.getByRole("button", { name: /start cycle/i })).toBeVisible();
  await page.getByRole("button", { name: /start cycle/i }).click();

  await expect.poll(() => cycleRequested).toBe(true);
});

// ── Flow 3: Aliases list ───────────────────────────────────────────────────────

test("aliases: page loads and shows alias table", async ({ page }) => {
  await setSessionCookie(page);
  await mockCommonEndpoints(page);

  await page.route("**/api/v1/aliases*", (route) =>
    route.fulfill({
      json: {
        aliases: [
          {
            id: "alias-1",
            canonical_name: "Arsenal",
            venue: "kalshi",
            raw_name: "Arsenal FC",
            confidence: 1.0,
            created_at: "2024-01-01T00:00:00Z",
            retired_at: null,
          },
        ],
        total: 1,
      },
    }),
  );
  await page.route("**/api/v1/aliases/conflicts", (route) =>
    route.fulfill({ json: { conflicts: [] } }),
  );

  await page.goto("/aliases");
  await expect(page.getByText("Arsenal")).toBeVisible();
});

// ── Flow 4: Bet detail ────────────────────────────────────────────────────────

test("bets: navigate from list to bet detail page", async ({ page }) => {
  await setSessionCookie(page);
  await mockCommonEndpoints(page);

  const BET_ID = "bet-abc-123";

  await page.route("**/api/v1/bets*", (route) => {
    const url = route.request().url();
    if (url.includes(BET_ID)) {
      return route.fulfill({
        json: {
          bet: {
            id: BET_ID,
            fixture_id: "fix-1",
            venue: "kalshi",
            market_ticker: "SOCCER-EPL-ARS",
            side: "yes",
            stake: "10.00",
            odds: 1.9,
            placed_at: "2024-01-10T12:00:00Z",
            settlement_status: "won",
            clv_pct: 3.5,
            pnl: "9.00",
          },
          kelly_breakdown: null,
          edge_math: null,
        },
      });
    }
    return route.fulfill({
      json: {
        bets: [
          {
            id: BET_ID,
            fixture_id: "fix-1",
            venue: "kalshi",
            market_ticker: "SOCCER-EPL-ARS",
            side: "yes",
            stake: "10.00",
            odds: 1.9,
            placed_at: "2024-01-10T12:00:00Z",
            settlement_status: "won",
            clv_pct: 0.035,
            pnl: "9.00",
          },
        ],
        total: 1,
      },
    });
  });

  await page.goto("/bets");
  // Find and click the bet row link
  const betLink = page.getByRole("link", { name: new RegExp(BET_ID.slice(0, 8), "i") });
  await expect(betLink).toBeVisible();
  await betLink.click();

  await expect(page).toHaveURL(new RegExp(`/bets/${BET_ID}`));
  await expect(page.getByText("SOCCER-EPL-ARS")).toBeVisible();
});

// ── Flow 5: Live trading check conditions ─────────────────────────────────────

test("live-trading: check conditions populates condition cards", async ({ page }) => {
  await setSessionCookie(page);
  await mockCommonEndpoints(page);

  await page.route("**/api/v1/live-trading/status", (route) =>
    route.fulfill({
      json: {
        enabled: false,
        gate_reasons: ["CLV condition not met", "Bankroll discipline not confirmed"],
      },
    }),
  );

  await page.route("**/api/v1/live-trading/check-conditions", (route) =>
    route.fulfill({
      json: {
        clv_condition: {
          met: false,
          bet_count: 42,
          days_span: 14,
          mean_clv_pct: 1.2,
        },
        bankroll_condition: {
          met: false,
          flag_name: "BANKROLL_DISCIPLINE_CONFIRMED",
          flag_set: false,
        },
        all_met: false,
      },
    }),
  );

  await page.goto("/live-trading");
  await expect(page.getByText(/LIVE TRADING IS DISABLED/i)).toBeVisible();

  await page.getByRole("button", { name: /check conditions/i }).click();

  // Condition cards should appear after the check
  await expect(page.getByText(/CLV Condition/i)).toBeVisible();
  await expect(page.getByText(/Bankroll/i)).toBeVisible();
});
