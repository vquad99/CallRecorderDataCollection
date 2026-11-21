// How a project's exports are laid out and named (D-149): the Rules tab's Export card with its
// preview, and the Export tab's note on the layout with what the client's format is missing.
// Requirements: EXP-001, EXP-002, EXP-006, PROJ-011
import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";

import { fakeApi, renderAt, signedInAs } from "../../test/fakeApi";
import { EXPORT_JOB, PROJECT } from "../../test/world";
import {
  audioNameProblem,
  CLIENT_AUDIO_NAME,
  conversationId,
  exampleAudioName,
  speakerId,
} from "./delivery";

const MANAGER = ["projects.view", "projects.manage", "exports.create"];

function rules(over: Record<string, unknown> = {}) {
  return fakeApi(
    signedInAs(MANAGER, {
      "GET /api/v1/projects/p1": () => [200, { ...PROJECT, ...over }],
      "PATCH /api/v1/projects/p1": (body) => [200, { ...PROJECT, ...(body as object) }],
    }),
  );
}

const card = () => screen.getByRole("region", { name: "Export" });
const patches = (calls: { method: string; body: unknown }[]) =>
  calls.filter((c) => c.method === "PATCH").map((c) => c.body as Record<string, unknown>);

/** Types a new audio file name ({ and } are typed as they are). */
async function rename(box: HTMLElement, text: string) {
  await userEvent.clear(box);
  await userEvent.click(box);
  await userEvent.paste(text);
}

describe("the names of the client's delivery format", () => {
  it("makes speaker and conversation IDs from the codes", () => {
    expect([speakerId("P000123", "NUMBER"), speakerId("P000007", "NUMBER")]).toEqual([
      "123",
      "007",
    ]);
    expect(speakerId("P1234567", "NUMBER")).toBe("1234567");
    expect(speakerId("P000123", "CODE")).toBe("P000123");
    expect(conversationId("T000045", "CON_NUMBER")).toBe("CON045");
    expect(conversationId("T001234", "CON_NUMBER")).toBe("CON1234");
    expect(conversationId("T000045", "CODE")).toBe("T000045");
    expect(exampleAudioName(CLIENT_AUDIO_NAME, "NUMBER", "CON_NUMBER")).toBe(
      "001_002_570001_576101_CON001.wav",
    );
  });

  it("says what is wrong with an audio file name", () => {
    expect(audioNameProblem(CLIENT_AUDIO_NAME)).toBeNull();
    expect(audioNameProblem(" {conversation}-{a} ")).toBeNull();
    expect(audioNameProblem("")).toMatch(/Write the audio file name/);
    expect(audioNameProblem("{a}_{b}")).toBe(
      "Include {conversation}, so that every name is unique.",
    );
    expect(audioNameProblem("{speaker}_{conversation}")).toMatch(/^\{speaker\} is not a token/);
    expect(audioNameProblem("{a} {conversation}")).toBe(
      "Between the tokens, use only letters, digits, _ and -.",
    );
    expect(audioNameProblem("{a}.{conversation}")).not.toBeNull();
    expect(audioNameProblem(`${"x".repeat(90)}_{conversation}`)).toBe("At most 100 characters.");
  });
});

