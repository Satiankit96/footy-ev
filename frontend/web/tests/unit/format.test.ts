import { describe, it, expect } from "vitest";
import { formatTimestamp, formatAge, formatClv, clvColor } from "@/lib/utils/format";

describe("formatTimestamp", () => {
  it("formats a valid ISO string", () => {
    const result = formatTimestamp("2024-03-15T10:30:00.000Z");
    expect(result).toMatch(/Mar/);
    expect(result).toMatch(/2024/);
  });

  it("returns original string on invalid input", () => {
    expect(formatTimestamp("not-a-date")).toBe("not-a-date");
  });
});

describe("formatAge", () => {
  it("returns em-dash for null", () => {
    expect(formatAge(null)).toBe("—");
  });

  it("returns a human-readable age for a valid ISO string", () => {
    const recent = new Date(Date.now() - 60_000).toISOString();
    const result = formatAge(recent);
    expect(result).toMatch(/minute|second/);
  });

  it("returns original string on invalid input", () => {
    expect(formatAge("bad-date")).toBe("bad-date");
  });
});

describe("formatClv", () => {
  it("returns em-dash for null", () => {
    expect(formatClv(null)).toBe("—");
  });

  it("shows + prefix for positive CLV", () => {
    expect(formatClv(3.5)).toBe("+3.50%");
  });

  it("shows - prefix for negative CLV", () => {
    expect(formatClv(-1.25)).toBe("-1.25%");
  });

  it("shows + for zero", () => {
    expect(formatClv(0)).toBe("+0.00%");
  });

  it("rounds to 2 decimal places", () => {
    expect(formatClv(1.999)).toBe("+2.00%");
  });
});

describe("clvColor", () => {
  it("returns muted for null", () => {
    expect(clvColor(null)).toBe("text-muted-foreground");
  });

  it("returns green-500 for CLV >= 2", () => {
    expect(clvColor(2.0)).toBe("text-green-500");
    expect(clvColor(5.0)).toBe("text-green-500");
  });

  it("returns green-400 for 0 <= CLV < 2", () => {
    expect(clvColor(0)).toBe("text-green-400");
    expect(clvColor(1.99)).toBe("text-green-400");
  });

  it("returns yellow for -2 <= CLV < 0", () => {
    expect(clvColor(-0.5)).toBe("text-yellow-500");
    expect(clvColor(-2.0)).toBe("text-yellow-500");
  });

  it("returns destructive for CLV < -2", () => {
    expect(clvColor(-2.01)).toBe("text-destructive");
    expect(clvColor(-10)).toBe("text-destructive");
  });
});
