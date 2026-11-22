// A participant's uploaded documents (D-144): the signed consent form for this project and the
// address proof, each with View (a short-lived link, opened in a new tab) and Upload or Replace,
// and the earlier versions with who uploaded them and when. Shown in its own window from a
// participant's row and in the participant's details; the task page uses the pieces for the
// signed consent forms of its two participants.
import { useId, useState } from "react";

import { ApiError } from "../../api/client";
import type { ConsentMode } from "../../api/projects";
import * as work from "../../api/work";
import { DataTable } from "../../components/DataTable";
import { IconButton } from "../../components/form/Button";
import { Icon } from "../../components/Icon";
import { ErrorNotice, SuccessNotice } from "../../components/Notice";
import { ErrorState, LoadingState } from "../../components/StateViews";
import { StatusBadge } from "../../components/StatusBadge";
import { useAction } from "../../hooks/useAction";
import { useResource } from "../../hooks/useResource";
import { when } from "../../lib/format";

export const DOCUMENT_WORDS: Record<work.DocumentKind, string> = {
  CONSENT_FORM: "Signed consent form",
  ADDRESS_PROOF: "Address proof",
};

const sizeText = (bytes: number) =>
  bytes < 1024 * 1024
    ? `${Math.max(1, Math.round(bytes / 1024))} KB`
    : `${(bytes / 1024 / 1024).toFixed(1)} MB`;

/** "Uploaded 21 Nov 2026, 10:30 by Ada · 240 KB" */
export const uploadedText = (d: work.ParticipantDocument) =>
  `Uploaded ${when(d.uploaded_at)} by ${d.uploaded_by ?? "someone"} · ${sizeText(d.size_bytes)}`;

/** Fetches a short-lived link and opens the file in a new tab; says how long the link works. */
export async function openDocument(
  projectId: string,
  participantId: string,
  doc: work.ParticipantDocument,
): Promise<string> {
  const link = await work.documentLink(projectId, participantId, doc.id);
  const a = document.createElement("a");
  a.href = link.url;
  a.target = "_blank";
  a.rel = "noopener noreferrer";
  a.click();
  const minutes = Math.max(1, Math.round(link.expires_in / 60));
  return `${doc.file_name} opened in a new tab. The link works for ${minutes} minutes.`;
}

/** Checks a file here first (type, size), then uploads it; a problem becomes the error shown. */
export async function sendDocument(
  projectId: string,
  participantId: string,
  kind: work.DocumentKind,
  file: File,
): Promise<work.ParticipantDocument> {
  const problem = work.documentProblem(file);
  if (problem) throw new ApiError({ status: 422, code: "INVALID_FILE", message: problem });
  return work.uploadDocument(projectId, participantId, kind, file);
}

/** A button that picks a file and uploads it at once. `compact`: the icon only (a table row's
 * action, D-141), the words shown on hover and read by screen readers. */
export function UploadButton({
  label,
  busy,
  disabled = false,
  compact = false,
  onFile,
}: {
  /** The words, e.g. "Upload signed consent form" or "Replace address proof". */
  label: string;
  busy: boolean;
  disabled?: boolean;
  compact?: boolean;
  onFile: (file: File) => void;
}) {
  const off = disabled || busy ? " is-disabled" : "";
  return (
    <label
      className={compact ? `icon-button upload-icon${off}` : `button button--secondary${off}`}
      title={compact ? label : undefined}
    >
      {busy ? (
        <span className="spinner" aria-hidden="true" />
      ) : (
        <Icon name="upload" size={compact ? 18 : 16} />
      )}
      {compact ? <span className="sr-only">{label}</span> : label}
      <input
        type="file"
        accept={work.DOCUMENT_ACCEPT}
        className="sr-only"
        disabled={disabled || busy}
        onChange={(e) => {
          const file = e.target.files?.[0];
          e.target.value = "";
          if (file) onFile(file);
        }}
      />
    </label>
  );
}

