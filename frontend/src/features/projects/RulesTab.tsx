// A project's rules (D-145): what it asks of its speakers, how consent is given and who gives the
// final approval. Every rule a client sets is a project setting; the first client's numbers are
// only what a new project starts with. One card per kind of rule (SECTIONS), all saved together
// through the project's PATCH with "Save rules": a later kind of rule is one more card with its
// fields in the draft. Everyone who sees the project may read them; project admins change them.
import { useId, useState, type ReactNode } from "react";

import * as api from "../../api/projects";
import { useAuth } from "../../auth/AuthContext";
import { Button } from "../../components/form/Button";
import { TextField } from "../../components/form/TextField";
import { IconTile, type IconName } from "../../components/Icon";
import { ErrorNotice, SuccessNotice } from "../../components/Notice";
import { useAction } from "../../hooks/useAction";
import { AGE_LIMITS, SPEAKER_FIELDS, SPEAKER_GROUPS, speakerLabel } from "../../lib/speakers";
import { useProject } from "./ProjectDetailPage";
import "./rules.css";

/** The rules as the form holds them: the ages as typed. */
interface RulesDraft extends Omit<api.ProjectRules, "speaker_min_age" | "speaker_max_age"> {
  speaker_min_age: string;
  speaker_max_age: string;
}

const draftOf = (rules: api.ProjectRules): RulesDraft => ({
  ...rules,
  speaker_min_age: String(rules.speaker_min_age),
  speaker_max_age: String(rules.speaker_max_age),
});

const rulesOf = (draft: RulesDraft): api.ProjectRules => ({
  ...draft,
  speaker_min_age: Number(draft.speaker_min_age),
  speaker_max_age: Number(draft.speaker_max_age),
});

/** What is wrong with the typed ages, by box (the server checks again). */
function ageErrors(draft: RulesDraft): { min?: string; max?: string } {
  const read = (text: string) => {
    const n = Number(text);
    return text.trim() !== "" && Number.isInteger(n) && n >= AGE_LIMITS.min && n <= AGE_LIMITS.max
      ? n
      : null;
  };
  const whole = `Type a whole number from ${AGE_LIMITS.min} to ${AGE_LIMITS.max}.`;
  const min = read(draft.speaker_min_age);
  const max = read(draft.speaker_max_age);
  if (max === null) return min === null ? { min: whole, max: whole } : { max: whole };
  if (min === null) return { min: whole };
  return min > max ? { max: `Must be at least the youngest speaker age (${min}).` } : {};
}

interface SectionProps {
  draft: RulesDraft;
  change: (patch: Partial<RulesDraft>) => void;
}

/** One kind of rule: a card with its heading. */
function RulesCard({
  icon,
  title,
  children,
}: {
  icon: IconName;
  title: string;
  children: ReactNode;
}) {
  const id = useId();
  return (
    <section className="card" aria-labelledby={id}>
      <h2 id={id} className="with-icon">
        <IconTile name={icon} size={28} />
        {title}
      </h2>
      {children}
    </section>
  );
}

/** A checkbox with a line under it that says what it does. */
function Tick({
  label,
  hint,
  checked,
  onChange,
}: {
  label: string;
  hint: string;
  checked: boolean;
  onChange: (checked: boolean) => void;
}) {
  const hintId = useId();
  return (
    <div className="field">
      <label className="checkbox">
        <input
          type="checkbox"
          checked={checked}
          aria-describedby={hintId}
          onChange={(e) => onChange(e.target.checked)}
        />
        {label}
      </label>
      <p id={hintId} className="field__hint">
        {hint}
      </p>
    </div>
  );
}

/** Who may speak (D-145) and who may be paired (D-143). */
function SpeakerRules({ draft, change }: SectionProps) {
  const errors = ageErrors(draft);
  const needed = new Set(draft.required_speaker_details);
  const toggle = (key: string, on: boolean) =>
    change({
      required_speaker_details: SPEAKER_FIELDS.map((f) => f.key).filter((k) =>
        k === key ? on : needed.has(k),
      ),
    });
  const age = (key: "speaker_min_age" | "speaker_max_age", label: string, error?: string) => (
    <TextField
      label={label}
      type="number"
      min={AGE_LIMITS.min}
      max={AGE_LIMITS.max}
      step={1}
      value={draft[key]}
      {...(error ? { error } : {})}
      onChange={(e) => change({ [key]: e.target.value })}
    />
  );
  return (
    <RulesCard icon="people" title="Speakers">
      <div className="form-grid">
        {age("speaker_min_age", "Youngest speaker age", errors.min)}
        {age("speaker_max_age", "Oldest speaker age", errors.max)}
      </div>
      <p className="field__hint rules__note">
        Checked when someone is added to the project, when their age is changed here and when a task
        is made. Ages saved before stay as they are.
      </p>
      <TextField
        label="Conversations per speaker (at most)"
        type="number"
        min={1}
        step={1}
        hint="Cancelled and rejected tasks do not count. Leave empty for no limit."
        value={draft.max_conversations_per_speaker ?? ""}
        onChange={(e) =>
          change({
            max_conversations_per_speaker: e.target.value
              ? Math.max(1, Math.trunc(Number(e.target.value)))
              : null,
          })
        }
      />
      <Tick
        label="Each pair of speakers only once"
        hint="When ticked, two people who already share a task (not cancelled or rejected) cannot be put on another one together. Tasks made before stay as they are."
        checked={draft.unique_pairs}
        onChange={(on) => change({ unique_pairs: on })}
      />
      <fieldset className="field">
        <legend className="field__label">Speaker details needed before a task</legend>
        <p className="field__hint">
          A task is made only for people who have every ticked detail; Add participant asks for
          them. The others may be left empty.
        </p>
        <div className="rules-details">
          {SPEAKER_GROUPS.map((group) => (
            <fieldset key={group.title} className="rules-details__group">
              <legend>{group.title}</legend>
              {group.keys.map((key) => (
                <label key={key} className="checkbox">
                  <input
                    type="checkbox"
                    checked={needed.has(key)}
                    onChange={(e) => toggle(key, e.target.checked)}
                  />
                  {speakerLabel(key)}
                </label>
              ))}
            </fieldset>
          ))}
        </div>
      </fieldset>
    </RulesCard>
  );
}

