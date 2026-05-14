import { render, screen, fireEvent, waitFor, cleanup } from "@testing-library/react";
import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";

vi.mock("next/navigation", () => ({
  usePathname: () => "/pipeline",
  useRouter: () => ({ push: vi.fn(), refresh: vi.fn() }),
}));

vi.mock("@/lib/api/ws", () => ({
  useWebSocket: () => ({ connected: false, lastMessage: null }),
}));

vi.mock("sonner", () => ({
  toast: { success: vi.fn(), error: vi.fn() },
  Toaster: () => null,
}));

import PipelinePage from "@/app/(dashboard)/pipeline/page";

function wrapper({ children }: { children: React.ReactNode }) {
  const qc = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
  return <QueryClientProvider client={qc}>{children}</QueryClientProvider>;
}

describe("Pipeline page", () => {
  beforeEach(() => {
    vi.restoreAllMocks();
  });

  afterEach(() => {
    cleanup();
  });

  it("renders status bar and action buttons", async () => {
    vi.spyOn(global, "fetch").mockImplementation(async (url) => {
      const urlStr = typeof url === "string" ? url : url.toString();
      if (urlStr.includes("/pipeline/status")) {
        return {
          ok: true,
          json: async () => ({
            last_cycle_at: null,
            last_cycle_duration_s: null,
            circuit_breaker: { state: "ok", last_tripped_at: null, reason: null },
            loop: { active: false, interval_min: null, started_at: null, last_cycle_at: null, cycles_completed: 0 },
            freshness: {},
          }),
        } as Response;
      }
      if (urlStr.includes("/pipeline/jobs")) {
        return { ok: true, json: async () => ({ jobs: [] }) } as Response;
      }
      return { ok: true, json: async () => ({}) } as Response;
    });

    render(<PipelinePage />, { wrapper });

    await waitFor(() => {
      expect(screen.getByText("Run Cycle")).toBeInTheDocument();
    });
    expect(screen.getByText("Start Loop")).toBeInTheDocument();
    expect(screen.getByText("IDLE")).toBeInTheDocument();
  });

  it("shows freshness gauges from status", async () => {
    vi.spyOn(global, "fetch").mockImplementation(async (url) => {
      const urlStr = typeof url === "string" ? url : url.toString();
      if (urlStr.includes("/pipeline/status")) {
        return {
          ok: true,
          json: async () => ({
            last_cycle_at: null,
            last_cycle_duration_s: null,
            circuit_breaker: { state: "ok", last_tripped_at: null, reason: null },
            loop: { active: false, interval_min: null, started_at: null, last_cycle_at: null, cycles_completed: 0 },
            freshness: {
              kalshi_events: { source: "kalshi_events", last_seen_at: null, age_seconds: null, threshold_seconds: 600, status: "stale" },
            },
          }),
        } as Response;
      }
      if (urlStr.includes("/pipeline/jobs")) {
        return { ok: true, json: async () => ({ jobs: [] }) } as Response;
      }
      return { ok: true, json: async () => ({}) } as Response;
    });

    render(<PipelinePage />, { wrapper });

    await waitFor(() => {
      expect(screen.getByText("kalshi_events")).toBeInTheDocument();
    });
  });

  it("cycle history table shows jobs", async () => {
    vi.spyOn(global, "fetch").mockImplementation(async (url) => {
      const urlStr = typeof url === "string" ? url : url.toString();
      if (urlStr.includes("/pipeline/status")) {
        return {
          ok: true,
          json: async () => ({
            last_cycle_at: null,
            last_cycle_duration_s: null,
            circuit_breaker: { state: "ok", last_tripped_at: null, reason: null },
            loop: { active: false, interval_min: null, started_at: null, last_cycle_at: null, cycles_completed: 0 },
            freshness: {},
          }),
        } as Response;
      }
      if (urlStr.includes("/pipeline/jobs")) {
        return {
          ok: true,
          json: async () => ({
            jobs: [
              {
                job_id: "abc123",
                job_type: "pipeline_cycle",
                status: "completed",
                started_at: "2026-05-14T00:00:00Z",
                completed_at: "2026-05-14T00:01:00Z",
                duration_s: 60.0,
                error: null,
                progress: [],
              },
            ],
          }),
        } as Response;
      }
      return { ok: true, json: async () => ({}) } as Response;
    });

    render(<PipelinePage />, { wrapper });

    await waitFor(() => {
      expect(screen.getByText("abc123")).toBeInTheDocument();
    });
    expect(screen.getByText("completed")).toBeInTheDocument();
  });

  it("Run Cycle button triggers POST", async () => {
    const fetchSpy = vi.spyOn(global, "fetch").mockImplementation(async (url, init) => {
      const urlStr = typeof url === "string" ? url : url.toString();
      if (urlStr.includes("/pipeline/cycle") && init?.method === "POST") {
        return { ok: true, json: async () => ({ job_id: "xyz", status: "queued" }) } as Response;
      }
      if (urlStr.includes("/pipeline/status")) {
        return {
          ok: true,
          json: async () => ({
            last_cycle_at: null,
            last_cycle_duration_s: null,
            circuit_breaker: { state: "ok", last_tripped_at: null, reason: null },
            loop: { active: false, interval_min: null, started_at: null, last_cycle_at: null, cycles_completed: 0 },
            freshness: {},
          }),
        } as Response;
      }
      if (urlStr.includes("/pipeline/jobs")) {
        return { ok: true, json: async () => ({ jobs: [] }) } as Response;
      }
      return { ok: true, json: async () => ({}) } as Response;
    });

    render(<PipelinePage />, { wrapper });

    await waitFor(() => {
      expect(screen.getByText("Run Cycle")).toBeInTheDocument();
    });

    fireEvent.click(screen.getByText("Run Cycle"));

    await waitFor(() => {
      const calls = fetchSpy.mock.calls.filter(
        ([u, i]) => typeof u === "string" && u.includes("/pipeline/cycle") && i?.method === "POST",
      );
      expect(calls.length).toBeGreaterThanOrEqual(1);
    });
  });

  it("loop toggle calls start endpoint", async () => {
    const fetchSpy = vi.spyOn(global, "fetch").mockImplementation(async (url, init) => {
      const urlStr = typeof url === "string" ? url : url.toString();
      if (urlStr.includes("/pipeline/loop/start") && init?.method === "POST") {
        return { ok: true, json: async () => ({ loop_id: "l1", interval_min: 15 }) } as Response;
      }
      if (urlStr.includes("/pipeline/status")) {
        return {
          ok: true,
          json: async () => ({
            last_cycle_at: null,
            last_cycle_duration_s: null,
            circuit_breaker: { state: "ok", last_tripped_at: null, reason: null },
            loop: { active: false, interval_min: null, started_at: null, last_cycle_at: null, cycles_completed: 0 },
            freshness: {},
          }),
        } as Response;
      }
      if (urlStr.includes("/pipeline/jobs")) {
        return { ok: true, json: async () => ({ jobs: [] }) } as Response;
      }
      return { ok: true, json: async () => ({}) } as Response;
    });

    render(<PipelinePage />, { wrapper });

    await waitFor(() => {
      expect(screen.getByText("Start Loop")).toBeInTheDocument();
    });

    fireEvent.click(screen.getByText("Start Loop"));

    await waitFor(() => {
      const calls = fetchSpy.mock.calls.filter(
        ([u, i]) => typeof u === "string" && u.includes("/pipeline/loop/start") && i?.method === "POST",
      );
      expect(calls.length).toBeGreaterThanOrEqual(1);
    });
  });

  it("useWebSocket hook interface works", async () => {
    const { useWebSocket } = await import("@/lib/api/ws");
    const result = (useWebSocket as unknown as (path: string) => { connected: boolean; lastMessage: null })("/test");
    expect(result).toHaveProperty("connected");
    expect(result).toHaveProperty("lastMessage");
  });
});
