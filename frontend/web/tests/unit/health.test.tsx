import { render, screen, waitFor } from "@testing-library/react";
import { describe, it, expect, vi, beforeEach } from "vitest";
import Home from "@/app/page";

describe("Home page", () => {
  beforeEach(() => {
    vi.restoreAllMocks();
  });

  it("shows API Connected when health endpoint succeeds", async () => {
    vi.spyOn(global, "fetch").mockResolvedValueOnce({
      ok: true,
      json: async () => ({ status: "ok", version: "0.1.0", uptime_s: 42.5 }),
    } as Response);

    render(<Home />);

    await waitFor(() => {
      expect(screen.getByText("API Connected")).toBeInTheDocument();
    });

    expect(screen.getByText("ok")).toBeInTheDocument();
    expect(screen.getByText("0.1.0")).toBeInTheDocument();
    expect(screen.getByText("42.5s")).toBeInTheDocument();
  });

  it("shows API Unreachable when health endpoint fails", async () => {
    vi.spyOn(global, "fetch").mockRejectedValueOnce(
      new Error("Connection refused"),
    );

    render(<Home />);

    await waitFor(() => {
      expect(screen.getByText("API Unreachable")).toBeInTheDocument();
    });
  });
});
