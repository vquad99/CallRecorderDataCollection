// Requirements: PART-001, PART-008, PART-009, PART-012
import { screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";

import { fakeApi, renderAt, signedInAs } from "../../test/fakeApi";

afterEach(() => vi.unstubAllGlobals());

const project = {
  id: "p1",
  code: "VOICE",
  name: "Voice",
  status: "ACTIVE",
  allows_telephony: true,
  allows_face_to_face: true,
  target_telephony_hours_per_day: "0.00",
  target_face_to_face_hours_per_day: "0.00",
  created_at: "",
  description: "",
  phone_visibility_policy: "ADMINS_ONLY",
  consent_policy_version: "1",
  consent_text: "",
  status_reason: null,
  status_changed_at: null,
  languages: [],
  audio_rules: [],
  retention_rules: [],
  accepts_new_work: true,
};
const asha = {
  id: "a1",
  participant_code: "P000001",
  language_code: "hi",
  dialect: "",
  display_label: "Asha",
  phone: "+919876543210",
  has_phone: true,
  consent_visible: true,
  notes: "",
  deleted: false,
  created_at: "",
};
const hidden = {
  ...asha,
  id: "b1",
  participant_code: "P000002",
  display_label: null,
  phone: null,
  consent_visible: false,
};

describe("participants tab", () => {
  it("shows hidden fields as hidden and offers no editing without manage rights", async () => {
    fakeApi(
      // consent.view is held, but the server says this person's consent is not this user's to see.
      signedInAs(["projects.view", "participants.view", "consent.view"], {
        "GET /api/v1/projects/p1": () => [200, project],
        "GET /api/v1/projects/p1/participants": () => [
          200,
          { items: [hidden], total: 1, page: 1, page_size: 25 },
        ],
      }),
    );
    renderAt("/projects/p1/participants");
    expect(await screen.findByText("P000002")).toBeInTheDocument();
    expect(screen.getAllByText("Hidden")).toHaveLength(2);
    expect(screen.queryByRole("button", { name: "Add participant" })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Export contacts" })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Consent" })).not.toBeInTheDocument();
  });

  it("shows recorded, approved and payable minutes when the server sends them (D-095)", async () => {
    const minutes = {
      conversations: 2,
      recorded_minutes: 9,
      approved_conversations: 1,
      approved_minutes: 5,
      payable_minutes: 2.5,
    };
    fakeApi(
      signedInAs(["projects.view", "participants.view"], {
        "GET /api/v1/projects/p1": () => [200, project],
        "GET /api/v1/projects/p1/participants": () => [
          200,
          { items: [{ ...asha, minutes }], total: 1, page: 1, page_size: 25 },
        ],
      }),
    );
    renderAt("/projects/p1/participants");
    expect(await screen.findByRole("columnheader", { name: /Payable min/ })).toBeInTheDocument();
    const row = screen.getByRole("row", { name: /P000001/ });
    expect(row).toHaveTextContent("9");
    expect(row).toHaveTextContent("5");
    expect(row).toHaveTextContent("2.5");
  });

  it("adds a participant and deletes one with a reason", async () => {
    const { calls } = fakeApi(
      signedInAs(["projects.view", "participants.view", "participants.manage"], {
        "GET /api/v1/projects/p1": () => [200, project],
        "GET /api/v1/projects/p1/participants": () => [
          200,
          { items: [asha], total: 1, page: 1, page_size: 25 },
        ],
        "POST /api/v1/projects/p1/participants": () => [
          201,
          { ...asha, id: "c1", participant_code: "P000003" },
        ],
        "POST /api/v1/projects/p1/participants/a1/delete": () => [200, { ...asha, deleted: true }],
      }),
    );
    renderAt("/projects/p1/participants");
    await userEvent.click(await screen.findByRole("button", { name: "Add participant" }));
    await userEvent.type(screen.getByLabelText(/Name or label/), "Chitra");
    await userEvent.selectOptions(screen.getByLabelText(/Language code/), "hi");
    await userEvent.click(screen.getByRole("button", { name: "Add participant" }));
    expect(await screen.findByText("P000003 added.")).toBeInTheDocument();
    expect(calls.find((c) => c.method === "POST")?.body).toEqual({
      display_label: "Chitra",
      phone: null,
      language_code: "hi",
      dialect: "",
      notes: "",
    });

    vi.spyOn(window, "prompt").mockReturnValue("Asked to be removed");
    await userEvent.click(screen.getByRole("button", { name: "Delete" }));
    expect(await screen.findByText("P000001 deleted.")).toBeInTheDocument();
    expect(calls.find((c) => c.path.endsWith("/delete"))?.body).toEqual({
      reason: "Asked to be removed",
    });
  });

  it("takes a 10-digit phone number with the country code chosen from a list", async () => {
    const { calls } = fakeApi(
      signedInAs(["projects.view", "participants.view", "participants.manage"], {
        "GET /api/v1/projects/p1": () => [200, project],
        "GET /api/v1/projects/p1/participants": () => [
          200,
          { items: [asha], total: 1, page: 1, page_size: 25 },
        ],
        "POST /api/v1/projects/p1/participants": () => [
          201,
          { ...asha, id: "c1", participant_code: "P000003" },
        ],
      }),
    );
    renderAt("/projects/p1/participants");
    await userEvent.click(await screen.findByRole("button", { name: "Add participant" }));
    await userEvent.type(screen.getByLabelText(/Name or label/), "Chitra");
    await userEvent.selectOptions(screen.getByLabelText(/Language code/), "ta");
    await userEvent.type(screen.getByLabelText(/Phone number/), "98765-4");
    expect(screen.getByText("Type exactly 10 digits (you typed 6).")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Add participant" })).toBeDisabled();
    await userEvent.type(screen.getByLabelText(/Phone number/), "32109");
    await userEvent.selectOptions(screen.getByLabelText("Country code"), "+44");
    await userEvent.click(screen.getByRole("button", { name: "Add participant" }));
    expect(await screen.findByText("P000003 added.")).toBeInTheDocument();
    expect(calls.find((c) => c.method === "POST")?.body).toMatchObject({
      phone: "+449876543210",
      language_code: "ta",
    });
  });

  it("adds an existing participant from another project (D-090)", async () => {
    const quinn = {
      id: "q1",
      participant_code: "P000009",
      display_label: "Quinn",
      language_code: "hi",
      dialect: "Awadhi",
    };
    const { calls } = fakeApi(
      signedInAs(["projects.view", "participants.view", "participants.manage"], {
        "GET /api/v1/projects/p1": () => [200, project],
        "GET /api/v1/projects/p1/participants": () => [
          200,
          { items: [asha], total: 1, page: 1, page_size: 25 },
        ],
        "GET /api/v1/projects/p1/participants/link-candidates": () => [200, [quinn]],
        "POST /api/v1/projects/p1/participants/link": () => [
          201,
          { ...asha, id: "q1", participant_code: "P000009" },
        ],
      }),
    );
    renderAt("/projects/p1/participants");
    await userEvent.click(await screen.findByRole("button", { name: "Add existing participant" }));
    expect(await screen.findByText("Quinn")).toBeInTheDocument();
    expect(screen.getByText("Hindi (hi) · Awadhi")).toBeInTheDocument();
    expect(screen.getByText("1 person")).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "Add P000009" }));
    expect(await screen.findByText("P000009 added to this project.")).toBeInTheDocument();
    expect(calls.find((c) => c.path.endsWith("/link"))?.body).toEqual({
      participant_code: "P000009",
    });
  });
});
