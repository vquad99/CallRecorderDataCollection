// One task (TASK-*), laid out so the status, both people and the next step show without scrolling
// (D-152): a compact stepper on top, then the work on the left (the next step as one card with its
// buttons, a consent form QC sent back (D-146), the QC checklist for the person who decides, the
// speakers' device details while they are filled (D-147)) and the task's records under it (audio
// quality, device details, recordings, phone calls); on the right a summary, both participants as
// one matrix and the history (TaskSide). On a phone: one column, the work first.
import { useState, type ReactNode } from "react";
import { Link, useLocation, useNavigate, useParams } from "react-router";

import * as rec from "../../api/recordings";
import * as work from "../../api/work";
import { useAuth } from "../../auth/AuthContext";
import { BackLink } from "../../components/BackLink";
import { useConfirm } from "../../components/ConfirmDialog";
import { DataTable } from "../../components/DataTable";
import { Button } from "../../components/form/Button";
import { Icon } from "../../components/Icon";
import { ErrorNotice, SuccessNotice } from "../../components/Notice";
import { ErrorState, LoadingState } from "../../components/StateViews";
import { StatusBadge } from "../../components/StatusBadge";
import { Stepper } from "../../components/Stepper";
import { useAction } from "../../hooks/useAction";
import { usePageTitle } from "../../hooks/usePageTitle";
import { useResource } from "../../hooks/useResource";
import { when } from "../../lib/format";
import { consentAnswer, labelFor, reasonChoices, TASK_STATUS_LABELS } from "../../lib/labels";
import { UploadButton } from "../participants/Documents";
import "../participants/participants.css";
import { AudioQcPanel, useAudioQc } from "./AudioQcPanel";
import { PhoneCalls } from "./CallCard";
import { DeviceDetailsCard, devicesWait, useDeviceDetails } from "./DeviceDetails";
import { ListenLatest, Player } from "./Listen";
import { Assignment, ParticipantsMatrix, TaskSummary, Timeline, useSignedForms } from "./TaskSide";
import "./tasks.css";

const FLOW: readonly work.TaskStatus[] = [
  "DRAFT",
  "ASSIGNED",
  "IN_PROGRESS",
  "RECORDED",
  "AUDIO_QC",
  "ADMIN_REVIEW",
  "APPROVED",
];
const status = (s: string) => labelFor(TASK_STATUS_LABELS, s);
/** Statuses beside the path, shown on the stepper at the step they wait at: a consent form to fix
 * waits at Audio QC (D-146); a task on hold at the step it was held from. */
const WAITS_AT: Partial<Record<work.TaskStatus, work.TaskStatus>> = { CONSENT_FIX: "AUDIO_QC" };

/** A changed task, with what to tell the person ("Sent to QC."). */
export type OnTaskChange = (task: work.TaskDetail, message?: string) => void;

/** Resume, put on hold, cancel or delete: the project admin's actions beside the title. The
 * moderator's and the reviewer's steps are the big buttons in the cards below. */
