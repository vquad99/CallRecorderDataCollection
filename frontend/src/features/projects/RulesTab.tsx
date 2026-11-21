// A project's rules (D-145): what it asks of its speakers, how consent is given, who gives the
// final approval, what QC checks (D-146), and what the moderator fills and reads (device details
// and reminders, D-147). Every rule a client sets is a project setting; the first client's
// numbers are only what a new project starts with. One card per kind of rule (SECTIONS), all
// saved together through the project's PATCH with "Save rules": a later kind of rule is one more
// card with its fields in the draft. Everyone who sees the project may read them; project admins
// change them.
import { useId, useState, type KeyboardEvent, type ReactNode } from "react";

import * as api from "../../api/projects";
import { useAuth } from "../../auth/AuthContext";
import { Button, IconButton } from "../../components/form/Button";
import { Select } from "../../components/form/Select";
import { TextField } from "../../components/form/TextField";
import { IconTile, type IconName } from "../../components/Icon";
import { ErrorNotice, SuccessNotice } from "../../components/Notice";
import { useAction } from "../../hooks/useAction";
import { AGE_LIMITS, SPEAKER_FIELDS, SPEAKER_GROUPS, speakerLabel } from "../../lib/speakers";
import { DEVICE_FIELDS } from "../tasks/deviceFields";
import { useProject } from "./ProjectDetailPage";
import {
  CLIENT_QC_CHECKLIST,
  keyProblem,
  MAX_ITEMS,
  MAX_KEY,
  MAX_QUESTION,
  questionProblem,
} from "./qcChecklist";
import {
  CLIENT_REMINDERS,
  linesOf,
  linesProblem,
  MAX_LINE,
  MAX_LINES,
  REMINDER_LISTS,
} from "./reminders";
import "./rules.css";

/** The reminders as the form holds them: each list as the text of its box, one line per entry. */
type ReminderTexts = { speaker_id: boolean } & Record<ReminderList, string>;
type ReminderList = (typeof REMINDER_LISTS)[number]["key"];

/** The rules as the form holds them: the ages and the reminders as typed. */
interface RulesDraft extends Omit<
  api.ProjectRules,
  "speaker_min_age" | "speaker_max_age" | "recording_reminders"
> {
  speaker_min_age: string;
  speaker_max_age: string;
  recording_reminders: ReminderTexts;
}

const textsOf = (r: api.Reminders): ReminderTexts => ({
  speaker_id: r.speaker_id,
  topics: r.topics.join("\n"),
  avoid: r.avoid.join("\n"),
  face_to_face: r.face_to_face.join("\n"),
  telephony: r.telephony.join("\n"),
});

const draftOf = (rules: api.ProjectRules): RulesDraft => ({
  ...rules,
  speaker_min_age: String(rules.speaker_min_age),
  speaker_max_age: String(rules.speaker_max_age),
  recording_reminders: textsOf(rules.recording_reminders),
});

const rulesOf = (draft: RulesDraft): api.ProjectRules => {
  const texts = draft.recording_reminders;
  return {
    ...draft,
    speaker_min_age: Number(draft.speaker_min_age),
    speaker_max_age: Number(draft.speaker_max_age),
    recording_reminders: {
      speaker_id: texts.speaker_id,
      topics: linesOf(texts.topics),
      avoid: linesOf(texts.avoid),
      face_to_face: linesOf(texts.face_to_face),
      telephony: linesOf(texts.telephony),
    },
  };
};

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

/** The checklist's problems, by question number (the server checks again). */
function checklistErrors(draft: RulesDraft): Record<number, string> {
  const errors: Record<number, string> = {};
  draft.qc_checklist.forEach((item, i) => {
    const problem = questionProblem(item.question);
    if (problem) errors[i] = problem;
  });
  return errors;
}

const SCOPES: readonly { value: api.ChecklistItem["scope"]; label: string }[] = [
  { value: "conversation", label: "The conversation (answered once)" },
  { value: "speaker", label: "Each speaker (answered for both)" },
];
const FAILS: readonly { value: string; label: string }[] = [
  { value: "no", label: "No" },
  { value: "yes", label: "Yes" },
  { value: "", label: "Never (observation only)" },
];

