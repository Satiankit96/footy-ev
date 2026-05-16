import React from "react";
import { render, screen, waitFor } from "@testing-library/react";
import { describe, it, expect, vi, beforeEach } from "vitest";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";

vi.mock("next/navigation", () => ({
  useSearchParams: () => new URLSearchParams(),
  useRouter: () => ({ push: vi.fn(), replace: vi.fn(), refresh: vi.fn() }),
  usePathname: () => "/diagnostics",
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

import DiagnosticsPage from "@/app/(dashboard)/diagnostics/page";
import DiagnosticsLogsPage from "@/app/(dashboard)/diagnostics/logs/page";

function wrapper({ children }: { children: React.ReactNode }) {
  const qc = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
  return <QueryClientProvider client={qc}>{children}</QueryClientProvider>;
}

const MOCK_CB_OK = { state: "ok", last_tripped_at: null, reason: null };
const MOCK_CB_TRIPPED = {
  state: "tripped",
  last_tripped_at: "2026-05-15T10:00:00",
  reason: "pipeline timeout",
};

const MOCK_MIGRATIONS = {
  migrations: [
    { name: "001_init.sql", applied: true, applied_at: "2026-04-01T00:00:00" },
    { name: "015_operator_actions.sql", applied: true, applied_at: "2026-05-15T00:00:00" },
  ],
};

const MOCK_ENV = {
  vars: [
    { name: "UI_OPERATOR_TOKEN", is_set: true, required: true },
    { name: "KALSHI_API_KEY_ID", is_set: false, required: false },
  ],
};

const MOCK_LOGS = {
  entries: [
    {
      timestamp: "2026-05-15T10:00:00",
      level: "WARNING",
      logger: "footy_ev_api.pipeline",
      message: "Pipeline cycle took 12s",
    },
    {
      timestamp: "2026-05-15T10:01:00",
      level: "ERROR",
      logger: "footy_ev_api.adapters",
      message: "DuckDB connection error",
    },
  ],
  total: 2,
};

function mockDiagnosticsFetch(overrides: Record<string, unknown> = {}) {
  vi.spyOn(global, "fetch").mockImplementation(async (url) => {
    const u = typeof url === "string" ? url : url.toString();
    if (u.includes("/diagnostics/circuit-breaker")) {
      return {
        ok: true,
        json: async () => overrides.cb ?? MOCK_CB_OK,
      } as Response;
    }
    if (u.includes("/diagnostics/migrations")) {
      return {
        ok: true,
        json: async () => overrides.migrations ?? MOCK_MIGRATIONS,
      } as Response;
    }
    if (u.includes("/diagnostics/env")) {
      return {
        ok: true,
        json: async () => overrides.env ?? MOCK_ENV,
      } as Response;
    }
    if (u.includes("/diagnostics/logs")) {
      return {
        ok: true,
        json: async () => overrides.logs ?? MOCK_LOGS,
      } as Response;
    }
    return { ok: true, json: async () => ({}) } as Response;
  });
}

describe("DiagnosticsPage", () => {
  beforeEach(() => vi.restoreAllMocks());

  it("renders circuit breaker ok state", async () => {
    mockDiagnosticsFetch();
    render(<DiagnosticsPage />, { wrapper });
    await waitFor(() => {
      expect(screen.getByText("OK")).toBeDefined();
    });
  });

  it("shows tripped badge when circuit breaker is tripped", async () => {
    mockDiagnosticsFetch({ cb: MOCK_CB_TRIPPED });
    render(<DiagnosticsPage />, { wrapper });
    await waitFor(() => {
      expect(screen.getByText("TRIPPED")).toBeDefined();
      expect(screen.getByText(/pipeline timeout/)).toBeDefined();
    });
  });

  it("renders migration table with names", async () => {
    mockDiagnosticsFetch();
    render(<DiagnosticsPage />, { wrapper });
    await waitFor(() => {
      expect(screen.getByText("001_init.sql")).toBeDefined();
      expect(screen.getByText("015_operator_actions.sql")).toBeDefined();
    });
  });

  it("renders env vars with set/unset indicators", async () => {
    mockDiagnosticsFetch();
    render(<DiagnosticsPage />, { wrapper });
    await waitFor(() => {
      expect(screen.getByText("UI_OPERATOR_TOKEN")).toBeDefined();
      expect(screen.getByText("KALSHI_API_KEY_ID")).toBeDefined();
    });
  });

  it("has a link to the logs page", async () => {
    mockDiagnosticsFetch();
    render(<DiagnosticsPage />, { wrapper });
    const link = screen.getByRole("link", { name: /view logs/i });
    expect(link).toBeDefined();
    expect((link as HTMLAnchorElement).href).toContain("/diagnostics/logs");
  });
});

describe("DiagnosticsLogsPage", () => {
  beforeEach(() => vi.restoreAllMocks());

  it("renders log entries", async () => {
    mockDiagnosticsFetch();
    render(<DiagnosticsLogsPage />, { wrapper });
    await waitFor(() => {
      expect(screen.getByText("Pipeline cycle took 12s")).toBeDefined();
      expect(screen.getByText("DuckDB connection error")).toBeDefined();
    });
  });

  it("shows entry count in header", async () => {
    mockDiagnosticsFetch();
    render(<DiagnosticsLogsPage />, { wrapper });
    await waitFor(() => {
      expect(screen.getByText(/2 \/ 2 entries/)).toBeDefined();
    });
  });

  it("has back link to diagnostics", () => {
    mockDiagnosticsFetch();
    render(<DiagnosticsLogsPage />, { wrapper });
    const link = screen.getByRole("link", { name: /diagnostics/i });
    expect((link as HTMLAnchorElement).href).toContain("/diagnostics");
  });
});