function TaskActions({ task, onChange }: { task: work.TaskDetail; onChange: OnTaskChange }) {
  const navigate = useNavigate();
  const confirm = useConfirm();
  const { busy, error, run } = useAction();
  const can = (to: work.TaskStatus) => task.allowed_transitions.includes(to);
  const held =
    task.status === "ON_HOLD" && task.held_from && can(task.held_from) ? task.held_from : null;
  // The server says whether Delete can work (FEW-12): nothing has happened on the task yet.
  const deletable = Boolean(task.can_delete);

  const move = (to: work.TaskStatus, title: string, confirmLabel: string, done: string) =>
    confirm.ask({
      title,
      confirmLabel,
      danger: to === "CANCELLED",
      reasons: reasonChoices(task.reasons[to]),
      action: async ({ reason, comment }) =>
        onChange(await work.transitionTask(task.id, to, reason, comment), done),
    });
  const remove = () =>
    confirm.ask({
      title: `Delete task ${task.task_code}?`,
      message:
        "Only a task with no recording, call or consent can be deleted. Otherwise, cancel it.",
      askReason: "Why is it deleted?",
      confirmLabel: "Delete task",
      danger: true,
      action: async ({ comment }) => {
        await work.deleteTask(task.id, comment);
        void navigate("/tasks", { state: { message: `Task ${task.task_code} deleted.` } });
      },
    });

  if (!held && !can("ON_HOLD") && !can("CANCELLED") && !deletable) return null;
  return (
    <>
      <span className="actions">
        {held ? (
          <Button
            icon="resume"
            busy={busy === "resume"}
            disabled={busy !== null}
            onClick={() =>
              void run(async () => {
                onChange(await work.transitionTask(task.id, held, "", ""), "Task resumed.");
              }, "resume")
            }
          >
            Resume task
          </Button>
        ) : null}
        {can("ON_HOLD") ? (
          <Button
            variant="secondary"
            icon="pause"
            disabled={busy !== null}
            onClick={() =>
              move("ON_HOLD", `Put task ${task.task_code} on hold?`, "Put on hold", "On hold.")
            }
          >
            Put on hold
          </Button>
        ) : null}
        {can("CANCELLED") ? (
          <Button
            variant="secondary"
            icon="prohibit"
            disabled={busy !== null}
            onClick={() =>
              move("CANCELLED", `Cancel task ${task.task_code}?`, "Cancel task", "Cancelled.")
            }
          >
            Cancel task
          </Button>
        ) : null}
        {deletable ? (
          <Button variant="secondary" icon="trash" disabled={busy !== null} onClick={remove}>
            Delete task
          </Button>
        ) : null}
      </span>
      <ErrorNotice error={error} />
      {confirm.dialog}
    </>
  );
}

const RECORD_STEPS = [
  "Start the session",
  "Both people agree on their consent form",
  "Open the recorder and record",
  "Listen, then send it to QC",
];

/** The moderator's way through a face-to-face session (D-091, D-092, D-119, D-127): start it,
 * wait for both people's consent on their form, record, then listen and send the recording to QC
 * or record it again. */
function RecordCard({ task, onChange }: { task: work.TaskDetail; onChange: OnTaskChange }) {
  const { busy, error, run } = useAction();
  const canStart = task.status !== "RECORDED" && task.allowed_transitions.includes("IN_PROGRESS");
  const recording = task.status === "IN_PROGRESS";
  const review = task.status === "RECORDED" && task.allowed_transitions.includes("AUDIO_QC");
  if (!canStart && !recording && !review) return null;
  const waiting = task.consent_missing.length > 0;
  const devices = devicesWait(task);
  const move = (to: work.TaskStatus, message: string) =>
    void run(async () => onChange(await work.transitionTask(task.id, to, "", ""), message), to);
  // The step in progress (1-based); while recording it is consent first, then the recorder.
  const step = review ? 4 : recording ? (waiting ? 2 : 3) : 1;
  return (
    <section className="card record-card work-card" aria-labelledby="record-card-title">
      <div className="record-card__text">
        <h2 id="record-card-title">
          {review ? "Check your recording" : recording ? "Ready to record" : "Start the session"}
        </h2>
        <ol className="record-card__steps">
          {RECORD_STEPS.map((text, i) => (
            <li key={text} className={i + 1 < step ? "is-done" : i + 1 === step ? "is-now" : ""}>
              {text}
            </li>
          ))}
        </ol>
        {review ? (
          <div className="record-card__listen">
            <ListenLatest taskId={task.id} />
          </div>
        ) : null}
      </div>
      <div className="record-card__go">
        {review ? (
          <>
            <Button
              icon="send"
              busy={busy === "AUDIO_QC"}
              disabled={busy !== null || devices !== null}
              aria-describedby={devices ? "record-qc-waits" : undefined}
              onClick={() => move("AUDIO_QC", "Sent to QC. A QC Executive checks it next.")}
            >
              Send to QC
            </Button>
            <Button
              variant="secondary"
              icon="record"
              busy={busy === "IN_PROGRESS"}
              disabled={busy !== null}
              onClick={() => move("IN_PROGRESS", "Ready to record again.")}
            >
              Record again
            </Button>
            {/* D-147: the device details of both people come first. */}
            {devices ? (
              <p id="record-qc-waits" className="muted">
                {devices}
              </p>
            ) : null}
          </>
        ) : recording ? (
          <>
            {/* D-119: the recorder waits until both people have agreed on their form. */}
            {waiting ? (
              <>
                <Button disabled aria-describedby="recorder-waits">
                  <Icon name="mic" size={16} weight="fill" />
                  Open the recorder
                </Button>
                <p id="recorder-waits" className="muted">
                  Waiting for both people to agree on their consent form.
                </p>
              </>
            ) : (
              <Link className="button button--primary" to={`/tasks/${task.id}/record`}>
                <Icon name="mic" size={16} weight="fill" />
                Open the recorder
              </Link>
            )}
          </>
        ) : (
          <Button
            icon="play"
            busy={busy === "IN_PROGRESS"}
            onClick={() => move("IN_PROGRESS", "Session started.")}
          >
            Start session
          </Button>
        )}
      </div>
      <ErrorNotice error={error} />
    </section>
  );
}

