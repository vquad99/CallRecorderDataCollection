// Participant personal page (D-067). Requirements: PART-013, PART-014
import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";

import { fakeApi, renderAt } from "../../test/fakeApi";
import { PORTAL } from "../../test/world";

afterEach(() => vi.unstubAllGlobals());

const anonymous = {
  "GET /api/v1/auth/csrf": () => [204, null] as [number, unknown],
  "GET /api/v1/auth/me": () =>
    [401, { error: { code: "UNAUTHENTICATED", message: "Sign in" } }] as [number, unknown],
};

describe("participant page", () => {
  it("shows the consent form and sessions, and sends the link secret in a header only", async () => {
    const { fetchMock } = fakeApi({
      ...anonymous,
      "GET /api/v1/portal/me": () => [200, PORTAL],
    });
    renderAt("/portal#secret-link-token-0123456789");
    expect(await screen.findByText("I agree that my voice is recorded.")).toBeInTheDocument();
    expect(screen.getByText("Waiting for your answer")).toBeInTheDocument();
    expect(screen.getByRole("cell", { name: "T000001" })).toBeInTheDocument();
    expect(screen.queryByRole("navigation", { name: "Main" })).not.toBeInTheDocument();
    const call = fetchMock.mock.calls.find(([url]) => String(url).includes("/portal/me"));
    expect(String(call?.[0])).not.toContain("secret-link-token");
    expect((call?.[1] as RequestInit).headers).toMatchObject({
      "X-Portal-Token": "secret-link-token-0123456789",
    });
  });

  it("needs the form to be read before agreeing, then shows the answer and offers withdrawal", async () => {
    const { calls } = fakeApi({
      ...anonymous,
      "GET /api/v1/portal/me": () => [200, PORTAL],
      "POST /api/v1/portal/consent": () => [
        200,
        { ...PORTAL, consent_status: "GIVEN", consent_at: "2026-11-10T00:00:00Z" },
      ],
    });
    renderAt("/portal#secret-link-token-0123456789");
    const agree = await screen.findByRole("button", { name: "I agree" });
    expect(agree).toBeDisabled();
    await userEvent.click(screen.getByLabelText("I have read and understood this form"));
    await userEvent.click(agree);
    expect(await screen.findByText("You agreed")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Withdraw my consent" })).toBeInTheDocument();
    await waitFor(() =>
      expect(calls.find((c) => c.path === "/api/v1/portal/consent")?.body).toEqual({
        decision: "GIVEN",
      }),
    );
  });

  it("explains a link without its secret and asks nothing of the server", async () => {
    const { calls } = fakeApi(anonymous);
    renderAt("/portal");
    expect(await screen.findByRole("alert")).toHaveTextContent("This link is incomplete");
    expect(calls.some((c) => c.path.includes("/portal/"))).toBe(false);
  });
});
