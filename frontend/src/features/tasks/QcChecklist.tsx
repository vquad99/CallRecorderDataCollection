// The QC checklist on the task page (D-146): the QC Executive ticks Yes or No for each question of
// the project's checklist (conversation questions once, speaker questions for each person) and,
// where the project takes signed consent forms, checks each person's form. The answers are kept
// as a draft while they tick and go with the decision; everyone who sees the task reads the
// newest decision's answers. The server judges again: this only shows what the answers allow.
// Laid out as matrices (D-152): one table for the conversation, one for the speakers with a column
// per person (15 questions take 15 rows, not 30), the consent check in the same style.
import { useId, useRef, useState, type ReactNode } from "react";

import * as qc from "../../api/audioQc";
import type { ApiError } from "../../api/client";
import type { ChecklistItem } from "../../api/projects";
import type * as work from "../../api/work";
import { DataTable } from "../../components/DataTable";
import { Button } from "../../components/form/Button";
import { Icon } from "../../components/Icon";
import { ErrorNotice, SuccessNotice } from "../../components/Notice";
import { StatusBadge } from "../../components/StatusBadge";
import { useAction } from "../../hooks/useAction";
import { toApiError } from "../../hooks/useResource";
import { when } from "../../lib/format";
import { consentAnswer, labelFor } from "../../lib/labels";
import { openDocument } from "../participants/Documents";
import { YesNo } from "./Matrix";

export const SIDES: readonly qc.Side[] = ["A", "B"];

export const noAnswers = (): qc.Answers => ({ conversation: {}, speakers: {}, consent: {} });

const partyOf = (task: work.TaskDetail, side: qc.Side) =>
  side === "A" ? task.participant_a : task.participant_b;

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
  /** Every question to answer (the speakers' twice, each signed form once) and those answered. */
  total: number;
  answered: number;
}