/** The project admin's final word after QC passed the recording (D-092, D-118). */
function AdminReviewCard({ task, onChange }: { task: work.TaskDetail; onChange: OnTaskChange }) {
  const confirm = useConfirm();
  const { busy, error, run } = useAction();
  if (task.status !== "ADMIN_REVIEW" || !task.allowed_transitions.includes("APPROVED")) return null;
  const reject = () =>
    confirm.ask({
      title: `Reject the recording of task ${task.task_code}?`,
      message: "The task ends as rejected.",
      confirmLabel: "Reject",
      danger: true,
      reasons: reasonChoices(task.reasons.REJECTED),
      action: async ({ reason, comment }) =>
        onChange(
          await work.transitionTask(task.id, "REJECTED", reason, comment),
          "Recording rejected.",
        ),
    });
  return (
    <section className="card record-card work-card" aria-labelledby="admin-review-title">
      <div className="record-card__text">
        <h2 id="admin-review-title">Final approval</h2>
        <p className="muted">QC passed this recording. Listen, then approve or reject it.</p>
        <div className="record-card__listen">
          <ListenLatest taskId={task.id} />
        </div>
      </div>
      <div className="record-card__go record-card__go--row">
        <Button
          icon="verified"
          busy={busy === "APPROVED"}
          disabled={busy !== null}
          onClick={() =>
            void run(async () => {
              const t = await work.transitionTask(task.id, "APPROVED", "", "");
              onChange(t, "Recording approved.");
            }, "APPROVED")
          }
        >
          Approve
        </Button>
        {task.allowed_transitions.includes("REJECTED") ? (
          <Button variant="danger" icon="failed" disabled={busy !== null} onClick={reject}>
            Reject
          </Button>
        ) : null}
      </div>
      <ErrorNotice error={error} />
      {confirm.dialog}
    </section>
  );
}

/** QC found the audio fine but a signed consent form not (D-146): whose form and what is wrong
 * with it; the moderator (or an admin) uploads a new scan, then sends the same recording back to
 * QC. Nothing is recorded again. */
function ConsentFixCard({ task, onChange }: { task: work.TaskDetail; onChange: OnTaskChange }) {
  const { busy, error, message, run, upload } = useSignedForms(task, onChange);
  const fix = task.consent_fix;
  if (task.status !== "CONSENT_FIX" || !fix) return null;
  const party = (side: "A" | "B") => (side === "A" ? task.participant_a : task.participant_b);
  const codes = fix.participants.map((p) => p.participant_code).join(" and ");
  // SECB-03: the project was switched to Online since QC sent it back. A signed form no longer
  // counts there: each person agrees on their personal page, and nobody uploads anything.
  const online = fix.by_upload === false;
  return (
    <section className="card record-card work-card" aria-labelledby="consent-fix-title">
      <div className="record-card__text">
        <h2 id="consent-fix-title">Consent form to fix</h2>
        {online ? (
          <p>
            QC found the recording fine but a problem with the signed consent form of {codes}. This
            project now takes consent online, so a signed form no longer counts: once{" "}
            {fix.participants.length > 1 ? "they have" : "the person has"} agreed on their personal
            page, send the same recording back to QC. Nothing is recorded again.
          </p>
        ) : (
          <p>
            QC found the recording fine but a problem with the signed consent form of {codes}.
            Upload a new scan, then send the same recording back to QC. Nothing is recorded again.
          </p>
        )}
        <p className="notice notice--warning">
          <strong>What QC found:</strong> {fix.comment}
          <span className="muted">
            {" "}
            · {fix.by ?? "QC"}, {when(fix.at)}
          </span>
        </p>
        <ul className="consent__rows">
          {fix.participants.map((p) => {
            const who = party(p.side);
            return (
              <li key={p.side} className="consent__row">
                <span className="consent__who">
                  <span className="consent__side">Participant {p.side}</span>
                  <PartyName party={who} />
                </span>
                {p.replaced ? (
                  <StatusBadge
                    tone="success"
                    label={online ? "Agreed online" : "New form uploaded"}
                  />
                ) : (
                  <StatusBadge
                    tone="warning"
                    label={online ? "Not agreed yet" : "New form needed"}
                  />
                )}
                {online ? null : who.can_upload_consent_form ? (
                  <UploadButton
                    label={`Upload a new consent form of ${p.participant_code}`}
                    busy={busy === `upload-${who.id}`}
                    disabled={busy !== null}
                    onFile={upload(who)}
                  />
                ) : (
                  <span className="muted">Ask the moderator or your admin to upload it.</span>
                )}
              </li>
            );
          })}
        </ul>
      </div>
      {fix.can_send_back ? (
        <div className="record-card__go">
          <Button
            icon="send"
            busy={busy === "send"}
            disabled={busy !== null || !fix.forms_replaced}
            aria-describedby={fix.forms_replaced ? undefined : "consent-fix-waits"}
            onClick={() =>
              void run(async () => {
                onChange(
                  await work.sendBackToQc(task.id),
                  "Sent back to QC with the same recording.",
                );
              }, "send")
            }
          >
            Send back to QC
          </Button>
          {fix.forms_replaced ? null : (
            <p id="consent-fix-waits" className="muted">
              {online ? "They agree on their personal page first." : "Upload the new form first."}
            </p>
          )}
        </div>
      ) : null}
      <ErrorNotice error={error} />
      <SuccessNotice message={message} />
    </section>
  );
}