/** The two ways participants give consent (D-144). */
const CONSENT_MODES: readonly { value: api.ConsentMode; label: string }[] = [
  { value: "ONLINE", label: "Online (participant agrees on their personal page)" },
  { value: "UPLOAD", label: "Upload (scanned signed form)" },
];

function ConsentRules({ draft, change }: SectionProps) {
  const hintId = useId();
  return (
    <RulesCard icon="verified" title="Consent">
      <fieldset className="field" aria-describedby={hintId}>
        <legend className="field__label">How participants give consent</legend>
        {CONSENT_MODES.map((m) => (
          <label key={m.value} className="checkbox">
            <input
              type="radio"
              name="consent_mode"
              value={m.value}
              checked={draft.consent_mode === m.value}
              onChange={() => change({ consent_mode: m.value })}
            />
            {m.label}
          </label>
        ))}
        <p id={hintId} className="field__hint">
          {draft.consent_mode === "UPLOAD"
            ? "No consent form is emailed. Staff upload each person's signed consent form when they add them, and a task needs it. A person who already agreed online still counts."
            : "Everyone who joins the project is emailed the consent form (its text is on the Overview tab) and agrees on their personal page."}
        </p>
      </fieldset>
    </RulesCard>
  );
}

function ApprovalRules({ draft, change }: SectionProps) {
  return (
    <RulesCard icon="ok" title="Approval">
      <Tick
        label="QC pass is the final approval (no admin review)"
        hint="When ticked, a recording the QC Executive passes is approved at once. Tasks already waiting for admin review stay there."
        checked={draft.qc_final_approval}
        onChange={(on) => change({ qc_final_approval: on })}
      />
    </RulesCard>
  );
}

/** The cards, in order: a later kind of rule is one more entry. */
const SECTIONS: readonly { key: string; Section: (props: SectionProps) => ReactNode }[] = [
  { key: "speakers", Section: SpeakerRules },
  { key: "consent", Section: ConsentRules },
  { key: "approval", Section: ApprovalRules },
];

export function RulesTab() {
  const { project, replace } = useProject();
  const { can } = useAuth();
  const canManage = can("projects.manage");
  const canEdit = canManage && project.status !== "ARCHIVED";
  const [draft, setDraft] = useState(() => draftOf(api.projectRules(project)));
  const { busy, error, message, run } = useAction();
  const change = (patch: Partial<RulesDraft>) => setDraft({ ...draft, ...patch });
  const wrong = Object.keys(ageErrors(draft)).length > 0;

  return (
    <form
      className="stack"
      noValidate
      onSubmit={(e) => {
        e.preventDefault();
        if (wrong) return;
        void run(async () => {
          // The Overview's settings go back as they are: the PATCH takes the whole project.
          const saved = await api.updateProject(project.id, {
            ...api.projectSettings(project),
            ...rulesOf(draft),
          });
          replace(saved);
          setDraft(draftOf(api.projectRules(saved)));
          return "Rules saved.";
        });
      }}
    >
      {!canManage ? (
        <p className="notice notice--info">
          Read only. Only a project administrator can change these rules.
        </p>
      ) : !canEdit ? (
        <p className="notice notice--info">Read only. Reopen the project to change its rules.</p>
      ) : null}
      <fieldset disabled={!canEdit} className="plain-fieldset stack">
        {SECTIONS.map(({ key, Section }) => (
          <Section key={key} draft={draft} change={change} />
        ))}
      </fieldset>
      {canEdit ? (
        <Button type="submit" icon="check" busy={busy !== null} disabled={wrong}>
          Save rules
        </Button>
      ) : null}
      <ErrorNotice error={error} />
      <SuccessNotice message={message} />
    </form>
  );
}
