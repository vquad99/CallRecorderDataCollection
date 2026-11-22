// Shared fields for creating and editing a project (PROJ-001..005). The project's rules (speakers,
// pairing, consent, approval) are on its Rules tab (D-145); a new project starts with the defaults.
// A project records one type, face-to-face or phone calls (D-153): two choices, one daily target.
import { useId, useState, type FormEvent } from "react";

import type { ProjectSettings } from "../../api/projects";
import { Button } from "../../components/form/Button";
import { Select } from "../../components/form/Select";
import { TextField } from "../../components/form/TextField";
import { onlyMode, type RecordingMode } from "./recordingType";

/** Filled in on every new project; the admin edits it to fit the project (D-083). */
export const SAMPLE_CONSENT_TEXT = `Consent to be recorded

What this is about
We are collecting recordings of everyday conversations between two people. The recordings help build and test speech technology, such as systems that understand spoken languages.

What will happen
- You will talk with another person for a set time. A moderator records the conversation.
- Only your voice and the conversation are recorded. No video is recorded.
- We note the language and dialect you speak.

How your recording is used and kept
- The recording, with your language and dialect, may be shared with the client of this project for speech research and product development.
- Your name, phone number and email address are never shared with the client.
- Recordings are stored securely and kept only as long as the project needs them.

Your choice
- Taking part is your choice. Saying no has no effect on you.
- You can stop the recording at any time.
- You can withdraw your consent later from your personal page.

Questions
If you have a question, ask the moderator or the project team before you agree.

By clicking "I agree" you confirm that you have read this form, you are 18 years or older, and you agree to be recorded.`;

/** A new project: no recording type chosen yet (D-153), the admin picks one. */
export const EMPTY_FIELDS: ProjectSettings = {
  name: "",
  description: "",
  allows_telephony: false,
  allows_face_to_face: false,
  target_telephony_hours_per_day: "0",
  target_face_to_face_hours_per_day: "0",
  phone_visibility_policy: "ADMINS_ONLY",
  consent_policy_version: "1",
  consent_text: SAMPLE_CONSENT_TEXT,
};

const TYPES: readonly { value: RecordingMode; label: string }[] = [
  { value: "FACE_TO_FACE", label: "Face-to-face" },
  { value: "TELEPHONY", label: "Phone call" },
];
const HOURS_KEY = {
  FACE_TO_FACE: "target_face_to_face_hours_per_day",
  TELEPHONY: "target_telephony_hours_per_day",
} as const;
const CHOOSE_ONE_TYPE = "Choose one recording type: face-to-face or phone call.";

export function ProjectForm({
  initial,
  submitLabel,
  busy,
  disabled = false,
  onSubmit,
}: {
  initial: ProjectSettings;
  submitLabel: string;
  busy: boolean;
  disabled?: boolean;
  onSubmit: (fields: ProjectSettings) => void;
}) {
  const [f, setF] = useState<ProjectSettings>(initial);
  // A project made before D-153 may allow both: nothing is chosen until the admin picks one.
  const [mode, setMode] = useState<RecordingMode | null>(() => onlyMode(initial));
  const [missing, setMissing] = useState(false);
  const both = initial.allows_telephony && initial.allows_face_to_face;
  const typeHint = useId();
  const typeError = useId();
  const set = <K extends keyof ProjectSettings>(key: K, value: ProjectSettings[K]) =>
    setF({ ...f, [key]: value });

  function submit(event: FormEvent) {
    event.preventDefault();
    if (mode === null) {
      setMissing(true);
      return;
    }
    // The one type, and a daily target only for it (the server refuses one for the other).
    const other = HOURS_KEY[mode === "TELEPHONY" ? "FACE_TO_FACE" : "TELEPHONY"];
    onSubmit({
      ...f,
      allows_face_to_face: mode === "FACE_TO_FACE",
      allows_telephony: mode === "TELEPHONY",
      [other]: Number(f[other]) > 0 ? "0" : f[other],
    });
  }

  return (
    <form onSubmit={submit} noValidate className="card">
      {disabled ? (
        <p className="notice notice--info readonly-note">
          Read only. Only a project administrator can change these settings.
        </p>
      ) : null}
      <fieldset disabled={disabled} className="plain-fieldset">
        <TextField
          label="Name"
          required
          value={f.name}
          onChange={(e) => set("name", e.target.value)}
        />
        <div className="field">
          <label htmlFor="project-description" className="field__label">
            Description
          </label>
          <textarea
            id="project-description"
            className="field__input"
            rows={3}
            value={f.description}
            onChange={(e) => set("description", e.target.value)}
          />
        </div>
        {both ? (
          <p className="notice notice--info">
            {disabled
              ? "This project allows both types: it was made before a project recorded one type."
              : "This project allows both types. Choose one: from now on a project records one type."}
          </p>
        ) : null}
        <fieldset
          className="field"
          aria-describedby={missing && mode === null ? `${typeHint} ${typeError}` : typeHint}
        >
          <legend className="field__label">
            Recording type <span aria-hidden="true">*</span>
          </legend>
          {TYPES.map((t) => (
            <label key={t.value} className="checkbox">
              <input
                type="radio"
                name="recording_type"
                value={t.value}
                checked={mode === t.value}
                aria-invalid={missing && mode === null ? true : undefined}
                onChange={() => setMode(t.value)}
              />
              {t.label}
            </label>
          ))}
          <p id={typeHint} className="field__hint">
            A project records one type. For the other, make another project.
          </p>
          {missing && mode === null ? (
            <p id={typeError} className="field__error">
              {CHOOSE_ONE_TYPE}
            </p>
          ) : null}
        </fieldset>
        {mode !== null ? (
          <TextField
            label={`${mode === "TELEPHONY" ? "Phone call" : "Face-to-face"} target (hours per day)`}
            type="number"
            min={0}
            step="0.5"
            value={f[HOURS_KEY[mode]]}
            onChange={(e) => set(HOURS_KEY[mode], e.target.value)}
          />
        ) : null}
        <Select
          label="Who may see participant phone numbers"
          value={f.phone_visibility_policy}
          onChange={(e) =>
            set(
              "phone_visibility_policy",
              e.target.value as ProjectSettings["phone_visibility_policy"],
            )
          }
          options={[
            { value: "ADMINS_ONLY", label: "Project admins only" },
            { value: "ASSIGNED_MODERATOR", label: "Project admins and the assigned moderator" },
          ]}
        />
        <TextField
          label="Consent policy version"
          required
          value={f.consent_policy_version}
          onChange={(e) => set("consent_policy_version", e.target.value)}
        />
        <div className="field">
          <label htmlFor="consent-text" className="field__label">
            Consent form text
          </label>
          <p id="consent-text-hint" className="field__hint">
            Participants read and answer this on their personal page. Change the version above when
            you change the text.
          </p>
          <textarea
            id="consent-text"
            className="field__input"
            rows={8}
            maxLength={20000}
            aria-describedby="consent-text-hint"
            value={f.consent_text}
            onChange={(e) => set("consent_text", e.target.value)}
          />
        </div>
        {disabled ? null : (
          <Button type="submit" busy={busy}>
            {submitLabel}
          </Button>
        )}
      </fieldset>
    </form>
  );
}