/** Consent comes from each participant's own consent form (D-127): nobody ticks it here, or from
 * their signed form uploaded by staff where the project takes them (D-144). Tasks are made only
 * for people who agreed (D-129), so this card shows for older tasks only: it says who has not
 * agreed, and people who manage participants can email them the form again (or upload the signed
 * form). Calling and recording wait until both have agreed (D-119). */
function ConsentStatus({ task, onChange }: { task: work.TaskDetail; onChange: OnTaskChange }) {
  const { can } = useAuth();
  const canSend = can("participants.manage");
  const uploads = task.consent_mode === "UPLOAD";
  const { busy, error, message, run, upload } = useSignedForms(task, onChange);
  const send = (p: work.Party) => void run(() => work.emailConsentForm(task.project_id, p), p.id);
  const parties = [task.participant_a, task.participant_b];
  return (
    <section className="card consent work-card" aria-labelledby="consent-title">
      <h2 id="consent-title">Waiting for consent</h2>
      <p className="muted">
        {uploads
          ? "Consent is each person's signed consent form, uploaded by staff (or their online agreement). Calling and recording start only when both have one."
          : "Consent is taken from each person's consent form. Calling and recording start only when both have agreed."}
      </p>
      <ul className="consent__rows">
        {parties.map((p, i) =>
          p.may_record ? null : (
            <li key={p.id} className="consent__row">
              <span className="consent__who">
                <span className="consent__side">Participant {i === 0 ? "A" : "B"}</span>
                <PartyName party={p} />
              </span>
              <ConsentChip party={p} mode={task.consent_mode} />
              {uploads ? (
                p.can_upload_consent_form ? (
                  <UploadButton
                    label={`Upload consent form of ${p.participant_code}`}
                    busy={busy === `upload-${p.id}`}
                    disabled={busy !== null}
                    onFile={upload(p)}
                  />
                ) : (
                  <span className="muted">Ask your admin to upload their signed consent form.</span>
                )
              ) : canSend && !p.has_email ? (
                <span className="muted">
                  No email address. Add one with Edit on the Participants page.
                </span>
              ) : canSend ? (
                <Button
                  variant="secondary"
                  icon="mail"
                  busy={busy === p.id}
                  disabled={busy !== null}
                  onClick={() => send(p)}
                >
                  Email consent form again
                </Button>
              ) : (
                <span className="muted">Ask your admin to send them the consent form.</span>
              )}
            </li>
          ),
        )}
      </ul>
      <ErrorNotice error={error} />
      <SuccessNotice message={message} />
    </section>
  );
}

