// The QC checklist on the task page (D-146): the QC Executive ticks Yes or No for each question of
// the project's checklist (conversation questions once, speaker questions for each person) and,
// where the project takes signed consent forms, checks each person's form. The answers are kept
// as a draft while they tick and go with the decision; everyone who sees the task reads the
// newest decision's answers. The server judges again: this only shows what the answers allow.
import { useRef, useState } from "react";

import * as qc from "../../api/audioQc";
import type { ApiError } from "../../api/client";
import type { ChecklistItem } from "../../api/projects";
import type * as work from "../../api/work";
import { DataTable } from "../../components/DataTable";
import { Button } from "../../components/form/Button";
import { ErrorNotice, SuccessNotice } from "../../components/Notice";
import { StatusBadge } from "../../components/StatusBadge";
import { useAction } from "../../hooks/useAction";
import { toApiError } from "../../hooks/useResource";
import { when } from "../../lib/format";
import { consentAnswer, labelFor } from "../../lib/labels";
import { openDocument } from "../participants/Documents";

export const SIDES: readonly qc.Side[] = ["A", "B"];

export const noAnswers = (): qc.Answers => ({ conversation: {}, speakers: {}, consent: {} });

const partyOf = (task: work.TaskDetail, side: qc.Side) =>
  side === "A" ? task.participant_a : task.participant_b;

/** "Participant A · P000001 Asha" */
const partyTitle = (task: work.TaskDetail, side: qc.Side) => {
  const p = partyOf(task, side);
  return `Participant ${side} · ${p.participant_code}${p.display_label ? ` ${p.display_label}` : ""}`;
};

const answerOf = (answers: qc.Answers, item: ChecklistItem, side: qc.Side | null) =>
  side ? answers.speakers[side]?.[item.key] : answers.conversation[item.key];

/** What the answers allow now. */
export interface Judgement {
  /** Required questions not answered yet. */
  missing: number;
  /** Questions answered so that the recording fails ("P000001: Is speech intelligible?"). */
  failing: string[];
  /** Participant codes whose signed form is not checked yet, or found not right. */
  consentUnchecked: string[];
  consentWrong: string[];
}

export function judge(
  task: work.TaskDetail,
  items: readonly ChecklistItem[],
  answers: qc.Answers,
  consentCheck: boolean,
): Judgement {
  const out: Judgement = { missing: 0, failing: [], consentUnchecked: [], consentWrong: [] };
  for (const item of items) {
    const sides = item.scope === "speaker" ? SIDES : [null];
    for (const side of sides) {
      const answer = answerOf(answers, item, side);
      if (answer === undefined && item.required) out.missing += 1;
      if (answer !== undefined && answer === item.fails_on)
        out.failing.push(
          side ? `${partyOf(task, side).participant_code}: ${item.question}` : item.question,
        );
    }
  }
  if (consentCheck) {
    for (const side of SIDES) {
      const code = partyOf(task, side).participant_code;
      const answer = answers.consent[side];
      if (answer === undefined) out.consentUnchecked.push(code);
      if (answer === "no") out.consentWrong.push(code);
    }
  }
  return out;
}

/** Saves the answers as a draft while the QC Executive ticks: one save at a time, the newest
 * answers last, so a page reload keeps them. */
export function useDraftSaver(taskId: string) {
  const [state, setState] = useState<"idle" | "saving" | "saved" | "failed">("idle");
  const [error, setError] = useState<ApiError | null>(null);
  const pending = useRef<qc.Answers | null>(null);
  const running = useRef(false);
  const flush = async () => {
    if (running.current) return;
    running.current = true;
    try {
      while (pending.current) {
        const next = pending.current;
        pending.current = null;
        try {
          await qc.saveDraft(taskId, next);
          setState(pending.current ? "saving" : "saved");
          setError(null);
        } catch (err) {
          setState("failed");
          setError(toApiError(err));
        }
      }
    } finally {
      running.current = false;
    }
  };
  const save = (answers: qc.Answers) => {
    pending.current = answers;
    setState("saving");
    void flush();
  };
  return { state, error, save };
}

