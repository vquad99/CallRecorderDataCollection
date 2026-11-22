// Consent online or by upload, and participants' scanned documents (D-144): adding someone with
// their signed consent form, what happens when an upload fails, the rows' "missing" badges, the
// Documents window, and the signed forms on the task page.
// Requirements: PART-006, PART-008, PART-016, STOR-005, SEC-010
import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";

import { fakeApi, renderAt, signedInAs, type Handler } from "../../test/fakeApi";
import {
  ALL_PERMISSIONS,
  DOCUMENT,
  NO_DOCUMENTS,
  PARTICIPANT,
  PARTICIPANT_B,
  PROJECT,
  SPEAKER_INPUT,
  TASK,
  worldHandlers,
} from "../../test/world";

afterEach(() => vi.unstubAllGlobals());
afterEach(() => vi.restoreAllMocks());

const UPLOAD_PROJECT = { ...PROJECT, consent_mode: "UPLOAD" };
const BY_UPLOAD =
  "This project takes a signed consent form uploaded by staff: no consent form is emailed. Upload it with Documents.";
const ADDED = {
  ...PARTICIPANT,
  id: "n1",
  participant_code: "P000003",
  display_label: "Chitra",
  consent_status: null,
  has_consent_form: false,
  has_address_proof: false,
  consent_email: BY_UPLOAD,
};
const pdf = (name = "chitra-consent.pdf") =>
  new File(["%PDF-1.7 a signed form"], name, { type: "application/pdf" });

type Box = ReturnType<typeof within>;
const labelled = (form: Box, label: string) => form.getByLabelText(new RegExp(`^${label}( \\*)?$`));

/** Name, email, language and every speaker detail (D-143) of someone new. */
async function fillPerson(user: ReturnType<typeof userEvent.setup>, form: Box) {
  await user.type(form.getByLabelText(/Name or label/), "Chitra");
  await user.type(form.getByLabelText(/Email address/), "chitra@example.org");
  await user.selectOptions(form.getByLabelText(/^Language/), "hi");
  for (const f of SPEAKER_INPUT) {
    if (f.list) await user.selectOptions(labelled(form, f.label), f.value);
    else await user.type(labelled(form, f.label), f.value);
  }
}

function serve(extra: Record<string, Handler> = {}) {
  return fakeApi(
    signedInAs(ALL_PERMISSIONS, {
      ...worldHandlers(),
      "GET /api/v1/projects/p1": () => [200, UPLOAD_PROJECT],
      ...extra,
    }),
  );
}

/** The request the browser sent for an upload: its file and headers. */
function sent(fetchMock: ReturnType<typeof fakeApi>["fetchMock"], path: string) {
  const call = fetchMock.mock.calls.find(([url]) => String(url).endsWith(path));
  const init = call?.[1];
  return { body: init?.body, headers: (init?.headers ?? {}) as Record<string, string> };
}

