// Audio quality card on the task page (D-079): what the automatic check found, who checks the
// recording, a player, the QC checklist (D-146) and the QC Executive's decision: Pass, Reject
// (D-118) or, where the project takes signed forms, Send back for consent. The server decides who
// may do what; this only shows the controls it allows.
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
        <DataTable label={all ? "All automatic checks" : "Checks that need attention"}>
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
              <tr key={c.code}>
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
      <ErrorNotice error={error} />
      <Button
        type="submit"
        variant="secondary"
        icon="userPlus"
        busy={busy !== null}
        disabled={!userId || (reassigning && !reason.trim())}
      >
        {reassigning ? "Reassign QC" : "Assign QC"}
      </Button>
    </form>
  );
}

/** What the answers say about the decision, in one line. */
function hint(j: Judgement, consentCheck: boolean): string {
  if (j.failing.length > 0)
    return `The recording fails the checklist (${j.failing[0]}): reject it.`;
  if (j.missing > 0)
    return j.missing === 1
      ? "1 question still to answer."
      : `${j.missing} questions still to answer.`;
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
  return (
    <>
      <section className="stack stack--tight" aria-labelledby="qc-checklist-title">
        <h3 id="qc-checklist-title">QC checklist</h3>
        <p className="muted">
          Listen, then tick Yes or No for every question. Your answers are kept as you tick and go
          with your decision.
        </p>
        <ChecklistForm task={task} view={checklist} answers={answers} onChange={change} />
        <p className="muted" role="status">
          {draft.state === "saving"
            ? "Saving your answers…"
            : draft.state === "saved"
              ? "Answers saved."
              : ""}
        </p>
        {draft.state === "failed" ? (
          <p className="notice notice--warning">
            Your answers could not be saved just now ({draft.error?.message}). They still go with
            your decision.
          </p>
        ) : null}
      </section>
      <section className="stack stack--tight" aria-labelledby="qc-decision-title">
        <h3 id="qc-decision-title">Your decision</h3>
        <p className="muted">
          {view.pass_approves
            ? "Pass approves the task: this project has no admin review."
            : "Pass sends it to the project admin for final approval."}{" "}
          Reject ends the task.
          {consentCheck
            ? " Send back for consent returns it to the moderator for a new signed form; the recording stays."
            : ""}
        </p>
        <p className="qc__hint">{hint(j, consentCheck)}</p>
        <div className="actions">
          <Button icon="verified" busy={busy !== null} disabled={!canPass} onClick={pass}>
            Pass
          </Button>
          {consentCheck ? (
            <Button
              variant="secondary"
              icon="fileText"
              disabled={busy !== null || !canSendBack}
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
  onDecided,
}: {
  task: work.TaskDetail;
  onDecided: () => void;
}) {
  const { state, reload, replace } = useResource(() => qc.getAudioQc(task.id), [task.id]);
  const { busy, error, run } = useAction();
  if (state.status === "loading") return <LoadingState label="Loading audio check" />;
  if (state.status === "failed") return <ErrorState error={state.error} onRetry={reload} />;
  const view = state.data;
  const automatic = view.results.find((r) => r.automated);
  const listen = automatic?.asset_id && (view.can_decide || view.can_recheck) ? automatic : null;
  const decisions = view.results.filter((r) => !r.automated);
  return (
    <section className="card stack stack--tight" aria-labelledby="qc-title">
      <div className="page-header">
        <h2 id="qc-title">Audio quality</h2>
        {automatic ? <Outcome outcome={automatic.outcome} /> : null}
      </div>
      <dl className="checks">
        <div className="checks__row">
          <dt>QC Executive</dt>
          <dd>{view.qc_name ?? "Not assigned"}</dd>
        </div>
        <div className="checks__row">
          <dt>Automatic check</dt>
          <dd>
            {automatic ? `${automatic.comment} · ${when(automatic.created_at)}` : "Not run yet"}
          </dd>
        </div>
      </dl>
      {automatic ? <Checks result={automatic} /> : null}
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
