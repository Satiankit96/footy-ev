import React from "react";
import { render, screen, waitFor } from "@testing-library/react";
import { describe, it, expect, vi, beforeEach } from "vitest";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";

vi.mock("next/navigation", () => ({
  useSearchParams: () => new URLSearchParams(),
  useRouter: () => ({ push: vi.fn(), replace: vi.fn(), refresh: vi.fn() }),
  usePathname: () => "/fixtures",
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

import FixturesPage from "@/app/(dashboard)/fixtures/page";

function wrapper({ children }: { children: React.ReactNode }) {
  const qc = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
  return <QueryClientProvider client={qc}>{children}</QueryClientProvider>;
}

const MOCK_FIXTURE = {
  fixture_id: "EPL|2025-2026|arsenal|manchester_city|2026-05-14",
  league: "EPL",
  season: "2025-2026",
  home_team_id: "arsenal",
  away_team_id: "manchester_city",
  home_team_raw: "Arsenal",
  away_team_raw: "Man City",
  match_date: "2026-05-14",
  kickoff_utc: "2026-05-14T15:00:00",
  home_score_ft: null,
  away_score_ft: null,
  result_ft: null,
  home_xg: null,
  away_xg: null,
  status: "scheduled",
  alias_count: 1,
};

function mockFixturesFetch(overrides: Record<string, unknown> = {}) {
  vi.spyOn(global, "fetch").mockImplementation(async (url) => {
    const urlStr = typeof url === "string" ? url : url.toString();
    if (urlStr.includes("/api/v1/auth/me")) {
      return {
        ok: true,
        json: async () => ({ username: "operator" }),
      } as Response;
    }
    if (urlStr.includes("/api/v1/fixtures")) {
      return {
        ok: true,
        json: async () =>
          overrides.fixtures ?? {
            fixtures: [MOCK_FIXTURE],
            total: 1,
          },
      } as Response;
    }
    return { ok: false, json: async () => ({}) } as Response;
  });
}

describe("FixturesPage", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("renders the page header", async () => {
    mockFixturesFetch();
    render(<FixturesPage />, { wrapper });
    expect(screen.getByText("Fixtures")).toBeDefined();
  });

  it("shows fixture row after load", async () => {
    mockFixturesFetch();
    render(<FixturesPage />, { wrapper });
    await waitFor(() => {
      expect(screen.getByText("arsenal")).toBeDefined();
    });
  });

  it("shows no fixtures message when empty", async () => {
    mockFixturesFetch({ fixtures: { fixtures: [], total: 0 } });
    render(<FixturesPage />, { wrapper });
    await waitFor(() => {
      expect(screen.getByText("No fixtures found.")).toBeDefined();
    });
  });

  it("shows total count from API", async () => {
    mockFixturesFetch({
      fixtures: { fixtures: [MOCK_FIXTURE], total: 42 },
    });
    render(<FixturesPage />, { wrapper });
    await waitFor(() => {
      expect(screen.getByText("42 total fixtures")).toBeDefined();
    });
  });

  it("shows scheduled status in row", async () => {
    mockFixturesFetch();
    render(<FixturesPage />, { wrapper });
    await waitFor(() => {
      // fixture row renders; verify status-bearing text is present
      const cells = screen.getAllByText(/scheduled/i);
      expect(cells.length).toBeGreaterThan(0);
    });
  });
});
