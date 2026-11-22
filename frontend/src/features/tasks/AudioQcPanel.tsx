// Audio quality card on the task page (D-079): what the automatic check found, who checks the
// recording, a player, the QC checklist (D-146) and the QC Executive's decision: Pass, Reject
// (D-118) or, where the project takes signed forms, Send back for consent. The server decides who
// may do what; this only shows the controls it allows. D-152: the checklist is a matrix with a
// count of what is answered and failing, and the decision bar stays at the bottom of the screen
// while the QC Executive works down the questions, saying why Pass waits.
import { useState } from "react";

import * as qc from "../../api/audioQc";
import { listMembers } from "../../api/projects";
import type * as work from "../../api/work";
import { useConfirm } from "../../components/ConfirmDialog";
import { DataTable } from "../../components/DataTable";
import { Button } from "../../components/form/Button";
import { Select } from "../../components/form/Select";
import { TextField } from "../../components/form/TextField";
import { ErrorNotice } from "../../components/Notice";
import { ErrorState, LoadingState } from "../../components/StateViews";
import { StatusBadge, type Tone } from "../../components/StatusBadge";
import { useAction } from "../../hooks/useAction";
import { useResource } from "../../hooks/useResource";
import { when } from "../../lib/format";
import { labelFor, REASON_LABELS, reasonChoices } from "../../lib/labels";
import { Player } from "./Listen";
import {
  ChecklistForm,
  ChecklistProgress,
  type Judgement,
  judge,
  noAnswers,
  RecordedChecklist,
  useDraftSaver,
} from "./QcChecklist";

const OUTCOME_TONE: Record<qc.QcOutcome, Tone> = {
  PASS: "success",
  NEEDS_REVIEW: "warning",
  FAIL: "danger",
  SEND_BACK_CONSENT: "warning",
};
const CHECK_TONE: Record<qc.CheckState, Tone> = {
  PASS: "success",
  FAIL: "danger",
  REVIEW: "warning",
  INFO: "neutral",
  NOT_APPLICABLE: "neutral",
};
/** Checks that need the listener's attention; the rest are behind "Show all checks". */
const ATTENTION: readonly qc.CheckState[] = ["FAIL", "REVIEW"];

/** The task's audio check, loaded once for this card and the page's summary (its QC Executive);
 * nothing is asked before the task has a recording. Loaded again whenever the task's status
 * changes (FEW-06): Send to QC assigns a QC Executive, and a task sent back to QC can be decided
 * again, without the page being opened anew. */
export function useAudioQc(task: work.TaskDetail, has: boolean) {
  return useResource<qc.AudioQcView | null>(
    () => (has ? qc.getAudioQc(task.id) : Promise.resolve(null)),
    [task.id, has, task.status],
  );
}
export type AudioQcResource = ReturnType<typeof useAudioQc>;

function Outcome({ outcome }: { outcome: qc.QcOutcome }) {
  return (
    <StatusBadge
      tone={OUTCOME_TONE[outcome] ?? "neutral"}
      label={labelFor(qc.OUTCOME_LABELS, outcome)}
    />
  );
}

/** The automatic checks: those that need attention, and every check on request. */
function Checks({ result }: { result: qc.QcResult }) {
  const [all, setAll] = useState(false);
  const attention = result.checks.filter((c) => ATTENTION.includes(c.state));
  const shown = all ? result.checks : attention;
  return (
    <div className="stack stack--tight">
      <div className="qc__summary">
        <p>
          {attention.length === 0
            ? "No check needs attention."
            : attention.length === 1
              ? "1 check needs attention:"
              : `${attention.length} checks need attention:`}
        </p>
        <Button variant="secondary" icon="tasks" aria-expanded={all} onClick={() => setAll(!all)}>
          {all
            ? "Show only checks that need attention"
            : `Show all checks (${result.checks.length})`}
        </Button>
      </div>
      {shown.length > 0 ? (
        <DataTable
          className="matrix qc-checks"
          label={all ? "All automatic checks" : "Checks that need attention"}
        >
          <thead>
            <tr>
              <th scope="col">Check</th>
              <th scope="col">Result</th>
              <th scope="col">Measured</th>
              <th scope="col">Allowed</th>
            </tr>
          </thead>
          <tbody>
            {shown.map((c) => (
              <tr key={c.code} className={c.state === "FAIL" ? "is-fail" : undefined}>
                <td>
                  {labelFor(qc.CHECK_LABELS, c.code)}
                  {c.message ? <div className="muted">{c.message}</div> : null}
                </td>
                <td>
                  <StatusBadge tone={CHECK_TONE[c.state]} label={qc.STATE_LABELS[c.state]} />
                </td>
                <td>{c.measured}</td>
                <td>{c.expected}</td>
              </tr>
            ))}
          </tbody>
        </DataTable>
      ) : null}
    </div>
  );
}

