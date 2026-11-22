// Adding, editing and looking at one participant, the same on the Participants page and on a
// project's Participants tab: the form, the consent history, the details and the documents open in
// a window next to the row that was clicked (D-104, D-144).
import { useId, useState, type ReactNode } from "react";

import type { ApiError } from "../../api/client";
import type { ConsentMode, Language } from "../../api/projects";
import * as work from "../../api/work";
import { Button } from "../../components/form/Button";
import { Select } from "../../components/form/Select";
import { TextField } from "../../components/form/TextField";
import { Modal } from "../../components/Modal";
import { ErrorNotice } from "../../components/Notice";
import { ErrorState, LoadingState } from "../../components/StateViews";
import { StatusBadge } from "../../components/StatusBadge";
import { useAction } from "../../hooks/useAction";
import { toApiError, useResource } from "../../hooks/useResource";
import { when } from "../../lib/format";
import { CONSENT_METHOD_LABELS, consentAnswer, labelFor } from "../../lib/labels";
import {
  AGE_LIMITS,
  ageProblem,
  EDUCATION_LABELS,
  EDUCATION_MEDIUM_LABELS,
  EMPTY_SPEAKER_DETAILS,
  GENDER_LABELS,
  INDIAN_STATES,
  missingSpeakerDetails,
  NO_PROJECT_RULES,
  pincodeProblem,
  speakerDetailsOf,
  type SpeakerKey,
  type SpeakerRules,
} from "../../lib/speakers";
import {
  COUNTRY_CODES,
  languageOptions,
  OTHER_CODE,
  phoneHint,
  phoneProblem,
  splitPhone,
} from "../projects/choices";
import { DOCUMENT_WORDS, DocumentsPanel, FileField, sendDocument } from "./Documents";
import { ParticipantDetails } from "./ParticipantDetails";
import "./participants.css";

export const EMPTY_PARTICIPANT: work.ParticipantFields = {
  display_label: "",
  phone: null,
  email: "",
  language_code: "",
  dialect: "",
  district: "",
  notes: "",
  ...EMPTY_SPEAKER_DETAILS,
};

/** Shown once a participant is added: the server says what happened to their consent form. */
export const addedText = (p: work.AddedParticipant, where = "") =>
  `${p.participant_code} added${where}. ${p.consent_email}`;

/** The scans chosen on the Add participant form, uploaded once the person is added (D-144). */
export interface AddFiles {
  consentForm: File | null;
  addressProof: File | null;
}
const NO_FILES: AddFiles = { consentForm: null, addressProof: null };

/** The form's starting values for an existing participant. A masked phone or a hidden email is
 * not sent back, so the stored one is kept. */
export const fieldsOf = (p: work.Participant): work.ParticipantFields => ({
  display_label: p.display_label ?? "",
  phone: p.phone_masked ? null : p.phone,
  language_code: p.language_code,
  dialect: p.dialect,
  district: p.district ?? "",
  notes: p.notes ?? "",
  email: p.email ?? (p.has_email ? undefined : ""),
  ...speakerDetailsOf(p),
});

type Place = "current" | "native" | "recording";
/** The speaker details typed as text or chosen from a list (all but the age). */
type SpeakerText = Exclude<keyof work.SpeakerDetails, "age"> | "district";

/** The age as typed is wrong for the project: a new age only. An age kept as it was may have been
 * saved in another project; the server does not check it again, a task does (D-145). */
const ageError = (f: work.ParticipantFields, initialAge: number | null, rules: SpeakerRules) =>
  f.age === initialAge ? undefined : ageProblem(f.age, rules);

/** Speaker details (D-143), short fields side by side: someone new needs those the project asks
 * for (D-145, marked *); someone saved before may be saved without them, and the form says which
 * are still missing. */