/** A file box for a form (the scan goes up once the form is saved), with its own checks. */
export function FileField({
  label,
  hint,
  required = false,
  file,
  onChange,
}: {
  label: string;
  hint: string;
  required?: boolean;
  file: File | null;
  onChange: (file: File | null) => void;
}) {
  const id = useId();
  const problem = work.documentProblem(file);
  return (
    <div className={`field${problem ? " field--invalid" : ""}`}>
      <label htmlFor={id} className="field__label">
        {label}
        {required ? <span aria-hidden="true"> *</span> : null}
      </label>
      <p id={`${id}-hint`} className="field__hint">
        {hint}
      </p>
      <input
        id={id}
        type="file"
        className="field__input"
        accept={work.DOCUMENT_ACCEPT}
        // Checked by the form itself (its button waits for the file), not by the browser.
        aria-required={required || undefined}
        aria-invalid={problem ? true : undefined}
        aria-describedby={`${id}-hint${problem ? ` ${id}-error` : ""}`}
        onChange={(e) => onChange(e.target.files?.[0] ?? null)}
      />
      {problem ? (
        <p id={`${id}-error`} className="field__error">
          {problem}
        </p>
      ) : null}
    </div>
  );
}

/** "Consent form missing" (projects that take signed forms) and "Address proof missing", for a
 * participant's row; nothing for people who do not manage participants. */
export function DocumentBadges({
  p,
  mode,
  consent = true,
}: {
  p: work.Participant;
  mode: ConsentMode | undefined;
  /** False where the row's consent chip already says the form is missing. */
  consent?: boolean;
}) {
  return (
    <>
      {consent && mode === "UPLOAD" && p.has_consent_form === false ? (
        <StatusBadge tone="warning" label="Consent form missing" />
      ) : null}
      {p.has_address_proof === false ? (
        <span title="Optional now, needed before delivery.">
          <StatusBadge tone="neutral" label="Address proof missing" />
        </span>
      ) : null}
    </>
  );
}

/** "21 Nov 2026, 10:30 · Ada · 240 KB": when, by whom and how big, for a table cell. */
const uploadedCell = (d: work.ParticipantDocument) =>
  `${when(d.uploaded_at)} by ${d.uploaded_by ?? "someone"} · ${sizeText(d.size_bytes)}`;

/** One kind of document as a table row (D-152): its name and state, the file, when and by whom
 * it was uploaded, and View and Upload or Replace as icons. */
function Slot({
  kind,
  doc,
  canUpload,
  missing,
  note,
  busy,
  onView,
  onFile,
}: {
  kind: work.DocumentKind;
  doc: work.ParticipantDocument | null;
  canUpload: boolean;
  /** Show "… missing" when there is none. */
  missing: boolean;
  note: string;
  busy: string | null;
  onView: (doc: work.ParticipantDocument) => void;
  onFile: (file: File) => void;
}) {
  const words = DOCUMENT_WORDS[kind];
  return (
    <tr>
      <th scope="row">
        <span className="docs__kind">
          <Icon name="fileText" size={16} />
          {words}
        </span>
        {doc ? (
          <StatusBadge tone="success" label="Uploaded" />
        ) : missing ? (
          <StatusBadge
            tone={kind === "CONSENT_FORM" ? "warning" : "neutral"}
            label={kind === "CONSENT_FORM" ? "Consent form missing" : "Address proof missing"}
          />
        ) : null}
      </th>
      {doc ? (
        <>
          <td className="docs__name">{doc.file_name}</td>
          <td className="docs__when">{uploadedCell(doc)}</td>
        </>
      ) : (
        <td colSpan={2} className="docs__note muted">
          {note}
        </td>
      )}
      <td className="docs__actions">
        {doc ? (
          <IconButton
            icon="eye"
            label={`View ${doc.file_name}`}
            busy={busy === `view-${doc.id}`}
            disabled={busy !== null}
            onClick={() => onView(doc)}
          />
        ) : null}
        {canUpload ? (
          <UploadButton
            compact
            label={`${doc ? "Replace" : "Upload"} ${words.toLowerCase()}`}
            busy={busy === `upload-${kind}`}
            disabled={busy !== null}
            onFile={onFile}
          />
        ) : null}
      </td>
    </tr>
  );
}

/** Everything uploaded for one participant in one project, with View and Upload or Replace.
 * `problem` is shown first (an upload that failed while adding them). */
