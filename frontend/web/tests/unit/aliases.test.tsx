import {
  render,
  screen,
  fireEvent,
  waitFor,
  cleanup,
} from "@testing-library/react";
import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";

vi.mock("next/navigation", () => ({
  usePathname: () => "/aliases",
  useRouter: () => ({ push: vi.fn(), replace: vi.fn(), refresh: vi.fn() }),
  useSearchParams: () => new URLSearchParams(),
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

vi.mock("@/components/bootstrap/bootstrap-modal", () => ({
  BootstrapModal: ({ onClose }: { onClose: () => void }) => (
    <div data-testid="bootstrap-modal">
      <button onClick={onClose}>Close</button>
    </div>
  ),
}));

import AliasesPage from "@/app/(dashboard)/aliases/page";

function wrapper({ children }: { children: React.ReactNode }) {
  const qc = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
  return <QueryClientProvider client={qc}>{children}</QueryClientProvider>;
}

const MOCK_ALIASES = {
  aliases: [
    {
      event_ticker: "KXEPLTOTAL-26MAY14-ARS-MCI",
      fixture_id: "epl_2026-05-14_ARS_MCI",
      confidence: 0.95,
      resolved_by: "fuzzy_match",
      resolved_at: "2026-05-14T12:00:00+00:00",
      status: "active",
    },
    {
      event_ticker: "KXEPLTOTAL-26MAY14-LIV-CHE",
      fixture_id: "epl_2026-05-14_LIV_CHE",
      confidence: 0.8,
      resolved_by: "manual",
      resolved_at: "2026-05-13T10:00:00+00:00",
      status: "retired",
    },
  ],
  total: 2,
};

function mockFetch(overrides: Record<string, unknown> = {}) {
  vi.spyOn(global, "fetch").mockImplementation(async (url) => {
    const urlStr = typeof url === "string" ? url : url.toString();
    if (urlStr.includes("/aliases/conflicts")) {
      return {
        ok: true,
        json: async () => overrides.conflicts ?? { conflicts: [] },
      } as Response;
    }
    if (urlStr.includes("/aliases")) {
      return {
        ok: true,
        json: async () => overrides.aliases ?? MOCK_ALIASES,
      } as Response;
    }
    return { ok: true, json: async () => ({}) } as Response;
  });
}

describe("Aliases page", () => {
  beforeEach(() => {
    vi.restoreAllMocks();
  });

  afterEach(() => {
    cleanup();
  });

  it("renders alias table with data", async () => {
    mockFetch();
    render(<AliasesPage />, { wrapper });
    await waitFor(() => {
      expect(
        screen.getByText("KXEPLTOTAL-26MAY14-ARS-MCI"),
      ).toBeDefined();
      expect(
        screen.getByText("epl_2026-05-14_ARS_MCI"),
      ).toBeDefined();
      expect(screen.getByText("95%")).toBeDefined();
    });
  });

  it("shows conflict banner when conflicts exist", async () => {
    mockFetch({
      conflicts: {
        conflicts: [
          {
            fixture_id: "epl_2026-05-14_ARS_MCI",
            alias_count: 2,
            tickers: ["T1", "T2"],
          },
        ],
      },
    });
    render(<AliasesPage />, { wrapper });
    await waitFor(() => {
      expect(
        screen.getByText(/has multiple active aliases/),
      ).toBeDefined();
    });
  });

  it("opens retire modal on Retire button click", async () => {
    mockFetch();
    render(<AliasesPage />, { wrapper });
    await waitFor(() => {
      expect(screen.getByText("KXEPLTOTAL-26MAY14-ARS-MCI")).toBeDefined();
    });
    const retireButtons = screen.getAllByText("Retire");
    fireEvent.click(retireButtons[0]);
    await waitFor(() => {
      expect(screen.getByText("Retire Alias")).toBeDefined();
      expect(screen.getByText(/RETIRE-MCI/)).toBeDefined();
    });
  });

  it("opens bootstrap modal on Bootstrap button click", async () => {
    mockFetch();
    render(<AliasesPage />, { wrapper });
    await waitFor(() => {
      expect(screen.getByText("Bootstrap")).toBeDefined();
    });
    fireEvent.click(screen.getByText("Bootstrap"));
    await waitFor(() => {
      expect(screen.getByTestId("bootstrap-modal")).toBeDefined();
    });
  });

  it("filters aliases by search text", async () => {
    mockFetch();
    render(<AliasesPage />, { wrapper });
    await waitFor(() => {
      expect(screen.getByText("KXEPLTOTAL-26MAY14-ARS-MCI")).toBeDefined();
    });
    const input = screen.getByPlaceholderText(/Filter by ticker/);
    fireEvent.change(input, { target: { value: "LIV" } });
    await waitFor(() => {
      expect(
        screen.queryByText("KXEPLTOTAL-26MAY14-ARS-MCI"),
      ).toBeNull();
      expect(
        screen.getByText("KXEPLTOTAL-26MAY14-LIV-CHE"),
      ).toBeDefined();
    });
  });
});