export function judge(
  task: work.TaskDetail,
  items: readonly ChecklistItem[],
  answers: qc.Answers,
  consentCheck: boolean,
): Judgement {
  const out: Judgement = {
    missing: 0,
    failing: [],
    consentUnchecked: [],
    consentWrong: [],
    total: 0,
    answered: 0,
  };
  for (const item of items) {
    const sides = item.scope === "speaker" ? SIDES : [null];
    for (const side of sides) {
      const answer = answerOf(answers, item, side);
      out.total += 1;
      if (answer !== undefined) out.answered += 1;
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
      out.total += 1;
      if (answer !== undefined) out.answered += 1;
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

/** A speaker's column heading: "Participant A", with their code and name under it. */
function SideHead({ task, side }: { task: work.TaskDetail; side: qc.Side }) {
  const p = partyOf(task, side);
  return (
    <th scope="col" className={`mx-${side.toLowerCase()} mx-col`}>
      <span className="mx-who">
        <span>Participant {side}</span>{" "}
        <span className="mx-who__meta">
          <span className="code-tag">{p.participant_code}</span>
          {p.display_label ? ` ${p.display_label}` : null}
        </span>
      </span>
    </th>
  );
}

/** A question as the row's heading, "(optional)" where it may stay unanswered. */
function QuestionCell({ item, n }: { item: ChecklistItem; n: number }) {
  return (
    <>
      <td className="mx-n">{n}</td>
      <th scope="row">
        {item.question}
        {item.required ? null : <span className="muted"> (optional)</span>}
      </th>
    </>
  );
}

/** One answer's cell: the Yes / No switch, rose with a cross when the answer fails the recording. */
function AnswerCell({
  label,
  item,
  value,
  onChange,
}: {
  label: string;
  item: ChecklistItem;
  value: qc.Answer | undefined;
  onChange: (answer: qc.Answer) => void;
}) {
  const fails = value !== undefined && value === item.fails_on;
  return (
    <td className={`mx-cell${fails ? " is-fail" : value === undefined ? " is-open" : ""}`}>
      <span className="mx-answer">
        <YesNo label={label} value={value} failsOn={item.fails_on} onChange={onChange} />
        {fails ? (
          <span className="mx-fails">
            <Icon name="failed" size={16} />
            <span className="sr-only">Fails</span>
          </span>
        ) : null}
      </span>
    </td>
  );
}

/** A block of the checklist with its small heading. */
function Block({
  title,
  note,
  children,
}: {
  title: string;
  note?: ReactNode;
  children: ReactNode;
}) {
  const id = useId();
  return (
    <section className="qc-block" aria-labelledby={id}>
      <h4 id={id}>{title}</h4>
      {note ? <p className="muted qc-block__note">{note}</p> : null}
      {children}
    </section>
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
      <Block
        title="Consent"
        note="This project takes consent online: the platform recorded each person's answer, so there is nothing to check here."
      >
        <DataTable className="matrix qc-table" label="Consent of each speaker">
          <thead>
            <tr>
              <th scope="col" className="mx-n">
                <span className="sr-only">Number</span>
              </th>
              <th scope="col">Consent form</th>
              {SIDES.map((side) => (
                <SideHead key={side} task={task} side={side} />
              ))}
            </tr>
          </thead>
          <tbody>
            <tr>
              <td className="mx-n" />
              <th scope="row">Their answer on the consent form</th>
              {SIDES.map((side) => {
                const p = partyOf(task, side);
                const { label, tone } = consentAnswer(p.consent_status, task.consent_mode);
                return (
                  <td key={side} className="mx-cell">
                    <StatusBadge tone={tone} label={label} />
                    {p.consent_at ? <div className="muted">{when(p.consent_at)}</div> : null}
                  </td>
                );
              })}
            </tr>
          </tbody>
        </DataTable>
      </Block>
    );
  }
  return (
    <Block
      title="Signed consent forms"
      note={<>Open each person&apos;s form and check it: {view.consent_question}.</>}
    >
      <DataTable className="matrix qc-table" label="Signed consent form of each speaker">
        <thead>
          <tr>
            <th scope="col" className="mx-n">
              <span className="sr-only">Number</span>
            </th>
            <th scope="col">Question</th>
            {SIDES.map((side) => (
              <SideHead key={side} task={task} side={side} />
            ))}
          </tr>
        </thead>
        <tbody>
          <tr>
            <td className="mx-n" />
            <th scope="row">{view.consent_question}</th>
            {SIDES.map((side) => {
              const p = partyOf(task, side);
              const doc = p.consent_form ?? null;
              const value = answers.consent[side];
              return (
                <td
                  key={side}
                  className={`mx-cell${value === "no" ? " is-fail" : value === undefined ? " is-open" : ""}`}
                >
                  <span className="mx-answer mx-answer--stack">
                    {doc ? (
                      <Button
                        variant="secondary"
                        icon="eye"
                        className="button button--secondary mx-view"
                        busy={busy === side}
                        disabled={busy !== null}
                        aria-label={`View the signed consent form of ${p.participant_code}`}
                        onClick={() =>
                          void run(() => openDocument(task.project_id, p.id, doc), side)
                        }
                      >
                        View
                      </Button>
                    ) : (
                      <StatusBadge tone="warning" label="No form uploaded" />
                    )}
                    <YesNo
                      label={`Consent form of ${p.participant_code} checked`}
                      value={value}
                      failsOn="no"
                      onChange={(a) => onAnswer(side, a)}
                    />
                  </span>
                </td>
              );
            })}
          </tr>
        </tbody>
      </DataTable>
      <ErrorNotice error={error} />
      <SuccessNotice message={message} />
    </Block>
  );
}

/** The questions to tick: the conversation's once, the speakers' as a matrix, then consent. */
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
    <div className="qc-matrix">
      <div className="qc-matrix__grid">
        {conversation.length > 0 ? (
          <Block title="The conversation">
            <DataTable className="matrix qc-table" label="Questions about the conversation">
              <thead>
                <tr>
                  <th scope="col" className="mx-n">
                    <span className="sr-only">Number</span>
                  </th>
                  <th scope="col">Question</th>
                  <th scope="col" className="mx-col">
                    Yes / No
                  </th>
                </tr>
              </thead>
              <tbody>
                {conversation.map((item, i) => (
                  <tr key={item.key}>
                    <QuestionCell item={item} n={i + 1} />
                    <AnswerCell
                      label={item.question}
                      item={item}
                      value={answers.conversation[item.key]}
                      onChange={(a) =>
                        onChange({
                          ...answers,
                          conversation: { ...answers.conversation, [item.key]: a },
                        })
                      }
                    />
                  </tr>
                ))}
              </tbody>
            </DataTable>
          </Block>
        ) : null}
        {speaker.length > 0 ? (
          <Block title="Each speaker">
            <DataTable className="matrix qc-table" label="Questions about each speaker">
              <thead>
                <tr>
                  <th scope="col" className="mx-n">
                    <span className="sr-only">Number</span>
                  </th>
                  <th scope="col">Question</th>
                  {SIDES.map((side) => (
                    <SideHead key={side} task={task} side={side} />
                  ))}
                </tr>
              </thead>
              <tbody>
                {speaker.map((item, i) => (
                  <tr key={item.key}>
                    <QuestionCell item={item} n={i + 1} />
                    {SIDES.map((side) => (
                      <AnswerCell
                        key={side}
                        label={`${item.question} – Participant ${side}`}
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
                  </tr>
                ))}
              </tbody>
            </DataTable>
          </Block>
        ) : null}
      </div>
      <ConsentCheck
        task={task}
        view={view}
        answers={answers}
        onAnswer={(side, a) => onChange({ ...answers, consent: { ...answers.consent, [side]: a } })}
      />
    </div>
  );
}

/** "Answered 31 / 43 · 2 failing" with a bar; the draft's state at the right. */
export function ChecklistProgress({ j, saving }: { j: Judgement; saving: ReactNode }) {
  const share = j.total > 0 ? Math.round((j.answered / j.total) * 100) : 0;
  return (
    <div className="qc-progress">
      <div className="qc-progress__text">
        <strong>
          Answered {j.answered} / {j.total}
        </strong>
        <span className={j.failing.length > 0 ? "qc-progress__fail" : "muted"}>
          {" "}
          · {j.failing.length} failing
        </span>
        {j.consentWrong.length > 0 ? (
          <span className="qc-progress__fail">
            {" "}
            · {j.consentWrong.length === 1 ? "1 form" : `${j.consentWrong.length} forms`} not right
          </span>
        ) : null}
      </div>
      <div
        className="qc-progress__bar"
        role="progressbar"
        aria-label="Questions answered"
        aria-valuemin={0}
        aria-valuemax={j.total}
        aria-valuenow={j.answered}
      >
        <span
          className={j.failing.length > 0 ? "is-fail" : share === 100 ? "is-done" : undefined}
          style={{ width: `${share}%` }}
        />
      </div>
      {saving}
    </div>
  );
}

const WORD: Record<qc.Answer, string> = { yes: "Yes", no: "No" };

/** A recorded answer: a tick and the word, or a cross, the word and "Fails". */
function Said({ answer, fails }: { answer: qc.Answer | null | undefined; fails: boolean }) {
  if (!answer) return <span className="muted">Not answered</span>;
  return (
    <span className={`mark ${fails ? "mark--no" : "mark--ok"}`}>
      <Icon name={fails ? "failed" : "ok"} size={16} />
      <span>{WORD[answer]}</span>
      {fails ? <StatusBadge tone="danger" label="Fails" /> : null}
    </span>
  );
}

/** A decision's answers, read only, with the questions as they read then, who and when: the same
 * matrices with a tick or a cross in each cell. */
export function RecordedChecklist({ latest }: { latest: qc.RecordedAnswers }) {
  const [open, setOpen] = useState(false);
  const fails = new Set(latest.failing.map((f) => `${f.side ?? ""}:${f.key}`));
  const conversation = latest.items.filter((i) => i.scope === "conversation");
  const speaker = latest.items.filter((i) => i.scope === "speaker");
  const [a, b] = latest.participants;
  const answered =
    Object.keys(latest.conversation).length +
    latest.participants.reduce((n, p) => n + Object.keys(p.answers).length, 0);
  const total = conversation.length + speaker.length * latest.participants.length;
  return (
    <section className="stack stack--tight" aria-labelledby="qc-answers-title">
      <div className="qc-recorded__head">
        <h3 id="qc-answers-title">QC checklist</h3>
        <Button
          variant="secondary"
          icon="tasks"
          aria-expanded={open}
          onClick={() => setOpen(!open)}
        >
          {open ? "Hide the answers" : "Show every answer"}
        </Button>
      </div>
      <p className="muted">
        {labelFor(qc.OUTCOME_LABELS, latest.outcome)} · answered by {latest.reviewer_name ?? "QC"} ·{" "}
        {when(latest.decided_at)} · {answered} / {total} answered
      </p>
      {latest.failing.length > 0 ? (
        <p className="qc-progress__fail">
          {latest.failing.length === 1
            ? "1 answer fails the recording."
            : `${latest.failing.length} answers fail the recording.`}
        </p>
      ) : null}
      {open ? (
        <div className="qc-matrix">
          <div className="qc-matrix__grid">
            {conversation.length > 0 ? (
              <DataTable className="matrix qc-table" label="Answers about the conversation">
                <thead>
                  <tr>
                    <th scope="col" className="mx-n">
                      <span className="sr-only">Number</span>
                    </th>
                    <th scope="col">The conversation</th>
                    <th scope="col" className="mx-col">
                      Answer
                    </th>
                  </tr>
                </thead>
                <tbody>
                  {conversation.map((item, i) => {
                    const failing = fails.has(`:${item.key}`);
                    return (
                      <tr key={item.key}>
                        <td className="mx-n">{i + 1}</td>
                        <th scope="row">{item.question}</th>
                        <td className={`mx-cell${failing ? " is-fail" : ""}`}>
                          <Said answer={latest.conversation[item.key]} fails={failing} />
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </DataTable>
            ) : null}
            {a && b ? (
              <DataTable className="matrix qc-table" label="Answers about each speaker">
                <thead>
                  <tr>
                    <th scope="col" className="mx-n">
                      <span className="sr-only">Number</span>
                    </th>
                    <th scope="col">Each speaker</th>
                    {[a, b].map((p) => (
                      <th key={p.side} scope="col" className={`mx-${p.side.toLowerCase()} mx-col`}>
                        <span className="mx-who">
                          <span>Participant {p.side}</span>{" "}
                          <span className="mx-who__meta">
                            <span className="code-tag">{p.participant_code}</span>
                          </span>
                        </span>
                      </th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {speaker.map((item, i) => (
                    <tr key={item.key}>
                      <td className="mx-n">{i + 1}</td>
                      <th scope="row">{item.question}</th>
                      {[a, b].map((p) => {
                        const failing = fails.has(`${p.side}:${item.key}`);
                        return (
                          <td key={p.side} className={`mx-cell${failing ? " is-fail" : ""}`}>
                            <Said answer={p.answers[item.key]} fails={failing} />
                          </td>
                        );
                      })}
                    </tr>
                  ))}
                  {latest.consent_check ? (
                    <tr>
                      <td className="mx-n" />
                      <th scope="row">
                        Consent form checked: signed, the right person, this project
                      </th>
                      {[a, b].map((p) => (
                        <td
                          key={p.side}
                          className={`mx-cell${p.consent === "no" ? " is-fail" : ""}`}
                        >
                          <Said answer={p.consent} fails={p.consent === "no"} />
                        </td>
                      ))}
                    </tr>
                  ) : null}
                </tbody>
              </DataTable>
            ) : null}
          </div>
        </div>
      ) : null}
    </section>
  );
}
