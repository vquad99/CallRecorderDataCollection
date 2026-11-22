// The Rules pages laid out as one look (D-158): a section's parts are groups under their own
// titles, described by their help and what is wrong; the age bands and the districts are small
// tables with their column titles written once; a question's box grows to show all its words and
// stays one line of text; the reminders' boxes grow with their lines; help is tied to its box.
// Requirements: PROJ-001, PROJ-011
import { screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";

import { fakeApi, renderAt, signedInAs } from "../../test/fakeApi";
import { PROJECT } from "../../test/world";
import { CLIENT_REMINDERS } from "./reminders";

const MANAGER = ["projects.view", "projects.manage"];

function rules(over: Record<string, unknown> = {}) {
  return fakeApi(
    signedInAs(MANAGER, {
      "GET /api/v1/projects/p1": () => [200, { ...PROJECT, ...over }],
      "PATCH /api/v1/projects/p1": (body) => [200, { ...PROJECT, ...(body as object) }],
    }),
  );
}

const patches = (calls: { method: string }[]) => calls.filter((c) => c.method === "PATCH");
/** The box behind a text box that sets its height: it holds the same words. */
const grown = (box: HTMLElement) => box.closest(".grow-box");

describe("the QC checklist's questions (D-158)", () => {
  it("shows each question whole and keeps it one line of text", async () => {
    const { calls } = rules();
    renderAt("/projects/p1/rules/qc-checklist");
    const card = await screen.findByRole("region", { name: "QC checklist" });
    const first = within(card).getByRole("group", { name: "1. two_speakers" });
    const words = within(first).getByLabelText("Question");
    // A box of several lines that grows with the words, never cut on one line.
    expect(words).toBeInstanceOf(HTMLTextAreaElement);
    expect(grown(words)).toHaveAttribute(
      "data-value",
      "The conversation is between exactly two speakers",
    );

    // Enter adds no line break, and saves nothing.
    await userEvent.type(words, "{Enter}");
    expect(words).toHaveValue("The conversation is between exactly two speakers");
    // Pasted lines are joined into one.
    await userEvent.clear(words);
    await userEvent.paste("Only two\npeople talk");
    expect(words).toHaveValue("Only two people talk");
    expect(grown(words)).toHaveAttribute("data-value", "Only two people talk");
    expect(patches(calls)).toHaveLength(0);
  });

  it("adds a new question with Enter in its own box, under its own title", async () => {
    const { calls } = rules();
    renderAt("/projects/p1/rules/qc-checklist");
    const card = await screen.findByRole("region", { name: "QC checklist" });
    const add = within(card).getByRole("group", { name: "Add a question" });
    expect(within(add).getByRole("heading", { level: 3, name: "Add a question" })).toBeVisible();
    await userEvent.type(within(add).getByLabelText("Key"), "music");
    const question = within(add).getByLabelText("New question");
    expect(question).toBeInstanceOf(HTMLTextAreaElement);
    await userEvent.type(question, "Is music{Enter}");
    const added = within(card).getByRole("group", { name: "3. music" });
    expect(within(added).getByLabelText("Question")).toHaveValue("Is music");
    expect(question).toHaveValue("");
    expect(patches(calls)).toHaveLength(0);
  });
});

describe("the targets on one grid (D-158)", () => {
  it("writes the age bands' column titles once, over boxes named by them", async () => {
    rules();
    renderAt("/projects/p1/rules/targets");
    const targets = await screen.findByRole("region", { name: "Targets" });
    const bands = within(targets).getByRole("group", { name: "Age bands (percent of speakers)" });
    expect(bands).toHaveAccessibleDescription(/^A band takes the ages from its first age/);
    for (const title of ["From age", "To age", "Percent"]) {
      expect(within(bands).getAllByText(title)).toHaveLength(1);
      expect(within(bands).getAllByRole("spinbutton", { name: title })).toHaveLength(4);
    }
    // What is wrong with the bands describes their part.
    await userEvent.click(within(bands).getByRole("button", { name: "Remove age band 50-60" }));
    expect(bands).toHaveAccessibleDescription(/The percents add up to 90, not 100\.$/);
  });

  it("puts gender and the districts under titles of their own", async () => {
    rules();
    renderAt("/projects/p1/rules/targets");
    const targets = await screen.findByRole("region", { name: "Targets" });
    const gender = within(targets).getByRole("group", { name: "Gender (percent of speakers)" });
    expect(gender).toHaveAccessibleDescription("Both empty: no gender target.");
    await userEvent.clear(within(gender).getByRole("spinbutton", { name: "Male (%)" }));
    expect(gender).toHaveAccessibleDescription(
      "Both empty: no gender target. Give both percents, or leave both empty for no target.",
    );

    const districts = within(targets).getByRole("group", {
      name: "Districts (by native district)",
    });
    expect(within(districts).queryByRole("textbox", { name: "District" })).toBeNull();
    await userEvent.click(
      within(districts).getByRole("button", { name: "Use the Konkani-region districts" }),
    );
    expect(districts).toHaveAccessibleDescription(/12\.5% each for 8\.$/);
    expect(within(districts).getAllByText("State")).toHaveLength(1);
    expect(within(districts).getAllByText("District")).toHaveLength(1);
    expect(within(districts).getAllByRole("combobox", { name: "State" })).toHaveLength(8);
    expect(within(districts).getAllByRole("textbox", { name: "District" })).toHaveLength(8);
  });
});

describe("help tied to its box (D-158)", () => {
  it("describes the speaker limit by its help, and the speaker details as a part", async () => {
    rules();
    renderAt("/projects/p1/rules/speakers");
    const limit = await screen.findByRole("spinbutton", {
      name: "Conversations per speaker (at most)",
    });
    expect(limit).toHaveAccessibleDescription(
      "Cancelled and rejected tasks do not count. Leave empty for no limit.",
    );
    const details = screen.getByRole("group", { name: "Speaker details needed before a task" });
    expect(details).toHaveAccessibleDescription(
      /^A task is made only for people who have every ticked detail/,
    );
    expect(
      screen.getByRole("heading", { level: 3, name: "Speaker details needed before a task" }),
    ).toBeVisible();
  });

  it("gives the audio name's example right after its help", async () => {
    rules();
    renderAt("/projects/p1/rules/export");
    const name = await screen.findByRole("textbox", { name: "Audio file name" });
    expect(name).toHaveAccessibleDescription(
      /between them\. e\.g\. 001_002_570001_576101_CON001\.wav$/,
    );
  });

  it("grows the reminders' boxes with their lines, three lines at least", async () => {
    rules();
    renderAt("/projects/p1/rules/reminders");
    const card = await screen.findByRole("region", { name: "Reminders for moderators" });
    const avoid = within(card).getByLabelText("Avoid");
    expect(avoid).toHaveAttribute("rows", "3");
    expect(grown(avoid)).toHaveAttribute("data-value", CLIENT_REMINDERS.avoid.join("\n"));
    await userEvent.type(avoid, "{Control>}{End}{/Control}{Enter}gossip");
    expect(grown(avoid)).toHaveAttribute(
      "data-value",
      [...CLIENT_REMINDERS.avoid, "gossip"].join("\n"),
    );
  });
});
