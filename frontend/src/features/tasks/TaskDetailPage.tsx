// One task: participants and consent, moderator, status actions, comments and timeline (TASK-*).
import { useState } from "react";
import { Link, useParams } from "react-router";

import type { ApiError } from "../../api/client";
import { listMembers } from "../../api/projects";
import * as rec from "../../api/recordings";
import * as work from "../../api/work";
import { useAuth } from "../../auth/AuthContext";
import { Button } from "../../components/form/Button";
import { Select } from "../../components/form/Select";
import { TextField } from "../../components/form/TextField";
import { ErrorNotice, SuccessNotice } from "../../components/Notice";
import { ErrorState, LoadingState } from "../../components/StateViews";
import { toApiError, useResource } from "../../hooks/useResource";
import { StatusBadge } from "../../components/StatusBadge";
import { Icon, IconTile } from "../../components/Icon";
import { Stepper } from "../../components/Stepper";
import { AudioQcPanel, Player } from "./AudioQcPanel";
import { PhoneCalls } from "./CallCard";

const FLOW: readonly string[] = [
  "DRAFT",
  "ASSIGNED",
  "IN_PROGRESS",
  "RECORDED",
  "AUDIO_QC",
  "ADMIN_REVIEW",
  "APPROVED",
];
const label = (s: string) => work.TASK_STATUS_LABELS[s as work.TaskStatus] ?? s;
const words = (s: string) => s.toLowerCase().replace(/_/g, " ");

function Actions({
  task,
  onChange,
}: {
  task: work.TaskDetail;
  onChange: (t: work.TaskDetail) => void;
}) {
  const [target, setTarget] = useState<work.TaskStatus | "">("");
  const [reason, setReason] = useState("");
  const [comment, setComment] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<ApiError | null>(null);
  if (task.allowed_transitions.length === 0) return null;
  const reasons = target ? task.reasons[target] : undefined;

  return (
    <form
      className="card"
      onSubmit={(e) => {
        e.preventDefault();
        if (!target) return;
        setBusy(true);
        setError(null);
        work
          .transitionTask(task.id, target, reason, comment)
          .then((t) => {
            onChange(t);
            setTarget("");
            setReason("");
            setComment("");
          })
          .catch((err: unknown) => setError(toApiError(err)))
          .finally(() => setBusy(false));
      }}
    >
      <h2>Change status</h2>
      <Select
        label="Move to"
        value={target}
        onChange={(e) => {
          setTarget(e.target.value as work.TaskStatus);
          setReason("");
        }}
        options={[
          { value: "", label: "Choose" },
          ...task.allowed_transitions.map((s) => ({
            value: s,
            label: s === task.held_from ? `Resume (${label(s)})` : label(s),
          })),
        ]}
      />
      {reasons ? (
        <Select
          label="Reason"
          value={reason}
          onChange={(e) => setReason(e.target.value)}
          options={[
            { value: "", label: "Choose a reason" },
            ...reasons.map((r) => ({ value: r, label: words(r) })),
          ]}
        />
      ) : null}
      {reasons ? (
        <TextField
          label="Comment"
          hint="Required when the reason is 'other'."
          value={comment}
          onChange={(e) => setComment(e.target.value)}
        />
      ) : null}
      <ErrorNotice error={error} />
      <Button type="submit" busy={busy} disabled={!target || (Boolean(reasons) && !reason)}>
        Apply
      </Button>
    </form>
  );
}

/** The delivery file of the newest finished recording, to listen to (D-092). */
function ListenLatest({ taskId }: { taskId: string }) {
  const { state } = useResource(() => rec.listRecordings(taskId), [taskId]);
  if (state.status !== "loaded") return null;
  const latest = state.data.find((r) => r.state === "READY");
  const asset = latest ? rec.deliveryAsset(latest.assets) : undefined;
  return asset ? (
    <Player assetId={asset.id} />
  ) : (
    <p className="muted">No finished recording yet.</p>
  );
}

