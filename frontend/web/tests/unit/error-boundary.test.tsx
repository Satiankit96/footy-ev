import React from "react";
import { render, screen } from "@testing-library/react";
import { describe, it, expect, vi } from "vitest";
import { ErrorBoundary, withErrorBoundary } from "@/components/error-boundary";

function Bomb({ shouldThrow }: { shouldThrow: boolean }) {
  if (shouldThrow) throw new Error("Test error message");
  return <div>Child content OK</div>;
}

const silenceConsoleError = () =>
  vi.spyOn(console, "error").mockImplementation(() => {});

describe("ErrorBoundary", () => {
  it("renders children when there is no error", () => {
    render(
      <ErrorBoundary>
        <Bomb shouldThrow={false} />
      </ErrorBoundary>,
    );
    expect(screen.getByText("Child content OK")).toBeDefined();
  });

  it("shows error UI when a child throws", () => {
    const spy = silenceConsoleError();
    render(
      <ErrorBoundary>
        <Bomb shouldThrow={true} />
      </ErrorBoundary>,
    );
    expect(screen.getByText("Something went wrong")).toBeDefined();
    expect(screen.getByText("Test error message")).toBeDefined();
    spy.mockRestore();
  });

  it("shows Try again button when an error is caught", () => {
    const spy = silenceConsoleError();
    render(
      <ErrorBoundary>
        <Bomb shouldThrow={true} />
      </ErrorBoundary>,
    );
    expect(screen.getByRole("button", { name: /try again/i })).toBeDefined();
    spy.mockRestore();
  });

  it("renders custom fallback when provided", () => {
    const spy = silenceConsoleError();
    render(
      <ErrorBoundary fallback={<div>Custom error UI</div>}>
        <Bomb shouldThrow={true} />
      </ErrorBoundary>,
    );
    expect(screen.getByText("Custom error UI")).toBeDefined();
    expect(screen.queryByText("Something went wrong")).toBeNull();
    spy.mockRestore();
  });

  it("does not show error UI for non-throwing children", () => {
    render(
      <ErrorBoundary>
        <Bomb shouldThrow={false} />
      </ErrorBoundary>,
    );
    expect(screen.queryByText("Something went wrong")).toBeNull();
    expect(screen.queryByRole("button", { name: /try again/i })).toBeNull();
  });
});

describe("withErrorBoundary", () => {
  it("wraps a component and renders it normally", () => {
    const Safe = withErrorBoundary(({ text }: { text: string }) => (
      <div>{text}</div>
    ));
    render(<Safe text="Hello from HOC" />);
    expect(screen.getByText("Hello from HOC")).toBeDefined();
  });

  it("catches errors in the wrapped component", () => {
    const spy = silenceConsoleError();
    const BombWrapped = withErrorBoundary(Bomb);
    render(<BombWrapped shouldThrow={true} />);
    expect(screen.getByText("Something went wrong")).toBeDefined();
    spy.mockRestore();
  });
});
