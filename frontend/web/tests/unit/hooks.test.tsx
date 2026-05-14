import { render, screen, waitFor, cleanup } from "@testing-library/react";
import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { useHealth, useShell } from "@/lib/api/hooks";

vi.mock("next/navigation", () => ({
  usePathname: () => "/",
  useRouter: () => ({ push: vi.fn(), refresh: vi.fn() }),
}));

function createWrapper() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return function Wrapper({ children }: { children: React.ReactNode }) {
    return <QueryClientProvider client={qc}>{children}</QueryClientProvider>;
  };
}

function HealthDisplay() {
  const { data, isLoading, error } = useHealth();
  if (isLoading) return <div>loading...</div>;
  if (error) return <div>error</div>;
  return <div>status:{data?.status}</div>;
}

function ShellDisplay() {
  const { data, isLoading, error } = useShell();
  if (isLoading) return <div>loading...</div>;
  if (error) return <div>error</div>;
  return (
    <div>
      <span>venue:{data?.venue.name}</span>
      <span>breaker:{data?.circuit_breaker.state}</span>
    </div>
  );
}

describe("useHealth hook", () => {
  beforeEach(() => {
    vi.restoreAllMocks();
  });

  afterEach(() => {
    cleanup();
  });

  it("fetches and renders health data", async () => {
    vi.spyOn(global, "fetch").mockResolvedValueOnce({
      ok: true,
      json: async () => ({ status: "ok", version: "0.1.0", uptime_s: 10, active_venue: null }),
    } as Response);

    render(<HealthDisplay />, { wrapper: createWrapper() });

    expect(screen.getByText("loading...")).toBeInTheDocument();

    await waitFor(() => {
      expect(screen.getByText("status:ok")).toBeInTheDocument();
    });
  });
});

describe("useShell hook", () => {
  beforeEach(() => {
    vi.restoreAllMocks();
  });

  afterEach(() => {
    cleanup();
  });

  it("fetches and renders shell data", async () => {
    vi.spyOn(global, "fetch").mockResolvedValueOnce({
      ok: true,
      json: async () => ({
        operator: "operator",
        venue: { name: "kalshi", base_url: "https://demo-api.kalshi.co", is_demo: true },
        circuit_breaker: { state: "ok", last_tripped_at: null, reason: null },
        pipeline: { loop_active: false, last_cycle_at: null },
      }),
    } as Response);

    render(<ShellDisplay />, { wrapper: createWrapper() });

    await waitFor(() => {
      expect(screen.getByText("venue:kalshi")).toBeInTheDocument();
      expect(screen.getByText("breaker:ok")).toBeInTheDocument();
    });
  });
});
