import React from "react";
import { render, screen, waitFor, fireEvent } from "@testing-library/react";
import { describe, it, expect, vi, beforeEach } from "vitest";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";

vi.mock("next/navigation", () => ({
  useRouter: () => ({ push: vi.fn(), replace: vi.fn(), refresh: vi.fn() }),
  usePathname: () => "/settings",
  useSearchParams: () => new URLSearchParams(),
}));

vi.mock("next-themes", () => ({
  useTheme: () => ({ theme: "system", setTheme: vi.fn() }),
}));

vi.mock("sonner", () => ({
  toast: { success: vi.fn(), error: vi.fn() },
}));

import SettingsPage from "@/app/(dashboard)/settings/page";

function wrapper({ children }: { children: React.ReactNode }) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return <QueryClientProvider client={qc}>{children}</QueryClientProvider>;
}

const MOCK_SETTINGS = {
  settings: {
    theme: "dark",
    density: "comfortable",
    default_page_size: 50,
    default_time_range_days: 30,
  },
};

const MOCK_CREDENTIALS = {
  configured: true,
  key_id_present: true,
  private_key_present: true,
  base_url: "https://api.kalshi.com",
  is_demo: false,
};

function mockFetch() {
  vi.spyOn(global, "fetch").mockImplementation(async (url) => {
    const u = typeof url === "string" ? url : url.toString();
    if (u.includes("/settings")) {
      return { ok: true, json: async () => MOCK_SETTINGS } as Response;
    }
    if (u.includes("/kalshi/credentials")) {
      return { ok: true, json: async () => MOCK_CREDENTIALS } as Response;
    }
    return { ok: true, json: async () => ({}) } as Response;
  });
}

describe("SettingsPage", () => {
  beforeEach(() => vi.restoreAllMocks());

  it("renders save button", async () => {
    mockFetch();
    render(<SettingsPage />, { wrapper });
    await waitFor(() => {
      expect(screen.getByRole("button", { name: /save settings/i })).toBeDefined();
    });
  });

  it("shows theme options", async () => {
    mockFetch();
    render(<SettingsPage />, { wrapper });
    await waitFor(() => {
      expect(screen.getByText("System")).toBeDefined();
      expect(screen.getByText("Light")).toBeDefined();
      expect(screen.getByText("Dark")).toBeDefined();
    });
  });

  it("shows density options", async () => {
    mockFetch();
    render(<SettingsPage />, { wrapper });
    await waitFor(() => {
      expect(screen.getByText("Comfortable")).toBeDefined();
      expect(screen.getByText("Compact")).toBeDefined();
    });
  });

  it("shows credentials section", async () => {
    mockFetch();
    render(<SettingsPage />, { wrapper });
    await waitFor(() => {
      expect(screen.getByText("Credentials Status")).toBeDefined();
    });
  });

  it("shows sign out button", async () => {
    mockFetch();
    render(<SettingsPage />, { wrapper });
    await waitFor(() => {
      expect(screen.getByRole("button", { name: /sign out/i })).toBeDefined();
    });
  });

  it("has page size options 25, 50, 100", async () => {
    mockFetch();
    render(<SettingsPage />, { wrapper });
    await waitFor(() => {
      expect(screen.getByText("25")).toBeDefined();
      expect(screen.getByText("50")).toBeDefined();
      expect(screen.getByText("100")).toBeDefined();
    });
  });
});

describe("CommandPalette exports", () => {
  it("CommandPalette and openPalette are exported", async () => {
    const mod = await import("@/components/command-palette");
    expect(typeof mod.CommandPalette).toBe("function");
    expect(typeof mod.openPalette).toBe("function");
  });
});
