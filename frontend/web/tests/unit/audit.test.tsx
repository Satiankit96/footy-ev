import React from "react";
import { render, screen, waitFor } from "@testing-library/react";
import { describe, it, expect, vi, beforeEach } from "vitest";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";

vi.mock("next/navigation", () => ({
  useSearchParams: () => new URLSearchParams(),
  useRouter: () => ({ push: vi.fn(), replace: vi.fn(), refresh: vi.fn() }),
  usePathname: () => "/audit",
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

import AuditPage from "@/app/(dashboard)/audit/page";

function wrapper({ children }: { children: React.ReactNode }) {
  const qc = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
  return <QueryClientProvider client={qc}>{children}</QueryClientProvider>;
}

const MOCK_ACTIONS = {
  actions: [
    {
      action_id: "aa-bb-cc",
      action_type: "pipeline_cycle",
      operator: "operator",
      performed_at: "2026-05-15T10:00:00",
      input_params: null,
      result_summary: "pipeline_cycle succeeded (HTTP 200)",
      request_id: "req-123",
    },
  ],
  total: 1,
};

const MOCK_VERSIONS = {
  versions: [
    {
      model_version: "xgb-v3.2.1",
      first_seen: "2026-04-01T09:00:00",
      last_seen: "2026-05-15T09:00:00",
      prediction_count: 42,
    },
  ],
};

const MOCK_DECISIONS = {
  decisions: [
    {
      bet_id: "bet-001",
      fixture_id: "EPL|2025-2026|arsenal|chelsea|2026-05-20",
      decided_at: "2026-05-15T10:30:00",
      market: "match_result",
      selection: "Home",
      stake_gbp: "15.00",
      odds: "2.10",
      edge_pct: 0.052,
      settlement_status: "pending",
      prediction_id: "pred-abc",
    },
  ],
  total: 1,
};

function mockAuditFetch(overrides: Record<string, unknown> = {}) {
  vi.spyOn(global, "fetch").mockImplementation(async (url) => {
    const u = typeof url === "string" ? url : url.toString();
    if (u.includes("/audit/operator-actions")) {
      return {
        ok: true,
        json: async () => overrides.actions ?? MOCK_ACTIONS,
      } as Response;
    }
    if (u.includes("/audit/model-versions")) {
      return {
        ok: true,
        json: async () => overrides.versions ?? MOCK_VERSIONS,
      } as Response;
    }
    if (u.includes("/audit/decisions")) {
      return {
        ok: true,
        json: async () => overrides.decisions ?? MOCK_DECISIONS,
      } as Response;
    }
    return { ok: true, json: async () => ({}) } as Response;
  });
}

describe("AuditPage", () => {
  beforeEach(() => vi.restoreAllMocks());

  it("renders page heading", () => {
    mockAuditFetch();
    render(<AuditPage />, { wrapper });
    expect(screen.getByRole("heading", { name: "Audit Trail" })).toBeDefined();
  });

  it("shows operator actions with action type badge", async () => {
    mockAuditFetch();
    render(<AuditPage />, { wrapper });
    await waitFor(() => {
      // "pipeline_cycle" appears in both the select options and the badge
      const matches = screen.getAllByText("pipeline_cycle");
      expect(matches.length).toBeGreaterThanOrEqual(1);
      expect(screen.getByText(/pipeline_cycle succeeded/)).toBeDefined();
    });
  });

  it("shows total count next to operator actions title", async () => {
    mockAuditFetch();
    render(<AuditPage />, { wrapper });
    await waitFor(() => {
      const totals = screen.getAllByText("(1 total)");
      expect(totals.length).toBeGreaterThanOrEqual(1);
    });
  });

  it("shows model version row", async () => {
    mockAuditFetch();
    render(<AuditPage />, { wrapper });
    await waitFor(() => {
      expect(screen.getByText("xgb-v3.2.1")).toBeDefined();
      expect(screen.getByText("42")).toBeDefined();
    });
  });

  it("shows bet decision row", async () => {
    mockAuditFetch();
    render(<AuditPage />, { wrapper });
    await waitFor(() => {
      expect(screen.getByText("Home")).toBeDefined();
      expect(screen.getByText("£15.00")).toBeDefined();
      expect(screen.getByText("5.2%")).toBeDefined();
    });
  });

  it("shows empty state when no operator actions", async () => {
    mockAuditFetch({ actions: { actions: [], total: 0 } });
    render(<AuditPage />, { wrapper });
    await waitFor(() => {
      expect(screen.getByText("No operator actions recorded yet.")).toBeDefined();
    });
  });

  it("shows empty state for decisions when none exist", async () => {
    mockAuditFetch({ decisions: { decisions: [], total: 0 } });
    render(<AuditPage />, { wrapper });
    await waitFor(() => {
      expect(screen.getByText("No bet decisions recorded yet.")).toBeDefined();
    });
  });
});
