// Device details per speaker on the task page (D-147): the moderator fills both people's details
// and saves them together; "Same as last time" fills a person's last details only when clicked;
// from QC on they are read only; only the details the project asks are shown, none when it asks
// none; Send to QC waits for them and goes once they are saved. D-152: one matrix, a row per
// detail and a column per speaker.
// Requirements: TASK-002, TASK-004, FTF-014, PROJ-011
import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";

import { fakeApi, ME, renderAt, signedInAs, type Handler } from "../../test/fakeApi";
import { ALL_PERMISSIONS, DEVICE_DETAILS, TASK, worldHandlers } from "../../test/world";

afterEach(() => vi.unstubAllGlobals());

const MODERATOR = { ...ME, roles: ["MODERATOR"], permissions: ALL_PERMISSIONS };
const RECORDING = {
  id: "r1",
  task_id: "t1",
  state: "READY",
  current: true,
  saved_seconds: 120,
  assets: [{ id: "as1", kind: "FTF_DERIVED_PCM" }],
};
const SAMSUNG = {
  device_make: "Samsung",
  device_model: "Galaxy A14",
  bluetooth_earphones: false,
  wired_earphones: true,
  loudspeaker_on: false,
};
const [PARTY_A, PARTY_B] = DEVICE_DETAILS.participants as [
  (typeof DEVICE_DETAILS.participants)[number],
  (typeof DEVICE_DETAILS.participants)[number],
];

function open(task: Record<string, unknown>, extra: Record<string, Handler> = {}) {
  const api = fakeApi({
    ...signedInAs(ALL_PERMISSIONS, {
      ...worldHandlers(),
      "GET /api/v1/tasks/t1": () => [200, task],
      "GET /api/v1/tasks/t1/recordings": () => [200, [RECORDING]],
      "GET /api/v1/tasks/t1/audio-qc": () => [
        404,
        { error: { code: "NOT_FOUND", message: "Not found" } },
      ],
      ...extra,
    }),
    "GET /api/v1/auth/me": () => [200, MODERATOR],
  });
  renderAt("/tasks/t1");
  return api;
}

// D-152: one matrix, a row per detail and a column per speaker; each box and switch is named
// "<detail> – Participant <side>".
const box = (side: "A" | "B", label: string) =>
  screen.getByLabelText(`${label} – Participant ${side}`);
const yesNo = (side: "A" | "B", question: string) =>
  screen.getByRole("radiogroup", { name: `${question} – Participant ${side}` });
const answer = (side: "A" | "B", question: string, said: "Yes" | "No") =>
  userEvent.click(within(yesNo(side, question)).getByRole("radio", { name: said }));
const stillToFill = () => screen.getByRole("row", { name: /^Still to fill/ });