describe("signed consent forms and documents (D-144)", () => {
  it("asks for the signed form when adding someone and uploads it once they are added", async () => {
    const { calls, fetchMock } = serve({
      "POST /api/v1/projects/p1/participants": () => [201, ADDED],
      "POST /api/v1/projects/p1/participants/n1/documents/consent-form": () => [201, DOCUMENT],
      "POST /api/v1/projects/p1/participants/n1/documents/address-proof": () => [
        201,
        { ...DOCUMENT, id: "d2", kind: "ADDRESS_PROOF", file_name: "proof.png" },
      ],
    });
    const user = userEvent.setup({ applyAccept: false, delay: null });
    renderAt("/projects/p1/participants");
    await user.click(await screen.findByRole("button", { name: "Add participant" }));
    const form = within(screen.getByRole("dialog", { name: "Add participant" }));
    await fillPerson(user, form);
    const add = form.getByRole("button", { name: "Add participant" });
    const scan = form.getByLabelText(/^Signed consent form \(scan\)/);
    const proof = form.getByLabelText(/^Address proof \(optional now, needed before delivery\)/);
    expect(scan).toBeRequired();
    expect(proof).not.toBeRequired();
    expect(scan).toHaveAttribute("accept", expect.stringContaining("application/pdf"));
    // Required in an Upload project: nothing is added without it.
    expect(add).toBeDisabled();
    // A wrong type or a file over 10 MB is said under the box before anything is sent.
    await user.upload(scan, new File(["hello"], "notes.txt", { type: "text/plain" }));
    expect(form.getByText("Choose a PDF, JPEG or PNG file.")).toBeInTheDocument();
    expect(add).toBeDisabled();
    const big = pdf("huge.pdf");
    Object.defineProperty(big, "size", { value: 10 * 1024 * 1024 + 1 });
    await user.upload(scan, big);
    expect(form.getByText(/larger than 10 MB/)).toBeInTheDocument();
    expect(add).toBeDisabled();
    await user.upload(scan, pdf());
    await user.upload(proof, new File(["\x89PNG"], "proof.png", { type: "image/png" }));
    expect(add).toBeEnabled();
    await user.click(add);
    expect(
      await screen.findByText(
        "P000003 added. Signed consent form uploaded. Address proof uploaded.",
      ),
    ).toBeInTheDocument();
    expect(screen.queryByRole("dialog", { name: "Add participant" })).toBeNull();
    // The person first, then the files, each as itself with its name.
    const order = calls.filter((c) => c.method === "POST").map((c) => c.path);
    expect(order).toEqual([
      "/api/v1/projects/p1/participants",
      "/api/v1/projects/p1/participants/n1/documents/consent-form",
      "/api/v1/projects/p1/participants/n1/documents/address-proof",
    ]);
    const upload = sent(fetchMock, "/n1/documents/consent-form");
    expect(upload.body).toBeInstanceOf(File);
    expect(upload.headers["Content-Type"]).toBe("application/pdf");
    expect(upload.headers["X-File-Name"]).toBe("chitra-consent.pdf");
  }, 20000);

  it("keeps the person added when an upload fails and opens their documents to try again", async () => {
    let uploads = 0;
    serve({
      "POST /api/v1/projects/p1/participants": () => [201, ADDED],
      "POST /api/v1/projects/p1/participants/n1/documents/consent-form": () =>
        ++uploads === 1
          ? [
              422,
              {
                error: {
                  code: "INVALID_FILE_TYPE",
                  message: "Only PDF, JPEG or PNG files can be uploaded.",
                },
              },
            ]
          : [201, DOCUMENT],
      "GET /api/v1/projects/p1/participants/n1/documents": () => [
        200,
        { ...NO_DOCUMENTS, consent_mode: "UPLOAD", may_upload_consent_form: true },
      ],
    });
    const user = userEvent.setup({ applyAccept: false, delay: null });
    renderAt("/projects/p1/participants");
    await user.click(await screen.findByRole("button", { name: "Add participant" }));
    const form = within(screen.getByRole("dialog", { name: "Add participant" }));
    await fillPerson(user, form);
    await user.upload(form.getByLabelText(/^Signed consent form \(scan\)/), pdf());
    await user.click(form.getByRole("button", { name: "Add participant" }));
    const docs = await screen.findByRole("dialog", { name: "Documents of P000003" });
    expect(await within(docs).findByRole("alert")).toHaveTextContent(
      "P000003 was added, but this could not be uploaded: Signed consent form: Only PDF, JPEG or PNG files can be uploaded. Upload it here.",
    );
    expect(screen.getByText(`P000003 added. ${BY_UPLOAD}`)).toBeInTheDocument();
    expect(within(docs).getAllByText("Consent form missing").length).toBeGreaterThan(0);
    await user.upload(within(docs).getByLabelText("Upload signed consent form"), pdf());
    expect(await within(docs).findByText("Signed consent form uploaded.")).toBeInTheDocument();
    expect(within(docs).queryByRole("alert")).toBeNull();
  }, 20000);

  it("asks only for the optional address proof in a project that takes consent online", async () => {
    serve({ "GET /api/v1/projects/p1": () => [200, PROJECT] });
    renderAt("/projects/p1/participants");
    await userEvent.click(await screen.findByRole("button", { name: "Add participant" }));
    const form = within(screen.getByRole("dialog", { name: "Add participant" }));
    expect(form.queryByLabelText(/Signed consent form/)).toBeNull();
    expect(form.getByLabelText(/^Address proof/)).not.toBeRequired();
  });

  it("marks what is missing on the rows and offers no consent email in an Upload project", async () => {
    serve({
      "GET /api/v1/projects/p1/participants": () => [
        200,
        {
          items: [
            { ...PARTICIPANT, consent_status: "UPLOADED", has_consent_form: true },
            {
              ...PARTICIPANT_B,
              consent_status: "NONE",
              has_consent_form: false,
              has_address_proof: true,
            },
          ],
          total: 2,
          page: 1,
          page_size: 25,
        },
      ],
    });
    renderAt("/participants");
    await userEvent.selectOptions(await screen.findByLabelText("Project"), "p1");
    const asha = (await screen.findByText("P000001")).closest("tr") as HTMLElement;
    const bina = screen.getByText("P000002").closest("tr") as HTMLElement;
    expect(within(asha).getByText("Form uploaded")).toBeInTheDocument();
    expect(within(asha).getByText("Address proof missing")).toBeInTheDocument();
    expect(within(asha).queryByText("Consent form missing")).toBeNull();
    // Said once: the consent column already reads "Consent form missing".
    expect(within(bina).getAllByText("Consent form missing")).toHaveLength(1);
    expect(within(bina).queryByText("Address proof missing")).toBeNull();
    expect(within(bina).getByRole("button", { name: "Documents" })).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Email consent form again" })).toBeNull();
    await userEvent.click(within(bina).getByRole("checkbox", { name: "Select P000002" }));
    const bar = screen.getByRole("group", { name: "Actions for selected participants" });
    expect(within(bar).queryByRole("button", { name: "Email consent form again" })).toBeNull();
  });

  it("shows both badges on the project's Participants tab", async () => {
    serve({
      "GET /api/v1/projects/p1/participants": () => [
        200,
        { items: [{ ...PARTICIPANT, consent_status: "NONE" }], total: 1, page: 1, page_size: 25 },
      ],
    });
    renderAt("/projects/p1/participants");
    const row = (await screen.findByText("P000001")).closest("tr") as HTMLElement;
    expect(within(row).getByText("Consent form missing")).toBeInTheDocument();
    expect(within(row).getByText("Address proof missing")).toBeInTheDocument();
    expect(within(row).queryByRole("button", { name: "Email consent form again" })).toBeNull();
  });

  it("lists the current files and earlier versions, opens one in a new tab and replaces one", async () => {
    const opened: { href: string; target: string }[] = [];
    vi.spyOn(HTMLAnchorElement.prototype, "click").mockImplementation(function (
      this: HTMLAnchorElement,
    ) {
      opened.push({ href: this.href, target: this.target });
    });
    const earlier = {
      ...DOCUMENT,
      id: "d0",
      file_name: "first-scan.jpg",
      content_type: "image/jpeg",
      uploaded_by: "Mona Moderator",
      uploaded_at: "2026-11-20T05:00:00Z",
      replaced_by: "Ada Admin",
      replaced_at: "2026-11-21T05:00:00Z",
    };
    const proof = { ...DOCUMENT, id: "d2", kind: "ADDRESS_PROOF", file_name: "aadhaar.png" };
    let replaced = false;
    const { calls, fetchMock } = serve({
      "GET /api/v1/projects/p1/participants/a1/documents": () => [
        200,
        {
          ...NO_DOCUMENTS,
          consent_mode: "UPLOAD",
          consent_form: replaced ? { ...DOCUMENT, id: "d3", file_name: "better.pdf" } : DOCUMENT,
          address_proof: proof,
          earlier: [earlier],
          may_upload_consent_form: true,
        },
      ],
      "POST /api/v1/projects/p1/participants/a1/documents/d1/url": () => [
        200,
        { url: "https://storage.example/d1?X-Amz-Signature=x", expires_in: 300 },
      ],
      "POST /api/v1/projects/p1/participants/a1/documents/d0/url": () => [
        200,
        { url: "https://storage.example/d0?X-Amz-Signature=x", expires_in: 300 },
      ],
      "POST /api/v1/projects/p1/participants/a1/documents/consent-form": () => {
        replaced = true;
        return [201, { ...DOCUMENT, id: "d3", file_name: "better.pdf" }];
      },
    });
    renderAt("/projects/p1/participants");
    const row = (await screen.findByText("P000001")).closest("tr") as HTMLElement;
    await userEvent.click(within(row).getByRole("button", { name: "Documents" }));
    const docs = within(await screen.findByRole("dialog", { name: "Documents of P000001" }));
    // D-152: one table row per kind of document, View and Replace as icons in the row.
    const current = within(docs.getByRole("table", { name: "Documents" }));
    const form = within(current.getByRole("row", { name: /^Signed consent form/ }));
    expect(form.getByText("asha-consent.pdf")).toBeInTheDocument();
    expect(form.getByText(/by Ada Admin · 240 KB/)).toBeInTheDocument();
    const address = within(current.getByRole("row", { name: /^Address proof/ }));
    expect(address.getByText("aadhaar.png")).toBeInTheDocument();
    const history = docs.getByRole("region", { name: "Earlier versions" });
    expect(within(history).getByRole("row", { name: /first-scan.jpg/ })).toHaveTextContent(
      /^Signed consent formfirst-scan.jpg/,
    );
    expect(history).toHaveTextContent("by Mona Moderator");
    expect(history).toHaveTextContent("by Ada Admin");
    await userEvent.click(form.getByRole("button", { name: "View asha-consent.pdf" }));
    expect(
      await docs.findByText("asha-consent.pdf opened in a new tab. The link works for 5 minutes."),
    ).toBeInTheDocument();
    expect(opened).toEqual([
      { href: "https://storage.example/d1?X-Amz-Signature=x", target: "_blank" },
    ]);
    await userEvent.click(within(history).getByRole("button", { name: "View first-scan.jpg" }));
    await waitFor(() => expect(opened).toHaveLength(2));
    await userEvent.upload(form.getByLabelText("Replace signed consent form"), pdf("better.pdf"));
    expect(await docs.findByText("better.pdf")).toBeInTheDocument();
    expect(sent(fetchMock, "/a1/documents/consent-form").headers["X-File-Name"]).toBe("better.pdf");
    // The list behind the window is loaded again, with a word for the person.
    expect(await screen.findByText("Documents of P000001 updated.")).toBeInTheDocument();
    expect(
      calls.filter((c) => c.path.startsWith("/api/v1/projects/p1/participants?")).length,
    ).toBeGreaterThan(1);
  });

  it("shows the Documents block in the participant's details", async () => {
    serve({
      "GET /api/v1/projects/p1/participants/a1/details": () => [
        200,
        {
          participant: { ...PARTICIPANT, consent_status: "UPLOADED", has_consent_form: true },
          updated_at: "2026-11-12T10:00:00Z",
          added_by: null,
          projects: [],
          removed: null,
          link: null,
          consent_form: null,
          sessions: [],
          sessions_total: 0,
          minutes: null,
          calls: null,
        },
      ],
      "GET /api/v1/projects/p1/participants/a1/documents": () => [
        200,
        { ...NO_DOCUMENTS, consent_mode: "UPLOAD", consent_form: DOCUMENT },
      ],
    });
    renderAt("/participants");
    await userEvent.selectOptions(await screen.findByLabelText("Project"), "p1");
    const row = (await screen.findByText("P000001")).closest("tr") as HTMLElement;
    await userEvent.click(within(row).getByRole("button", { name: "View" }));
    const panel = within(await screen.findByRole("dialog", { name: "Participant details" }));
    expect(await panel.findByText("Consent: Form uploaded")).toBeInTheDocument();
    const block = panel.getByRole("region", { name: "Documents" });
    expect(await within(block).findByText("asha-consent.pdf")).toBeInTheDocument();
    expect(within(block).getByText("Address proof missing")).toBeInTheDocument();
  });
});

