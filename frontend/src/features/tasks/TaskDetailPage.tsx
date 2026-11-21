// One task: participants and consent, moderator, the next step as one card with its buttons,
// audio quality, recordings and the history (TASK-*).
import { useState } from "react";
import { Link, useLocation, useNavigate, useParams } from "react-router";

import { listMembers } from "../../api/projects";
import * as rec from "../../api/recordings";
import * as work from "../../api/work";
import { useAuth } from "../../auth/AuthContext";
import { BackLink } from "../../components/BackLink";
import { useConfirm } from "../../components/ConfirmDialog";
import { DataTable } from "../../components/DataTable";
import { Button } from "../../components/form/Button";
import { Select } from "../../components/form/Select";
import { TextField } from "../../components/form/TextField";
import { Icon, IconTile } from "../../components/Icon";
import { ErrorNotice, SuccessNotice } from "../../components/Notice";
import { ErrorState, LoadingState } from "../../components/StateViews";
import { StatusBadge } from "../../components/StatusBadge";
import { Stepper } from "../../components/Stepper";
import { useAction } from "../../hooks/useAction";
import { useResource } from "../../hooks/useResource";
import { when } from "../../lib/format";
import {
  consentAnswer,
  labelFor,
  MODE_LABELS,
  PRIORITY_LABELS,
  REASON_LABELS,
  reasonChoices,
  TASK_STATUS_LABELS,
} from "../../lib/labels";
import { AudioQcPanel } from "./AudioQcPanel";
import { PhoneCalls } from "./CallCard";
import { openDocument, sendDocument, UploadButton, uploadedText } from "../participants/Documents";
import "../participants/participants.css";
import { ListenLatest, Player } from "./Listen";
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
  const deletable = task.can_assign && ["DRAFT", "ASSIGNED", "CANCELLED"].includes(task.status);

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
  const move = (to: work.TaskStatus, message: string) =>
    void run(async () => onChange(await work.transitionTask(task.id, to, "", ""), message), to);
  // The step in progress (1-based); while recording it is consent first, then the recorder.
  const step = review ? 4 : recording ? (waiting ? 2 : 3) : 1;
  return (
    <section className="card record-card" aria-labelledby="record-card-title">
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
              disabled={busy !== null}
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
    <section className="card record-card" aria-labelledby="admin-review-title">
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

function Assignment({ task, onChange }: { task: work.TaskDetail; onChange: OnTaskChange }) {
  const members = useResource(() => listMembers(task.project_id), [task.project_id]);
  const [userId, setUserId] = useState("");
  const [reason, setReason] = useState("");
  const { busy, error, run } = useAction();
  const moderators =
    members.state.status === "loaded"
      ? members.state.data.filter((m) => m.roles.includes("MODERATOR") && m.status === "ACTIVE")
      : [];
  return (
    <form
      className="card"
      onSubmit={(e) => {
        e.preventDefault();
        void run(async () => {
          onChange(await work.assignModerator(task.id, userId, reason), "Moderator assigned.");
          setUserId("");
          setReason("");
        });
      }}
    >
      <h2>{task.moderator_id ? "Reassign moderator" : "Assign moderator"}</h2>
      <Select
        label="Moderator"
        value={userId}
        onChange={(e) => setUserId(e.target.value)}
        options={[
          { value: "", label: "Choose a moderator" },
          ...moderators
            .filter((m) => m.user_id !== task.moderator_id)
            .map((m) => ({ value: m.user_id, label: `${m.display_name} (${m.email})` })),
        ]}
      />
      {task.moderator_id ? (
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
        busy={busy !== null}
        disabled={!userId || (Boolean(task.moderator_id) && !reason.trim())}
      >
        {task.moderator_id ? "Reassign" : "Assign"}
      </Button>
    </form>
  );
}

/** Uploading a participant's signed consent form from the task page, and opening one (D-144):
 * the task is loaded again after an upload, so its consent and buttons follow at once. */
function useSignedForms(task: work.TaskDetail, onChange: OnTaskChange) {
  const action = useAction();
  const upload = (p: work.Party) => (file: File) =>
    void action.run(async () => {
      await sendDocument(task.project_id, p.id, "CONSENT_FORM", file);
      onChange(
        await work.getTask(task.id),
        `Signed consent form of ${p.participant_code} uploaded.`,
      );
    }, `upload-${p.id}`);
  const view = (p: work.Party, doc: work.ParticipantDocument) =>
    void action.run(() => openDocument(task.project_id, p.id, doc), `view-${doc.id}`);
  return { ...action, upload, view };
}

/** The two participants' signed consent forms, where the project takes them (D-144): the project's
 * admins, the moderator and the QC Executive of the task open them here; the admins and the
 * moderator of the open task upload or replace one (for example a better scan). */
function SignedForms({ task, onChange }: { task: work.TaskDetail; onChange: OnTaskChange }) {
  const { busy, error, message, upload, view } = useSignedForms(task, onChange);
  const parties = [task.participant_a, task.participant_b];
  const shown = parties.some((p) => p.consent_form || p.can_upload_consent_form);
  if (task.consent_mode !== "UPLOAD" || !shown) return null;
  return (
    <section className="card consent" aria-labelledby="signed-forms-title">
      <h2 id="signed-forms-title">
        <Icon name="fileText" size={20} />
        Signed consent forms
      </h2>
      <ul className="consent__rows">
        {parties.map((p, i) => {
          const doc = p.consent_form ?? null;
          return (
            <li key={p.id} className="consent__row signed-forms__row">
              <span className="consent__who">
                <span className="consent__side">Participant {i === 0 ? "A" : "B"}</span>
                <PartyName party={p} />
              </span>
              {doc ? (
                <span className="docs__file">
                  <span className="docs__name">{doc.file_name}</span>
                  <span className="muted">{uploadedText(doc)}</span>
                </span>
              ) : (
                <StatusBadge tone="warning" label="Consent form missing" />
              )}
              <span className="actions">
                {doc ? (
                  <Button
                    variant="secondary"
                    icon="eye"
                    busy={busy === `view-${doc.id}`}
                    disabled={busy !== null}
                    aria-label={`View the signed consent form of ${p.participant_code}`}
                    onClick={() => view(p, doc)}
                  >
                    View
                  </Button>
                ) : null}
                {p.can_upload_consent_form ? (
                  <UploadButton
                    label={`${doc ? "Replace" : "Upload"} consent form of ${p.participant_code}`}
                    busy={busy === `upload-${p.id}`}
                    disabled={busy !== null}
                    onFile={upload(p)}
                  />
                ) : null}
              </span>
            </li>
          );
        })}
      </ul>
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
    <section className="card consent" aria-labelledby="consent-title">
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

const ENTRY_KIND: Record<work.TimelineEntry["kind"], string> = {
  status: "Status changed",
  assignment: "Assigned",
  comment: "Comment",
};

/** A history entry in words: "In progress → Recorded" with the reason given, or its text. */
export function entryText(e: work.TimelineEntry): { title: string; detail: string } {
  if (e.kind !== "status" || !e.to_status) return { title: e.text, detail: "" };
  const title = e.from_status
    ? `${status(e.from_status)} → ${status(e.to_status)}`
    : `Created as ${status(e.to_status)}`;
  const detail = [e.reason_code ? labelFor(REASON_LABELS, e.reason_code) : "", e.comment ?? ""]
    .filter(Boolean)
    .join(" · ");
  return { title, detail };
}

function Timeline({ taskId, version }: { taskId: string; version: string }) {
  const { state, reload } = useResource(() => work.getTimeline(taskId), [taskId, version]);
  const [text, setText] = useState("");
  const { busy, error, message, run } = useAction(reload);
  return (
    <section className="card" aria-labelledby="timeline-title">
      <h2 id="timeline-title">History</h2>
      {state.status === "loading" ? <LoadingState /> : null}
      {state.status === "failed" ? <ErrorState error={state.error} onRetry={reload} /> : null}
      {state.status === "loaded" ? (
        <ol className="list timeline">
          {state.data.map((e, i) => {
            const { title, detail } = entryText(e);
            return (
              <li key={`${e.at}-${i}`}>
                <span className="muted">
                  {when(e.at)} · {e.actor ?? "Platform"} · {ENTRY_KIND[e.kind]}
                </span>
                <div>{title}</div>
                {detail ? <div className="muted">{detail}</div> : null}
              </li>
            );
          })}
        </ol>
      ) : null}
      <form
        onSubmit={(e) => {
          e.preventDefault();
          void run(async () => {
            await work.addComment(taskId, text);
            setText("");
            return "Comment added.";
          });
        }}
      >
        <TextField label="Add a comment" value={text} onChange={(e) => setText(e.target.value)} />
        <Button
          type="submit"
          variant="secondary"
          icon="comment"
          busy={busy !== null}
          disabled={!text.trim()}
        >
          Add comment
        </Button>
      </form>
      <ErrorNotice error={error} />
      <SuccessNotice message={message} />
    </section>
  );
}

const HAS_RECORDINGS: readonly string[] = [
  "RECORDED",
  "AUDIO_QC",
  "ADMIN_REVIEW",
  "APPROVED",
  "REJECTED",
];

/** The task's finished recordings; a download brings the consent record with the audio. A
 * recording the moderator replaced with Record again is greyed and says so (D-135); the server
 * lists it only for the people who run the project and the moderator. People who may export get
 * the approved task's files as one ZIP, as the project export makes them (D-136). */
function Recordings({ task }: { task: work.TaskDetail }) {
  const { can } = useAuth();
  const { state, reload } = useResource(() => rec.listRecordings(task.id), [task.id]);
  const { busy, error, message, run } = useAction();
  const ready = state.status === "loaded" ? state.data.filter((r) => r.state === "READY") : [];
  const exportable = can("exports.create") && task.status === "APPROVED" && ready.length > 0;
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
        <DataTable>
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
                  {/* The delivered file's length: a phone call is cut to its recording marks. */}
                  <td>{rec.lengthLabel(file ? file.duration_ms / 1000 : r.saved_seconds)}</td>
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

export function TaskDetailPage() {
  const { taskId = "" } = useParams();
  const { state, reload, replace } = useResource(() => work.getTask(taskId), [taskId]);
  // A message handed over by the page before (the recorder: "Sent to QC.").
  const handed = (useLocation().state as { message?: string } | null)?.message ?? null;
  const [message, setMessage] = useState<string | null>(handed);
  if (state.status === "loading") return <LoadingState label="Loading task" />;
  if (state.status === "failed") return <ErrorState error={state.error} onRetry={reload} />;
  const task = state.data;
  const onChange: OnTaskChange = (t, text) => {
    replace(t);
    setMessage(text ?? null);
  };
  const waitingConsent =
    task.consent_missing.length > 0 && ["DRAFT", "ASSIGNED", "IN_PROGRESS"].includes(task.status);
  const consent = waitingConsent ? <ConsentStatus task={task} onChange={onChange} /> : null;
  const onPath = FLOW.includes(task.status) ? task.status : (task.held_from ?? "DRAFT");
  return (
    <section aria-labelledby="task-title" className="stack">
      <BackLink to="/tasks">All tasks</BackLink>
      <div className="page-header">
        <span className="page-header__title">
          <h1 id="task-title">
            <IconTile name={task.recording_mode === "TELEPHONY" ? "phone" : "mic"} />
            Task {task.task_code}
          </h1>
          <StatusBadge status={task.status} label={status(task.status)} />
        </span>
        <TaskActions task={task} onChange={onChange} />
      </div>
      <SuccessNotice message={message} />
      <div className="card">
        <Stepper
          steps={FLOW.map(status)}
          current={task.status === "APPROVED" ? FLOW.length : Math.max(0, FLOW.indexOf(onPath))}
          halted={!FLOW.includes(task.status)}
          label={`Workflow progress: ${status(task.status)}`}
        />
      </div>
      <dl className="checks checks--facts card">
        <div className="checks__row">
          <dt>Recording type</dt>
          <dd>{labelFor(MODE_LABELS, task.recording_mode)}</dd>
        </div>
        <div className="checks__row">
          <dt>Priority</dt>
          <dd>{labelFor(PRIORITY_LABELS, task.priority)}</dd>
        </div>
        <div className="checks__row">
          <dt>Moderator</dt>
          <dd>{task.moderator_name ?? "Not assigned"}</dd>
        </div>
        {[task.participant_a, task.participant_b].map((p, i) => (
          <div key={p.id} className="checks__row">
            <dt>Participant {i === 0 ? "A" : "B"}</dt>
            <dd className="party">
              <span className="party__name">{p.display_label ?? p.participant_code}</span>
              <span className="party__meta">
                {p.display_label ? <span className="code-tag">{p.participant_code}</span> : null}
                <ConsentChip party={p} mode={task.consent_mode} />
              </span>
            </dd>
          </div>
        ))}
        {task.reason_code ? (
          <div className="checks__row">
            <dt>Reason</dt>
            <dd>{labelFor(REASON_LABELS, task.reason_code)}</dd>
          </div>
        ) : null}
      </dl>
      <SignedForms task={task} onChange={onChange} />
      {task.can_reassign ? <Assignment task={task} onChange={onChange} /> : null}
      {task.recording_mode === "TELEPHONY" ? (
        <PhoneCalls
          task={task}
          onChange={onChange}
          // Quietly: the page stays as it is until the new task arrives (no loading flash).
          onTaskStale={() => void work.getTask(task.id).then(replace)}
          consent={consent}
        />
      ) : (
        <>
          {task.is_moderator ? <RecordCard task={task} onChange={onChange} /> : null}
          {consent}
        </>
      )}
      <AdminReviewCard task={task} onChange={onChange} />
      {HAS_RECORDINGS.includes(task.status) ? (
        <AudioQcPanel task={task} onDecided={reload} />
      ) : null}
      {HAS_RECORDINGS.includes(task.status) ? <Recordings task={task} /> : null}
      <Timeline
        taskId={task.id}
        version={`${task.status}-${task.moderator_id ?? ""}-${task.participant_a.consent_at ?? ""}-${task.participant_b.consent_at ?? ""}`}
      />
    </section>
  );
}