/** A participant as their code, with their name for people who may see it (D-128). */
function PartyName({ party }: { party: work.Party }) {
  return (
    <>
      <span className="code-tag">{party.participant_code}</span>
      {party.display_label ? <span>{party.display_label}</span> : null}
    </>
  );
}

/** A participant's consent as a coloured chip, as the server counts it: their answer, or "Form
 * uploaded" / "Consent form missing" where the project takes signed forms (D-144). */
function ConsentChip({ party, mode }: { party: work.Party; mode: string | undefined }) {
  const { label, tone } = consentAnswer(party.consent_status, mode);
  return <StatusBadge tone={tone} label={label} />;
}

/** Statuses that can have a recording: a cancelled task keeps the one it had (FEW-10), shown only
 * when there is one. */
const HAS_RECORDINGS: readonly string[] = [
  "RECORDED",
  "AUDIO_QC",
  "CONSENT_FIX",
  "ADMIN_REVIEW",
  "APPROVED",
  "REJECTED",
  "CANCELLED",
];
/** The task's finished recordings; a download brings the consent record with the audio. A
 * recording the moderator replaced with Record again is greyed and says so (D-135); the server
 * lists it only for the people who run the project and the moderator. People who may export get
 * the approved task's files as one ZIP, as the project export makes them (D-136). A task
 * cancelled before anything was recorded shows no card at all. */
function Recordings({ task }: { task: work.TaskDetail }) {
  const { can } = useAuth();
  const { state, reload } = useResource(() => rec.listRecordings(task.id), [task.id]);
  const { busy, error, message, run } = useAction();
  const ready = state.status === "loaded" ? state.data.filter((r) => r.state === "READY") : [];
  const exportable = can("exports.create") && task.status === "APPROVED" && ready.length > 0;
  if (task.status === "CANCELLED" && state.status !== "failed" && ready.length === 0) return null;
  return (
    <section className="card" aria-labelledby="recordings-title">
      <div className="card__head">
        <h2 id="recordings-title">Recordings</h2>
        {exportable ? (
          <Button
            variant="secondary"
            icon="fileZip"
            busy={busy === "task-files"}
            disabled={busy !== null}
            onClick={() =>
              void run(async () => {
                await rec.downloadTaskFiles(task.id);
                return "Task files downloaded.";
              }, "task-files")
            }
          >
            Download task files
          </Button>
        ) : null}
      </div>
      {state.status === "loading" ? <LoadingState /> : null}
      {state.status === "failed" ? <ErrorState error={state.error} onRetry={reload} /> : null}
      {state.status === "loaded" && ready.length === 0 ? (
        <p className="muted">No finished recording yet.</p>
      ) : null}
      {ready.length > 0 ? (
        <DataTable className="rec-table">
          <thead>
            <tr>
              <th scope="col">Recording</th>
              <th scope="col">Length</th>
              <th scope="col">Listen</th>
              {can("recordings.download") ? <th scope="col">Download</th> : null}
            </tr>
          </thead>
          <tbody>
            {ready.map((r, i) => {
              const file = rec.deliveryAsset(r.assets);
              return (
                <tr key={r.id} className={r.current ? undefined : "row--replaced"}>
                  <td>
                    <span className="cell-icon">
                      <Icon name="waveform" size={16} />
                      Recording {ready.length - i}
                    </span>
                    {file ? <div className="muted">{rec.formatLabel(file)}</div> : null}
                    {r.current ? null : (
                      <StatusBadge tone="neutral" label="Rejected by moderator – recorded again" />
                    )}
                  </td>
                  {/* The delivered file's length: a phone call is cut to its recording marks;
                      its effective speech and long pauses under it (D-148). */}
                  <td>
                    {rec.lengthLabel(file ? file.duration_ms / 1000 : r.saved_seconds)}
                    {file && rec.speechLabel(file) ? (
                      <div className="muted">{rec.speechLabel(file)}</div>
                    ) : null}
                  </td>
                  <td>{file ? <Player assetId={file.id} /> : "-"}</td>
                  {can("recordings.download") ? (
                    <td>
                      <Button
                        variant="secondary"
                        icon="fileAudio"
                        busy={busy === r.id}
                        disabled={busy !== null}
                        onClick={() =>
                          void run(async () => {
                            await rec.downloadWithConsent(r, task.task_code);
                            return "Recording, consent record and details downloaded.";
                          }, r.id)
                        }
                      >
                        Download with consent form
                      </Button>
                    </td>
                  ) : null}
                </tr>
              );
            })}
          </tbody>
        </DataTable>
      ) : null}
      <ErrorNotice error={error} />
      <SuccessNotice message={message} />
    </section>
  );
}