function AssignQc({
  task,
  view,
  onChange,
}: {
  task: work.TaskDetail;
  view: qc.AudioQcView;
  onChange: (v: qc.AudioQcView) => void;
}) {
  const members = useResource(() => listMembers(task.project_id), [task.project_id]);
  const [userId, setUserId] = useState("");
  const [reason, setReason] = useState("");
  const { busy, error, run } = useAction();
  const people =
    members.state.status === "loaded"
      ? members.state.data.filter(
          (m) =>
            m.roles.includes("QC_EXECUTIVE") &&
            m.status === "ACTIVE" &&
            m.user_id !== view.qc_user_id &&
            m.user_id !== task.moderator_id,
        )
      : [];
  const reassigning = Boolean(view.qc_user_id);
  return (
    <form
      className="qc-assign"
      onSubmit={(e) => {
        e.preventDefault();
        void run(async () => {
          onChange(await qc.assignQc(task.id, userId, reason));
          setUserId("");
          setReason("");
        });
      }}
    >
      <Select
        label={reassigning ? "Hand to another QC Executive" : "QC Executive"}
        value={userId}
        onChange={(e) => setUserId(e.target.value)}
        options={[
          { value: "", label: "Choose a QC Executive" },
          ...people.map((m) => ({ value: m.user_id, label: `${m.display_name} (${m.email})` })),
        ]}
      />
      {reassigning ? (
        <TextField
          label="Reason for reassigning"
          required
          value={reason}
          onChange={(e) => setReason(e.target.value)}
        />
      ) : null}
      <Button
        type="submit"
        variant="secondary"
        icon="userPlus"
        busy={busy !== null}
        disabled={!userId || (reassigning && !reason.trim())}
      >
        {reassigning ? "Reassign QC" : "Assign QC"}
      </Button>
      <ErrorNotice error={error} />
    </form>
  );
}

/** What the answers say about the decision, in one line; it is also why Pass waits. While
 * questions are open it also counts the signed forms still to check, so it adds up with the
 * "Answered n / total" above the checklist (UXW-02). */
function hint(j: Judgement, consentCheck: boolean): string {
  if (j.failing.length > 0)
    return `The recording fails the checklist (${j.failing[0]}): reject it.`;
  if (j.missing > 0) {
    const questions = j.missing === 1 ? "1 question" : `${j.missing} questions`;
    const forms = consentCheck ? j.consentUnchecked.length : 0;
    return forms > 0
      ? `${questions} and ${forms === 1 ? "1 consent form" : `${forms} consent forms`} still to answer.`
      : `${questions} still to answer.`;
  }
  if (consentCheck && j.consentWrong.length > 0)
    return `The consent form of ${j.consentWrong.join(" and ")} is not right: send the task back for its consent form.`;
  if (consentCheck && j.consentUnchecked.length > 0)
    return `Check the signed consent form of ${j.consentUnchecked.join(" and ")}.`;
  return "Every answer lets the recording pass.";
}

/** Pass sends the recording to the project admin, or approves the task where QC pass is the
 * final approval (D-138); Reject asks why and ends the task; Send back for consent (projects that
 * take signed forms) returns it to the moderator for a new form (D-146). The checklist's answers
 * go with each; Pass and Send back wait until they allow it. */