function SpeakerFields({
  f,
  setF,
  isNew,
  rules,
  initialAge,
}: {
  f: work.ParticipantFields;
  setF: (next: work.ParticipantFields) => void;
  isNew: boolean;
  rules: SpeakerRules;
  initialAge: number | null;
}) {
  const missing = missingSpeakerDetails(f, rules.required);
  const need = (key: SpeakerKey) => isNew && rules.required.includes(key);
  // The native district is the participant's district: a string, never null.
  const set = (key: SpeakerText, value: string) =>
    setF({ ...f, [key]: key === "district" || value ? value : null });
  const choices = (labels: Record<string, string>) => [
    { value: "", label: "Choose" },
    ...Object.entries(labels).map(([value, label]) => ({ value, label })),
  ];
  const pick = (key: SpeakerText, label: string, options: { value: string; label: string }[]) => (
    <Select
      label={label}
      required={need(key)}
      value={f[key] ?? ""}
      onChange={(e) => set(key, e.target.value)}
      options={options}
    />
  );
  const type = (key: SpeakerText, label: string, max = 100, hint = "") => (
    <TextField
      label={label}
      required={need(key)}
      maxLength={max}
      {...(hint ? { hint } : {})}
      value={f[key] ?? ""}
      onChange={(e) => set(key, e.target.value)}
    />
  );
  const place = (where: Place, title: string, note: string) => {
    const pin = `${where}_pincode` as const;
    const problem = pincodeProblem(f[pin]);
    return (
      <>
        <p className="field__hint">{note}</p>
        <div className="form-grid">
          {pick(`${where}_state`, `${title} state`, [
            { value: "", label: "Choose a state" },
            ...INDIAN_STATES.map((s) => ({ value: s, label: s })),
          ])}
          {type(where === "native" ? "district" : `${where}_district`, `${title} district`)}
          <TextField
            label={`${title} PIN code`}
            required={need(pin)}
            inputMode="numeric"
            maxLength={6}
            value={f[pin] ?? ""}
            {...(problem ? { error: problem } : {})}
            onChange={(e) => set(pin, e.target.value.replace(/\D/g, ""))}
          />
        </div>
      </>
    );
  };
  const agePrompt = ageError(f, initialAge, rules);
  const ages = `${rules.minAge} to ${rules.maxAge}`;
  const ageHint = ageProblem(f.age, rules)
    ? `Outside this project's speaker ages (${ages}): they cannot be put on a task here.`
    : `Speakers aged ${ages}.`;
  return (
    <fieldset className="field speaker-details">
      <legend className="field__label">Speaker details</legend>
      {isNew ? (
        <p className="field__hint">
          {rules.required.length > 0
            ? "Those marked * are needed to add them: a task is made only for people who have them."
            : "None are needed in this project: fill in what you know."}
        </p>
      ) : missing.length > 0 ? (
        <p className="notice notice--info" role="status">
          Missing: {missing.join(", ")}. A task is made only for people who have the speaker details
          this project needs.
        </p>
      ) : null}
      <div className="form-grid">
        <TextField
          label="Age"
          type="number"
          required={need("age")}
          min={AGE_LIMITS.min}
          max={AGE_LIMITS.max}
          step={1}
          {...(agePrompt ? { error: agePrompt } : { hint: ageHint })}
          value={f.age ?? ""}
          onChange={(e) => setF({ ...f, age: e.target.value ? Number(e.target.value) : null })}
        />
        {pick("gender", "Gender", choices(GENDER_LABELS))}
      </div>
      {place("current", "Current", "Where they live now.")}
      {place("native", "Native", "Where they were born.")}
      {type("native_language", "Native language", 50, "For example Konkani.")}
      <div className="form-grid">
        {pick("education", "Education", choices(EDUCATION_LABELS))}
        {pick("education_medium", "Medium of education", choices(EDUCATION_MEDIUM_LABELS))}
      </div>
      {place("recording", "Recording", "Where the recording takes place.")}
    </fieldset>
  );
}

