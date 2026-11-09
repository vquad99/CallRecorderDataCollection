// Requirements: FND-018, FND-017
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

import { ErrorBoundary } from "./ErrorBoundary";
import { EmptyState, ErrorState, LoadingState } from "./StateViews";

describe("state views", () => {
  it("announces loading politely", () => {
    render(<LoadingState label="Fetching tasks" />);
    expect(screen.getByRole("status")).toHaveTextContent("Fetching tasks");
  });

  it("shows an empty state with its action", () => {
    render(
      <EmptyState title="No tasks" message="Nothing assigned" action={<a href="/">Home</a>} />,
    );
    expect(screen.getByRole("heading", { name: "No tasks" })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Home" })).toBeInTheDocument();
  });

  it("shows an error with reference and a working retry", async () => {
    const onRetry = vi.fn();
    render(<ErrorState message="Server down" requestId="rid-9" onRetry={onRetry} />);
    expect(screen.getByRole("alert")).toHaveTextContent("Server down");
    expect(screen.getByText("Reference: rid-9")).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "Try again" }));
    expect(onRetry).toHaveBeenCalledOnce();
  });
});

function Thrower(): never {
  throw new Error("render failure");
}

describe("ErrorBoundary", () => {
  it("catches a render error and shows a recoverable message", () => {
    const consoleError = vi.spyOn(console, "error").mockImplementation(() => undefined);
    render(
      <ErrorBoundary>
        <Thrower />
      </ErrorBoundary>,
    );
    expect(screen.getByRole("alert")).toHaveTextContent("The page failed to display");
    expect(screen.getByRole("button", { name: "Try again" })).toBeInTheDocument();
    expect(consoleError).toHaveBeenCalled();
  });
});
