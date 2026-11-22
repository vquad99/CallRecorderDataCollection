// The project's audio, progress and target settings on the Rules tab, and the Progress tab
// (D-148, plain tables in D-153): completed minutes, conversations and speakers against the
// targets, what is still needed (D-153), and the shares with their variance in one balance table.
// Requirements: DASH-001, PROJ-001, PROJ-011
import { cleanup, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";

import { fakeApi, renderAt, signedInAs } from "../../test/fakeApi";
import { PROGRESS, PROJECT } from "../../test/world";
import { capacityText, variance } from "./ProgressTab";
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
  it("shows the client's defaults and saves the pause limit, the listen and what counts", async () => {
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
    // The client's four age bands.
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
    // The client's eight districts, then one removed.
    expect(
      within(targets).getByText(/the Progress page shows the speakers' own districts/),
    ).toBeInTheDocument();
    await userEvent.click(
      within(targets).getByRole("button", { name: "Use the client's Konkani districts" }),
    );
    expect(within(targets).getAllByRole("textbox", { name: "District" })).toHaveLength(8);
    expect(within(targets).getByText(/12\.5 % each for 8/)).toBeInTheDocument();
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
      within(targets).getByRole("button", { name: "Reset to the client's age bands" }),
    );
    await waitFor(() => expect(screen.getByRole("button", { name: "Save rules" })).toBeEnabled());
    expect(patches(calls)).toHaveLength(0);
  });

  it("keeps the targets read only in an archived project", async () => {
    rules({ status: "ARCHIVED" });
    renderAt("/projects/p1/rules/targets");
    const targets = await screen.findByRole("region", { name: "Targets" });
    expect(within(targets).getByRole("spinbutton", { name: "Speakers" })).toBeDisabled();
    expect(
      within(targets).getByRole("button", { name: "Use the client's Konkani districts" }),
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

describe("the Progress tab", () => {
  function progress(body: unknown = PROGRESS, permissions = MANAGER, project: unknown = PROJECT) {
    return fakeApi(
      signedInAs(permissions, {
        "GET /api/v1/projects/p1": () => [200, project],
        "GET /api/v1/projects/p1/progress": () => [200, body],
      }),
    );
  }

  /** A table row's cells, as text. */
  const cells = (row: Element | null) =>
    Array.from((row as HTMLTableRowElement | null)?.cells ?? []).map((c) => c.textContent);
  /** The row of a table (or of one of its sections) named by its first cell. */
  const line = (table: HTMLElement, label: string) =>
    cells(within(table).getByRole("rowheader", { name: label }).closest("tr"));
  /** The cells of a row of the "Still needed" matrix, each read as "still needed | its parts". */
  const needRow = (table: HTMLElement, label: string) =>
    Array.from(
      within(table).getByRole("rowheader", { name: label }).closest("tr")?.querySelectorAll("td") ??
        [],
    ).map(
      (td) =>
        `${td.querySelector(".need")?.textContent} | ${Array.from(
          td.querySelectorAll(".need__part"),
          (part) => part.textContent,
        ).join(" · ")}`,
    );
  /** One key figure of the line at the top. */
  const figure = (label: string) =>
    within(screen.getByRole("group", { name: "Against the targets" }))
      .getByText(label)
      .closest(".figline__item") as HTMLElement;

  it("comes right after the overview, for the people who manage the project", async () => {
    progress();
    renderAt("/projects/p1");
    const tabs = await screen.findByRole("navigation", { name: "Project sections" });
    expect(
      within(tabs)
        .getAllByRole("link")
        .map((l) => l.textContent)
        .slice(0, 3),
    ).toEqual(["Overview", "Progress", "Team"]);
    await userEvent.click(within(tabs).getByRole("link", { name: "Progress" }));
    expect(await screen.findByRole("region", { name: "Still needed" })).toBeInTheDocument();
  });

  it("shows no Progress tab to others and answers No access at its address", async () => {
    progress(PROGRESS, ["projects.view"]);
    renderAt("/projects/p1/progress");
    expect(await screen.findByText("No access")).toBeInTheDocument();
    expect(screen.queryByRole("navigation", { name: "Project sections" })).toBeNull();
  });

  it("shows the key figures in one line and the rest as plain tables (D-153)", async () => {
    progress();
    renderAt("/projects/p1/progress");
    const done = await screen.findByRole("region", { name: "Completed" });
    expect(figure("Completed")).toHaveTextContent("11 min of 1 h");
    expect(figure("Completed")).toHaveTextContent("18.3 % of the target, effective speech");
    expect(figure("Approved conversations")).toHaveTextContent("3 / 600");
    expect(figure("Approved conversations")).toHaveTextContent("0.5 % of the target");
    expect(figure("Speakers")).toHaveTextContent("5 / 5001 % of the target");
    expect(figure("Registered")).toHaveTextContent("6");
    expect(figure("Registered")).toHaveTextContent("4 at the limit of 2 conversations");
    expect(figure("Effective speech")).toHaveTextContent("71.9 %of the recorded audio");
    // No boxes of figures: no progress bars, no tiles.
    expect(screen.queryByRole("progressbar")).toBeNull();
    // Completed: approved, and recorded but not yet approved, in one table.
    const table = within(done).getByRole("table", { name: "Completed" });
    expect(line(table, "Approved")).toEqual(["Approved", "3", "17 min", "11 min"]);
    expect(line(table, "Recorded, not yet approved")).toEqual([
      "Recorded, not yet approved",
      "1",
      "1 min",
      "30 s",
    ]);
    expect(done).toHaveTextContent(
      /1 approved conversation is not measured yet: each counts as none until it is/,
    );
    // The conversations by status: one plain table, the empty stages left out.
    const statuses = screen.getByRole("table", { name: "Conversations by status" });
    expect(line(statuses, "Approved")).toEqual(["Approved", "3", "43%"]);
    expect(line(statuses, "Rejected")).toEqual(["Rejected", "1", "14%"]);
    expect(within(statuses).queryByRole("rowheader", { name: "Not started" })).toBeNull();
  });

  it("shows what is still needed: speakers by age band and gender, districts, conversations", async () => {
    progress();
    renderAt("/projects/p1/progress");
    const needed = await screen.findByRole("region", { name: "Still needed" });
    expect(needed).toHaveTextContent(
      "To reach the targets: 495 more speakers and 595 more conversations. Even if every one of " +
        "the 6 registered speakers records 2 conversations, 594 more speakers are needed for the " +
        "595 conversations still to make.",
    );
    const matrix = within(needed).getByRole("table", {
      name: "Speakers still needed by age band and gender",
    });
    expect(
      within(matrix)
        .getAllByRole("columnheader")
        .map((h) => h.textContent),
    ).toEqual(["Age band", "Male", "Female", "Total"]);
    // Each cell: still needed in bold, then the target, done and registered.
    expect(needRow(matrix, "20-30")).toEqual([
      "100 | target 100 · done 0 · registered 0",
      "98 | target 100 · done 2 · registered 0",
      "198 | target 200 · done 2 · registered 0",
    ]);
    expect(needRow(matrix, "30-40")[0]).toBe("73 | target 75 · done 1 · registered 1");
    expect(needRow(matrix, "Total")).toEqual([
      "247 | target 250 · done 2 · registered 1",
      "248 | target 250 · done 2 · registered 0",
      "495 | target 500 · done 5 · registered 1",
    ]);
    expect(within(matrix).getByText("98")).toHaveClass("need");
    expect(within(matrix).getByText("98").closest("td")?.getAttribute("title")).toBe(
      "20-30, female: 98 still needed, target 100, done 2, registered 0",
    );
    // Districts: an equal share each; people from other districts have no target.
    const districts = within(needed).getByRole("table", {
      name: "Speakers still needed by native district",
    });
    expect(line(districts, "North Goa (Goa)")).toEqual(["North Goa (Goa)", "63", "2", "1", "60"]);
    expect(line(districts, "Other districts")).toEqual(["Other districts", "–", "1", "0", "–"]);
    expect(line(districts, "Total")).toEqual(["Total", "126", "4", "1", "122"]);
    // Conversations, by type too in a project that records both (made before D-153).
    const talks = within(needed).getByRole("table", { name: "Conversations still to make" });
    expect(line(talks, "All conversations")).toEqual(["All conversations", "600", "3", "2", "595"]);
    expect(line(talks, "Phone call")).toEqual(["Phone call", "300", "1", "1", "298"]);
  });

  it("leaves out the split by type in a project that records one (D-153)", async () => {
    const one = {
      ...PROGRESS,
      recording_mode: "FACE_TO_FACE",
      modes: null,
      still_needed: {
        ...PROGRESS.still_needed,
        conversations: PROGRESS.still_needed.conversations.slice(0, 1),
      },
    };
    progress(one, MANAGER, { ...PROJECT, allows_telephony: false });
    renderAt("/projects/p1/progress");
    const balance = await screen.findByRole("table", { name: "Balance against the targets" });
    expect(within(balance).queryByRole("rowgroup", { name: "Face-to-face and phone" })).toBeNull();
    expect(within(balance).getByRole("rowgroup", { name: "Gender" })).toBeInTheDocument();
    const talks = screen.getByRole("table", { name: "Conversations still to make" });
    expect(
      within(talks)
        .getAllByRole("rowheader")
        .map((r) => r.textContent),
    ).toEqual(["All conversations"]);
    expect(screen.getByText("How these are counted").closest("details")).not.toHaveTextContent(
      "Face-to-face and phone are shares",
    );
  });

  it("says what is missing when there are no targets to share out", async () => {
    const all = { target: null, done: 5, registered: 1, still_needed: null };
    const none = {
      ...PROGRESS,
      still_needed: {
        speakers: {
          target: null,
          by_age: false,
          by_gender: false,
          rows: [{ key: "ALL", label: "All ages", male: all, female: all, total: all }],
          total: { key: "TOTAL", label: "Total", male: all, female: all, total: all },
        },
        districts: { has_target: false, rows: [], total: null },
        conversations: [
          {
            key: "ALL",
            label: "All conversations",
            target: null,
            approved: 3,
            in_pipeline: 2,
            still_to_make: null,
          },
        ],
        capacity: {
          limit: null,
          registered: 6,
          places_left: null,
          conversations_to_make: null,
          more_speakers_needed: null,
        },
      },
    };
    progress(none);
    renderAt("/projects/p1/progress");
    const needed = await screen.findByRole("region", { name: "Still needed" });
    expect(needed).toHaveTextContent(
      "No speakers or conversations target: set them on the Rules tab (Targets).",
    );
    expect(needed).toHaveTextContent("No speakers target: the table shows who there is.");
    const matrix = within(needed).getByRole("table", {
      name: "Speakers still needed by age band and gender",
    });
    expect(needRow(matrix, "All ages")[2]).toBe("– | done 5 · registered 1");
    expect(within(matrix).queryByRole("rowheader", { name: "Total" })).toBeNull();
    expect(needed).toHaveTextContent(
      "No districts listed: list them on the Rules tab (Targets) to see who is needed by district.",
    );
  });

  it("writes whether the registered speakers can give the conversations still to make", () => {
    const base = {
      limit: 3,
      registered: 200,
      places_left: 600,
      conversations_to_make: 300,
      more_speakers_needed: 0,
    };
    expect(capacityText(base)).toBe(
      "The 200 registered speakers can give the 300 conversations still to make (each at most 3 conversations).",
    );
    expect(capacityText({ ...base, places_left: 480, more_speakers_needed: 40 })).toBe(
      "Even if every one of the 200 registered speakers records 3 conversations, 40 more speakers are needed for the 300 conversations still to make.",
    );
    expect(capacityText({ ...base, conversations_to_make: 0 })).toBe(
      "No more conversations are needed beyond the open tasks.",
    );
    expect(capacityText({ ...base, limit: null })).toBe(
      "No limit on conversations per speaker: the 200 registered speakers can give the 300 conversations still to make.",
    );
    expect(capacityText({ ...base, conversations_to_make: null })).toBeNull();
  });

  it("shows every share in one balance table, people without a detail as Not given", async () => {
    progress();
    renderAt("/projects/p1/progress");
    const balance = await screen.findByRole("table", { name: "Balance against the targets" });
    // Actual (count, percent, bar) and target (percent, variance) as column groups.
    expect(within(balance).getByRole("columnheader", { name: "Actual" })).toHaveAttribute(
      "colspan",
      "3",
    );
    expect(within(balance).getByRole("columnheader", { name: "Target" })).toHaveAttribute(
      "colspan",
      "2",
    );
    const group = (name: string) => within(balance).getByRole("rowgroup", { name });
    // Group, count, actual percent, the bar (drawing only), target percent, variance.
    expect(line(group("Gender"), "Male")).toEqual(["Male", "2", "40 %", "", "50 %", "−10 %"]);
    expect(line(group("Gender"), "Not given")).toEqual(["Not given", "1", "20 %", "", "-", "-"]);
    expect(line(group("Age bands"), "50-60")).toEqual(["50-60", "1", "20 %", "", "10 %", "+10 %"]);
    expect(line(group("Age bands"), "20-30")).toEqual(["20-30", "2", "40 %", "", "40 %", "0 %"]);
    expect(line(group("Face-to-face and phone"), "Face-to-face")).toEqual([
      "Face-to-face",
      "2",
      "66.7 %",
      "",
      "50 %",
      "+16.7 %",
    ]);
    expect(line(group("Districts"), "North Goa (Goa)")).toEqual([
      "North Goa (Goa)",
      "2",
      "40 %",
      "",
      "12.5 %",
      "+27.5 %",
    ]);
    // Below the target red, above it green: the sign says the same.
    for (const below of within(group("Gender")).getAllByText("−10 %")) {
      expect(below).toHaveClass("variance--below");
    }
    expect(within(group("Districts")).getByText("+27.5 %")).toHaveClass("variance--above");
    // What each section is of, and the definitions folded away under the table.
    expect(
      screen.getAllByText("Percent of the 5 speakers with an approved conversation."),
    ).toHaveLength(3);
    expect(screen.getByText("Percent of the 3 approved conversations.")).toBeInTheDocument();
    const how = screen.getByText("How these are counted").closest("details") as HTMLElement;
    expect(how).not.toHaveAttribute("open");
    expect(within(how).getByText("Effective speech")).toBeInTheDocument();
    expect(within(how).getByText("Still needed")).toBeInTheDocument();
    expect(how).toHaveTextContent("longer than 3 s");
  });

  it("shows the first ten districts and the rest on request", async () => {
    const rows = Array.from({ length: 12 }, (_, i) => ({
      key: `D${i + 1}`,
      label: `District ${i + 1}`,
      count: 1,
      percent: 8.3,
      target_percent: null,
      variance: null,
    }));
    progress({ ...PROGRESS, districts: { ...PROGRESS.districts, total: 12, rows } });
    renderAt("/projects/p1/progress");
    const balance = await screen.findByRole("table", { name: "Balance against the targets" });
    const districts = within(balance).getByRole("rowgroup", { name: "Districts" });
    expect(within(districts).queryByText("District 11")).toBeNull();
    await userEvent.click(screen.getByRole("button", { name: "Show all (12)" }));
    expect(within(districts).getByText("District 12")).toBeInTheDocument();
  });

  it("says when nothing is approved yet and when there is no target", async () => {
    const empty = {
      ...PROGRESS,
      completed: {
        ...PROGRESS.completed,
        completed_ms: 0,
        target_hours: null,
        percent_of_target: null,
        approved_conversations: 0,
        approved_ms: 0,
        approved_effective_ms: 0,
        not_measured: 0,
        effective_share_pct: null,
      },
      conversations: {
        ...PROGRESS.conversations,
        approved: 0,
        percent_of_target: 0,
        by_status: {},
      },
      speakers: { ...PROGRESS.speakers, with_approved: 0, limit: null, at_limit: null },
      age_bands: { basis: "speakers", total: 0, has_target: false, rows: [] },
      gender: { ...PROGRESS.gender, total: 0 },
      modes: { ...PROGRESS.modes, total: 0 },
      districts: { basis: "speakers", total: 0, has_target: false, rows: [] },
    };
    progress(empty);
    renderAt("/projects/p1/progress");
    expect(
      await screen.findByText(
        "No approved conversations yet: the figures fill in as conversations are approved.",
      ),
    ).toBeInTheDocument();
    expect(figure("Completed")).toHaveTextContent("No hours target: set one on the Rules tab.");
    expect(figure("Registered")).toHaveTextContent("no limit per speaker");
    // The sections say why they are empty; no share rows.
    const balance = screen.getByRole("table", { name: "Balance against the targets" });
    expect(within(balance).queryByRole("rowheader", { name: "Male" })).toBeNull();
    expect(
      screen.getByText(
        "No approved conversations yet. No age bands set: add them on the Rules tab.",
      ),
    ).toBeInTheDocument();
    expect(screen.getByText("No conversations yet.")).toBeInTheDocument();
    expect(screen.queryByText(/not measured yet/)).toBeNull();
  });

  it("writes a variance with its sign", () => {
    expect([variance(4), variance(-6), variance(0), variance(27.5)]).toEqual([
      "+4 %",
      "−6 %",
      "0 %",
      "+27.5 %",
    ]);
  });
});

describe("the Participants page (D-153)", () => {
  it("says how many speakers are still needed, with a link to Progress", async () => {
    fakeApi(
      signedInAs([...MANAGER, "participants.view"], {
        "GET /api/v1/projects/p1": () => [200, PROJECT],
        "GET /api/v1/projects/p1/progress": () => [200, PROGRESS],
      }),
    );
    renderAt("/projects/p1/participants");
    const note = (await screen.findByText("Still needed: 495 speakers")).closest("p");
    expect(note).toHaveTextContent(
      "Still needed: 495 speakers to recruit for the target of 500. Which ages, genders and districts: see Progress.",
    );
    expect(within(note as HTMLElement).getByRole("link", { name: "see Progress" })).toHaveAttribute(
      "href",
      "/projects/p1/progress",
    );
  });

  it("says when no more are needed, and nothing without a speakers target", async () => {
    const answer = (target: number | null, still: number | null) => ({
      ...PROGRESS,
      still_needed: {
        ...PROGRESS.still_needed,
        speakers: {
          ...PROGRESS.still_needed.speakers,
          target,
          total: {
            ...PROGRESS.still_needed.speakers.total,
            total: { target, done: 400, registered: 100, still_needed: still },
          },
        },
      },
    });
    let body = answer(500, 0);
    const { calls } = fakeApi(
      signedInAs([...MANAGER, "participants.view"], {
        "GET /api/v1/projects/p1": () => [200, PROJECT],
        "GET /api/v1/projects/p1/progress": () => [200, body],
      }),
    );
    renderAt("/projects/p1/participants");
    expect((await screen.findByText("No more speakers needed")).closest("p")).toHaveTextContent(
      "No more speakers needed: the people done and registered cover the target of 500 (see Progress).",
    );
    cleanup();
    body = answer(null, null);
    renderAt("/projects/p1/participants");
    await waitFor(() =>
      expect(calls.filter((c) => c.path === "/api/v1/projects/p1/progress")).toHaveLength(2),
    );
    expect(await screen.findByLabelText("Search by code or name")).toBeInTheDocument();
    expect(screen.queryByText(/Still needed|No more speakers/)).toBeNull();
  });
});