describe("the Export card of the Rules tab", () => {
  it("starts with the client's format and saves the layout, the IDs and the audio name", async () => {
    const { calls } = rules();
    renderAt("/projects/p1/rules");
    const layout = await screen.findByRole("group", { name: "Layout of an export" });
    const client = within(layout).getByRole("radio", { name: "The client's delivery format" });
    expect(client).toBeChecked();
    expect(layout).toHaveAccessibleDescription(/MISSING\.csv lists what is not on file/);
    expect(within(card()).getByText("e.g. 001_002_570001_576101_CON001.wav")).toBeInTheDocument();
    const name = within(card()).getByRole("textbox", { name: "Audio file name" });
    expect(name).toHaveValue(CLIENT_AUDIO_NAME);
    expect(name).toHaveAccessibleDescription(/\{a_pin\} and \{b_pin\}: their native PIN codes/);

    // Codes instead of numbers: the preview follows.
    await userEvent.selectOptions(within(card()).getByLabelText("Speaker IDs"), "CODE");
    expect(
      within(card()).getByText("e.g. P000001_P000002_570001_576101_CON001.wav"),
    ).toBeInTheDocument();
    await userEvent.selectOptions(within(card()).getByLabelText("Conversation IDs"), "CODE");
    await rename(name, "{conversation}-{a}-{b}");
    expect(within(card()).getByText("e.g. T000001-P000001-P000002.wav")).toBeInTheDocument();
    await userEvent.click(within(layout).getByRole("radio", { name: "The platform's own layout" }));
    expect(layout).toHaveAccessibleDescription(/each recording's details file and consent record/);

    await userEvent.click(screen.getByRole("button", { name: "Save rules" }));
    expect(await screen.findByText("Rules saved.")).toBeInTheDocument();
    expect(patches(calls)[0]).toMatchObject({
      name: "Hindi conversations",
      export_layout: "PLATFORM",
      speaker_id_style: "CODE",
      conversation_id_style: "CODE",
      audio_name_pattern: "{conversation}-{a}-{b}",
      // The other rules go back as they are.
      target_speakers: 500,
      qc_checklist: PROJECT.qc_checklist,
    });
  });

  it("refuses an audio name without the conversation or with unknown tokens", async () => {
    const { calls } = rules({ audio_name_pattern: "{conversation}" });
    renderAt("/projects/p1/rules");
    const name = await screen.findByRole("textbox", { name: "Audio file name" });
    await rename(name, "{a}_{b}");
    expect(name).toHaveAccessibleDescription(
      /Include \{conversation\}, so that every name is unique/,
    );
    expect(within(card()).queryByText(/^e\.g\./)).toBeNull();
    expect(screen.getByRole("button", { name: "Save rules" })).toBeDisabled();
    await rename(name, "{a}_{pin}_{conversation}");
    expect(name).toHaveAccessibleDescription(/\{pin\} is not a token/);
    await rename(name, "{a} {conversation}");
    expect(name).toHaveAccessibleDescription(/use only letters, digits, _ and -/);
    // Back to the client's format in one click.
    await userEvent.click(
      within(card()).getByRole("button", { name: "Reset to the client's format" }),
    );
    expect(name).toHaveValue(CLIENT_AUDIO_NAME);
    expect(within(card()).getByText("e.g. 001_002_570001_576101_CON001.wav")).toBeInTheDocument();
    await waitFor(() => expect(screen.getByRole("button", { name: "Save rules" })).toBeEnabled());
    expect(patches(calls)).toHaveLength(0);
  });

  it("is read only in an archived project", async () => {
    rules({ status: "ARCHIVED" });
    renderAt("/projects/p1/rules");
    const layout = await screen.findByRole("group", { name: "Layout of an export" });
    expect(
      within(layout).getByRole("radio", { name: "The client's delivery format" }),
    ).toBeDisabled();
    expect(within(card()).getByRole("textbox", { name: "Audio file name" })).toBeDisabled();
  });
});

describe("the Export tab's layout", () => {
  function exportTab(over: Record<string, unknown>, summary: Record<string, unknown>) {
    return fakeApi(
      signedInAs(MANAGER, {
        "GET /api/v1/projects/p1": () => [200, { ...PROJECT, ...over }],
        "GET /api/v1/projects/p1/export/summary": () => [
          200,
          {
            recordings: 2,
            face_to_face: 1,
            telephony: 1,
            audio_bytes: 2_000_000,
            file_name: "both_HINDI_20261122_0900.zip",
            ...summary,
          },
        ],
        "GET /api/v1/projects/p1/exports": () => [
          200,
          {
            items: [
              {
                ...EXPORT_JOB,
                filters: { ...EXPORT_JOB.filters, layout: over.export_layout ?? "CLIENT" },
                missing: summary.missing ?? 0,
              },
            ],
            total: 1,
            page: 1,
            page_size: 20,
          },
        ],
      }),
    );
  }

  it("says the client's format is used, links to the Rules tab and counts what is missing", async () => {
    exportTab({ speaker_id_style: "CODE" }, { layout: "CLIENT", missing: 3 });
    renderAt("/projects/p1/export");
    const note = await screen.findByText(/client's delivery format/);
    const paragraph = note.closest("p") as HTMLElement;
    expect(paragraph).toHaveTextContent("P000001_P000002_570001_576101_CON001.wav");
    expect(paragraph).toHaveTextContent(/MISSING\.csv listing what is not on file/);
    expect(
      within(paragraph).getByRole("link", { name: "Change it on the Rules tab" }),
    ).toHaveAttribute("href", "/projects/p1/rules");
    expect(
      await screen.findByText("3 items missing", { selector: ".export__summary span" }),
    ).toBeVisible();
    // The prepared export says it too, and in which layout it was made.
    const list = await screen.findByRole("table", { name: "Prepared exports" });
    expect(within(list).getByText("3 items missing")).toBeInTheDocument();
    expect(list).toHaveTextContent("Client's format · Audio + metadata · approved tasks · CSV");
  });

  it("says when nothing is missing", async () => {
    exportTab({}, { layout: "CLIENT", missing: 0 });
    renderAt("/projects/p1/export");
    expect(await screen.findByText("Nothing missing")).toBeInTheDocument();
  });

  it("names the platform's own layout", async () => {
    exportTab({ export_layout: "PLATFORM" }, { layout: "PLATFORM", missing: 0 });
    renderAt("/projects/p1/export");
    const note = await screen.findByText(/platform's own layout/);
    expect(note.closest("p")).toHaveTextContent(/details file and consent record/);
    expect(await screen.findByText("2 recordings")).toBeInTheDocument();
    expect(screen.queryByText(/missing/i)).toBeNull();
    const list = await screen.findByRole("table", { name: "Prepared exports" });
    expect(list).not.toHaveTextContent("Client's format");
  });
});