describe("device details on the task page (D-147)", () => {
  it("fills both speakers' details and saves them together", { timeout: 15000 }, async () => {
    let task = { ...TASK, status: "IN_PROGRESS", device_details_missing: ["P000001", "P000002"] };
    const api = open(task, {
      "GET /api/v1/tasks/t1": () => [200, task],
      "PUT /api/v1/tasks/t1/device-details": (body) => {
        task = { ...task, device_details_missing: [] };
        const sent = (body as { participants: Record<string, unknown>[] }).participants;
        return [
          200,
          {
            ...DEVICE_DETAILS,
            complete: true,
            participants: DEVICE_DETAILS.participants.map((p, i) => ({
              ...p,
              details: { ...sent[i], side: undefined },
              missing: [],
              filled_by: "Mona Moderator",
              filled_at: "2026-11-22T10:00:00Z",
            })),
          },
        ];
      },
    });
    const card = await screen.findByRole("region", { name: "Device details" });
    expect(await within(card).findByText(/Call type: Face-to-face/)).toBeInTheDocument();
    // Each speaker's column by code and, for people who may see it, name.
    expect(
      within(card).getByRole("columnheader", { name: "Participant A P000001 Asha" }),
    ).toBeInTheDocument();
    // What is still to fill, under each column.
    expect(stillToFill()).toHaveTextContent("Still to fill5 details5 details");
    expect(stillToFill().children[1]).toHaveAttribute(
      "title",
      "Device make, Device model, Bluetooth earphones used, Wired earphones used, Loudspeaker on",
    );
    const save = within(card).getByRole("button", { name: "Save device details" });
    expect(save).toBeDisabled(); // nothing changed yet

    await userEvent.type(box("A", "Device make"), "Samsung");
    await userEvent.type(box("A", "Device model"), "Galaxy A14");
    await answer("A", "Bluetooth earphones used", "No");
    await answer("A", "Wired earphones used", "Yes");
    await answer("A", "Loudspeaker on", "No");
    expect(stillToFill()).toHaveTextContent("Still to fillNothing5 details");
    await userEvent.type(box("B", "Device make"), "Nokia");
    await userEvent.type(box("B", "Device model"), "105");
    await answer("B", "Bluetooth earphones used", "No");
    await answer("B", "Wired earphones used", "No");
    await answer("B", "Loudspeaker on", "No");
    await userEvent.click(save);

    expect(await within(card).findByText("Device details saved.")).toBeInTheDocument();
    const puts = api.calls.filter((c) => c.method === "PUT");
    expect(puts).toHaveLength(1);
    expect(puts[0]?.body).toEqual({
      participants: [
        { side: "A", ...SAMSUNG },
        {
          side: "B",
          device_make: "Nokia",
          device_model: "105",
          bluetooth_earphones: false,
          wired_earphones: false,
          loudspeaker_on: false,
        },
      ],
    });
    // The task is loaded again, so its Send to QC follows what is still missing.
    await waitFor(() =>
      expect(
        api.calls.filter((c) => c.method === "GET" && c.path === "/api/v1/tasks/t1"),
      ).toHaveLength(2),
    );
  });

  it("offers Same as last time and fills nothing by itself", async () => {
    const api = open(
      { ...TASK, status: "IN_PROGRESS", device_details_missing: ["P000001", "P000002"] },
      {
        "GET /api/v1/tasks/t1/device-details": () => [
          200,
          {
            ...DEVICE_DETAILS,
            participants: [
              PARTY_A,
              {
                ...PARTY_B,
                last_time: { ...SAMSUNG, task_code: "T000007", filled_at: "2026-11-20T10:00:00Z" },
              },
            ],
          },
        ],
        "PUT /api/v1/tasks/t1/device-details": () => [200, DEVICE_DETAILS],
      },
    );
    await screen.findByLabelText("Device make – Participant B");
    // Only the person seen before has it, in their column's heading; their boxes stay empty
    // until it is clicked.
    expect(screen.getAllByRole("button", { name: /Same as last time/ })).toHaveLength(1);
    const make = box("B", "Device make");
    expect(make).toHaveValue("");
    await userEvent.click(
      screen.getByRole("button", { name: "Same as last time (T000007) – Participant B" }),
    );
    expect(make).toHaveValue("Samsung");
    expect(box("B", "Device model")).toHaveValue("Galaxy A14");
    expect(box("A", "Device make")).toHaveValue("");
    expect(
      within(yesNo("B", "Wired earphones used")).getByRole("radio", { name: "Yes" }),
    ).toBeChecked();
    expect(api.calls.filter((c) => c.method === "PUT")).toHaveLength(0);
    await userEvent.click(screen.getByRole("button", { name: "Save device details" }));
    await waitFor(() => expect(api.calls.filter((c) => c.method === "PUT")).toHaveLength(1));
    expect(api.calls.find((c) => c.method === "PUT")?.body).toEqual({
      participants: [
        { side: "A", ...PARTY_A.details },
        { side: "B", ...SAMSUNG },
      ],
    });
  });

  it("shows them read only once the task went to QC", async () => {
    open(
      { ...TASK, status: "AUDIO_QC", allowed_transitions: [] },
      {
        "GET /api/v1/tasks/t1/device-details": () => [
          200,
          {
            ...DEVICE_DETAILS,
            editable: false,
            participants: [
              {
                ...PARTY_A,
                details: SAMSUNG,
                missing: [],
                filled_by: "Mona Moderator",
                filled_at: "2026-11-22T10:00:00Z",
              },
              PARTY_B,
            ],
          },
        ],
      },
    );
    const card = await screen.findByRole("region", { name: "Device details" });
    await within(card).findByText("Galaxy A14");
    expect(within(card).queryByRole("textbox")).toBeNull();
    expect(within(card).queryByRole("radio")).toBeNull();
    expect(within(card).queryByRole("button", { name: "Save device details" })).toBeNull();
    // One matrix: a row per detail, a column per speaker.
    const rows = within(card)
      .getAllByRole("row")
      .map((row) => Array.from(row.children, (cell) => cell.textContent).join(" | "));
    expect(rows.slice(1, 6)).toEqual([
      "Device make | Samsung | Not answered",
      "Device model | Galaxy A14 | Not answered",
      "Bluetooth earphones used | No | Not answered",
      "Wired earphones used | Yes | Not answered",
      "Loudspeaker on | No | Not answered",
    ]);
    expect(within(card).getByText(/^Filled in by Mona Moderator/)).toBeInTheDocument();
    expect(within(card).getByText("Not filled in.")).toBeInTheDocument();
  });

  it("shows only the details the project asks", async () => {
    const asked = ["device_make", "loudspeaker_on"];
    const { calls } = open(
      { ...TASK, status: "IN_PROGRESS", device_fields: asked },
      {
        "GET /api/v1/tasks/t1/device-details": () => [
          200,
          {
            ...DEVICE_DETAILS,
            fields: asked,
            participants: DEVICE_DETAILS.participants.map((p) => ({ ...p, missing: asked })),
          },
        ],
      },
    );
    await screen.findByLabelText("Device make – Participant A");
    expect(screen.queryByLabelText("Device model – Participant A")).toBeNull();
    expect(yesNo("A", "Loudspeaker on")).toBeInTheDocument();
    expect(
      screen.queryByRole("radiogroup", { name: "Wired earphones used – Participant A" }),
    ).toBeNull();
    expect(calls.some((c) => c.path.endsWith("/device-details"))).toBe(true);
  });

  it("asks nothing where the project asks no device details", async () => {
    const { calls } = open({ ...TASK, status: "IN_PROGRESS", device_fields: [] });
    await screen.findByRole("heading", { name: "Ready to record" });
    expect(screen.queryByRole("region", { name: "Device details" })).toBeNull();
    expect(calls.some((c) => c.path.endsWith("/device-details"))).toBe(false);
  });

  it(
    "keeps Send to QC waiting until both speakers' details are saved",
    { timeout: 15000 },
    async () => {
      let task = {
        ...TASK,
        status: "RECORDED",
        allowed_transitions: ["AUDIO_QC", "IN_PROGRESS"],
        device_details_missing: ["P000002"],
      };
      const api = open(task, {
        "GET /api/v1/tasks/t1": () => [200, task],
        "GET /api/v1/tasks/t1/device-details": () => [
          200,
          {
            ...DEVICE_DETAILS,
            participants: [{ ...PARTY_A, details: SAMSUNG, missing: [] }, PARTY_B],
          },
        ],
        "PUT /api/v1/tasks/t1/device-details": () => {
          task = { ...task, device_details_missing: [] };
          return [200, { ...DEVICE_DETAILS, complete: true }];
        },
        "POST /api/v1/tasks/t1/transition": () => [
          200,
          { ...task, status: "AUDIO_QC", allowed_transitions: [] },
        ],
      });
      const send = await screen.findByRole("button", { name: "Send to QC" });
      expect(send).toBeDisabled();
      expect(send).toHaveAccessibleDescription(
        "Fill in the device details of P000002 first (Device details card).",
      );
      await screen.findByLabelText("Device make – Participant B");
      await userEvent.type(box("B", "Device make"), "Nokia");
      await userEvent.type(box("B", "Device model"), "105");
      for (const question of ["Bluetooth earphones used", "Wired earphones used", "Loudspeaker on"])
        await answer("B", question, "No");
      await userEvent.click(screen.getByRole("button", { name: "Save device details" }));
      await waitFor(() => expect(screen.getByRole("button", { name: "Send to QC" })).toBeEnabled());
      await userEvent.click(screen.getByRole("button", { name: "Send to QC" }));
      await waitFor(() =>
        expect(api.calls.find((c) => c.path.endsWith("/transition"))?.body).toEqual({
          to: "AUDIO_QC",
          reason_code: null,
          comment: "",
        }),
      );
    },
  );
});