/** One question of the checklist: its words, what it applies to, when it fails, required. */
function ChecklistRow({
  item,
  index,
  count,
  error,
  onChange,
  onMove,
  onRemove,
}: {
  item: api.ChecklistItem;
  index: number;
  count: number;
  error: string | undefined;
  onChange: (item: api.ChecklistItem) => void;
  onMove: (by: -1 | 1) => void;
  onRemove: () => void;
}) {
  return (
    <li>
      <fieldset className="qc-rule">
        <legend className="qc-rule__head">
          <span className="qc-rule__number">{index + 1}.</span>{" "}
          <span className="code-tag">{item.key}</span>
        </legend>
        <span className="qc-rule__tools">
          <IconButton
            icon="up"
            label={`Move ${item.key} up`}
            disabled={index === 0}
            onClick={() => onMove(-1)}
          />
          <IconButton
            icon="down"
            label={`Move ${item.key} down`}
            disabled={index === count - 1}
            onClick={() => onMove(1)}
          />
          <IconButton icon="trash" label={`Remove ${item.key}`} onClick={onRemove} />
        </span>
        <TextField
          label="Question"
          value={item.question}
          maxLength={MAX_QUESTION}
          {...(error ? { error } : {})}
          onChange={(e) => onChange({ ...item, question: e.target.value })}
        />
        <div className="form-grid">
          <Select
            label="Applies to"
            value={item.scope}
            options={SCOPES}
            onChange={(e) =>
              onChange({ ...item, scope: e.target.value as api.ChecklistItem["scope"] })
            }
          />
          <Select
            label="The recording fails when the answer is"
            value={item.fails_on ?? ""}
            options={FAILS}
            onChange={(e) =>
              onChange({
                ...item,
                fails_on: (e.target.value || null) as api.ChecklistItem["fails_on"],
              })
            }
          />
        </div>
        <label className="checkbox">
          <input
            type="checkbox"
            checked={item.required}
            onChange={(e) => onChange({ ...item, required: e.target.checked })}
          />
          Required (answered before Pass)
        </label>
      </fieldset>
    </li>
  );
}

/** The questions the QC Executive answers Yes or No for each recording (D-146). */
function QcChecklistRules({ draft, change }: SectionProps) {
  const items = draft.qc_checklist;
  const errors = checklistErrors(draft);
  const [key, setKey] = useState("");
  const [question, setQuestion] = useState("");
  const [tried, setTried] = useState(false);
  const keyError = keyProblem(key, items);
  const newError = questionProblem(question);
  const full = items.length >= MAX_ITEMS;
  const set = (next: api.ChecklistItem[]) => change({ qc_checklist: next });
  const add = () => {
    setTried(true);
    if (keyError || newError || full) return;
    set([
      ...items,
      { key, question: question.trim(), scope: "conversation", fails_on: "no", required: true },
    ]);
    setKey("");
    setQuestion("");
    setTried(false);
  };
  const move = (i: number, by: -1 | 1) => {
    const next = [...items];
    const [item] = next.splice(i, 1);
    if (item) next.splice(i + by, 0, item);
    set(next);
  };
  // Enter in the new question's boxes adds it, instead of saving the rules.
  const onEnter = (e: KeyboardEvent) => {
    if (e.key === "Enter") {
      e.preventDefault();
      add();
    }
  };
  return (
    <RulesCard icon="tasks" title="QC checklist">
      <p className="field__hint rules__note">
        The QC Executive answers Yes or No to each question for every recording: questions about the
        conversation once, questions about the speakers for each person. A recording passes only
        when every required question is answered and no answer fails it. Answers already given keep
        the questions as they read then.
      </p>
      <p className="muted">
        {items.length === 1 ? "1 question" : `${items.length} questions`} (at most {MAX_ITEMS}).
      </p>
      {items.length > 0 ? (
        <ol className="qc-rules">
          {items.map((item, i) => (
            <ChecklistRow
              key={item.key}
              item={item}
              index={i}
              count={items.length}
              error={errors[i]}
              onChange={(next) => set(items.map((x, j) => (j === i ? next : x)))}
              onMove={(by) => move(i, by)}
              onRemove={() => set(items.filter((_, j) => j !== i))}
            />
          ))}
        </ol>
      ) : (
        <p className="muted">No questions: QC checks only the consent forms.</p>
      )}
      <fieldset className="qc-rule qc-rule--new">
        <legend className="qc-rule__head">Add a question</legend>
        <div className="form-grid">
          <TextField
            label="Key"
            hint="Lowercase letters, digits and _, like speech_intelligible. It names the answer in the delivery."
            value={key}
            maxLength={MAX_KEY}
            {...(tried && keyError ? { error: keyError } : {})}
            onChange={(e) => setKey(e.target.value.trim())}
            onKeyDown={onEnter}
          />
          <TextField
            label="New question"
            value={question}
            maxLength={MAX_QUESTION}
            {...(tried && newError ? { error: newError } : {})}
            onChange={(e) => setQuestion(e.target.value)}
            onKeyDown={onEnter}
          />
        </div>
        <div className="actions">
          <Button variant="secondary" icon="plus" disabled={full} onClick={add}>
            Add question
          </Button>
          <Button
            variant="secondary"
            icon="history"
            onClick={() => set(CLIENT_QC_CHECKLIST.map((i) => ({ ...i })))}
          >
            Reset to the client&apos;s list
          </Button>
        </div>
        {full ? <p className="muted">The list is full ({MAX_ITEMS} questions).</p> : null}
      </fieldset>
    </RulesCard>
  );
}

