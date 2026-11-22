// The project's audio, progress and target settings on the Rules tab (D-148): the long-pause
// limit, the listen and what completed minutes count; the hours, speakers, conversations, age
// bands, gender and district targets, with what is wrong said in words before anything is sent.
// Requirements: PROJ-001, PROJ-011
import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";

import { fakeApi, renderAt, signedInAs } from "../../test/fakeApi";
import { PROJECT } from "../../test/world";
import { CLIENT_DISTRICTS } from "./targets";

const MANAGER = ["projects.view", "projects.manage"];

function rules(over: Record<string, unknown> = {}) {
  return fakeApi(
    signedInAs(MANAGER, {
      "GET /api/v1/projects/p1": () => [200, { ...PROJECT, ...over }],
      "PATCH /api/v1/projects/p1": (body) => [200, { ...PROJECT, ...(body as object) }],
    }),
  );
}

const card = (name: string) => screen.getByRole("region", { name });
const patches = (calls: { method: string; body: unknown }[]) =>
  calls.filter((c) => c.method === "PATCH").map((c) => c.body as Record<string, unknown>);

describe("audio and progress rules", () => {
  it("shows the defaults and saves the pause limit, the listen and what counts", async () => {
    const { calls } = rules();
    renderAt("/projects/p1/rules/audio-progress");
    const limit = await screen.findByRole("spinbutton", { name: "Long pause (seconds)" });
    const audio = card("Audio and progress");
    expect(limit).toHaveValue(3);
    const listen = within(audio).getByRole("checkbox", { name: "Long pauses need a listen" });
    expect(listen).not.toBeChecked();
    const counts = within(audio).getByRole("group", { name: "Completed minutes count" });
    expect(within(counts).getByRole("radio", { name: /^Effective speech/ })).toBeChecked();
    expect(counts).toHaveAccessibleDescription(/Payments always count the full length/);

    await userEvent.clear(limit);
    await userEvent.type(limit, "5");
    await userEvent.click(listen);
    await userEvent.click(within(counts).getByRole("radio", { name: /^Full length/ }));
    await userEvent.click(screen.getByRole("button", { name: "Save rules" }));
    expect(await screen.findByText("Rules saved.")).toBeInTheDocument();
    expect(patches(calls)[0]).toMatchObject({
      name: "Hindi conversations",
      pause_limit_seconds: 5,
      long_pauses_need_review: true,
      progress_counts: "FULL",
      // The targets go back as they are.
      target_speakers: 500,
      target_conversations: 600,
      target_age_bands: PROJECT.target_age_bands,
      target_gender: { MALE: 50, FEMALE: 50 },
      target_modes: { FACE_TO_FACE: 50, TELEPHONY: 50 },
      target_districts: [],
      target_hours: null,
    });
  });

  it("refuses a pause limit outside 1 to 30 seconds", async () => {
    const { calls } = rules();
    renderAt("/projects/p1/rules/audio-progress");
    const limit = await screen.findByRole("spinbutton", { name: "Long pause (seconds)" });
    await userEvent.clear(limit);
    await userEvent.type(limit, "31");
    expect(limit).toHaveAccessibleDescription(/Type a whole number of seconds from 1 to 30/);
    expect(screen.getByRole("button", { name: "Save rules" })).toBeDisabled();
    expect(patches(calls)).toHaveLength(0);
  });
});