export function ParticipantForm({
  initial,
  languages,
  submitLabel,
  onSubmit,
  busy,
  error,
  isNew = false,
  consentMode,
  rules = NO_PROJECT_RULES,
}: {
  initial: work.ParticipantFields;
  languages: readonly Language[]; // the project's languages; empty means any
  submitLabel: string;
  onSubmit: (f: work.ParticipantFields, files: AddFiles) => void;
  busy: boolean;
  error: ApiError | null;
  /** A new participant needs the speaker details the project asks for (D-143, D-145). */
  isNew?: boolean;
  /** Adding someone: the project's way of consent. Upload asks for the signed form (D-144). */
  consentMode?: ConsentMode | undefined;
  /** The project's speaker ages and needed details (D-145); without a project, any age and
   * nothing needed. The server checks again. */
  rules?: SpeakerRules;
}) {
  const [f, setF] = useState(initial);
  const [files, setFiles] = useState<AddFiles>(NO_FILES);
  const waitsId = useId();
  const scans = isNew && consentMode !== undefined;
  const needsForm = scans && consentMode === "UPLOAD";
  const [phone, setPhone] = useState(() => splitPhone(initial.phone));
  const typedPhone = phone.digits ? `${phone.cc}${phone.digits}` : null;
  // A saved number left as it is goes back as it is, unchecked: the file import keeps any
  // international number (D-083), and the rest of the person can still be edited.
  const phoneKept = Boolean(initial.phone) && typedPhone === initial.phone;
  const phoneError = (!phoneKept && phoneProblem(phone.cc, phone.digits)) || undefined;
  // A wrong speaker detail stops the form; a missing one only for someone new, and only one the
  // project needs (D-143, D-145).
  const speakerWrong =
    Boolean(ageError(f, initial.age, rules)) ||
    [f.current_pincode, f.native_pincode, f.recording_pincode].some((pin) => pincodeProblem(pin));
  // What the button waits for, said next to it rather than left to the asterisks (UXW-09).
  const missing = [
    f.display_label.trim() ? null : "Name or label",
    initial.email !== undefined && !f.email?.trim() ? "Email address" : null,
    f.language_code.trim() ? null : "Language",
    ...(isNew ? missingSpeakerDetails(f, rules.required) : []),
    needsForm && !files.consentForm ? "Signed consent form (scan)" : null,
  ].filter((name): name is string => name !== null);
  const wrong =
    Boolean(phoneError) ||
    speakerWrong ||
    Boolean(work.documentProblem(files.consentForm)) ||
    Boolean(work.documentProblem(files.addressProof));
  const waits =
    missing.length > 0
      ? `Still to fill: ${missing.join(", ")}.`
      : wrong
        ? "Correct the fields marked in red."
        : null;
  return (
    <form
      onSubmit={(e) => {
        e.preventDefault();
        if (waits !== null) return;
        onSubmit(
          { ...f, phone: phoneKept ? initial.phone : typedPhone, email: f.email?.trim() },
          files,
        );
      }}
    >
      <TextField
        label="Name or label"
        required
        value={f.display_label}
        onChange={(e) => setF({ ...f, display_label: e.target.value })}
      />
      <div className="form-grid phone-fields">
        <Select
          label="Country code"
          value={phone.cc}
          onChange={(e) => setPhone({ ...phone, cc: e.target.value })}
          options={COUNTRY_CODES.map((c) => ({
            value: c.code,
            label: c.code === OTHER_CODE ? c.name : `${c.code} ${c.name}`,
          }))}
        />
        <TextField
          label="Phone number"
          hint={phoneHint(phone.cc)}
          inputMode="tel"
          autoComplete={phone.cc === OTHER_CODE ? "tel" : "tel-national"}
          // Room for a number pasted with spaces; the digits are checked, never cut.
          maxLength={20}
          value={phone.digits}
          {...(phoneError ? { error: phoneError } : {})}
          onChange={(e) => {
            const raw = e.target.value;
            // A whole number pasted with its "+" brings its country code with it.
            setPhone(
              raw.trim().startsWith("+")
                ? splitPhone(raw)
                : { ...phone, digits: raw.replace(/\D/g, "") },
            );
          }}
        />
      </div>
      {/* Every participant needs an email: the consent form is sent there (D-128). A saved email
          this user may not see stays as it is when the box is left empty. */}
      <TextField
        label="Email address"
        type="email"
        required={initial.email !== undefined}
        hint={
          initial.email === undefined
            ? "Saved and hidden from you. Leave empty to keep it."
            : "The consent form is sent to this address."
        }
        value={f.email ?? ""}
        onChange={(e) => setF({ ...f, email: e.target.value })}
      />
      <Select
        label="Language"
        required
        value={f.language_code}
        onChange={(e) => setF({ ...f, language_code: e.target.value })}
        options={languageOptions(languages, initial.language_code)}
      />
      <TextField
        label="Dialect"
        value={f.dialect}
        onChange={(e) => setF({ ...f, dialect: e.target.value })}
      />
      <TextField
        label="Internal notes"
        value={f.notes}
        onChange={(e) => setF({ ...f, notes: e.target.value })}
      />
      <SpeakerFields f={f} setF={setF} isNew={isNew} rules={rules} initialAge={initial.age} />
      {scans ? (
        <fieldset className="field">
          <legend className="field__label">Documents</legend>
          <p className="field__hint">
            PDF, JPEG or PNG, at most {work.MAX_DOCUMENT_MB} MB each. They are uploaded as soon as
            the participant is added.
          </p>
          <div className="form-grid">
            {needsForm ? (
              <FileField
                label="Signed consent form (scan)"
                hint="Their consent in this project: no consent form is emailed."
                required
                file={files.consentForm}
                onChange={(file) => setFiles({ ...files, consentForm: file })}
              />
            ) : null}
            <FileField
              label="Address proof (optional now, needed before delivery)"
              hint="One for the person, in every project."
              file={files.addressProof}
              onChange={(file) => setFiles({ ...files, addressProof: file })}
            />
          </div>
        </fieldset>
      ) : null}
      <ErrorNotice error={error} />
      {/* The main button at the form's foot, on the left (D-158), what it waits for beside it. */}
      <div className="form-foot">
        <Button
          type="submit"
          busy={busy}
          disabled={waits !== null}
          aria-describedby={waits ? waitsId : undefined}
        >
          {submitLabel}
        </Button>
        {/* Not a live region: the Edit form's "Missing:" notice is the form's status. */}
        {waits ? (
          <p id={waitsId} className="form-waits">
            {waits}
          </p>
        ) : null}
      </div>
    </form>
  );
}

