import React from "react";
import { render, screen, waitFor } from "@testing-library/react";
import { describe, it, expect, vi, beforeEach } from "vitest";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";

vi.mock("next/navigation", () => ({
  useSearchParams: () => new URLSearchParams(),
  useRouter: () => ({ push: vi.fn(), replace: vi.fn(), refresh: vi.fn() }),
  usePathname: () => "/warehouse",
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

vi.mock("recharts", async () => {
  const actual = await vi.importActual<typeof import("recharts")>("recharts");
  return {
    ...actual,
    ResponsiveContainer: ({ children }: { children: React.ReactNode }) => (
      <div style={{ width: 400, height: 300 }}>{children}</div>
    ),
  };
});

import WarehousePage from "@/app/(dashboard)/warehouse/page";
import TeamsPage from "@/app/(dashboard)/warehouse/teams/page";
import PlayersPage from "@/app/(dashboard)/warehouse/players/page";

function wrapper({ children }: { children: React.ReactNode }) {
  const qc = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
  return <QueryClientProvider client={qc}>{children}</QueryClientProvider>;
}

const MOCK_TABLES = {
  tables: [
    { name: "paper_bets", row_count: 42, last_write: "2026-05-15T10:00:00" },
    { name: "raw_match_results", row_count: 380, last_write: null },
  ],
};

const MOCK_TEAMS = {
  teams: [
    { team_id: "arsenal", name: "Arsenal", league: "EPL", fixture_count: 38 },
    { team_id: "chelsea", name: null, league: "EPL", fixture_count: 38 },
  ],
  total: 2,
};

const MOCK_QUERY_NAMES = [
  "fixture_xg_history",
  "odds_movement",
  "snapshot_counts_by_venue",
  "team_form_last_n",
  "top_fixtures_by_bet_count",
];

function mockWarehouseFetch(overrides: Record<string, unknown> = {}) {
  vi.spyOn(global, "fetch").mockImplementation(async (url) => {
    const u = typeof url === "string" ? url : url.toString();
    if (u.includes("/api/v1/warehouse/tables")) {
      return {
        ok: true,
        json: async () => overrides.tables ?? MOCK_TABLES,
      } as Response;
    }
    if (/\/warehouse\/teams(\?|$)/.test(u)) {
      return {
        ok: true,
        json: async () => overrides.teams ?? MOCK_TEAMS,
      } as Response;
    }
    if (u.includes("/api/v1/warehouse/players")) {
      return {
        ok: true,
        json: async () => ({
          players: [],
          note: "No players table in current schema.",
        }),
      } as Response;
    }
    if (u.includes("/api/v1/warehouse/query/names")) {
      return {
        ok: true,
        json: async () => MOCK_QUERY_NAMES,
      } as Response;
    }
    return { ok: false, json: async () => ({}) } as Response;
  });
}

describe("WarehousePage", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("renders page header", () => {
    mockWarehouseFetch();
    render(<WarehousePage />, { wrapper });
    expect(screen.getByText("Warehouse")).toBeDefined();
  });

  it("shows tables after load", async () => {
    mockWarehouseFetch();
    render(<WarehousePage />, { wrapper });
    await waitFor(() => {
      expect(screen.getByText("paper_bets")).toBeDefined();
    });
  });

  it("shows row counts in tables overview", async () => {
    mockWarehouseFetch();
    render(<WarehousePage />, { wrapper });
    await waitFor(() => {
      expect(screen.getByText("42")).toBeDefined();
    });
  });

  it("shows Query Runner section", () => {
    mockWarehouseFetch();
    render(<WarehousePage />, { wrapper });
    expect(screen.getByText("Query Runner")).toBeDefined();
  });

  it("shows query names in dropdown after load", async () => {
    mockWarehouseFetch();
    render(<WarehousePage />, { wrapper });
    await waitFor(() => {
      expect(screen.getByText("top_fixtures_by_bet_count")).toBeDefined();
    });
  });
});

describe("TeamsPage", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("renders teams page header", () => {
    mockWarehouseFetch();
    render(<TeamsPage />, { wrapper });
    expect(screen.getByRole("heading", { name: "Teams" })).toBeDefined();
  });

  it("shows team rows after load", async () => {
    mockWarehouseFetch();
    render(<TeamsPage />, { wrapper });
    await waitFor(() => {
      expect(screen.getByText("Arsenal")).toBeDefined();
    });
  });

  it("shows fixture counts", async () => {
    mockWarehouseFetch();
    render(<TeamsPage />, { wrapper });
    await waitFor(() => {
      // Both arsenal and chelsea have fixture_count=38
      const cells = screen.getAllByText("38");
      expect(cells.length).toBeGreaterThanOrEqual(1);
    });
  });
});

describe("PlayersPage", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("renders players page header", () => {
    mockWarehouseFetch();
    render(<PlayersPage />, { wrapper });
    expect(screen.getByRole("heading", { name: "Players" })).toBeDefined();
  });

  it("shows empty state note after load", async () => {
    mockWarehouseFetch();
    render(<PlayersPage />, { wrapper });
    await waitFor(() => {
      expect(screen.getByText(/No players table/i)).toBeDefined();
    });
  });
});
