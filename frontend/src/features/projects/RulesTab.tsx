// A project's rules (D-145): what it asks of its speakers, how consent is given, who gives the
// final approval, what QC checks (D-146), what the moderator fills and reads (device details
// and reminders, D-147), the audio, progress and target settings (D-148), and how exports are laid
// out and named (D-149). Every rule a client sets is a project setting; the first client's numbers
// are only what a new project starts with. One card per kind of rule (SECTIONS), all
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
import {
  AGE_LIMITS,
  INDIAN_STATES,
  SPEAKER_FIELDS,
  SPEAKER_GROUPS,
  speakerLabel,
} from "../../lib/speakers";
import { DEVICE_FIELDS } from "../tasks/deviceFields";
import { audioNameProblem, CLIENT_AUDIO_NAME, exampleAudioName, MAX_AUDIO_NAME } from "./delivery";
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
import {
  bandsProblem,
  CLIENT_AGE_BANDS,
  CLIENT_DISTRICTS,
  districtsProblem,
  MAX_BANDS,
  MAX_DISTRICTS,
  PAUSE_LIMITS,
  pauseLimitOf,
  percentsProblem,
} from "./targets";
import "./rules.css";

/** The reminders as the form holds them: each list as the text of its box, one line per entry. */
type ReminderTexts = { speaker_id: boolean } & Record<ReminderList, string>;
type ReminderList = (typeof REMINDER_LISTS)[number]["key"];

/** An age band as typed (D-148). */
interface BandTexts {
  from: string;
  to: string;
  percent: string;
}

/** The targets as typed (D-148): an empty box is no target. */
interface TargetTexts {
  hours: string;
  speakers: string;
  conversations: string;
  bands: BandTexts[];
  male: string;
  female: string;
  face_to_face: string;
  telephony: string;
  districts: api.TargetDistrict[];
}

type TargetKey =
  | "target_hours"
  | "target_speakers"
  | "target_conversations"
  | "target_age_bands"
  | "target_gender"
  | "target_modes"
  | "target_districts";

/** The rules as the form holds them: the ages, the reminders, the pause limit and the targets as
 * typed. */
interface RulesDraft extends Omit<
  api.ProjectRules,
  "speaker_min_age" | "speaker_max_age" | "recording_reminders" | "pause_limit_seconds" | TargetKey
> {
  speaker_min_age: string;
  speaker_max_age: string;
  recording_reminders: ReminderTexts;
  pause_limit_seconds: string;
  targets: TargetTexts;
}

const textsOf = (r: api.Reminders): ReminderTexts => ({
  speaker_id: r.speaker_id,
  topics: r.topics.join("\n"),
  avoid: r.avoid.join("\n"),
  face_to_face: r.face_to_face.join("\n"),
  telephony: r.telephony.join("\n"),
});

const text = (n: number | null | undefined) => (n === null || n === undefined ? "" : String(n));
const bandTexts = (bands: readonly api.AgeBand[]): BandTexts[] =>
  bands.map((b) => ({ from: String(b.from), to: String(b.to), percent: String(b.percent) }));

const targetTextsOf = (rules: api.ProjectRules): TargetTexts => ({
  hours: rules.target_hours === null ? "" : String(Number(rules.target_hours)),
  speakers: text(rules.target_speakers),
  conversations: text(rules.target_conversations),
  bands: bandTexts(rules.target_age_bands),
  male: text(rules.target_gender.MALE),
  female: text(rules.target_gender.FEMALE),
  face_to_face: text(rules.target_modes.FACE_TO_FACE),
  telephony: text(rules.target_modes.TELEPHONY),
  districts: rules.target_districts.map((d) => ({ ...d })),
});

const draftOf = (rules: api.ProjectRules): RulesDraft => ({
  ...rules,
  speaker_min_age: String(rules.speaker_min_age),
  speaker_max_age: String(rules.speaker_max_age),
  recording_reminders: textsOf(rules.recording_reminders),
  pause_limit_seconds: String(rules.pause_limit_seconds),
  targets: targetTextsOf(rules),
});

/** A typed number, or null for an empty box. */
const numberOf = (value: string): number | null => (value.trim() === "" ? null : Number(value));

