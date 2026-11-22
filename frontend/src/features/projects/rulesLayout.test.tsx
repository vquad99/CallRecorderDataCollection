// The Rules pages laid out as one look (D-158): a section's parts are groups under their own
// titles, described by their help and what is wrong; the age bands and the districts are small
// tables with their column titles written once; a question's box grows to show all its words and
// stays one line of text; the reminders' boxes grow with their lines; help is tied to its box.
// D-159: the intros and the help on every Rules page share one measure, and on a phone no box is
// held narrower than the line.
// Requirements: PROJ-001, PROJ-011
import { readFileSync } from "node:fs";

import { screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it } from "vitest";

import { fakeApi, renderAt, signedInAs } from "../../test/fakeApi";
import { PROJECT } from "../../test/world";
import { RULE_SECTIONS } from "./ProjectDetailPage";
import { CLIENT_REMINDERS } from "./reminders";

// Read from the disk: the test runner hands every stylesheet import over empty.
const rulesCss = readFileSync("src/features/projects/rules.css", "utf8");

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

/** Puts the Rules styles in the page, as a wide screen applies them or as a phone does: the test
 * browser applies no media or container query of its own, so for a phone the rules for a narrow
 * screen and a narrow frame are added again after the others, in their order. Returns what takes
 * them out. */
function rulesStyles(phone = false) {
  const sheets = [rulesCss];
  if (phone) {
    const probe = document.createElement("style");
    probe.textContent = rulesCss;
    document.head.append(probe);
    const narrow = [...(probe.sheet?.cssRules ?? [])].filter(
      (rule): rule is CSSConditionRule =>
        "conditionText" in rule && /max-width/.test((rule as CSSConditionRule).conditionText),
    );
    probe.remove();
    expect(narrow.length).toBeGreaterThan(0);
    sheets.push(narrow.flatMap((rule) => [...rule.cssRules].map((r) => r.cssText)).join("\n"));
  }
  const styles = sheets.map((css) => {
    const style = document.createElement("style");
    style.textContent = css;
    document.head.append(style);
    return style;
  });
  return () => styles.forEach((style) => style.remove());
}

const SECTIONS = RULE_SECTIONS.map((s) => [s.title, s.key] as const);
const style = (el: Element, property: string) => getComputedStyle(el).getPropertyValue(property);

describe("the Rules pages' text and boxes (D-159)", () => {
  let unstyle = () => {};
  afterEach(() => unstyle());

  it.each(SECTIONS)("%s: every intro and help wraps at one measure", async (title, key) => {
    unstyle = rulesStyles();
    rules();
    renderAt(`/projects/p1/rules/${key}`);
    const card = await screen.findByRole("region", { name: title });
    // The section's small text: everything written but what is wrong, notices and counts.
    const texts = [...card.querySelectorAll("p:not(.field__error, .notice, .muted)")];
    expect(texts.length).toBeGreaterThan(0);
    // As wide as a form's box at most, and never a word alone on the last line. A box's help is
    // evened out over its lines: not two words alone either ("personal page.").
    for (const text of texts)
      expect([text.textContent, style(text, "max-width"), style(text, "text-wrap")]).toEqual([
        text.textContent,
        "640px",
        text.matches(".field__hint:not(.rules__note)") ? "balance" : "pretty",
      ]);
    // A choice of two lines keeps no word alone on its last line either.
    for (const choice of card.querySelectorAll(".checkbox"))
      expect([choice.textContent, style(choice, "text-wrap")]).toEqual([
        choice.textContent,
        "pretty",
      ]);
  });

  it("gives the warning before a change the same measure", async () => {
    unstyle = rulesStyles();
    rules({ consent_mode: "UPLOAD" });
    renderAt("/projects/p1/rules/consent");
    const card = await screen.findByRole("region", { name: "Consent" });
    await userEvent.click(within(card).getByRole("radio", { name: /^Online/ }));
    const warning = within(card).getByText(/^Signed forms uploaded so far stop counting/);
    expect([style(warning, "max-width"), style(warning, "text-wrap")]).toEqual(["640px", "pretty"]);
  });

  it.each(SECTIONS)("%s: on a phone no box is held narrower than the line", async (title, key) => {
    unstyle = rulesStyles(true);
    rules();
    renderAt(`/projects/p1/rules/${key}`);
    const card = await screen.findByRole("region", { name: title });
    const fields = [...card.querySelectorAll(".field")];
    expect(fields.length).toBeGreaterThan(0);
    for (const field of fields) {
      const name = (field.textContent ?? "").slice(0, 40);
      expect([name, style(field, "max-width")]).toEqual([name, "none"]);
      // In a grid of boxes, no column of a fixed width either.
      const grid = field.parentElement;
      if (grid && style(grid, "display") === "grid")
        expect(`${name}: ${style(grid, "grid-template-columns")}`).not.toMatch(
          /minmax\(0,\s*\d+px\)/,
        );
    }
  });
});