function Decision({
  task,
  view,
  checklist,
  automatic,
  onDecided,
}: {
  task: work.TaskDetail;
  view: qc.AudioQcView;
  checklist: qc.ChecklistView;
  automatic: qc.QcResult | undefined;
  onDecided: () => void;
}) {
  const confirm = useConfirm();
  const { busy, error, run } = useAction(onDecided);
  const [answers, setAnswers] = useState<qc.Answers>(() => checklist.draft?.answers ?? noAnswers());
  const draft = useDraftSaver(task.id);
  const consentCheck = checklist.consent_check;
  const j = judge(task, checklist.items, answers, consentCheck);
  const clean = j.missing === 0 && j.failing.length === 0;
  const canPass =
    clean && (!consentCheck || (j.consentUnchecked.length === 0 && j.consentWrong.length === 0));
  const canSendBack = consentCheck && clean && j.consentWrong.length > 0;
  const change = (next: qc.Answers) => {
    setAnswers(next);
    draft.save(next);
  };
  const decided = async (outcome: qc.Decision, reason: string, comment: string) => {
    await qc.decideQc(task.id, outcome, reason, comment, answers);
    onDecided();
  };
  const pass = () =>
    // Passing a recording the automatic check failed needs the reason in words.
    automatic?.outcome === "FAIL"
      ? confirm.ask({
          title: "Pass a recording that failed the automatic check?",
          askReason: "Why does it pass?",
          confirmLabel: "Pass",
          action: ({ comment }) => decided("PASS", "", comment),
        })
      : void run(() => qc.decideQc(task.id, "PASS", "", "", answers), "PASS");
  const reject = () =>
    confirm.ask({
      title: `Reject the recording of task ${task.task_code}?`,
      message: "The task ends as rejected. Your checklist answers are kept with it.",
      confirmLabel: "Reject",
      danger: true,
      reasons: reasonChoices(view.reasons.FAIL),
      action: ({ reason, comment }) => decided("FAIL", reason, comment),
    });
  const sendBack = () =>
    confirm.ask({
      title: `Send task ${task.task_code} back for its consent form?`,
      message: `The recording stays as it is. The moderator uploads a new signed form for ${j.consentWrong.join(" and ")} and sends the same recording back to you.`,
      askReason: "What is wrong with the form",
      confirmLabel: "Send back",
      action: ({ comment }) => decided("SEND_BACK_CONSENT", "", comment),
    });
  const tone = j.failing.length > 0 ? "is-fail" : canPass ? "is-ok" : "";
  return (
    <>
      <section className="stack stack--tight" aria-labelledby="qc-checklist-title">
        <div className="qc-checklist__head">
          <h3 id="qc-checklist-title">QC checklist</h3>
          <p className="muted">
            Listen, then tick Yes or No for every question; your answers are kept as you go.{" "}
            {view.pass_approves
              ? "Pass approves the task: this project has no admin review."
              : "Pass sends it to the project admin for final approval."}{" "}
            Reject ends the task.
            {consentCheck
              ? " Send back for consent returns it to the moderator for a new signed form; the recording stays."
              : ""}
          </p>
        </div>
        <ChecklistProgress
          j={j}
          saving={
            <p className="muted qc-progress__saved" role="status">
              {draft.state === "saving"
                ? "Saving your answers…"
                : draft.state === "saved"
                  ? "Answers saved."
                  : ""}
            </p>
          }
        />
        <ChecklistForm task={task} view={checklist} answers={answers} onChange={change} />
        {draft.state === "failed" ? (
          <p className="notice notice--warning">
            Your answers could not be saved just now ({draft.error?.message}). They still go with
            your decision.
          </p>
        ) : null}
      </section>
      {/* The decision stays in view at the bottom of the screen while the questions scroll. */}
      <section className="qc-decide" aria-labelledby="qc-decision-title">
        <div className="qc-decide__text">
          <h3 id="qc-decision-title">Your decision</h3>
          <p id="qc-decide-hint" className={`qc__hint ${tone}`}>
            {hint(j, consentCheck)}
          </p>
        </div>
        <div className="actions qc-decide__buttons">
          <Button
            icon="verified"
            busy={busy !== null}
            disabled={!canPass}
            aria-describedby={canPass ? undefined : "qc-decide-hint"}
            onClick={pass}
          >
            Pass
          </Button>
          {consentCheck ? (
            <Button
              variant="secondary"
              icon="fileText"
              disabled={busy !== null || !canSendBack}
              aria-describedby={canSendBack ? undefined : "qc-decide-hint"}
              onClick={sendBack}
            >
              Send back for consent
            </Button>
          ) : null}
          <Button variant="danger" icon="failed" disabled={busy !== null} onClick={reject}>
            Reject
          </Button>
        </div>
        <ErrorNotice error={error} />
        {confirm.dialog}
      </section>
    </>
  );
}

