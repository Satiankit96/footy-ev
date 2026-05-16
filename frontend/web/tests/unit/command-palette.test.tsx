import React from "react";
import { render, screen, fireEvent, act } from "@testing-library/react";
import { describe, it, expect, vi, afterEach } from "vitest";

vi.mock("next/navigation", () => ({
  useRouter: () => ({ push: vi.fn() }),
  usePathname: () => "/",
}));

vi.mock("sonner", () => ({
  toast: { success: vi.fn(), error: vi.fn() },
}));

import { CommandPalette, openPalette, closePalette } from "@/components/command-palette";

afterEach(() => {
  act(() => {
    closePalette();
  });
});

describe("CommandPalette", () => {
  it("renders nothing when closed", () => {
    render(<CommandPalette />);
    expect(screen.queryByRole("dialog")).toBeNull();
  });

  it("becomes visible after openPalette() is called", () => {
    render(<CommandPalette />);
    act(() => {
      openPalette();
    });
    expect(screen.getByRole("dialog")).toBeDefined();
  });

  it("shows navigation group items when open", () => {
    render(<CommandPalette />);
    act(() => {
      openPalette();
    });
    expect(screen.getByText("Dashboard")).toBeDefined();
    expect(screen.getByText("Settings")).toBeDefined();
    expect(screen.getByText("Pipeline")).toBeDefined();
  });

  it("shows Actions group when open", () => {
    render(<CommandPalette />);
    act(() => {
      openPalette();
    });
    expect(screen.getByText("Run pipeline cycle")).toBeDefined();
  });

  it("filters items by search query", () => {
    render(<CommandPalette />);
    act(() => {
      openPalette();
    });
    const input = screen.getByPlaceholderText("Search pages, actions…");
    fireEvent.change(input, { target: { value: "settings" } });
    expect(screen.getByText("Settings")).toBeDefined();
    expect(screen.queryByText("Dashboard")).toBeNull();
  });

  it("shows no-results message for unmatched query", () => {
    render(<CommandPalette />);
    act(() => {
      openPalette();
    });
    const input = screen.getByPlaceholderText("Search pages, actions…");
    fireEvent.change(input, { target: { value: "xyznotfound123" } });
    expect(screen.getByText(/No results for/)).toBeDefined();
  });

  it("closes when Escape is pressed on the dialog panel", () => {
    render(<CommandPalette />);
    act(() => {
      openPalette();
    });
    const dialog = screen.getByRole("dialog");
    fireEvent.keyDown(dialog, { key: "Escape" });
    expect(screen.queryByRole("dialog")).toBeNull();
  });

  it("closes when backdrop is clicked", () => {
    const { container } = render(<CommandPalette />);
    act(() => {
      openPalette();
    });
    expect(screen.getByRole("dialog")).toBeDefined();
    const backdrop = container.firstChild as HTMLElement;
    fireEvent.click(backdrop);
    expect(screen.queryByRole("dialog")).toBeNull();
  });
});

describe("CommandPalette exports", () => {
  it("exports openPalette and closePalette as functions", async () => {
    const mod = await import("@/components/command-palette");
    expect(typeof mod.openPalette).toBe("function");
    expect(typeof mod.closePalette).toBe("function");
  });
});
