import React from "react";
import { render, screen, waitFor } from "@testing-library/react";
import { describe, it, expect, vi, beforeEach } from "vitest";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";

vi.mock("next/navigation", () => ({
  useSearchParams: () => new URLSearchParams(),
  useRouter: () => ({ push: vi.fn(), replace: vi.fn(), refresh: vi.fn() }),
  usePathname: () => "/risk",
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

// Suppress recharts console errors in test env
vi.mock("recharts", async () => {
  const actual = await vi.importActual<typeof import("recharts")>("recharts");
  return {
    ...actual,
    ResponsiveContainer: ({ children }: { children: React.ReactNode }) => (
      <div style={{ width: 400, height: 200 }}>{children}</div>
    ),
  };
});

import RiskPage from "@/app/(dashboard)/risk/page";

function wrapper({ children }: { children: React.ReactNode }) {
  const qc = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
  return <QueryClientProvider client={qc}>{children}</QueryClientProvider>;
}

const MOCK_BANKROLL = {
  current: "985.50",
  peak: "1000.00",
  drawdown_pct: 0.015,
  sparkline: [],
};

const MOCK_EXPOSURE = {
  today_open: "25.00",
  total_open: "125.00",
  per_fixture: [],
};

function mockRiskFetch(overrides: Record<string, unknown> = {}) {
  vi.spyOn(global, "fetch").mockImplementation(async (url) => {
    const u = typeof url === "string" ? url : url.toString();
    if (u.includes("/api/v1/risk/bankroll")) {
      return {
        ok: true,
        json: async () => overrides.bankroll ?? MOCK_BANKROLL,
      } as Response;
    }
    if (u.includes("/api/v1/risk/exposure")) {
      return {
        ok: true,
        json: async () => overrides.exposure ?? MOCK_EXPOSURE,
      } as Response;
    }
    if (u.includes("/api/v1/risk/kelly-preview")) {
      return {
        ok: true,
        json: async () => ({
          stake: "8.75",
          f_full: 0.0875,
          f_used: 0.00875,
          p_lb: 0.53,
          clv_multiplier: 0.5,
          per_bet_cap_hit: false,
        }),
      } as Response;
    }
    if (u.includes("/api/v1/bets")) {
      return {
        ok: true,
        json: async () => ({ bets: [], total: 0 }),
      } as Response;
    }
    return { ok: false, json: async () => ({}) } as Response;
  });
}

describe("RiskPage", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("renders page header", async () => {
    mockRiskFetch();
    render(<RiskPage />, { wrapper });
    expect(screen.getByText("Risk")).toBeDefined();
  });

  it("shows current bankroll after load", async () => {
    mockRiskFetch();
    render(<RiskPage />, { wrapper });
    await waitFor(() => {
      expect(screen.getByText("£985.50")).toBeDefined();
    });
  });

  it("shows today open exposure after load", async () => {
    mockRiskFetch();
    render(<RiskPage />, { wrapper });
    await waitFor(() => {
      expect(screen.getByText("£25.00")).toBeDefined();
    });
  });

  it("shows kelly preview section", async () => {
    mockRiskFetch();
    render(<RiskPage />, { wrapper });
    expect(screen.getByText("Kelly Preview")).toBeDefined();
  });

  it("shows drawdown in red when over 10%", async () => {
    mockRiskFetch({
      bankroll: {
        current: "800.00",
        peak: "1000.00",
        drawdown_pct: 0.2,
        sparkline: [],
      },
    });
    render(<RiskPage />, { wrapper });
    await waitFor(() => {
      const el = screen.getByText("20.00%");
      expect(el).toBeDefined();
      expect(el.className).toContain("red");
    });
  });
});