/** Where the link an answer came in on was emailed, masked ("ka•••@example.org"), as the server
 * notes it (SECB-02); nothing on answers from before. */
const emailedTo = (note: string) => /\(link emailed to ([^()]+)\)\s*$/.exec(note)?.[1];

/** Every consent answer of this participant, newest first; older ones may have been noted by a
 * moderator (before D-129). */
export function ConsentList({
  projectId,
  participantId,
}: {
  projectId: string;
  participantId: string;
}) {
  const { state, reload } = useResource(
    () => work.consentHistory(projectId, participantId),
    [projectId, participantId],
  );
  if (state.status === "loading") return <LoadingState label="Loading consent" />;
  if (state.status === "failed") return <ErrorState error={state.error} onRetry={reload} />;
  if (state.data.length === 0) return <p className="muted">No consent recorded yet.</p>;
  return (
    <ul className="list">
      {state.data.map((c) => {
        const answer = consentAnswer(c.status);
        const sentTo = emailedTo(c.note);
        return (
          <li key={c.id}>
            <StatusBadge tone={answer.tone} label={answer.label} />{" "}
            {labelFor(CONSENT_METHOD_LABELS, c.method)}
            <div className="muted">
              {when(c.created_at)} · form version {c.policy_version}
              {c.captured_by === null ? " · answered by the participant" : ""}
              {c.captured_by === null && sentTo ? ` (link emailed to ${sentTo})` : ""}
            </div>
          </li>
        );
      })}
    </ul>
  );
}

type Opened =
  | { kind: "add" }
  | { kind: "edit" | "history" | "details"; participant: work.Participant }
  /** `problem`: an upload that failed while adding them (D-144). */
  | { kind: "documents"; participant: work.Participant; problem?: string };

/** Uploads the scans chosen on the Add form for someone just added: what was uploaded, and what
 * could not be (with the server's reason). */
async function uploadChosen(projectId: string, participantId: string, files: AddFiles) {
  const done: string[] = [];
  const failed: string[] = [];
  const chosen: [work.DocumentKind, File | null][] = [
    ["CONSENT_FORM", files.consentForm],
    ["ADDRESS_PROOF", files.addressProof],
  ];
  for (const [kind, file] of chosen) {
    if (!file) continue;
    try {
      await sendDocument(projectId, participantId, kind, file);
      done.push(`${DOCUMENT_WORDS[kind]} uploaded.`);
    } catch (err) {
      failed.push(`${DOCUMENT_WORDS[kind]}: ${toApiError(err).message}`);
    }
  }
  return { done, failed };
}

/** The Add or Edit window, with a busy state and an error of its own: each opening starts clean,
 * never showing what went wrong in the window before (FEW-09). */
