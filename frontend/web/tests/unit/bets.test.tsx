import React from "react";
import { render, screen, waitFor } from "@testing-library/react";
import { describe, it, expect, vi, beforeEach } from "vitest";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";

vi.mock("next/navigation", () => ({
  useSearchParams: () => new URLSearchParams(),
  useRouter: () => ({ push: vi.fn(), replace: vi.fn(), refresh: vi.fn() }),
  usePathname: () => "/bets",
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

import BetsPage from "@/app/(dashboard)/bets/page";

function wrapper({ children }: { children: React.ReactNode }) {
  const qc = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
  return <QueryClientProvider client={qc}>{children}</QueryClientProvider>;
}

const MOCK_BET = {
  decision_id: "bet001",
  fixture_id: "EPL|2025-2026|arsenal|chelsea|2026-05-20",
  market: "ou_2.5",
  selection: "over",
  odds_at_decision: 2.1,
  stake_gbp: "12.50",
  edge_pct: 0.055,
  kelly_fraction_used: 0.0125,
  settlement_status: "pending",
  clv_pct: 0.035,
  decided_at: "2026-05-20T09:00:00",
  venue: "kalshi",
};

function mockBetsFetch(overrides: Record<string, unknown> = {}) {
  vi.spyOn(global, "fetch").mockImplementation(async (url) => {
    const urlStr = typeof url === "string" ? url : url.toString();
    if (urlStr.includes("/api/v1/auth/me")) {
      return { ok: true, json: async () => ({ username: "operator" }) } as Response;
    }
    if (urlStr.includes("/api/v1/bets")) {
      return {
        ok: true,
        json: async () =>
          overrides.bets ?? { bets: [MOCK_BET], total: 1 },
      } as Response;
    }
    return { ok: false, json: async () => ({}) } as Response;
  });
}

describe("BetsPage", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("renders page header", async () => {
    mockBetsFetch();
    render(<BetsPage />, { wrapper });
    expect(screen.getByText("Paper Bets")).toBeDefined();
  });

  it("shows bet row after load", async () => {
    mockBetsFetch();
    render(<BetsPage />, { wrapper });
    await waitFor(() => {
      expect(screen.getByText("ou_2.5")).toBeDefined();
    });
  });

  it("shows no bets message when empty", async () => {
    mockBetsFetch({ bets: { bets: [], total: 0 } });
    render(<BetsPage />, { wrapper });
    await waitFor(() => {
      expect(screen.getByText("No bets found.")).toBeDefined();
    });
  });

  it("shows total count from API", async () => {
    mockBetsFetch({ bets: { bets: [MOCK_BET], total: 7 } });
    render(<BetsPage />, { wrapper });
    await waitFor(() => {
      expect(screen.getByText("7 total bets")).toBeDefined();
    });
  });

  it("shows positive CLV with green class", async () => {
    mockBetsFetch();
    render(<BetsPage />, { wrapper });
    await waitFor(() => {
      expect(screen.getByText("ou_2.5")).toBeDefined();
    });
    // CLV 0.035 → "3.50%" rendered in green td
    const clvCell = screen.getByText("3.50%");
    expect(clvCell).toBeDefined();
    expect(clvCell.className).toContain("green");
  });
});