/** What the moderator fills for each speaker before sending a recording to QC (D-147). */
function DeviceRules({ draft, change }: SectionProps) {
  const asked = new Set(draft.device_fields);
  const toggle = (key: api.DeviceField, on: boolean) =>
    change({
      device_fields: DEVICE_FIELDS.map((f) => f.key).filter((k) => (k === key ? on : asked.has(k))),
    });
  return (
    <RulesCard icon="phone" title="Device details">
      <p className="field__hint rules__note">
        The moderator fills these for each speaker of every conversation; a recording goes to QC
        only when the ticked ones are filled. The call type (Telephonic or Face-to-face) comes from
        the task.
      </p>
      <fieldset className="field">
        <legend className="field__label">Asked for each speaker</legend>
        {DEVICE_FIELDS.map((f) => (
          <label key={f.key} className="checkbox">
            <input
              type="checkbox"
              checked={asked.has(f.key)}
              onChange={(e) => toggle(f.key, e.target.checked)}
            />
            {f.label}
            {f.yesNo ? " (Yes / No)" : ""}
          </label>
        ))}
      </fieldset>
      {asked.size === 0 ? (
        <p className="muted">Nothing ticked: no device details are asked.</p>
      ) : null}
    </RulesCard>
  );
}

/** What is wrong with each reminder box, by list (the server checks again). */
function reminderErrors(draft: RulesDraft): Partial<Record<ReminderList, string>> {
  const errors: Partial<Record<ReminderList, string>> = {};
  for (const { key } of REMINDER_LISTS) {
    const problem = linesProblem(draft.recording_reminders[key]);
    if (problem) errors[key] = problem;
  }
  return errors;
}

/** One box of lines, one entry per line. */
function LinesBox({
  label,
  hint,
  value,
  error,
  onChange,
}: {
  label: string;
  hint: string;
  value: string;
  error: string | undefined;
  onChange: (value: string) => void;
}) {
  const id = useId();
  return (
    <div className={`field${error ? " field--invalid" : ""}`}>
      <label htmlFor={id} className="field__label">
        {label}
      </label>
      <p id={`${id}-hint`} className="field__hint">
        {hint}
      </p>
      <textarea
        id={id}
        className="field__input"
        rows={Math.min(8, Math.max(3, value.split("\n").length))}
        value={value}
        aria-invalid={error ? true : undefined}
        aria-describedby={error ? `${id}-hint ${id}-error` : `${id}-hint`}
        onChange={(e) => onChange(e.target.value)}
      />
      {error ? (
        <p id={`${id}-error`} className="field__error">
          {error}
        </p>
      ) : null}
    </div>
  );
}

/** What the moderator reads before recording and calling (D-147). */
function ReminderRules({ draft, change }: SectionProps) {
  const texts = draft.recording_reminders;
  const errors = reminderErrors(draft);
  const set = (patch: Partial<ReminderTexts>) =>
    change({ recording_reminders: { ...texts, ...patch } });
  return (
    <RulesCard icon="mic" title="Reminders for moderators">
      <p className="field__hint rules__note">
        Shown on the recorder before Start recording and on the call card before Start call, with
        the task&apos;s own speakers. At most {MAX_LINES} lines per box, {MAX_LINE} characters per
        line.
      </p>
      <Tick
        label="Ask each speaker to start with their first name and speaker ID"
        hint="“I am <first name> and speaker ID <code>”, with each speaker's code (their name only for people who may see it)."
        checked={texts.speaker_id}
        onChange={(on) => set({ speaker_id: on })}
      />
      <div className="rules-reminders">
        {REMINDER_LISTS.map(({ key, label, hint }) => (
          <LinesBox
            key={key}
            label={label}
            hint={hint}
            value={texts[key]}
            error={errors[key]}
            onChange={(value) => set({ [key]: value })}
          />
        ))}
      </div>
      <div className="actions">
        <Button
          variant="secondary"
          icon="history"
          onClick={() => change({ recording_reminders: textsOf(CLIENT_REMINDERS) })}
        >
          Reset to the client&apos;s text
        </Button>
      </div>
    </RulesCard>
  );
}

/** The cards, in order: a later kind of rule is one more entry. */
const SECTIONS: readonly { key: string; Section: (props: SectionProps) => ReactNode }[] = [
  { key: "speakers", Section: SpeakerRules },
  { key: "consent", Section: ConsentRules },
  { key: "approval", Section: ApprovalRules },
  { key: "qc-checklist", Section: QcChecklistRules },
  { key: "devices", Section: DeviceRules },
  { key: "reminders", Section: ReminderRules },
];

export function RulesTab() {
  const { project, replace } = useProject();
  const { can } = useAuth();
  const canManage = can("projects.manage");
  const canEdit = canManage && project.status !== "ARCHIVED";
  const [draft, setDraft] = useState(() => draftOf(api.projectRules(project)));
  const { busy, error, message, run } = useAction();
  const change = (patch: Partial<RulesDraft>) => setDraft({ ...draft, ...patch });
  const wrong =
    Object.keys(ageErrors(draft)).length > 0 ||
    Object.keys(checklistErrors(draft)).length > 0 ||
    Object.keys(reminderErrors(draft)).length > 0;

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