/** Two buttons, Yes and No; the chosen one is pressed. */
function YesNo({
  label,
  value,
  onChange,
}: {
  label: string;
  value: qc.Answer | undefined;
  onChange: (answer: qc.Answer) => void;
}) {
  return (
    <div className="seg" role="group" aria-label={label}>
      {(["yes", "no"] as const).map((a) => (
        <button
          key={a}
          type="button"
          className="seg__option"
          aria-pressed={value === a}
          onClick={() => onChange(a)}
        >
          {a === "yes" ? "Yes" : "No"}
        </button>
      ))}
    </div>
  );
}

function Question({
  item,
  value,
  onChange,
}: {
  item: ChecklistItem;
  value: qc.Answer | undefined;
  onChange: (answer: qc.Answer) => void;
}) {
  const fails = value !== undefined && value === item.fails_on;
  return (
    <li className="qc-list__row">
      <span className="qc-list__question">
        {item.question}
        {item.required ? null : <span className="muted"> (optional)</span>}
        {fails ? <StatusBadge tone="danger" label="Fails" /> : null}
      </span>
      <YesNo label={item.question} value={value} onChange={onChange} />
    </li>
  );
}

/** Each person's consent: their signed form to open and check (Upload projects), or their online
 * answer, which the platform recorded (Online projects): nothing to check there. */
function ConsentCheck({
  task,
  view,
  answers,
  onAnswer,
}: {
  task: work.TaskDetail;
  view: qc.ChecklistView;
  answers: qc.Answers;
  onAnswer: (side: qc.Side, answer: qc.Answer) => void;
}) {
  const { busy, error, message, run } = useAction();
  if (!view.consent_check) {
    return (
      <fieldset className="qc-group">
        <legend>Consent</legend>
        <p className="muted">
          This project takes consent online: the platform recorded each person&apos;s answer, so
          there is nothing to check here.
        </p>
        <ul className="qc-list">
          {SIDES.map((side) => {
            const p = partyOf(task, side);
            const { label, tone } = consentAnswer(p.consent_status, task.consent_mode);
            return (
              <li key={side} className="qc-list__row">
                <span className="qc-list__question">{partyTitle(task, side)}</span>
                <span className="qc-list__answer">
                  <StatusBadge tone={tone} label={label} />
                  {p.consent_at ? <span className="muted">{when(p.consent_at)}</span> : null}
                </span>
              </li>
            );
          })}
        </ul>
      </fieldset>
    );
  }
  return (
    <fieldset className="qc-group">
      <legend>Signed consent forms</legend>
      <p className="muted">Open each person&apos;s form and check it: {view.consent_question}.</p>
      <ul className="qc-list">
        {SIDES.map((side) => {
          const p = partyOf(task, side);
          const doc = p.consent_form ?? null;
          return (
            <li key={side} className="qc-list__row">
              <span className="qc-list__question">
                {partyTitle(task, side)}
                {doc ? (
                  <Button
                    variant="secondary"
                    icon="eye"
                    busy={busy === side}
                    disabled={busy !== null}
                    aria-label={`View the signed consent form of ${p.participant_code}`}
                    onClick={() => void run(() => openDocument(task.project_id, p.id, doc), side)}
                  >
                    View
                  </Button>
                ) : (
                  <StatusBadge tone="warning" label="No form uploaded" />
                )}
              </span>
              <YesNo
                label={`Consent form of ${p.participant_code} checked`}
                value={answers.consent[side]}
                onChange={(a) => onAnswer(side, a)}
              />
            </li>
          );
        })}
      </ul>
      <ErrorNotice error={error} />
      <SuccessNotice message={message} />
    </fieldset>
  );
}