export function DocumentsPanel({
  projectId,
  participantId,
  problem = null,
  onChanged,
}: {
  projectId: string;
  participantId: string;
  problem?: string | null;
  /** After an upload (for example to load the list behind again). */
  onChanged?: () => void;
}) {
  const { state, reload } = useResource(
    () => work.participantDocuments(projectId, participantId),
    [projectId, participantId],
  );
  const [shownProblem, setShownProblem] = useState(problem);
  const { busy, error, message, run } = useAction();
  if (state.status === "loading") return <LoadingState label="Loading documents" />;
  if (state.status === "failed") return <ErrorState error={state.error} onRetry={reload} />;
  const d = state.data;
  const view = (doc: work.ParticipantDocument) =>
    void run(() => openDocument(projectId, participantId, doc), `view-${doc.id}`);
  const upload = (kind: work.DocumentKind) => (file: File) =>
    void run(async () => {
      await sendDocument(projectId, participantId, kind, file);
      setShownProblem(null);
      reload();
      onChanged?.();
      return `${DOCUMENT_WORDS[kind]} uploaded.`;
    }, `upload-${kind}`);
  const uploadMode = d.consent_mode === "UPLOAD";
  return (
    <div className="stack docs">
      {shownProblem ? (
        <p className="notice notice--error" role="alert">
          {shownProblem}
        </p>
      ) : null}
      <ErrorNotice error={error} />
      <SuccessNotice message={message} />
      <DataTable className="docs-table" label="Documents">
        <thead>
          <tr>
            <th scope="col">Document</th>
            <th scope="col">File</th>
            <th scope="col">Uploaded</th>
            <th scope="col">
              <span className="sr-only">Actions</span>
            </th>
          </tr>
        </thead>
        <tbody>
          <Slot
            kind="CONSENT_FORM"
            doc={d.consent_form}
            canUpload={d.may_upload_consent_form}
            missing={uploadMode}
            note={
              uploadMode
                ? "Not uploaded yet. A task needs it, unless they agreed online."
                : "This project takes consent online: the participant agrees on their personal page."
            }
            busy={busy}
            onView={view}
            onFile={upload("CONSENT_FORM")}
          />
          {d.may_view_address_proof ? (
            <Slot
              kind="ADDRESS_PROOF"
              doc={d.address_proof}
              canUpload={d.may_upload_address_proof}
              missing
              note="Not uploaded yet: optional now, needed before delivery. One for the person, in every project."
              busy={busy}
              onView={view}
              onFile={upload("ADDRESS_PROOF")}
            />
          ) : null}
        </tbody>
      </DataTable>
      <p className="muted docs__hint">
        PDF, JPEG or PNG, at most {work.MAX_DOCUMENT_MB} MB. A new upload replaces the current one;
        earlier ones stay below.
      </p>
      {d.earlier.length > 0 ? (
        <section aria-label="Earlier versions" className="docs__earlier">
          <h4>Earlier versions</h4>
          <DataTable className="docs-table" label="Earlier versions">
            <thead>
              <tr>
                <th scope="col">Document</th>
                <th scope="col">File</th>
                <th scope="col">Uploaded</th>
                <th scope="col">Replaced</th>
                <th scope="col">
                  <span className="sr-only">Actions</span>
                </th>
              </tr>
            </thead>
            <tbody>
              {d.earlier.map((e) => (
                <tr key={e.id} className="row--replaced">
                  <th scope="row">{DOCUMENT_WORDS[e.kind]}</th>
                  <td className="docs__name">{e.file_name}</td>
                  <td className="docs__when">{uploadedCell(e)}</td>
                  <td className="docs__when">
                    {when(e.replaced_at)} by {e.replaced_by ?? "someone"}
                  </td>
                  <td className="docs__actions">
                    <IconButton
                      icon="eye"
                      label={`View ${e.file_name}`}
                      busy={busy === `view-${e.id}`}
                      disabled={busy !== null}
                      onClick={() => view(e)}
                    />
                  </td>
                </tr>
              ))}
            </tbody>
          </DataTable>
        </section>
      ) : null}
    </div>
  );
}
