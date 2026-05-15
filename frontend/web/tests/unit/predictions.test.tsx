import React from "react";
import { render, screen, waitFor } from "@testing-library/react";
import { describe, it, expect, vi, beforeEach } from "vitest";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";

vi.mock("next/navigation", () => ({
  useSearchParams: () => new URLSearchParams(),
  useRouter: () => ({ push: vi.fn(), replace: vi.fn(), refresh: vi.fn() }),
  usePathname: () => "/predictions",
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

import PredictionsPage from "@/app/(dashboard)/predictions/page";

function wrapper({ children }: { children: React.ReactNode }) {
  const qc = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
  return <QueryClientProvider client={qc}>{children}</QueryClientProvider>;
}

const MOCK_PREDICTION = {
  prediction_id: "abc123def456abc123def456abc12345",
  fixture_id: "EPL|2025-2026|arsenal|manchester_city|2026-05-14",
  market: "ou_2.5",
  selection: "over",
  p_raw: 0.5412,
  p_calibrated: 0.5198,
  sigma_p: 0.05,
  model_version: "xgb_ou25_v1",
  features_hash: "deadbeef12345678",
  as_of: "2026-05-14T10:00:00+00:00",
  generated_at: "2026-05-14T10:00:01+00:00",
  run_id: "api_run_abc123",
};

function mockPredictionsFetch(overrides: Record<string, unknown> = {}) {
  vi.spyOn(global, "fetch").mockImplementation(async (url) => {
    const urlStr = typeof url === "string" ? url : url.toString();
    if (urlStr.includes("/api/v1/auth/me")) {
      return {
        ok: true,
        json: async () => ({ username: "operator" }),
      } as Response;
    }
    if (urlStr.includes("/api/v1/predictions/run")) {
      return {
        ok: true,
        json: async () => ({ job_id: "job-abc", status: "queued" }),
      } as Response;
    }
    if (urlStr.includes("/api/v1/predictions")) {
      return {
        ok: true,
        json: async () =>
          overrides.predictions ?? {
            predictions: [MOCK_PREDICTION],
            total: 1,
          },
      } as Response;
    }
    return { ok: false, json: async () => ({}) } as Response;
  });
}

describe("PredictionsPage", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("renders page header", async () => {
    mockPredictionsFetch();
    render(<PredictionsPage />, { wrapper });
    expect(screen.getByText("Predictions")).toBeDefined();
  });

  it("shows prediction row after load", async () => {
    mockPredictionsFetch();
    render(<PredictionsPage />, { wrapper });
    await waitFor(() => {
      expect(screen.getByText("ou_2.5")).toBeDefined();
    });
  });

  it("shows no predictions message when empty", async () => {
    mockPredictionsFetch({ predictions: { predictions: [], total: 0 } });
    render(<PredictionsPage />, { wrapper });
    await waitFor(() => {
      expect(screen.getByText("No predictions found.")).toBeDefined();
    });
  });

  it("shows total count from API", async () => {
    mockPredictionsFetch({
      predictions: { predictions: [MOCK_PREDICTION], total: 17 },
    });
    render(<PredictionsPage />, { wrapper });
    await waitFor(() => {
      expect(screen.getByText("17 total predictions")).toBeDefined();
    });
  });

  it("shows model version in rendered row", async () => {
    mockPredictionsFetch();
    render(<PredictionsPage />, { wrapper });
    await waitFor(() => {
      expect(screen.getByText("xgb_ou25_v1")).toBeDefined();
    });
  });
});
