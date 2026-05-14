import { render, screen } from "@testing-library/react";
import { describe, it, expect, vi } from "vitest";
import { VenuePill } from "@/components/layout/venue-pill";
import { CircuitBreakerLED } from "@/components/layout/circuit-breaker-led";
import { TooltipProvider } from "@/components/ui/tooltip";

vi.mock("next/navigation", () => ({
  usePathname: () => "/",
  useRouter: () => ({ push: vi.fn(), refresh: vi.fn() }),
}));

describe("VenuePill", () => {
  it("shows DEMO badge for demo venue", () => {
    const venue = {
      name: "kalshi",
      base_url: "https://demo-api.kalshi.co/trade-api/v2",
      is_demo: true,
    };
    render(<VenuePill venue={venue} />);
    expect(screen.getByText("KALSHI · DEMO")).toBeInTheDocument();
  });

  it("shows PROD badge for production venue", () => {
    const venue = {
      name: "kalshi",
      base_url: "https://api.elections.kalshi.com/trade-api/v2",
      is_demo: false,
    };
    render(<VenuePill venue={venue} />);
    expect(screen.getByText("KALSHI · PROD")).toBeInTheDocument();
  });

  it("shows NO VENUE when not configured", () => {
    render(<VenuePill venue={null} />);
    expect(screen.getByText("NO VENUE")).toBeInTheDocument();
  });
});

describe("CircuitBreakerLED", () => {
  it("shows green dot when OK", () => {
    render(
      <TooltipProvider>
        <CircuitBreakerLED breaker={{ state: "ok", reason: null }} />
      </TooltipProvider>,
    );
    const led = screen.getByLabelText("Circuit breaker OK");
    expect(led).toBeInTheDocument();
    expect(led.className).toContain("bg-success");
  });

  it("shows red pulsing dot when tripped", () => {
    render(
      <TooltipProvider>
        <CircuitBreakerLED
          breaker={{ state: "tripped", reason: "stale data" }}
        />
      </TooltipProvider>,
    );
    const led = screen.getByLabelText("TRIPPED: stale data");
    expect(led).toBeInTheDocument();
    expect(led.className).toContain("bg-destructive");
    expect(led.className).toContain("animate-pulse");
  });
});

describe("Sidebar", () => {
  it("renders all navigation sections", async () => {
    const { Sidebar } = await import("@/components/layout/sidebar");
    render(<Sidebar />);
    expect(screen.getByText("Home")).toBeInTheDocument();
    expect(screen.getByText("Pipeline")).toBeInTheDocument();
    expect(screen.getByText("Kalshi")).toBeInTheDocument();
    expect(screen.getByText("Predictions")).toBeInTheDocument();
    expect(screen.getByText("Live Trading")).toBeInTheDocument();
    expect(screen.getByText("Settings")).toBeInTheDocument();
  });
});