/** The questions to tick: the conversation's once, the speakers' for each person, then consent. */
export function ChecklistForm({
  task,
  view,
  answers,
  onChange,
}: {
  task: work.TaskDetail;
  view: qc.ChecklistView;
  answers: qc.Answers;
  onChange: (answers: qc.Answers) => void;
}) {
  const conversation = view.items.filter((i) => i.scope === "conversation");
  const speaker = view.items.filter((i) => i.scope === "speaker");
  return (
    <div className="stack stack--tight">
      {conversation.length > 0 ? (
        <fieldset className="qc-group">
          <legend>The conversation</legend>
          <ul className="qc-list">
            {conversation.map((item) => (
              <Question
                key={item.key}
                item={item}
                value={answers.conversation[item.key]}
                onChange={(a) =>
                  onChange({ ...answers, conversation: { ...answers.conversation, [item.key]: a } })
                }
              />
            ))}
          </ul>
        </fieldset>
      ) : null}
      {speaker.length > 0
        ? SIDES.map((side) => (
            <fieldset key={side} className="qc-group">
              <legend>{partyTitle(task, side)}</legend>
              <ul className="qc-list">
                {speaker.map((item) => (
                  <Question
                    key={item.key}
                    item={item}
                    value={answers.speakers[side]?.[item.key]}
                    onChange={(a) =>
                      onChange({
                        ...answers,
                        speakers: {
                          ...answers.speakers,
                          [side]: { ...answers.speakers[side], [item.key]: a },
                        },
                      })
                    }
                  />
                ))}
              </ul>
            </fieldset>
          ))
        : null}
      <ConsentCheck
        task={task}
        view={view}
        answers={answers}
        onAnswer={(side, a) => onChange({ ...answers, consent: { ...answers.consent, [side]: a } })}
      />
    </div>
  );
}

const WORD: Record<qc.Answer, string> = { yes: "Yes", no: "No" };

function Said({ answer, fails }: { answer: qc.Answer | null | undefined; fails: boolean }) {
  if (!answer) return <span className="muted">Not answered</span>;
  return (
    <span className="qc-list__answer">
      {WORD[answer]}
      {fails ? <StatusBadge tone="danger" label="Fails" /> : null}
    </span>
  );
}

/** A decision's answers, read only, with the questions as they read then, who and when. */
export function RecordedChecklist({ latest }: { latest: qc.RecordedAnswers }) {
  const [open, setOpen] = useState(false);
  const fails = new Set(latest.failing.map((f) => `${f.side ?? ""}:${f.key}`));
  const conversation = latest.items.filter((i) => i.scope === "conversation");
  const speaker = latest.items.filter((i) => i.scope === "speaker");
  const [a, b] = latest.participants;
  return (
    <section className="stack stack--tight" aria-labelledby="qc-answers-title">
      <h3 id="qc-answers-title">QC checklist</h3>
      <p className="muted">
        {labelFor(qc.OUTCOME_LABELS, latest.outcome)} · answered by {latest.reviewer_name ?? "QC"} ·{" "}
        {when(latest.decided_at)}
      </p>
      {latest.failing.length > 0 ? (
        <p>
          {latest.failing.length === 1
            ? "1 answer fails the recording."
            : `${latest.failing.length} answers fail the recording.`}
        </p>
      ) : null}
      <div>
        <Button
          variant="secondary"
          icon="tasks"
          aria-expanded={open}
          onClick={() => setOpen(!open)}
        >
          {open ? "Hide the answers" : "Show every answer"}
        </Button>
      </div>
      {open ? (
        <>
          {conversation.length > 0 ? (
            <DataTable label="Answers about the conversation">
              <thead>
                <tr>
                  <th scope="col">The conversation</th>
                  <th scope="col">Answer</th>
                </tr>
              </thead>
              <tbody>
                {conversation.map((item) => (
                  <tr key={item.key}>
                    <td>{item.question}</td>
                    <td>
                      <Said
                        answer={latest.conversation[item.key]}
                        fails={fails.has(`:${item.key}`)}
                      />
                    </td>
                  </tr>
                ))}
              </tbody>
            </DataTable>
          ) : null}
          {a && b ? (
            <DataTable label="Answers about each speaker">
              <thead>
                <tr>
                  <th scope="col">Each speaker</th>
                  <th scope="col">{a.participant_code}</th>
                  <th scope="col">{b.participant_code}</th>
                </tr>
              </thead>
              <tbody>
                {speaker.map((item) => (
                  <tr key={item.key}>
                    <td>{item.question}</td>
                    {[a, b].map((p) => (
                      <td key={p.side}>
                        <Said
                          answer={p.answers[item.key]}
                          fails={fails.has(`${p.side}:${item.key}`)}
                        />
                      </td>
                    ))}
                  </tr>
                ))}
                {latest.consent_check ? (
                  <tr>
                    <td>Consent form checked: signed, the right person, this project</td>
                    {[a, b].map((p) => (
                      <td key={p.side}>
                        <Said answer={p.consent} fails={p.consent === "no"} />
                      </td>
                    ))}
                  </tr>
                ) : null}
              </tbody>
            </DataTable>
          ) : null}
        </>
      ) : null}
    </section>
  );
}
