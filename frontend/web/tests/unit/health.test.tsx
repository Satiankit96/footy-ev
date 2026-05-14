import { render, screen } from "@testing-library/react";
import { describe, it, expect } from "vitest";
import DashboardPage from "@/app/(dashboard)/page";

describe("Dashboard page", () => {
  it("shows placeholder message", () => {
    render(<DashboardPage />);
    expect(
      screen.getByText("Dashboard tiles coming in Stage 3+"),
    ).toBeInTheDocument();
  });
});
