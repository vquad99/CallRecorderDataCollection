// One task: participants and consent, moderator, status actions, comments and timeline (TASK-*).
import { useState } from "react";
import { useParams } from "react-router";

import type { ApiError } from "../../api/client";
import { listMembers } from "../../api/projects";
import * as work from "../../api/work";
import { Button } from "../../components/form/Button";
import { Select } from "../../components/form/Select";
import { TextField } from "../../components/form/TextField";
import { ErrorNotice, SuccessNotice } from "../../components/Notice";
import { ErrorState, LoadingState } from "../../components/StateViews";
import { toApiError, useResource } from "../../hooks/useResource";

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
    <section className="card" aria-labelledby="consent-title">
      <h2 id="consent-title">Record consent</h2>
      <Select
        label="How consent was given"
        value={method}
        onChange={(e) => setMethod(e.target.value)}
        options={["VERBAL_RECORDED", "VERBAL_NOTED", "WRITTEN", "DIGITAL"].map((m) => ({
          value: m,
          label: words(m),
        }))}
      />
      {[task.participant_a, task.participant_b].map((p, i) => (
        <div key={p.id} className="actions">
          <span>
            Participant {i === 0 ? "A" : "B"} ({p.participant_code}):
          </span>
          <Button busy={busy} onClick={() => record(p.id, "GIVEN")}>
            Consent given
          </Button>
          <Button variant="secondary" busy={busy} onClick={() => record(p.id, "REFUSED")}>
            Refused
          </Button>
        </div>
      ))}
      <ErrorNotice error={error} />
    </section>
  );
}

function Timeline({ taskId, version }: { taskId: string; version: string }) {
  const { state, reload } = useResource(() => work.getTimeline(taskId), [taskId, version]);
  const [text, setText] = useState("");
  const [error, setError] = useState<ApiError | null>(null);
  const [ok, setOk] = useState<string | null>(null);
  return (
    <section className="card" aria-labelledby="timeline-title">
      <h2 id="timeline-title">History</h2>
      {state.status === "loading" ? <LoadingState /> : null}
      {state.status === "failed" ? (
        <ErrorState message={state.error.message} onRetry={reload} />
      ) : null}
      {state.status === "loaded" ? (
        <ol className="list">
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
          work
            .addComment(taskId, text)
            .then(() => {
              setText("");
              setOk("Comment added.");
              reload();
            })
            .catch((err: unknown) => setError(toApiError(err)));
        }}
      >
        <TextField label="Add a comment" value={text} onChange={(e) => setText(e.target.value)} />
        <Button type="submit" variant="secondary" disabled={!text.trim()}>
          Add comment
        </Button>
      </form>
      <ErrorNotice error={error} />
      <SuccessNotice message={ok} />
    </section>
  );
}

export function TaskDetailPage() {
  const { taskId = "" } = useParams();
  const { state, reload, replace } = useResource(() => work.getTask(taskId), [taskId]);
  if (state.status === "loading") return <LoadingState label="Loading task" />;
  if (state.status === "failed")
    return <ErrorState message={state.error.message} onRetry={reload} />;
  const task = state.data;
  const consentOpen =
    task.is_moderator && (task.status === "ASSIGNED" || task.status === "IN_PROGRESS");
  return (
    <section aria-labelledby="task-title" className="stack">
      <div className="page-header">
        <h1 id="task-title">Task {task.task_code}</h1>
        <span className="badge">{label(task.status)}</span>
      </div>
      <dl className="checks card">
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
            <dd>
              {p.participant_code} · consent:{" "}
              {p.consent_status ? words(p.consent_status) : "not recorded"}
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
      {consentOpen ? <ConsentCapture task={task} onChange={replace} /> : null}
      <Actions task={task} onChange={replace} />
      <Timeline
        taskId={task.id}
        version={`${task.status}-${task.moderator_id ?? ""}-${task.participant_a.consent_at ?? ""}-${task.participant_b.consent_at ?? ""}`}
      />
    </section>
  );
}