/** The moderator's way through a session (D-091, D-092): start it, record, then listen and send
 * the recording to QC or record it again. One card, one main button at each step. */
function RecordCard({
  task,
  onChange,
}: {
  task: work.TaskDetail;
  onChange: (t: work.TaskDetail) => void;
}) {
  const [busy, setBusy] = useState<string | null>(null);
  const [error, setError] = useState<ApiError | null>(null);
  const canStart = task.status !== "RECORDED" && task.allowed_transitions.includes("IN_PROGRESS");
  const recording = task.status === "IN_PROGRESS";
  const review = task.status === "RECORDED" && task.allowed_transitions.includes("AUDIO_QC");
  if (!canStart && !recording && !review) return null;
  const move = (to: work.TaskStatus) => {
    setBusy(to);
    setError(null);
    work
      .transitionTask(task.id, to, "", "")
      .then(onChange)
      .catch((err: unknown) => setError(toApiError(err)))
      .finally(() => setBusy(null));
  };
  const step = review ? 4 : recording ? 2 : 1;
  const steps = [
    "Start the session",
    "Record each person's consent below",
    "Open the recorder and record",
    "Listen, then send it to QC",
  ];
  return (
    <section className="card record-card" aria-labelledby="record-card-title">
      <div className="record-card__text">
        <h2 id="record-card-title">
          {review ? "Check your recording" : recording ? "Ready to record" : "Start the session"}
        </h2>
        <ol className="record-card__steps">
          {steps.map((text, i) => (
            <li
              key={text}
              className={
                i + 1 < step ? "is-done" : i + 1 === step || (recording && i === 2) ? "is-now" : ""
              }
            >
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
            <Button busy={busy === "AUDIO_QC"} onClick={() => move("AUDIO_QC")}>
              Send to QC
            </Button>
            <Button
              variant="secondary"
              busy={busy === "IN_PROGRESS"}
              onClick={() => move("IN_PROGRESS")}
            >
              Record again
            </Button>
          </>
        ) : recording ? (
          <Link className="button button--primary" to={`/tasks/${task.id}/record`}>
            <Icon name="mic" size={16} weight="fill" />
            Open the recorder
          </Link>
        ) : (
          <Button busy={busy === "IN_PROGRESS"} onClick={() => move("IN_PROGRESS")}>
            Start session
          </Button>
        )}
      </div>
      <ErrorNotice error={error} />
    </section>
  );
}

/** The project admin's final word after QC passed the recording (D-092). */
function AdminReviewCard({
  task,
  onChange,
}: {
  task: work.TaskDetail;
  onChange: (t: work.TaskDetail) => void;
}) {
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<ApiError | null>(null);
  if (task.status !== "ADMIN_REVIEW" || !task.allowed_transitions.includes("APPROVED")) return null;
  return (
    <section className="card record-card" aria-labelledby="admin-review-title">
      <div className="record-card__text">
        <h2 id="admin-review-title">Final approval</h2>
        <p className="muted">
          QC passed this recording. Listen, then approve it. To reject it or send it back for a new
          recording, use Change status below.
        </p>
        <div className="record-card__listen">
          <ListenLatest taskId={task.id} />
        </div>
      </div>
      <div className="record-card__go">
        <Button
          busy={busy}
          onClick={() => {
            setBusy(true);
            setError(null);
            work
              .transitionTask(task.id, "APPROVED", "", "")
              .then(onChange)
              .catch((err: unknown) => setError(toApiError(err)))
              .finally(() => setBusy(false));
          }}
        >
          Approve
        </Button>
      </div>
      <ErrorNotice error={error} />
    </section>
  );
}

function Assignment({
  task,
  onChange,
}: {
  task: work.TaskDetail;
  onChange: (t: work.TaskDetail) => void;
}) {
  const members = useResource(() => listMembers(task.project_id), [task.project_id]);
  const [userId, setUserId] = useState("");
  const [reason, setReason] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<ApiError | null>(null);
  const moderators =
    members.state.status === "loaded"
      ? members.state.data.filter((m) => m.roles.includes("MODERATOR") && m.status === "ACTIVE")
      : [];
  return (
    <form
      className="card"
      onSubmit={(e) => {
        e.preventDefault();
        setBusy(true);
        setError(null);
        work
          .assignModerator(task.id, userId, reason)
          .then((t) => {
            onChange(t);
            setUserId("");
            setReason("");
          })
          .catch((err: unknown) => setError(toApiError(err)))
          .finally(() => setBusy(false));
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
        busy={busy}
        disabled={!userId || (Boolean(task.moderator_id) && !reason.trim())}
      >
        {task.moderator_id ? "Reassign" : "Assign"}
      </Button>
    </form>
  );
}

function ConsentCapture({
  task,
  onChange,
}: {
  task: work.TaskDetail;
  onChange: (t: work.TaskDetail) => void;
}) {
  const [method, setMethod] = useState("VERBAL_RECORDED");
  const [error, setError] = useState<ApiError | null>(null);
  const [busy, setBusy] = useState(false);
  const record = (participantId: string, status: string) => {
    setBusy(true);
    setError(null);
    work
      .captureConsent(task.id, participantId, status, method)
      .then(onChange)
      .catch((err: unknown) => setError(toApiError(err)))
      .finally(() => setBusy(false));
  };
  return (
    <section className="card consent" aria-labelledby="consent-title">
      <div className="consent__head">
        <div>
          <h2 id="consent-title">Record consent</h2>
          <p className="muted">Ask each person before you record, then mark their answer.</p>
        </div>
        <div className="consent__method">
          <Select
            label="How consent was given"
            value={method}
            onChange={(e) => setMethod(e.target.value)}
            options={["VERBAL_RECORDED", "VERBAL_NOTED", "WRITTEN", "DIGITAL"].map((m) => ({
              value: m,
              label: words(m),
            }))}
          />
        </div>
      </div>
      <ul className="consent__rows">
        {[task.participant_a, task.participant_b].map((p, i) => (
          <li key={p.id} className="consent__row">
            <span className="consent__who">
              <span className="consent__side">Participant {i === 0 ? "A" : "B"}</span>
              <span className="code-tag">{p.participant_code}</span>
            </span>
            <ConsentChip status={p.consent_status} />
            <span className="seg" role="group" aria-label={`Consent of ${p.participant_code}`}>
              <button
                type="button"
                className="seg__option"
                aria-pressed={p.consent_status === "GIVEN"}
                disabled={busy}
                onClick={() => record(p.id, "GIVEN")}
              >
                Consent given
              </button>
              <button
                type="button"
                className="seg__option seg__option--no"
                aria-pressed={p.consent_status === "REFUSED"}
                disabled={busy}
                onClick={() => record(p.id, "REFUSED")}
              >
                Refused
              </button>
            </span>
          </li>
        ))}
      </ul>
      <ErrorNotice error={error} />
    </section>
  );
}

const CONSENT_WORDS: Record<string, string> = {
  GIVEN: "Given",
  REFUSED: "Refused",
  WITHDRAWN: "Withdrawn",
};

/** A participant's consent for this session as a coloured chip (D-091). */
function ConsentChip({ status }: { status: string | null }) {
  const tone =
    status === "GIVEN" ? "success" : status === "REFUSED" || status === "WITHDRAWN" ? "danger" : "";
  return (
    <span className={`badge${tone ? ` badge--${tone}` : ""}`}>
      <span className="badge__dot" aria-hidden="true" />
      {CONSENT_WORDS[status ?? ""] ?? "Not recorded"}
    </span>
  );
}

function Timeline({ taskId, version }: { taskId: string; version: string }) {
  const { state, reload } = useResource(() => work.getTimeline(taskId), [taskId, version]);
  const [text, setText] = useState("");
  const [error, setError] = useState<ApiError | null>(null);
  const [ok, setOk] = useState<string | null>(null);
  const [sending, setSending] = useState(false);
  return (
    <section className="card" aria-labelledby="timeline-title">
      <h2 id="timeline-title">History</h2>
      {state.status === "loading" ? <LoadingState /> : null}
      {state.status === "failed" ? <ErrorState error={state.error} onRetry={reload} /> : null}
      {state.status === "loaded" ? (
        <ol className="list timeline">
          {state.data.map((e, i) => (
            <li key={`${e.at}-${i}`}>
              <span className="muted">
                {new Date(e.at).toLocaleString()} · {e.actor ?? "Platform"} · {e.kind}
              </span>
              <div>{e.text}</div>
            </li>
          ))}
        </ol>
      ) : null}
      <form
        onSubmit={(e) => {
          e.preventDefault();
          setError(null);
          setSending(true);
          work
            .addComment(taskId, text)
            .then(() => {
              setText("");
              setOk("Comment added.");
              reload();
            })
            .catch((err: unknown) => setError(toApiError(err)))
            .finally(() => setSending(false));
        }}
      >
        <TextField label="Add a comment" value={text} onChange={(e) => setText(e.target.value)} />
        <Button type="submit" variant="secondary" busy={sending} disabled={!text.trim()}>
          Add comment
        </Button>
      </form>
      <ErrorNotice error={error} />
      <SuccessNotice message={ok} />
    </section>
  );
}

const HAS_RECORDINGS = ["RECORDED", "AUDIO_QC", "ADMIN_REVIEW", "APPROVED", "REJECTED", "RETURNED"];

/** The task's finished recordings; a download brings the consent record with the audio. */
function Recordings({ task }: { task: work.TaskDetail }) {
  const { can } = useAuth();
  const { state, reload } = useResource(() => rec.listRecordings(task.id), [task.id]);
  const [busy, setBusy] = useState<string | null>(null);
  const [error, setError] = useState<ApiError | null>(null);
  const [message, setMessage] = useState<string | null>(null);
  const ready = state.status === "loaded" ? state.data.filter((r) => r.state === "READY") : [];
  return (
    <section className="card" aria-labelledby="recordings-title">
      <h2 id="recordings-title">Recordings</h2>
      {state.status === "loading" ? <LoadingState /> : null}
      {state.status === "failed" ? <ErrorState error={state.error} onRetry={reload} /> : null}
      {state.status === "loaded" && ready.length === 0 ? (
        <p className="muted">No finished recording yet.</p>
      ) : null}
      {ready.length > 0 ? (
        <table className="table">
          <thead>
            <tr>
              <th scope="col">Recording</th>
              <th scope="col">Length</th>
              <th scope="col">Files</th>
              <th scope="col">Listen</th>
              {can("recordings.download") ? <th scope="col">Download</th> : null}
            </tr>
          </thead>
          <tbody>
            {ready.map((r, i) => (
              <tr key={r.id}>
                <td>
                  <span className="cell-icon">
                    <Icon name="waveform" size={15} />
                    Recording {ready.length - i}
                  </span>
                </td>
                <td>{rec.lengthLabel(r.saved_seconds)}</td>
                <td>{r.assets.length} audio + consent record + details</td>
                <td>
                  {rec.deliveryAsset(r.assets) ? (
                    <Player assetId={(rec.deliveryAsset(r.assets) as rec.Asset).id} />
                  ) : (
                    "-"
                  )}
                </td>
                {can("recordings.download") ? (
                  <td>
                    <Button
                      variant="secondary"
                      busy={busy === r.id}
                      onClick={() => {
                        setBusy(r.id);
                        setError(null);
                        setMessage(null);
                        rec
                          .downloadWithConsent(r, task.task_code)
                          .then(() =>
                            setMessage("Recording, consent record and details downloaded."),
                          )
                          .catch((err: unknown) => setError(toApiError(err)))
                          .finally(() => setBusy(null));
                      }}
                    >
                      <Icon name="upload" size={15} />
                      Download with consent form
                    </Button>
                  </td>
                ) : null}
              </tr>
            ))}
          </tbody>
        </table>
      ) : null}
      <ErrorNotice error={error} />
      <SuccessNotice message={message} />
    </section>
  );
}

export function TaskDetailPage() {
  const { taskId = "" } = useParams();
  const { state, reload, replace } = useResource(() => work.getTask(taskId), [taskId]);
  if (state.status === "loading") return <LoadingState label="Loading task" />;
  if (state.status === "failed") return <ErrorState error={state.error} onRetry={reload} />;
  const task = state.data;
  const consentOpen =
    task.is_moderator && (task.status === "ASSIGNED" || task.status === "IN_PROGRESS");
  return (
    <section aria-labelledby="task-title" className="stack">
      <div className="page-header">
        <h1 id="task-title">
          <IconTile name={task.recording_mode === "TELEPHONY" ? "phone" : "mic"} tone="teal" />
          Task {task.task_code}
        </h1>
        <StatusBadge status={task.status} label={label(task.status)} />
      </div>
      <div className="card">
        <Stepper
          steps={FLOW.map((s) => label(s))}
          current={
            task.status === "APPROVED"
              ? FLOW.length
              : Math.max(
                  0,
                  FLOW.indexOf(
                    (FLOW.includes(task.status) ? task.status : task.held_from) ?? "DRAFT",
                  ),
                )
          }
          halted={!FLOW.includes(task.status)}
          label={`Workflow progress: ${label(task.status)}`}
        />
      </div>
      <dl className="checks checks--facts card">
        <div className="checks__row">
          <dt>Mode</dt>
          <dd>{task.recording_mode === "TELEPHONY" ? "Telephony" : "Face-to-face"}</dd>
        </div>
        <div className="checks__row">
          <dt>Priority</dt>
          <dd>{task.priority.toLowerCase()}</dd>
        </div>
        <div className="checks__row">
          <dt>Moderator</dt>
          <dd>{task.moderator_name ?? "Not assigned"}</dd>
        </div>
        {[task.participant_a, task.participant_b].map((p, i) => (
          <div key={p.id} className="checks__row">
            <dt>Participant {i === 0 ? "A" : "B"}</dt>
            <dd className="party">
              <span className="code-tag">{p.participant_code}</span>
              <ConsentChip status={p.consent_status} />
            </dd>
          </div>
        ))}
        {task.reason_code ? (
          <div className="checks__row">
            <dt>Reason</dt>
            <dd>{words(task.reason_code)}</dd>
          </div>
        ) : null}
      </dl>
      {task.can_assign && ["DRAFT", "ASSIGNED", "ON_HOLD", "RETURNED"].includes(task.status) ? (
        <Assignment task={task} onChange={replace} />
      ) : null}
      {task.is_moderator && task.recording_mode === "FACE_TO_FACE" ? (
        <RecordCard task={task} onChange={replace} />
      ) : null}
      {task.recording_mode === "TELEPHONY" ? (
        <PhoneCalls
          task={task}
          onChange={replace}
          // Quietly: the page stays as it is until the new task arrives (no loading flash).
          onTaskStale={() => void work.getTask(task.id).then(replace)}
        />
      ) : null}
      <AdminReviewCard task={task} onChange={replace} />
      {consentOpen ? <ConsentCapture task={task} onChange={replace} /> : null}
      {HAS_RECORDINGS.includes(task.status) ? (
        <AudioQcPanel task={task} onDecided={reload} />
      ) : null}
      {HAS_RECORDINGS.includes(task.status) ? <Recordings task={task} /> : null}
      <Actions task={task} onChange={replace} />
      <Timeline
        taskId={task.id}
        version={`${task.status}-${task.moderator_id ?? ""}-${task.participant_a.consent_at ?? ""}-${task.participant_b.consent_at ?? ""}`}
      />
    </section>
  );
}