/** Percents for two keys: none typed is no target. */
function sharesOf<K extends string>(pairs: [K, string][]): Partial<Record<K, number>> {
  if (pairs.every(([, v]) => v.trim() === "")) return {};
  return Object.fromEntries(pairs.map(([k, v]) => [k, Number(v)])) as Partial<Record<K, number>>;
}

const rulesOf = (draft: RulesDraft): api.ProjectRules => {
  const { targets, ...rest } = draft;
  const texts = draft.recording_reminders;
  return {
    ...rest,
    speaker_min_age: Number(draft.speaker_min_age),
    speaker_max_age: Number(draft.speaker_max_age),
    recording_reminders: {
      speaker_id: texts.speaker_id,
      topics: linesOf(texts.topics),
      avoid: linesOf(texts.avoid),
      face_to_face: linesOf(texts.face_to_face),
      telephony: linesOf(texts.telephony),
    },
    pause_limit_seconds: Number(draft.pause_limit_seconds),
    target_hours: targets.hours.trim() === "" ? null : targets.hours.trim(),
    target_speakers: numberOf(targets.speakers),
    target_conversations: numberOf(targets.conversations),
    target_age_bands: targets.bands.map((b) => ({
      from: Number(b.from),
      to: Number(b.to),
      percent: Number(b.percent),
    })),
    target_gender: sharesOf([
      ["MALE", targets.male],
      ["FEMALE", targets.female],
    ]),
    target_modes: sharesOf([
      ["FACE_TO_FACE", targets.face_to_face],
      ["TELEPHONY", targets.telephony],
    ]),
    target_districts: targets.districts.map((d) => ({
      state: d.state,
      district: d.district.split(/\s+/).filter(Boolean).join(" "),
    })),
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

type TargetErrors = Partial<
  Record<
    "pause" | "hours" | "speakers" | "conversations" | "bands" | "gender" | "modes" | "districts",
    string
  >
>;

/** What is wrong with the audio, progress and target settings, by box (the server checks
 * again). */
function targetErrors(draft: RulesDraft): TargetErrors {
  const t = draft.targets;
  const errors: TargetErrors = {};
  if (pauseLimitOf(draft.pause_limit_seconds) === null)
    errors.pause = `Type a whole number of seconds from ${PAUSE_LIMITS.min} to ${PAUSE_LIMITS.max}.`;
  if (t.hours.trim() !== "" && !/^\d+(\.\d{1,2})?$/.test(t.hours.trim()))
    errors.hours = "Type hours as a number with at most two decimals, or leave it empty.";
  for (const key of ["speakers", "conversations"] as const) {
    const n = numberOf(t[key]);
    if (n !== null && !(Number.isInteger(n) && n >= 1))
      errors[key] = "Type a whole number from 1, or leave it empty.";
  }
  const bands = t.bands.map((b) => ({
    from: Number(b.from || NaN),
    to: Number(b.to || NaN),
    percent: Number(b.percent || NaN),
  }));
  const bandError = bandsProblem(bands);
  if (bandError) errors.bands = bandError;
  for (const [key, pair] of [
    ["gender", [t.male, t.female]],
    ["modes", [t.face_to_face, t.telephony]],
  ] as const) {
    if (pair.every((v) => v.trim() === "")) continue;
    const problem = pair.some((v) => v.trim() === "")
      ? "Give both percents, or leave both empty for no target."
      : percentsProblem(pair.map(Number));
    if (problem) errors[key] = problem;
  }
  const districtError = districtsProblem(t.districts);
  if (districtError) errors.districts = districtError;
  return errors;
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

/** What counts as completed minutes (D-148). */
const COUNTS: readonly { value: api.ProgressCounts; label: string }[] = [
  { value: "EFFECTIVE", label: "Effective speech (the time someone speaks)" },
  { value: "FULL", label: "Full length of the recordings" },
];

/** Long pauses and what completed minutes count (D-148). The length limits stay on the Audio
 * rules tab. */
function AudioProgressRules({ draft, change }: SectionProps) {
  const errors = targetErrors(draft);
  const hintId = useId();
  return (
    <RulesCard icon="waveform" title="Audio and progress">
      <p className="field__hint rules__note">
        Effective speech is the time someone speaks: the recording without its silences (gaps under
        0.3 s between words count as speech). A long pause is a silence inside the conversation
        longer than the limit; silence before the first word and after the last is not a pause.
      </p>
      <TextField
        label="Long pause (seconds)"
        type="number"
        min={PAUSE_LIMITS.min}
        max={PAUSE_LIMITS.max}
        step={1}
        hint="The automatic check counts the pauses longer than this and shows the longest."
        value={draft.pause_limit_seconds}
        {...(errors.pause ? { error: errors.pause } : {})}
        onChange={(e) => change({ pause_limit_seconds: e.target.value })}
      />
      <Tick
        label="Long pauses need a listen"
        hint="When ticked, a recording with a long pause is marked “Listen and decide” by the automatic check. Otherwise the pauses are only shown."
        checked={draft.long_pauses_need_review}
        onChange={(on) => change({ long_pauses_need_review: on })}
      />
      <fieldset className="field" aria-describedby={hintId}>
        <legend className="field__label">Completed minutes count</legend>
        {COUNTS.map((c) => (
          <label key={c.value} className="checkbox">
            <input
              type="radio"
              name="progress_counts"
              value={c.value}
              checked={draft.progress_counts === c.value}
              onChange={() => change({ progress_counts: c.value })}
            />
            {c.label}
          </label>
        ))}
        <p id={hintId} className="field__hint">
          What the Progress tab and the dashboard count as completed for approved conversations.
          Payments always count the full length.
        </p>
      </fieldset>
    </RulesCard>
  );
}

/** Two percents that add up to 100, or both empty for no target. */
function PercentPair({
  legend,
  hint,
  labels,
  values,
  error,
  onChange,
}: {
  legend: string;
  hint: string;
  labels: [string, string];
  values: [string, string];
  error: string | undefined;
  onChange: (values: [string, string]) => void;
}) {
  const hintId = useId();
  const errorId = useId();
  const box = (i: 0 | 1) => (
    <TextField
      label={labels[i]}
      type="number"
      min={0}
      max={100}
      step={1}
      value={values[i]}
      aria-invalid={error ? true : undefined}
      onChange={(e) =>
        onChange(i === 0 ? [e.target.value, values[1]] : [values[0], e.target.value])
      }
    />
  );
  return (
    <fieldset className="field" aria-describedby={error ? `${hintId} ${errorId}` : hintId}>
      <legend className="field__label">{legend}</legend>
      <p id={hintId} className="field__hint">
        {hint}
      </p>
      <div className="form-grid">
        {box(0)}
        {box(1)}
      </div>
      {error ? (
        <p id={errorId} className="field__error">
          {error}
        </p>
      ) : null}
    </fieldset>
  );
}

/** The collection targets (D-148), shown against what was collected on the Progress tab. */
function TargetRules({ draft, change }: SectionProps) {
  const t = draft.targets;
  const errors = targetErrors(draft);
  const set = (patch: Partial<TargetTexts>) => change({ targets: { ...t, ...patch } });
  const setBand = (i: number, patch: Partial<BandTexts>) =>
    set({ bands: t.bands.map((b, j) => (j === i ? { ...b, ...patch } : b)) });
  const setDistrict = (i: number, patch: Partial<api.TargetDistrict>) =>
    set({ districts: t.districts.map((d, j) => (j === i ? { ...d, ...patch } : d)) });
  const share = t.districts.length > 0 ? Math.round(10000 / t.districts.length) / 100 : 0;
  const counted = draft.progress_counts === "FULL" ? "full length" : "effective speech";
  const whole = (label: string, key: "speakers" | "conversations") => (
    <TextField
      label={label}
      type="number"
      min={1}
      step={1}
      hint="Leave empty for no target."
      value={t[key]}
      {...(errors[key] ? { error: errors[key] } : {})}
      onChange={(e) => set({ [key]: e.target.value })}
    />
  );
  return (
    <RulesCard icon="target" title="Targets">
      <p className="field__hint rules__note">
        The Progress tab shows what was collected against these. Age, gender and districts are
        shares of the speakers with an approved conversation; face-to-face and phone are shares of
        the approved conversations. The first client&apos;s targets are where a project starts.
      </p>
      <div className="form-grid">
        <TextField
          label="Hours completed"
          type="number"
          min={0}
          step={0.5}
          hint={`Approved conversations, counted as ${counted}. Leave empty for no target.`}
          value={t.hours}
          {...(errors.hours ? { error: errors.hours } : {})}
          onChange={(e) => set({ hours: e.target.value })}
        />
        {whole("Speakers", "speakers")}
        {whole("Conversations", "conversations")}
      </div>
      <fieldset className="field">
        <legend className="field__label">Age bands (percent of speakers)</legend>
        <p className="field__hint">
          A band takes the ages from its first age up to, but not including, its last; the band that
          ends highest also takes its last age. The percents add up to 100; no bands is no age
          target.
        </p>
        {t.bands.length > 0 ? (
          <ol className="target-rows">
            {t.bands.map((b, i) => (
              <li key={i} className="target-row">
                <TextField
                  label="From age"
                  type="number"
                  min={AGE_LIMITS.min}
                  max={AGE_LIMITS.max}
                  value={b.from}
                  onChange={(e) => setBand(i, { from: e.target.value })}
                />
                <TextField
                  label="To age"
                  type="number"
                  min={AGE_LIMITS.min}
                  max={AGE_LIMITS.max}
                  value={b.to}
                  onChange={(e) => setBand(i, { to: e.target.value })}
                />
                <TextField
                  label="Percent"
                  type="number"
                  min={0}
                  max={100}
                  value={b.percent}
                  onChange={(e) => setBand(i, { percent: e.target.value })}
                />
                <IconButton
                  icon="trash"
                  label={`Remove age band ${b.from}-${b.to}`}
                  onClick={() => set({ bands: t.bands.filter((_, j) => j !== i) })}
                />
              </li>
            ))}
          </ol>
        ) : (
          <p className="muted">No age bands: no age target.</p>
        )}
        {errors.bands ? <p className="field__error">{errors.bands}</p> : null}
        <div className="actions">
          <Button
            variant="secondary"
            icon="plus"
            disabled={t.bands.length >= MAX_BANDS}
            onClick={() => set({ bands: [...t.bands, { from: "", to: "", percent: "" }] })}
          >
            Add age band
          </Button>
          <Button
            variant="secondary"
            icon="history"
            onClick={() => set({ bands: bandTexts(CLIENT_AGE_BANDS) })}
          >
            Reset to the client&apos;s age bands
          </Button>
        </div>
      </fieldset>
      <PercentPair
        legend="Gender (percent of speakers)"
        hint="Both empty: no gender target."
        labels={["Male (%)", "Female (%)"]}
        values={[t.male, t.female]}
        error={errors.gender}
        onChange={([male, female]) => set({ male, female })}
      />
      <PercentPair
        legend="Face-to-face and phone (percent of approved conversations)"
        hint="Both empty: no target."
        labels={["Face-to-face (%)", "Phone call (%)"]}
        values={[t.face_to_face, t.telephony]}
        error={errors.modes}
        onChange={([face_to_face, telephony]) => set({ face_to_face, telephony })}
      />
      <fieldset className="field">
        <legend className="field__label">Districts (by native district)</legend>
        <p className="field__hint">
          Each listed district is expected to give an equal share of the speakers
          {t.districts.length > 0
            ? `: ${share} % each for ${t.districts.length}.`
            : ". None listed: the Progress tab shows the speakers' own districts."}
        </p>
        {t.districts.length > 0 ? (
          <ol className="target-rows">
            {t.districts.map((d, i) => (
              <li key={i} className="target-row target-row--district">
                <Select
                  label="State"
                  value={d.state}
                  options={[
                    { value: "", label: "Choose a state" },
                    ...INDIAN_STATES.map((s) => ({ value: s, label: s })),
                  ]}
                  onChange={(e) => setDistrict(i, { state: e.target.value })}
                />
                <TextField
                  label="District"
                  value={d.district}
                  maxLength={100}
                  onChange={(e) => setDistrict(i, { district: e.target.value })}
                />
                <IconButton
                  icon="trash"
                  label={`Remove ${d.district || `district ${i + 1}`}`}
                  onClick={() => set({ districts: t.districts.filter((_, j) => j !== i) })}
                />
              </li>
            ))}
          </ol>
        ) : null}
        {errors.districts ? <p className="field__error">{errors.districts}</p> : null}
        <div className="actions">
          <Button
            variant="secondary"
            icon="plus"
            disabled={t.districts.length >= MAX_DISTRICTS}
            onClick={() => set({ districts: [...t.districts, { state: "", district: "" }] })}
          >
            Add district
          </Button>
          <Button
            variant="secondary"
            icon="history"
            onClick={() => set({ districts: CLIENT_DISTRICTS.map((d) => ({ ...d })) })}
          >
            Use the client&apos;s Konkani districts
          </Button>
        </div>
      </fieldset>
    </RulesCard>
  );
}

const LAYOUTS: readonly { value: api.ExportLayout; label: string }[] = [
  { value: "CLIENT", label: "The client's delivery format" },
  { value: "PLATFORM", label: "The platform's own layout" },
];
const SPEAKER_ID_STYLES: readonly { value: api.SpeakerIdStyle; label: string }[] = [
  { value: "NUMBER", label: "Number (P000123 is 123)" },
  { value: "CODE", label: "Participant code (P000123)" },
];
const CONVERSATION_ID_STYLES: readonly { value: api.ConversationIdStyle; label: string }[] = [
  { value: "CON_NUMBER", label: "CON and number (T000045 is CON045)" },
  { value: "CODE", label: "Task code (T000045)" },
];

/** How the project's exports are laid out and named (D-149). */
function ExportRules({ draft, change }: SectionProps) {
  const hintId = useId();
  const problem = audioNameProblem(draft.audio_name_pattern);
  return (
    <RulesCard icon="fileZip" title="Export">
      <fieldset className="field" aria-describedby={hintId}>
        <legend className="field__label">Layout of an export</legend>
        {LAYOUTS.map((l) => (
          <label key={l.value} className="checkbox">
            <input
              type="radio"
              name="export_layout"
              value={l.value}
              checked={draft.export_layout === l.value}
              onChange={() => change({ export_layout: l.value })}
            />
            {l.label}
          </label>
        ))}
        <p id={hintId} className="field__hint">
          {draft.export_layout === "CLIENT"
            ? "Face-to-face and phone audio in their own folders, named as below; a metadata file per speaker and per speaker of each conversation; consent forms and address proofs under speakers/; MISSING.csv lists what is not on file."
            : "A folder for face-to-face recordings and one for phone calls, with each recording's details file and consent record."}
        </p>
      </fieldset>
      <div className="form-grid">
        <Select
          label="Speaker IDs"
          value={draft.speaker_id_style}
          options={SPEAKER_ID_STYLES}
          onChange={(e) => change({ speaker_id_style: e.target.value as api.SpeakerIdStyle })}
        />
        <Select
          label="Conversation IDs"
          value={draft.conversation_id_style}
          options={CONVERSATION_ID_STYLES}
          onChange={(e) =>
            change({ conversation_id_style: e.target.value as api.ConversationIdStyle })
          }
        />
      </div>
      <TextField
        label="Audio file name"
        value={draft.audio_name_pattern}
        maxLength={MAX_AUDIO_NAME}
        hint="{a} and {b}: the two speakers' IDs; {a_pin} and {b_pin}: their native PIN codes (000000 when not given); {conversation}: the conversation ID. Letters, digits, _ and - between them."
        {...(problem ? { error: problem } : {})}
        onChange={(e) => change({ audio_name_pattern: e.target.value })}
      />
      {problem ? null : (
        <p className="field__hint rules__note">
          e.g.{" "}
          {exampleAudioName(
            draft.audio_name_pattern,
            draft.speaker_id_style,
            draft.conversation_id_style,
          )}
        </p>
      )}
      <div className="actions">
        <Button
          variant="secondary"
          icon="history"
          onClick={() =>
            change({
              export_layout: "CLIENT",
              speaker_id_style: "NUMBER",
              conversation_id_style: "CON_NUMBER",
              audio_name_pattern: CLIENT_AUDIO_NAME,
            })
          }
        >
          Reset to the client&apos;s format
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
  { key: "audio-progress", Section: AudioProgressRules },
  { key: "targets", Section: TargetRules },
  { key: "export", Section: ExportRules },
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
    Object.keys(reminderErrors(draft)).length > 0 ||
    Object.keys(targetErrors(draft)).length > 0 ||
    audioNameProblem(draft.audio_name_pattern) !== null;

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
