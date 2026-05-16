import React from "react";
import { render, screen } from "@testing-library/react";
import { describe, it, expect, vi } from "vitest";

vi.mock("@/components/ui/tooltip", () => ({
  Tooltip: ({ children }: { children: React.ReactNode }) => <>{children}</>,
  TooltipTrigger: ({
    children,
    ...props
  }: React.HTMLAttributes<HTMLButtonElement> & { children?: React.ReactNode }) => (
    <button {...props}>{children}</button>
  ),
  TooltipContent: ({ children }: { children: React.ReactNode }) => (
    <div>{children}</div>
  ),
  TooltipProvider: ({ children }: { children: React.ReactNode }) => (
    <>{children}</>
  ),
}));

import { CircuitBreakerLED } from "@/components/layout/circuit-breaker-led";
import type { CircuitBreakerInfo } from "@/lib/api/hooks";

describe("CircuitBreakerLED", () => {
  it("shows OK label when breaker is null", () => {
    render(<CircuitBreakerLED breaker={null} />);
    expect(screen.getByLabelText("Circuit breaker OK")).toBeDefined();
  });

  it("shows OK label when breaker state is ok", () => {
    const breaker: CircuitBreakerInfo = {
      state: "ok",
      last_tripped_at: null,
      reason: null,
    };
    render(<CircuitBreakerLED breaker={breaker} />);
    expect(screen.getByLabelText("Circuit breaker OK")).toBeDefined();
  });

  it("shows TRIPPED label when breaker is tripped", () => {
    const breaker: CircuitBreakerInfo = {
      state: "tripped",
      last_tripped_at: "2024-01-01T00:00:00Z",
      reason: "stale data detected",
    };
    render(<CircuitBreakerLED breaker={breaker} />);
    const led = screen.getByLabelText(/TRIPPED/);
    expect(led).toBeDefined();
    expect(led.getAttribute("aria-label")).toContain("stale data detected");
  });

  it("shows 'unknown' reason when tripped with no reason", () => {
    const breaker: CircuitBreakerInfo = {
      state: "tripped",
      last_tripped_at: null,
      reason: null,
    };
    render(<CircuitBreakerLED breaker={breaker} />);
    expect(screen.getByLabelText(/unknown/)).toBeDefined();
  });
});