describe("targets", () => {
  it("edits every target and saves them with the rules", async () => {
    const { calls } = rules();
    renderAt("/projects/p1/rules/targets");
    const hours = await screen.findByRole("spinbutton", { name: "Hours completed" });
    const targets = card("Targets");
    expect(hours).toHaveAccessibleDescription(/counted as effective speech/);
    const speakers = within(targets).getByRole("spinbutton", { name: "Speakers" });
    expect(speakers).toHaveValue(500);
    expect(within(targets).getByRole("spinbutton", { name: "Conversations" })).toHaveValue(600);
    // The four default age bands.
    expect(within(targets).getAllByRole("spinbutton", { name: "Percent" })).toHaveLength(4);
    expect(
      within(targets)
        .getAllByRole("spinbutton", { name: "From age" })
        .map((b) => (b as HTMLInputElement).value),
    ).toEqual(["20", "30", "40", "50"]);

    await userEvent.type(hours, "1000");
    await userEvent.clear(speakers);
    // A band removed: the percents no longer add up, and nothing can be saved until they do.
    await userEvent.click(within(targets).getByRole("button", { name: "Remove age band 50-60" }));
    expect(within(targets).getByText("The percents add up to 90, not 100.")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Save rules" })).toBeDisabled();
    const percents = within(targets).getAllByRole("spinbutton", { name: "Percent" });
    await userEvent.clear(percents[0] as HTMLElement);
    await userEvent.type(percents[0] as HTMLElement, "50");
    // Gender 60/40; no target for face-to-face and phone.
    const male = within(targets).getByRole("spinbutton", { name: "Male (%)" });
    const female = within(targets).getByRole("spinbutton", { name: "Female (%)" });
    await userEvent.clear(male);
    await userEvent.type(male, "60");
    await userEvent.clear(female);
    await userEvent.type(female, "40");
    await userEvent.clear(within(targets).getByRole("spinbutton", { name: "Face-to-face (%)" }));
    await userEvent.clear(within(targets).getByRole("spinbutton", { name: "Phone call (%)" }));
    // The eight Konkani-region districts, then one removed.
    expect(
      within(targets).getByText(/the Progress page shows the speakers' own districts/),
    ).toBeInTheDocument();
    await userEvent.click(
      within(targets).getByRole("button", { name: "Use the Konkani-region districts" }),
    );
    expect(within(targets).getAllByRole("textbox", { name: "District" })).toHaveLength(8);
    expect(within(targets).getByText(/12\.5% each for 8/)).toBeInTheDocument();
    await userEvent.click(within(targets).getByRole("button", { name: "Remove Raigad" }));
    await userEvent.click(screen.getByRole("button", { name: "Save rules" }));
    expect(await screen.findByText("Rules saved.")).toBeInTheDocument();
    expect(patches(calls)[0]).toMatchObject({
      target_hours: "1000",
      target_speakers: null,
      target_conversations: 600,
      target_age_bands: [
        { from: 20, to: 30, percent: 50 },
        { from: 30, to: 40, percent: 30 },
        { from: 40, to: 50, percent: 20 },
      ],
      target_gender: { MALE: 60, FEMALE: 40 },
      target_modes: {},
      target_districts: CLIENT_DISTRICTS.slice(0, 7),
    });
  });

  it("says what is wrong with the shares and the districts", async () => {
    const { calls } = rules({ target_districts: [{ state: "Goa", district: "North Goa" }] });
    renderAt("/projects/p1/rules/targets");
    const targets = await screen.findByRole("region", { name: "Targets" });
    const male = within(targets).getByRole("spinbutton", { name: "Male (%)" });
    await userEvent.clear(male);
    expect(
      within(targets).getByText("Give both percents, or leave both empty for no target."),
    ).toBeInTheDocument();
    await userEvent.type(male, "70");
    expect(within(targets).getByText("The percents add up to 120, not 100.")).toBeInTheDocument();
    await userEvent.clear(male);
    await userEvent.type(male, "50");
    await userEvent.click(within(targets).getByRole("button", { name: "Add district" }));
    expect(
      within(targets).getByText("District 2: choose the state and type the district."),
    ).toBeInTheDocument();
    const states = within(targets).getAllByRole("combobox", { name: "State" });
    await userEvent.selectOptions(states[1] as HTMLElement, "Goa");
    await userEvent.type(
      within(targets).getAllByRole("textbox", { name: "District" })[1] as HTMLElement,
      "north  goa",
    );
    expect(within(targets).getByText("District 2: north goa is listed twice.")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Save rules" })).toBeDisabled();
    // Overlapping bands.
    await userEvent.click(within(targets).getByRole("button", { name: "Remove north goa" }));
    const to = within(targets).getAllByRole("spinbutton", { name: "To age" });
    await userEvent.clear(to[0] as HTMLElement);
    await userEvent.type(to[0] as HTMLElement, "35");
    expect(within(targets).getByText("Age bands 20-35 and 30-40 overlap.")).toBeInTheDocument();
    await userEvent.click(
      within(targets).getByRole("button", { name: "Reset to the default age bands" }),
    );
    await waitFor(() => expect(screen.getByRole("button", { name: "Save rules" })).toBeEnabled());
    expect(patches(calls)).toHaveLength(0);
  });

  it("refuses 0 hours: no target is an empty box (PROJ-12)", async () => {
    const { calls } = rules();
    renderAt("/projects/p1/rules/targets");
    const hours = await screen.findByRole("spinbutton", { name: "Hours completed" });
    const save = screen.getByRole("button", { name: "Save rules" });
    for (const typed of ["0", "0.00", "1.234"]) {
      await userEvent.clear(hours);
      await userEvent.type(hours, typed);
      expect(hours).toHaveAccessibleDescription(
        /Type hours above 0 with at most two decimals, or leave it empty\./,
      );
      expect(save).toBeDisabled();
    }
    await userEvent.clear(hours);
    await userEvent.type(hours, "0.5");
    expect(save).toBeEnabled();
    await userEvent.click(save);
    expect(await screen.findByText("Rules saved.")).toBeInTheDocument();
    expect(patches(calls)[0]).toMatchObject({ target_hours: "0.5" });
  });

  it("keeps the targets read only in an archived project", async () => {
    rules({ status: "ARCHIVED" });
    renderAt("/projects/p1/rules/targets");
    const targets = await screen.findByRole("region", { name: "Targets" });
    expect(within(targets).getByRole("spinbutton", { name: "Speakers" })).toBeDisabled();
    expect(
      within(targets).getByRole("button", { name: "Use the Konkani-region districts" }),
    ).toBeDisabled();
    await userEvent.click(
      within(screen.getByRole("navigation", { name: "Project sections" })).getByRole("link", {
        name: "Audio and progress",
      }),
    );
    expect(
      within(await screen.findByRole("region", { name: "Audio and progress" })).getByRole(
        "spinbutton",
        { name: "Long pause (seconds)" },
      ),
    ).toBeDisabled();
  });
});
