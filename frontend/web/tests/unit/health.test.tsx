import { render, screen, waitFor } from "@testing-library/react";
import { describe, it, expect, vi } from "vitest";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import DashboardPage from "@/app/(dashboard)/page";

vi.mock("next/navigation", () => ({
  usePathname: () => "/",
  useRouter: () => ({ push: vi.fn(), refresh: vi.fn() }),
}));

function wrapper({ children }: { children: React.ReactNode }) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return <QueryClientProvider client={qc}>{children}</QueryClientProvider>;
}

describe("Dashboard page", () => {
  it("shows placeholder message and health status", async () => {
    vi.spyOn(global, "fetch").mockResolvedValueOnce({
      ok: true,
      json: async () => ({ status: "ok", version: "0.1.0", uptime_s: 42.5 }),
    } as Response);

    render(<DashboardPage />, { wrapper });

    expect(
      screen.getByText("Dashboard tiles coming in Stage 3+"),
    ).toBeInTheDocument();

    await waitFor(() => {
      expect(screen.getByText(/API ok/)).toBeInTheDocument();
    });
  });
});