/** The QC checklist's part of the card: the answers to tick for the person who decides, or the
 * newest decision's answers for everyone else (D-146). */
function Checklist({
  task,
  view,
  automatic,
  onDecided,
}: {
  task: work.TaskDetail;
  view: qc.AudioQcView;
  automatic: qc.QcResult | undefined;
  onDecided: () => void;
}) {
  const { state, reload } = useResource(
    () => qc.getChecklist(task.id),
    [task.id, task.status, view.can_decide],
  );
  if (state.status === "loading") return <LoadingState label="Loading the QC checklist" />;
  if (state.status === "failed") return <ErrorState error={state.error} onRetry={reload} />;
  const checklist = state.data;
  if (view.can_decide && checklist.can_answer)
    return (
      <Decision
        task={task}
        view={view}
        checklist={checklist}
        automatic={automatic}
        onDecided={onDecided}
      />
    );
  return checklist.latest ? <RecordedChecklist latest={checklist.latest} /> : null;
}

export function AudioQcPanel({
  task,
  resource,
  onDecided,
}: {
  task: work.TaskDetail;
  resource: AudioQcResource;
  onDecided: () => void;
}) {
  const { state, reload, replace } = resource;
  const { busy, error, run } = useAction();
  // A task cancelled before its recording was checked has no card (FEW-10); one cancelled after
  // keeps its checks and decisions, read only.
  const cancelled = task.status === "CANCELLED";
  if (state.status === "loading")
    return cancelled ? null : <LoadingState label="Loading audio check" />;
  if (state.status === "failed") return <ErrorState error={state.error} onRetry={reload} />;
  const view = state.data;
  if (!view || (cancelled && view.results.length === 0)) return null;
  const automatic = view.results.find((r) => r.automated);
  const listen = automatic?.asset_id && (view.can_decide || view.can_recheck) ? automatic : null;
  const decisions = view.results.filter((r) => !r.automated);
  return (
    <section className="card stack stack--tight qc-panel" aria-labelledby="qc-title">
      {/* The title, the automatic check's result, and listening beside them. */}
      <div className="card__head qc-head">
        <span className="qc-head__title">
          <h2 id="qc-title">Audio quality</h2>
          {automatic ? <Outcome outcome={automatic.outcome} /> : null}
        </span>
        {listen?.asset_id || view.can_recheck ? (
          <div className="actions">
            {listen?.asset_id ? <Player assetId={listen.asset_id} /> : null}
            {view.can_recheck ? (
              <Button
                variant="secondary"
                icon="refresh"
                busy={busy !== null}
                onClick={() =>
                  void run(async () => {
                    const v = await qc.recheckQc(task.id);
                    replace(v);
                    if (v.task_status !== task.status) onDecided();
                  })
                }
              >
                Check the stored file again
              </Button>
            ) : null}
          </div>
        ) : null}
      </div>
      <p className="qc-auto__line">
        <span className="qc-auto__label">Automatic check</span>
        {automatic ? `${automatic.comment} · ${when(automatic.created_at)}` : "Not run yet"}
      </p>
      {automatic ? <Checks result={automatic} /> : null}
      <ErrorNotice error={error} />
      {view.can_assign ? <AssignQc task={task} view={view} onChange={replace} /> : null}
      {decisions.length > 0 || view.can_decide ? (
        <Checklist task={task} view={view} automatic={automatic} onDecided={onDecided} />
      ) : null}
      {decisions.length > 0 ? (
        <div>
          <h3>Decisions</h3>
          <ol className="list timeline">
            {decisions.map((d) => (
              <li key={d.id}>
                <span className="muted">
                  {when(d.created_at)} · {d.reviewer_name ?? "Platform"}
                </span>
                <div>
                  <Outcome outcome={d.outcome} />
                  {d.reason_code ? ` ${labelFor(REASON_LABELS, d.reason_code)}` : ""}
                  {d.comment ? ` · ${d.comment}` : ""}
                </div>
              </li>
            ))}
          </ol>
        </div>
      ) : null}
    </section>
  );
}
