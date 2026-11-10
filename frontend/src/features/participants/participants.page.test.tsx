// Participants section (D-073). Requirements: PART-016, PART-017
import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";

import { fakeApi, renderAt, signedInAs } from "../../test/fakeApi";
import { ALL_PERMISSIONS, worldHandlers } from "../../test/world";

afterEach(() => vi.unstubAllGlobals());

const wait = { timeout: 5000 };

function open(extra: Parameters<typeof signedInAs>[1] = {}) {
  return fakeApi(signedInAs(ALL_PERMISSIONS, { ...worldHandlers(), ...extra }));
}

describe("participants section", () => {
  it("is in the menu and lists the project's participants with their consent state", async () => {
    open();
    renderAt("/participants");
    expect(await screen.findByText("P000001", {}, wait)).toBeInTheDocument();
    expect(screen.getByRole("navigation", { name: "Main" })).toHaveTextContent("Participants");
    const row = screen.getByText("P000001").closest("tr") as HTMLElement;
    expect(within(row).getByText("Agreed")).toBeInTheDocument();
    expect(within(row).getByText("Waiting for review")).toBeInTheDocument();
    expect(within(row).getByRole("button", { name: "Resend" })).toBeInTheDocument();
  });

  it("approves, and rejects only with a reason the participant will see", async () => {
    vi.stubGlobal("prompt", () => "Signature of the wrong person");
    const { calls } = open({
      "POST /api/v1/projects/p1/participants/a1/consent-review": () => [200, {}],
    });
    renderAt("/participants");
    const row = (await screen.findByText("P000001", {}, wait)).closest("tr") as HTMLElement;
    await userEvent.click(within(row).getByRole("button", { name: "Approve" }));
    expect(await screen.findByText("Consent of P000001 approved.")).toBeInTheDocument();
    await userEvent.click(
      within(screen.getByText("P000001").closest("tr") as HTMLElement).getByRole("button", {
        name: "Reject",
      }),
    );
    await waitFor(() =>
      expect(calls.filter((c) => c.path.endsWith("/consent-review")).map((c) => c.body)).toEqual([
        { decision: "APPROVED", note: "" },
        { decision: "REJECTED", note: "Signature of the wrong person" },
      ]),
    );
  });

  it("sends consent forms to the selected participants and names the ones that failed", async () => {
    const { calls } = open({
      "POST /api/v1/projects/p1/participants/bulk": () => [
        200,
        {
          results: [
            {
              participant_id: "a1",
              participant_code: "P000001",
              ok: true,
              message: "Consent form sent",
            },
            {
              participant_id: "b1",
              participant_code: "P000002",
              ok: false,
              message: "This participant has no email address",
            },
          ],
          done: 1,
          failed: 1,
        },
      ],
    });
    renderAt("/participants");
    await screen.findByText("P000001", {}, wait);
    await userEvent.click(screen.getByLabelText("Select all on this page"));
    const bar = screen.getByRole("group", { name: "Actions for selected participants" });
    expect(bar).toHaveTextContent("2 selected");
    await userEvent.click(within(bar).getByRole("button", { name: "Send consent form" }));
    expect(await screen.findByText("1 done, 1 not done.")).toBeInTheDocument();
    expect(screen.getByRole("list", { name: "Not done" })).toHaveTextContent(
      "P000002: This participant has no email address",
    );
    const sent = calls.find((c) => c.path.endsWith("/participants/bulk"))?.body as {
      action: string;
      participant_ids: string[];
    };
    expect(sent.action).toBe("send_consent");
    expect(sent.participant_ids).toHaveLength(2);
  });

  it("checks a pasted file before adding anyone", async () => {
    const { calls } = open({
      "POST /api/v1/projects/p1/participants/import": (body) => {
        const confirm = (body as { confirm: boolean }).confirm;
        return [
          200,
          {
            rows: [
              {
                line: 2,
                name: "Kiran",
                ok: true,
                message: confirm ? "Added" : "Ready to add",
                participant_code: confirm ? "P000010" : null,
              },
              { line: 3, name: "", ok: false, message: "Name is missing", participant_code: null },
            ],
            ready: 1,
            created: confirm ? 1 : 0,
          },
        ];
      },
    });
    renderAt("/participants");
    await screen.findByText("P000001", {}, wait);
    await userEvent.click(screen.getByRole("button", { name: "Add many" }));
    await userEvent.type(screen.getByLabelText("Participants (CSV)"), "name,language");
    expect(screen.getByRole("button", { name: "Add 0 participants" })).toBeDisabled();
    await userEvent.click(screen.getByRole("button", { name: "Check rows" }));
    expect(await screen.findByText("1 of 2 rows are ready.")).toBeInTheDocument();
    expect(screen.getByText("Name is missing")).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "Add 1 participants" }));
    expect(await screen.findByText("1 added.")).toBeInTheDocument();
    expect(
      calls
        .filter((c) => c.path.endsWith("/import"))
        .map((c) => (c.body as { confirm: boolean }).confirm),
    ).toEqual([false, true]);
  });

  it("opens one participant's consent form as they answered it", async () => {
    open({
      "GET /api/v1/projects/p1/participants/a1/consent-form": () => [
        200,
        {
          participant_code: "P000001",
          project_code: "HINDI",
          project_name: "Hindi conversations",
          form_text: "I agree that my voice is recorded.",
          form_version: "2",
          answered: true,
          current: {
            status: "GIVEN",
            answered_at: "2026-11-10T08:00:00Z",
            policy_version: "2",
            review_status: "REJECTED",
            review_note: "Wrong person",
            reviewed_at: "2026-11-10T09:00:00Z",
          },
          earlier: [
            {
              status: "REFUSED",
              answered_at: "2026-11-09T08:00:00Z",
              policy_version: "1",
              review_status: null,
              review_note: "",
              reviewed_at: null,
            },
          ],
        },
      ],
    });
    renderAt("/participants");
    const row = (await screen.findByText("P000001", {}, wait)).closest("tr") as HTMLElement;
    await userEvent.click(within(row).getByRole("button", { name: "View" }));
    const panel = await screen.findByRole("region", { name: "Consent form" });
    expect(
      await within(panel).findByText("I agree that my voice is recorded."),
    ).toBeInTheDocument();
    expect(panel).toHaveTextContent("Sent back: Wrong person");
    expect(panel).toHaveTextContent("Did not agree · version 1");
    expect(within(panel).getByRole("button", { name: "Download" })).toBeInTheDocument();
    await userEvent.click(within(panel).getByRole("button", { name: "Close" }));
    expect(screen.queryByRole("region", { name: "Consent form" })).toBeNull();
  });
});
