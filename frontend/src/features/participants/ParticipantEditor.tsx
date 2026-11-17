// Adding, editing and looking at one participant, the same on the Participants page and on a
// project's Participants tab: the form, the consent history and the details open in a window next
// to the row that was clicked (D-104).
import { useState, type ReactNode } from "react";

import { ApiError } from "../../api/client";
import type { Language } from "../../api/projects";
import * as work from "../../api/work";
import { Button } from "../../components/form/Button";
import { Select } from "../../components/form/Select";
import { TextField } from "../../components/form/TextField";
import { Modal } from "../../components/Modal";
import { ErrorNotice } from "../../components/Notice";
import { ErrorState, LoadingState } from "../../components/StateViews";
import { StatusBadge } from "../../components/StatusBadge";
import { useAction } from "../../hooks/useAction";
import { useResource } from "../../hooks/useResource";
import { when } from "../../lib/format";
import { CONSENT_METHOD_LABELS, consentAnswer, labelFor } from "../../lib/labels";
import { COUNTRY_CODES, languageOptions, PHONE_DIGITS, splitPhone } from "../projects/choices";
import { ParticipantDetails } from "./ParticipantDetails";
import "./participants.css";

export const EMPTY_PARTICIPANT: work.ParticipantFields = {
  display_label: "",
  phone: null,
  language_code: "",
  dialect: "",
  district: "",
  notes: "",
};

/** Emails the participant the link to their consent form; says what was done. */
export async function emailConsentForm(projectId: string, p: work.Participant): Promise<string> {
  const r = await work.emailPortalLink(projectId, p.id);
  if (!r.sent) {
    throw new ApiError({
      status: 0,
      code: "EMAIL_NOT_SENT",
      message: "The email could not be sent.",
    });
  }
  return `Consent form sent to ${p.participant_code}.`;
}

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
});

export function ParticipantForm({
  initial,
  languages,
  submitLabel,
  onSubmit,
  busy,
  error,
}: {
  initial: work.ParticipantFields;
  languages: readonly Language[]; // the project's languages; empty means any
  submitLabel: string;
  onSubmit: (f: work.ParticipantFields) => void;
  busy: boolean;
  error: ApiError | null;
}) {
  const [f, setF] = useState(initial);
  const [phone, setPhone] = useState(() => splitPhone(initial.phone));
  const phoneError =
    phone.digits && phone.digits.length !== PHONE_DIGITS
      ? `Type exactly ${PHONE_DIGITS} digits (you typed ${phone.digits.length}).`
      : undefined;
  return (
    <form
      onSubmit={(e) => {
        e.preventDefault();
        if (phoneError) return;
        onSubmit({
          ...f,
          phone: phone.digits ? `${phone.cc}${phone.digits}` : null,
          email: f.email?.trim(),
        });
      }}
    >
      <TextField
        label="Name or label"
        required
        value={f.display_label}
        onChange={(e) => setF({ ...f, display_label: e.target.value })}
      />
      <Select
        label="Country code"
        value={phone.cc}
        onChange={(e) => setPhone({ ...phone, cc: e.target.value })}
        options={COUNTRY_CODES.map((c) => ({ value: c.code, label: `${c.code} ${c.name}` }))}
      />
      <TextField
        label="Phone number"
        hint={`${PHONE_DIGITS} digits, without the country code. Needed for phone call tasks.`}
        inputMode="numeric"
        autoComplete="tel-national"
        maxLength={PHONE_DIGITS}
        value={phone.digits}
        {...(phoneError ? { error: phoneError } : {})}
        onChange={(e) => setPhone({ ...phone, digits: e.target.value.replace(/\D/g, "") })}
      />
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
        label="District"
        value={f.district}
        onChange={(e) => setF({ ...f, district: e.target.value })}
      />
      <TextField
        label="Internal notes"
        value={f.notes}
        onChange={(e) => setF({ ...f, notes: e.target.value })}
      />
      <ErrorNotice error={error} />
      <div className="dialog__actions">
        <Button
          type="submit"
          busy={busy}
          disabled={!f.display_label.trim() || !f.language_code.trim() || Boolean(phoneError)}
        >
          {submitLabel}
        </Button>
      </div>
    </form>
  );
}

/** Every consent this participant gave, refused or withdrew, newest first. */
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
        return (
          <li key={c.id}>
            <StatusBadge tone={answer.tone} label={answer.label} />{" "}
            {labelFor(CONSENT_METHOD_LABELS, c.method)}
            <div className="muted">
              {when(c.created_at)} · form version {c.policy_version}
              {c.captured_by === null ? " · answered by the participant" : ""}
            </div>
          </li>
        );
      })}
    </ul>
  );
}

type Opened =
  { kind: "add" } | { kind: "edit" | "history" | "details"; participant: work.Participant };

/** The windows for one project's participants. `open(...)` shows one; render `dialog`. */
export function useParticipantWindows({
  projectId,
  languages,
  onSaved,
}: {
  projectId: string;
  languages: readonly Language[];
  /** After an add or an edit, with what to tell the person ("P000003 added."). */
  onSaved: (message: string) => void;
}) {
  const [opened, setOpened] = useState<Opened | null>(null);
  const { busy, error, run } = useAction();
  const close = () => setOpened(null);
  let dialog: ReactNode = null;
  if (opened?.kind === "add" || opened?.kind === "edit") {
    const editing = opened.kind === "edit" ? opened.participant : null;
    dialog = (
      <Modal
        title={editing ? `Edit ${editing.participant_code}` : "Add participant"}
        onClose={close}
      >
        <ParticipantForm
          initial={editing ? fieldsOf(editing) : EMPTY_PARTICIPANT}
          languages={languages}
          submitLabel={editing ? "Save changes" : "Add participant"}
          busy={busy !== null}
          error={error}
          onSubmit={(fields) =>
            void run(async () => {
              const saved = editing
                ? await work.correctParticipant(projectId, editing.id, fields)
                : await work.createParticipant(projectId, fields);
              close();
              onSaved(`${saved.participant_code} ${editing ? "saved" : "added"}.`);
            })
          }
        />
      </Modal>
    );
  } else if (opened?.kind === "history") {
    dialog = (
      <Modal title={`Consent history of ${opened.participant.participant_code}`} onClose={close}>
        <ConsentList projectId={projectId} participantId={opened.participant.id} />
      </Modal>
    );
  } else if (opened?.kind === "details") {
    dialog = (
      <Modal title="Participant details" onClose={close} wide>
        <ParticipantDetails projectId={projectId} participantId={opened.participant.id} />
      </Modal>
    );
  }
  return { open: setOpened, dialog };
}
