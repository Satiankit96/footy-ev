import { describe, it, expect, vi, beforeEach } from "vitest";
import { ApiError, apiClient } from "@/lib/api/client";

vi.mock("next/navigation", () => ({
  usePathname: () => "/",
  useRouter: () => ({ push: vi.fn(), refresh: vi.fn() }),
}));

describe("apiClient", () => {
  beforeEach(() => {
    vi.restoreAllMocks();
  });

  it("get returns typed response on success", async () => {
    vi.spyOn(global, "fetch").mockResolvedValueOnce({
      ok: true,
      json: async () => ({ status: "ok", version: "0.1.0", uptime_s: 1.0, active_venue: null }),
    } as Response);

    const data = await apiClient.get<{ status: string; version: string }>("/api/v1/health");
    expect(data.status).toBe("ok");
    expect(data.version).toBe("0.1.0");
  });

  it("get throws ApiError with envelope on non-2xx", async () => {
    vi.spyOn(global, "fetch").mockResolvedValueOnce({
      ok: false,
      status: 500,
      json: async () => ({
        error: { code: "INTERNAL", message: "something broke", details: {}, request_id: "req-123" },
      }),
    } as Response);

    try {
      await apiClient.get("/api/v1/health");
      expect.fail("should have thrown");
    } catch (e) {
      expect(e).toBeInstanceOf(ApiError);
      const err = e as ApiError;
      expect(err.status).toBe(500);
      expect(err.code).toBe("INTERNAL");
      expect(err.message).toBe("something broke");
    }
  });

  it("get redirects to /login on 401", async () => {
    const locationSpy = vi.spyOn(window, "location", "get").mockReturnValue({
      ...window.location,
      href: "",
    });
    Object.defineProperty(window, "location", {
      value: { href: "" },
      writable: true,
    });

    vi.spyOn(global, "fetch").mockResolvedValueOnce({
      ok: false,
      status: 401,
      json: async () => ({
        error: { code: "UNAUTHORIZED", message: "Not authenticated" },
      }),
    } as Response);

    try {
      await apiClient.get("/api/v1/auth/me");
    } catch {
      // expected
    }
    expect(window.location.href).toBe("/login");

    locationSpy.mockRestore();
  });

  it("post sends JSON body", async () => {
    const fetchSpy = vi.spyOn(global, "fetch").mockResolvedValueOnce({
      ok: true,
      json: async () => ({ ok: true }),
    } as Response);

    await apiClient.post("/api/v1/auth/login", { token: "abc" });

    const call = fetchSpy.mock.calls[0];
    const init = call[1] as RequestInit;
    expect(init.method).toBe("POST");
    expect(init.headers).toHaveProperty("Content-Type", "application/json");
    expect(init.body).toBe(JSON.stringify({ token: "abc" }));
  });

  it("sends X-Request-ID header", async () => {
    const fetchSpy = vi.spyOn(global, "fetch").mockResolvedValueOnce({
      ok: true,
      json: async () => ({}),
    } as Response);

    await apiClient.get("/api/v1/health");

    const headers = (fetchSpy.mock.calls[0][1] as RequestInit).headers as Record<string, string>;
    expect(headers["X-Request-ID"]).toBeDefined();
    expect(headers["X-Request-ID"].length).toBeGreaterThan(0);
  });
});