function ParticipantFormWindow({
  projectId,
  editing,
  languages,
  consentMode,
  rules,
  onSaved,
  close,
  open,
}: {
  projectId: string;
  /** The person edited; null to add someone. */
  editing: work.Participant | null;
  languages: readonly Language[];
  consentMode: ConsentMode | undefined;
  rules: SpeakerRules;
  onSaved: (message: string) => void;
  close: () => void;
  /** Opens another window in its place (their documents, after an upload failed). */
  open: (next: Opened) => void;
}) {
  const { busy, error, run } = useAction();
  const add = async (fields: work.ParticipantFields, files: AddFiles) => {
    const added = await work.createParticipant(projectId, fields);
    const { done, failed } = await uploadChosen(projectId, added.id, files);
    // In a project that takes signed forms the server's word is about emails; the uploads say
    // more.
    const told = consentMode === "UPLOAD" && done.length > 0 ? "" : ` ${added.consent_email}`;
    onSaved(`${added.participant_code} added.${told}${done.map((d) => ` ${d}`).join("")}`);
    if (failed.length === 0) return close();
    // The person stays added; their documents window says what failed, to upload it again.
    open({
      kind: "documents",
      participant: added,
      problem: `${added.participant_code} was added, but this could not be uploaded: ${failed.join(" ")} Upload it here.`,
    });
  };
  return (
    <Modal
      title={editing ? `Edit ${editing.participant_code}` : "Add participant"}
      onClose={close}
      wide
    >
      <ParticipantForm
        initial={editing ? fieldsOf(editing) : EMPTY_PARTICIPANT}
        languages={languages}
        isNew={!editing}
        consentMode={consentMode}
        rules={rules}
        submitLabel={editing ? "Save changes" : "Add participant"}
        busy={busy !== null}
        error={error}
        onSubmit={(fields, files) =>
          void run(async () => {
            if (!editing) return add(fields, files);
            const saved = await work.correctParticipant(projectId, editing.id, fields);
            close();
            onSaved(`${saved.participant_code} saved.`);
          })
        }
      />
    </Modal>
  );
}

/** The windows for one project's participants. `open(...)` shows one; render `dialog`. */
export function useParticipantWindows({
  projectId,
  languages,
  consentMode,
  rules = NO_PROJECT_RULES,
  onSaved,
}: {
  projectId: string;
  languages: readonly Language[];
  /** The project's way of consent (D-144): Upload asks for the signed form on Add. */
  consentMode?: ConsentMode | undefined;
  /** The project's speaker ages and needed details (D-145). */
  rules?: SpeakerRules;
  /** After an add, an edit or an upload, with what to tell the person ("P000003 added. Consent
   * form emailed."). */
  onSaved: (message: string) => void;
}) {
  const [opened, setOpened] = useState<Opened | null>(null);
  const close = () => setOpened(null);
  let dialog: ReactNode = null;
  if (opened?.kind === "add" || opened?.kind === "edit") {
    const editing = opened.kind === "edit" ? opened.participant : null;
    dialog = (
      <ParticipantFormWindow
        key={editing ? editing.id : "add"}
        projectId={projectId}
        editing={editing}
        languages={languages}
        consentMode={consentMode}
        rules={rules}
        onSaved={onSaved}
        close={close}
        open={setOpened}
      />
    );
  } else if (opened?.kind === "history") {
    dialog = (
      <Modal title={`Consent history of ${opened.participant.participant_code}`} onClose={close}>
        <ConsentList projectId={projectId} participantId={opened.participant.id} />
      </Modal>
    );
  } else if (opened?.kind === "details") {
    const code = opened.participant.participant_code;
    dialog = (
      <Modal title="Participant details" onClose={close} wide>
        <ParticipantDetails
          projectId={projectId}
          participantId={opened.participant.id}
          consentMode={consentMode}
          required={rules.required}
          // An upload in the details reloads the list behind and says so (FEW-13).
          onChanged={() => onSaved(`Documents of ${code} updated.`)}
        />
      </Modal>
    );
  } else if (opened?.kind === "documents") {
    dialog = (
      <Modal
        title={`Documents of ${opened.participant.participant_code}`}
        onClose={close}
        size="medium"
      >
        <DocumentsPanel
          projectId={projectId}
          participantId={opened.participant.id}
          problem={opened.problem ?? null}
          onChanged={() => onSaved(`Documents of ${opened.participant.participant_code} updated.`)}
        />
      </Modal>
    );
  }
  return { open: setOpened, dialog };
}
