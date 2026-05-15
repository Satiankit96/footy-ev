import { render, screen, fireEvent, waitFor, cleanup } from "@testing-library/react";
import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";

vi.mock("next/navigation", () => ({
  usePathname: () => "/kalshi",
  useRouter: () => ({ push: vi.fn(), refresh: vi.fn() }),
}));

vi.mock("next/link", () => ({
  default: ({
    children,
    href,
  }: {
    children: React.ReactNode;
    href: string;
  }) => <a href={href}>{children}</a>,
}));

vi.mock("sonner", () => ({
  toast: { success: vi.fn(), error: vi.fn() },
  Toaster: () => null,
}));

import KalshiPage from "@/app/(dashboard)/kalshi/page";

function wrapper({ children }: { children: React.ReactNode }) {
  const qc = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
  return <QueryClientProvider client={qc}>{children}</QueryClientProvider>;
}

function mockFetch(overrides: Record<string, unknown> = {}) {
  vi.spyOn(global, "fetch").mockImplementation(async (url) => {
    const urlStr = typeof url === "string" ? url : url.toString();
    if (urlStr.includes("/kalshi/credentials/status")) {
      return {
        ok: true,
        json: async () =>
          overrides.credentials ?? {
            configured: true,
            key_id_present: true,
            private_key_present: true,
            base_url: "https://demo-api.kalshi.co/trade-api/v2",
            is_demo: true,
          },
      } as Response;
    }
    if (urlStr.includes("/kalshi/health")) {
      return {
        ok: true,
        json: async () =>
          overrides.health ?? {
            ok: true,
            latency_ms: 42.5,
            clock_skew_s: 0.3,
            base_url: "https://demo-api.kalshi.co/trade-api/v2",
            error: null,
          },
      } as Response;
    }
    if (urlStr.includes("/kalshi/events")) {
      return {
        ok: true,
        json: async () =>
          overrides.events ?? {
            events: [
              {
                event_ticker: "KXEPLTOTAL-TEST",
                series_ticker: "KXEPLTOTAL",
                title: "Test Match",
                sub_title: null,
                category: "football",
                alias_status: "resolved",
                fixture_id: "FIX-001",
              },
            ],
            total: 1,
          },
      } as Response;
    }
    return { ok: true, json: async () => ({}) } as Response;
  });
}

describe("Kalshi page", () => {
  beforeEach(() => {
    vi.restoreAllMocks();
  });

  afterEach(() => {
    cleanup();
  });

  it("renders green credentials banner when configured", async () => {
    mockFetch();
    render(<KalshiPage />, { wrapper });
    await waitFor(() => {
      expect(screen.getByText(/Kalshi Connected/)).toBeDefined();
      expect(screen.getByText(/DEMO/)).toBeDefined();
    });
  });

  it("renders red credentials banner when not configured", async () => {
    mockFetch({
      credentials: {
        configured: false,
        key_id_present: false,
        private_key_present: true,
        base_url: "",
        is_demo: false,
      },
    });
    render(<KalshiPage />, { wrapper });
    await waitFor(() => {
      expect(screen.getByText(/Kalshi Not Configured/)).toBeDefined();
      expect(screen.getByText(/KALSHI_API_KEY_ID/)).toBeDefined();
    });
  });

  it("health check button shows latency result", async () => {
    mockFetch();
    render(<KalshiPage />, { wrapper });
    await waitFor(() => {
      expect(screen.getByText("Check Connection")).toBeDefined();
    });
    fireEvent.click(screen.getByText("Check Connection"));
    await waitFor(() => {
      expect(screen.getByText("42.5")).toBeDefined();
    });
  });

  it("events table renders with alias badges", async () => {
    mockFetch();
    render(<KalshiPage />, { wrapper });

    await waitFor(() => {
      expect(screen.getByText("Refresh")).toBeDefined();
    });
    fireEvent.click(screen.getByText("Refresh"));

    await waitFor(() => {
      expect(screen.getByText("KXEPLTOTAL-TEST")).toBeDefined();
      expect(screen.getByText("Test Match")).toBeDefined();
      expect(screen.getByText("Resolved")).toBeDefined();
    });
  });

  it("market detail page renders bid/ask prices", async () => {
    vi.spyOn(global, "fetch").mockImplementation(async (url) => {
      const urlStr = typeof url === "string" ? url : url.toString();
      if (urlStr.includes("/kalshi/markets/")) {
        return {
          ok: true,
          json: async () => ({
            market: {
              ticker: "KXEPLTOTAL-TEST-2",
              event_ticker: "KXEPLTOTAL-TEST",
              floor_strike: "2.5",
              yes_bid: "0.5500",
              no_bid: "0.4500",
              yes_ask: "0.5700",
              no_ask: "0.4300",
              yes_bid_size: 10.0,
              yes_ask_size: 5.0,
              decimal_odds: "1.8182",
              implied_probability: "55.00",
            },
            recent_snapshots: [],
          }),
        } as Response;
      }
      return { ok: true, json: async () => ({}) } as Response;
    });

    const React = await import("react");
    const { default: MarketDetailPage } = await import(
      "@/app/(dashboard)/kalshi/markets/[ticker]/page"
    );
    const { act } = await import("@testing-library/react");

    await act(async () => {
      render(
        <React.Suspense fallback={<div>Loading</div>}>
          <MarketDetailPage
            params={Promise.resolve({ ticker: "KXEPLTOTAL-TEST-2" })}
          />
        </React.Suspense>,
        { wrapper },
      );
    });

    await waitFor(() => {
      expect(screen.getByText("0.5500")).toBeDefined();
      expect(screen.getByText("0.4500")).toBeDefined();
      expect(screen.getByText("1.8182")).toBeDefined();
      expect(screen.getByText("55.00%")).toBeDefined();
    });
  });
});