/** Where the device details are filled (In progress, Recorded): with the work; read only after. */
const FILLS_DEVICES: readonly string[] = ["IN_PROGRESS", "RECORDED"];

/** Who acts next, in one line, for someone with nothing to do on the task now (D-152). */
function nextStep(task: work.TaskDetail, qcName: string | null | undefined): string {
  const moderator = task.moderator_name ?? "the moderator";
  switch (task.status) {
    case "DRAFT":
      return task.moderator_name
        ? `Waiting for ${moderator} to start the session.`
        : "Waiting for a moderator to be assigned.";
    case "ASSIGNED":
      return `Waiting for ${moderator} to start the session.`;
    case "IN_PROGRESS":
      return task.recording_mode === "TELEPHONY"
        ? `${moderator} is calling the participants.`
        : `${moderator} is recording the conversation.`;
    case "RECORDED":
      return `${moderator} listens to the recording, then sends it to QC.`;
    case "AUDIO_QC":
      return qcName
        ? `Waiting for QC: ${qcName} checks the recording.`
        : "Waiting for a QC Executive to be assigned.";
    case "CONSENT_FIX":
      return "Waiting for a new signed consent form.";
    case "ADMIN_REVIEW":
      return "QC passed the recording. Waiting for the project admin's final approval.";
    case "APPROVED":
      return "Approved. Nothing more to do on this task.";
    case "REJECTED":
      return "Rejected. The task has ended.";
    case "CANCELLED":
      return "Cancelled. The task has ended.";
    case "ON_HOLD":
      return "On hold. A project admin resumes it when it can go on.";
    default:
      return "";
  }
}

function NextStep({ text }: { text: string }) {
  if (!text) return null;
  return (
    <section className="card next-step" aria-label="Next step">
      <Icon name="info" size={18} />
      <p>{text}</p>
    </section>
  );
}

/** The two columns under the stepper: the work and the task's records on the left, the summary,
 * the participants and the history on the right (D-152). Grid areas put the work first on a
 * phone, then the side, then the records. */
function TaskBody({
  task,
  onChange,
  reload,
  replace,
}: {
  task: work.TaskDetail;
  onChange: OnTaskChange;
  reload: () => void;
  replace: (t: work.TaskDetail) => void;
}) {
  const devices = useDeviceDetails(task);
  const has = HAS_RECORDINGS.includes(task.status);
  const audio = useAudioQc(task, has);
  // The QC Executive who decides: the checklist is their work.
  const decides = audio.state.status === "loaded" && Boolean(audio.state.data?.can_decide);
  const waitingConsent =
    task.consent_missing.length > 0 && ["DRAFT", "ASSIGNED", "IN_PROGRESS"].includes(task.status);
  // D-147: once saved, the task is loaded again quietly, so Send to QC follows what is missing.
  const deviceCard = (
    <DeviceDetailsCard
      task={task}
      resource={devices}
      onSaved={() => void work.getTask(task.id).then(replace)}
    />
  );
  const fills = FILLS_DEVICES.includes(task.status);
  const qcPanel = has ? <AudioQcPanel task={task} resource={audio} onDecided={reload} /> : null;
  const assigns = task.can_reassign && !task.moderator_id;
  // As the moderator's card decides (RecordCard, CallCard): a session to start, run or check.
  const moderates =
    task.is_moderator &&
    ((task.status !== "RECORDED" && task.allowed_transitions.includes("IN_PROGRESS")) ||
      task.status === "IN_PROGRESS" ||
      (task.status === "RECORDED" && task.allowed_transitions.includes("AUDIO_QC")));
  const hasWork =
    assigns ||
    moderates ||
    waitingConsent ||
    (task.status === "CONSENT_FIX" && Boolean(task.consent_fix)) ||
    (task.status === "ADMIN_REVIEW" && task.allowed_transitions.includes("APPROVED")) ||
    decides ||
    (fills && devices.asked);
  const qcName = audio.state.status === "loaded" ? audio.state.data?.qc_name : null;
  const layout = (callCard: ReactNode, callHistory: ReactNode) => (
    <div className="task-layout">
      <div className="task-work stack">
        {hasWork ? null : <NextStep text={nextStep(task, qcName)} />}
        {assigns ? <Assignment task={task} onChange={onChange} card /> : null}
        {task.recording_mode === "TELEPHONY" ? (
          callCard
        ) : task.is_moderator ? (
          <RecordCard task={task} onChange={onChange} />
        ) : null}
        {waitingConsent ? <ConsentStatus task={task} onChange={onChange} /> : null}
        <ConsentFixCard task={task} onChange={onChange} />
        <AdminReviewCard task={task} onChange={onChange} />
        {decides ? qcPanel : null}
        {fills ? deviceCard : null}
      </div>
      <aside className="task-side" aria-label="About this task">
        <TaskSummary task={task} audio={audio} onChange={onChange} />
        <ParticipantsMatrix task={task} devices={devices} onChange={onChange} />
        <Timeline
          taskId={task.id}
          version={`${task.status}-${task.moderator_id ?? ""}-${task.participant_a.consent_at ?? ""}-${task.participant_b.consent_at ?? ""}`}
        />
      </aside>
      <div className="task-rest stack">
        {decides ? null : qcPanel}
        {fills ? null : deviceCard}
        {has ? <Recordings task={task} /> : null}
        {callHistory}
      </div>
    </div>
  );
  return task.recording_mode === "TELEPHONY" ? (
    <PhoneCalls
      task={task}
      onChange={onChange}
      // Quietly: the page stays as it is until the new task arrives (no loading flash).
      onTaskStale={() => void work.getTask(task.id).then(replace)}
    >
      {layout}
    </PhoneCalls>
  ) : (
    layout(null, null)
  );
}

