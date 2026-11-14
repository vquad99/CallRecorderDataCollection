// Dashboard filters and phone-call figures (D-108).
// Requirements: DASH-001, DASH-002, DASH-004
import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";

import { fakeApi, renderAt, signedInAs } from "../../test/fakeApi";
import { ALL_PERMISSIONS, DASHBOARD, worldHandlers } from "../../test/world";

const wait = { timeout: 5000 };

function open(answer: (url: URL) => unknown = () => DASHBOARD) {
  return fakeApi(
    signedInAs(ALL_PERMISSIONS, {
      ...worldHandlers(),
      "GET /api/v1/dashboard": (_b, url) => [200, answer(url)],
    }),
  );
}

/** The dashboard requests, as "name=value&..." without the fixed parts. */
const asked = (calls: { path: string }[]) =>
  calls.filter((c) => c.path.startsWith("/api/v1/dashboard")).map((c) => c.path.split("?")[1]);

describe("dashboard filters", () => {
  it("narrows the figures by type, language, dialect, status and person", async () => {
    const { calls } = open((url) =>
      url.searchParams.get("mode") === "TELEPHONY"
        ? { ...DASHBOARD, recordings: 7, recorded_hours: 3 }
        : DASHBOARD,
    );
    renderAt("/dashboard");
    const filters = await screen.findByRole("group", { name: "Filters" }, wait);
    await screen.findByText("Moderator output", {}, wait);
    expect(asked(calls)).toEqual(["days=30"]);

    await userEvent.selectOptions(within(filters).getByLabelText("Recording type"), "TELEPHONY");
    await waitFor(() => expect(asked(calls).at(-1)).toBe("days=30&mode=TELEPHONY"));
    // The lists come from the server: the languages and dialects spoken, the people at work.
    await userEvent.selectOptions(within(filters).getByLabelText("Language"), "hi");
    await userEvent.selectOptions(within(filters).getByLabelText("Dialect"), "Awadhi");
    await userEvent.selectOptions(within(filters).getByLabelText("Task status"), "APPROVED");
    await userEvent.selectOptions(within(filters).getByLabelText("Staff"), "u7");
    await waitFor(() =>
      expect(asked(calls).at(-1)).toBe(
        "days=30&mode=TELEPHONY&language=hi&dialect=Awadhi&status=APPROVED&staff_id=u7",
      ),
    );
    expect(within(filters).getByRole("option", { name: "Max Moderator" })).toBeInTheDocument();

    // One click takes every filter off again.
    await userEvent.click(within(filters).getByRole("button", { name: "Clear filters" }));
    await waitFor(() => expect(asked(calls).at(-1)).toBe("days=30"));
    expect(within(filters).queryByRole("button", { name: "Clear filters" })).toBeNull();
    expect(within(filters).getByLabelText("Recording type")).toHaveValue("");
  });

  it("takes chosen days instead of a period, and catches days the wrong way round", async () => {
    const { calls } = open();
    renderAt("/dashboard");
    await screen.findByText("Moderator output", {}, wait);
    expect(screen.queryByLabelText("From")).toBeNull();
    await userEvent.selectOptions(screen.getByLabelText("Period"), "custom");
    await userEvent.type(await screen.findByLabelText("From"), "2026-11-01");
    await userEvent.type(screen.getByLabelText("To"), "2026-11-10");
    await waitFor(() =>
      expect(asked(calls).at(-1)).toBe("days=30&date_from=2026-11-01&date_to=2026-11-10"),
    );
    const before = asked(calls).length;
    await userEvent.clear(screen.getByLabelText("To"));
    await userEvent.type(screen.getByLabelText("To"), "2026-10-20");
    expect(await screen.findByText("Must not be before the first day")).toBeInTheDocument();
    // Nothing was asked of the server for days that cannot be.
    expect(
      asked(calls)
        .slice(before)
        .some((q) => q?.includes("date_to=2026-10-20")),
    ).toBe(false);
  });

  it("shows managers the phone calls, and offers no person filter to others", async () => {
    open();
    renderAt("/dashboard");
    const card = (await screen.findByRole("heading", { name: "Phone calls" }, wait)).closest(
      "section",
    ) as HTMLElement;
    expect(card).toHaveTextContent("Placed12");
    expect(card).toHaveTextContent("Recorded9");
    expect(card).toHaveTextContent("Could not be placed2");
    expect(card).toHaveTextContent("Waiting for a person1");
    expect(within(card).getByRole("link", { name: "Phone calls" })).toHaveAttribute(
      "href",
      "/calls",
    );
  });

  it("gives a client viewer the filters that are about the recordings only", async () => {
    open(() => ({
      ...DASHBOARD,
      view: "client",
      tasks_by_status: null,
      qc: null,
      queues: null,
      team: null,
      storage_bytes: null,
      calls: null,
      options: { languages: ["hi"], dialects: [] },
    }));
    renderAt("/dashboard");
    const filters = await screen.findByRole("group", { name: "Filters" }, wait);
    await screen.findByRole("heading", { name: "Collection progress" }, wait);
    expect(within(filters).getByLabelText("Recording type")).toBeInTheDocument();
    expect(within(filters).getByLabelText("Language")).toBeInTheDocument();
    expect(within(filters).queryByLabelText("Dialect")).toBeNull(); // none is spoken here
    expect(within(filters).queryByLabelText("Task status")).toBeNull();
    expect(within(filters).queryByLabelText("Staff")).toBeNull();
    expect(screen.queryByRole("heading", { name: "Phone calls" })).toBeNull();
  });
});
