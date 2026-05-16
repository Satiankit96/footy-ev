import React from "react";
import { render, screen, waitFor, fireEvent } from "@testing-library/react";
import { describe, it, expect, vi, beforeEach } from "vitest";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";

vi.mock("next/navigation", () => ({
  useSearchParams: () => new URLSearchParams(),
  useRouter: () => ({ push: vi.fn(), replace: vi.fn(), refresh: vi.fn() }),
  usePathname: () => "/live-trading",
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

import LiveTradingPage from "@/app/(dashboard)/live-trading/page";

function wrapper({ children }: { children: React.ReactNode }) {
  const qc = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
  return <QueryClientProvider client={qc}>{children}</QueryClientProvider>;
}

const MOCK_STATUS = {
  enabled: false,
  gate_reasons: [
    "BANKROLL_DISCIPLINE_CONFIRMED env var not set",
    "CLV condition requires 1000+ settled bets over 60+ days — run /check-conditions to evaluate",
  ],
};

const MOCK_CONDITIONS_NOT_MET = {
  clv_condition: {
    met: false,
    bet_count: 47,
    days_span: 12,
    mean_clv_pct: 0.008,
  },
  bankroll_condition: {
    met: false,
    flag_name: "BANKROLL_DISCIPLINE_CONFIRMED",
    flag_set: false,
  },
  all_met: false,
};

const MOCK_CONDITIONS_MET = {
  clv_condition: {
    met: true,
    bet_count: 1250,
    days_span: 90,
    mean_clv_pct: 0.032,
  },
  bankroll_condition: {
    met: true,
    flag_name: "BANKROLL_DISCIPLINE_CONFIRMED",
    flag_set: true,
  },
  all_met: true,
};

function mockFetch(statusOverride?: unknown, conditionsOverride?: unknown) {
  vi.spyOn(global, "fetch").mockImplementation(async (url, opts) => {
    const u = typeof url === "string" ? url : url.toString();
    const method = (opts?.method ?? "GET").toUpperCase();
    if (u.includes("/live-trading/status") && method === "GET") {
      return {
        ok: true,
        json: async () => statusOverride ?? MOCK_STATUS,
      } as Response;
    }
    if (u.includes("/live-trading/check-conditions") && method === "POST") {
      return {
        ok: true,
        json: async () => conditionsOverride ?? MOCK_CONDITIONS_NOT_MET,
      } as Response;
    }
    return { ok: true, json: async () => ({}) } as Response;
  });
}

describe("LiveTradingPage", () => {
  beforeEach(() => vi.restoreAllMocks());

  it("always shows the red disabled banner", () => {
    mockFetch();
    render(<LiveTradingPage />, { wrapper });
    expect(screen.getByText("LIVE TRADING IS DISABLED")).toBeDefined();
  });

  it("shows gate reasons from status endpoint", async () => {
    mockFetch();
    render(<LiveTradingPage />, { wrapper });
    await waitFor(() => {
      expect(
        screen.getByText(/BANKROLL_DISCIPLINE_CONFIRMED env var not set/),
      ).toBeDefined();
    });
  });

  it("has no enable button, toggle, or switch", () => {
    mockFetch();
    render(<LiveTradingPage />, { wrapper });
    const buttons = screen.getAllByRole("button");
    for (const btn of buttons) {
      const label = btn.textContent?.toLowerCase() ?? "";
      expect(label).not.toMatch(/enable|activate|go live|toggle/);
    }
  });

  it("shows check conditions button", () => {
    mockFetch();
    render(<LiveTradingPage />, { wrapper });
    expect(screen.getByRole("button", { name: /check conditions/i })).toBeDefined();
  });

  it("shows unmet conditions after clicking check", async () => {
    mockFetch();
    render(<LiveTradingPage />, { wrapper });
    fireEvent.click(screen.getByRole("button", { name: /check conditions/i }));
    await waitFor(() => {
      expect(screen.getByText(/47 settled bets/)).toBeDefined();
    });
  });

  it("shows met conditions correctly", async () => {
    mockFetch(MOCK_STATUS, MOCK_CONDITIONS_MET);
    render(<LiveTradingPage />, { wrapper });
    fireEvent.click(screen.getByRole("button", { name: /check conditions/i }));
    await waitFor(() => {
      expect(screen.getByText(/1250 settled bets/)).toBeDefined();
      expect(screen.getByText(/Both conditions met/)).toBeDefined();
    });
  });

  it("shows documentation panel with both condition descriptions", () => {
    mockFetch();
    render(<LiveTradingPage />, { wrapper });
    expect(
      screen.getByText(/Positive CLV on 1,000\+ bets over 60\+ days/),
    ).toBeDefined();
    expect(screen.getByText(/Confirmed disposable bankroll/)).toBeDefined();
  });

  it("shows the env note at the bottom", () => {
    mockFetch();
    render(<LiveTradingPage />, { wrapper });
    expect(screen.getByText(/This cannot be done through the UI/)).toBeDefined();
  });

  it("shows LIVE_TRADING in the env note", () => {
    mockFetch();
    render(<LiveTradingPage />, { wrapper });
    expect(screen.getByText(/LIVE_TRADING=true/)).toBeDefined();
  });
});
