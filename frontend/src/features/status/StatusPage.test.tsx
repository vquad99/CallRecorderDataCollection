// Requirements: FND-016, FND-018
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";

import { StatusPage } from "./StatusPage";

const json = (status: number, body: unknown) =>
  new Response(JSON.stringify(body), { status, headers: { "content-type": "application/json" } });

const version = { name: "conversation-collection-platform", version: "0.1.0", environment: "test" };

afterEach(() => vi.unstubAllGlobals());

describe("StatusPage", () => {
  it("shows ready state and version", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(() =>
        Promise.resolve(
          json(200, {
            status: "ready",
            checks: { database: "ok", redis: "not_configured" },
            version,
          }),
        ),
      ),
    );
    render(<StatusPage />);
    expect(await screen.findByText("Ready")).toBeInTheDocument();
    expect(screen.getByText("Not configured")).toBeInTheDocument();
    expect(screen.getByText("Version 0.1.0 (test)")).toBeInTheDocument();
  });

  it("shows not-ready from a 503 readiness answer", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(() =>
        Promise.resolve(
          json(200, { status: "not_ready", checks: { database: "error", redis: "ok" }, version }),
        ),
      ),
    );
    render(<StatusPage />);
    expect(await screen.findByText("Not ready")).toBeInTheDocument();
    expect(screen.getByText("Not reachable")).toBeInTheDocument();
  });

  it("shows an error with retry when the server cannot be reached", async () => {
    const fetchMock = vi.fn().mockRejectedValue(new TypeError("Failed to fetch"));
    vi.stubGlobal("fetch", fetchMock);
    render(<StatusPage />);
    expect(await screen.findByRole("alert")).toHaveTextContent("Cannot reach the server");
    fetchMock.mockImplementation(() =>
      Promise.resolve(json(200, { status: "ready", checks: {}, version })),
    );
    await userEvent.click(screen.getByRole("button", { name: "Try again" }));
    expect(await screen.findByText("Ready")).toBeInTheDocument();
  });
});