/** The page of one task. Remounted for each task (FEW-14): its message and every card's state
 * start again when the address moves to another task (a participant's Sessions link). */
export function TaskDetailPage() {
  const { taskId = "" } = useParams();
  return <TaskPage key={taskId} taskId={taskId} />;
}

function TaskPage({ taskId }: { taskId: string }) {
  const { state, reload, replace } = useResource(() => work.getTask(taskId), [taskId]);
  // A message handed over by the page before (the recorder: "Sent to QC.").
  const handed = (useLocation().state as { message?: string } | null)?.message ?? null;
  const [message, setMessage] = useState<string | null>(handed);
  const loaded = state.status === "loaded" ? state.data : null;
  // The browser tab names the task once it has loaded (UXA-08).
  usePageTitle(loaded ? `Task ${loaded.task_code}` : null);
  if (state.status === "loading") return <LoadingState label="Loading task" />;
  if (state.status === "failed") {
    // A task that is gone or not one's own: still a titled page with the way back (POL-13).
    return (
      <section aria-labelledby="task-title" className="stack">
        <BackLink to="/tasks">All tasks</BackLink>
        <h1 id="task-title">Task</h1>
        <ErrorState error={state.error} onRetry={reload} />
      </section>
    );
  }
  const task = state.data;
  const onChange: OnTaskChange = (t, text) => {
    replace(t);
    setMessage(text ?? null);
  };
  // Where the task is, or stopped (FEW-11): on hold at the step it was held from, rejected or
  // cancelled at the step it ended at; a consent form to fix waits at Audio QC.
  const stop = task.held_from ?? task.ended_from ?? "DRAFT";
  const onPath = FLOW.includes(task.status)
    ? task.status
    : (WAITS_AT[task.status] ?? WAITS_AT[stop] ?? stop);
  return (
    <section aria-labelledby="task-title" className="stack task-page">
      <BackLink to="/tasks">All tasks</BackLink>
      <div className="page-header">
        <span className="page-header__title">
          <h1 id="task-title">Task {task.task_code}</h1>
          <StatusBadge status={task.status} label={status(task.status)} />
        </span>
        <TaskActions task={task} onChange={onChange} />
      </div>
      <SuccessNotice message={message} />
      <div className="task-steps">
        <Stepper
          steps={FLOW.map(status)}
          current={task.status === "APPROVED" ? FLOW.length : Math.max(0, FLOW.indexOf(onPath))}
          halted={!FLOW.includes(task.status)}
          label={`Workflow progress: ${status(task.status)}`}
        />
      </div>
      <TaskBody task={task} onChange={onChange} reload={reload} replace={replace} />
    </section>
  );
}