describe("signed consent forms on the task page (D-144)", () => {
  const uploadTask = (extra: Record<string, unknown> = {}) => ({
    ...TASK,
    consent_mode: "UPLOAD",
    allowed_transitions: ["IN_PROGRESS"],
    consent_missing: ["B"],
    participant_a: {
      ...TASK.participant_a,
      consent_status: "UPLOADED",
      consent_form: DOCUMENT,
      can_upload_consent_form: true,
    },
    participant_b: {
      ...TASK.participant_b,
      consent_status: null,
      consent_at: null,
      may_record: false,
      consent_form: null,
      can_upload_consent_form: true,
    },
    ...extra,
  });

  it("shows Form uploaded and Consent form missing, and lets the moderator upload the form", async () => {
    let uploaded = false;
    const { calls } = fakeApi(
      signedInAs(["tasks.view"], {
        ...worldHandlers(),
        "GET /api/v1/tasks/t1": () => [
          200,
          uploaded
            ? uploadTask({
                consent_missing: [],
                participant_b: {
                  ...TASK.participant_b,
                  consent_status: "UPLOADED",
                  consent_form: { ...DOCUMENT, id: "d9", file_name: "bina.pdf" },
                  can_upload_consent_form: true,
                },
              })
            : uploadTask(),
        ],
        "POST /api/v1/projects/p1/participants/b1/documents/consent-form": () => {
          uploaded = true;
          return [201, { ...DOCUMENT, id: "d9", file_name: "bina.pdf" }];
        },
      }),
    );
    renderAt("/tasks/t1");
    const waiting = await screen.findByRole("region", { name: "Waiting for consent" });
    expect(within(waiting).getByText("Consent form missing")).toBeInTheDocument();
    // Nothing is emailed in an Upload project: the signed form is uploaded instead.
    expect(within(waiting).queryByRole("button", { name: /Email consent form/ })).toBeNull();
    // D-152: the signed forms sit in the participants matrix, one cell per person.
    const forms = screen.getByRole("region", { name: "Participants" });
    expect(within(forms).getByText("asha-consent.pdf")).toBeInTheDocument();
    expect(screen.getAllByText("Form uploaded").length).toBeGreaterThan(0);
    await userEvent.upload(
      within(forms).getByLabelText("Upload consent form of P000002"),
      pdf("bina.pdf"),
    );
    expect(await screen.findByText("Signed consent form of P000002 uploaded.")).toBeInTheDocument();
    expect(await within(forms).findByText("bina.pdf")).toBeInTheDocument();
    expect(screen.queryByRole("region", { name: "Waiting for consent" })).toBeNull();
    expect(calls.filter((c) => c.path === "/api/v1/tasks/t1").length).toBeGreaterThan(1);
  });

  it("lets the QC Executive look at the forms without uploading", async () => {
    vi.spyOn(HTMLAnchorElement.prototype, "click").mockImplementation(() => undefined);
    fakeApi(
      signedInAs(["tasks.view", "audio_qc.review"], {
        ...worldHandlers(),
        "GET /api/v1/tasks/t1": () => [
          200,
          uploadTask({
            is_moderator: false,
            can_assign: false,
            can_reassign: false,
            participant_a: {
              ...TASK.participant_a,
              consent_status: "UPLOADED",
              consent_form: DOCUMENT,
              can_upload_consent_form: false,
            },
            participant_b: {
              ...TASK.participant_b,
              consent_status: null,
              may_record: false,
              consent_form: null,
              can_upload_consent_form: false,
            },
          }),
        ],
        "POST /api/v1/projects/p1/participants/a1/documents/d1/url": () => [
          200,
          { url: "https://storage.example/d1", expires_in: 300 },
        ],
      }),
    );
    renderAt("/tasks/t1");
    const forms = await screen.findByRole("region", { name: "Participants" });
    expect(within(forms).queryByLabelText(/Upload consent form/)).toBeNull();
    expect(within(forms).queryByLabelText(/Replace consent form/)).toBeNull();
    await userEvent.click(
      within(forms).getByRole("button", { name: "View the signed consent form of P000001" }),
    );
    expect(await within(forms).findByText(/opened in a new tab/)).toBeInTheDocument();
    const waiting = screen.getByRole("region", { name: "Waiting for consent" });
    expect(
      within(waiting).getByText("Ask your admin to upload their signed consent form."),
    ).toBeInTheDocument();
  });
});
