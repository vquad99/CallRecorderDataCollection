// Shared fields for creating and editing a project (PROJ-001..005).
import { useState, type FormEvent } from "react";

import type { ProjectFields } from "../../api/projects";
import { Button } from "../../components/form/Button";
import { Select } from "../../components/form/Select";
import { TextField } from "../../components/form/TextField";

export const EMPTY_FIELDS: ProjectFields = {
  name: "",
  description: "",
  allows_telephony: true,
  allows_face_to_face: true,
  target_telephony_hours_per_day: "0",
  target_face_to_face_hours_per_day: "0",
  phone_visibility_policy: "ADMINS_ONLY",
  consent_policy_version: "1",
  consent_text: "",
};

export function ProjectForm({
  initial,
  submitLabel,
  busy,
  disabled = false,
  onSubmit,
  extra,
}: {
  initial: ProjectFields;
  submitLabel: string;
  busy: boolean;
  disabled?: boolean;
  onSubmit: (fields: ProjectFields) => void;
  extra?: React.ReactNode;
}) {
  const [f, setF] = useState<ProjectFields>(initial);
  const set = <K extends keyof ProjectFields>(key: K, value: ProjectFields[K]) =>
    setF({ ...f, [key]: value });

  function submit(event: FormEvent) {
    event.preventDefault();
    onSubmit(f);
  }

  return (
    <form onSubmit={submit} noValidate className="card">
      {disabled ? (
        <p className="notice notice--info readonly-note">
          Read only. Only a project administrator can change these settings.
        </p>
      ) : null}
      <fieldset disabled={disabled} className="plain-fieldset">
        {extra}
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
        <fieldset className="field">
          <legend className="field__label">Recording modes allowed</legend>
          <label className="checkbox">
            <input
              type="checkbox"
              checked={f.allows_telephony}
              onChange={(e) => set("allows_telephony", e.target.checked)}
            />
            Telephony
          </label>
          <label className="checkbox">
            <input
              type="checkbox"
              checked={f.allows_face_to_face}
              onChange={(e) => set("allows_face_to_face", e.target.checked)}
            />
            Face-to-face
          </label>
        </fieldset>
        <TextField
          label="Telephony target (hours per day)"
          type="number"
          min={0}
          step="0.5"
          value={f.target_telephony_hours_per_day}
          onChange={(e) => set("target_telephony_hours_per_day", e.target.value)}
        />
        <TextField
          label="Face-to-face target (hours per day)"
          type="number"
          min={0}
          step="0.5"
          value={f.target_face_to_face_hours_per_day}
          onChange={(e) => set("target_face_to_face_hours_per_day", e.target.value)}
        />
        <Select
          label="Who may see participant phone numbers"
          value={f.phone_visibility_policy}
          onChange={(e) =>
            set(
              "phone_visibility_policy",
              e.target.value as ProjectFields["phone_visibility_policy"],
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
