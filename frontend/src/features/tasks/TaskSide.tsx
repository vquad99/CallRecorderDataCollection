// The task page's side column (D-152): a compact summary (status, recording type, priority,
// moderator, QC), the two participants as one matrix (code, name, consent, signed form, device
// details, speaker details) with uploading and opening the signed forms in its cells, and the
// history, the newest three entries first with "Show all". On a wide screen it stays in view
// beside the work; on a phone it comes after the work.
import { useState, type ReactNode } from "react";

import { listMembers } from "../../api/projects";
import * as work from "../../api/work";
import { useAuth } from "../../auth/AuthContext";
import { DataTable } from "../../components/DataTable";
import { Button } from "../../components/form/Button";
import { Select } from "../../components/form/Select";
import { TextField } from "../../components/form/TextField";
import { Icon, type IconName } from "../../components/Icon";
import { Modal } from "../../components/Modal";
import { ErrorNotice, SuccessNotice } from "../../components/Notice";
import { ErrorState, LoadingState } from "../../components/StateViews";
import { StatusBadge } from "../../components/StatusBadge";
import { useAction } from "../../hooks/useAction";
import { useResource } from "../../hooks/useResource";
import { day, when } from "../../lib/format";
import {
  consentAnswer,
  labelFor,
  MODE_LABELS,
  PRIORITY_LABELS,
  REASON_LABELS,
  TASK_STATUS_LABELS,
} from "../../lib/labels";
import { openDocument, sendDocument, UploadButton, uploadedText } from "../participants/Documents";
import { ParticipantDetails } from "../participants/ParticipantDetails";
import type { AudioQcResource } from "./AudioQcPanel";
import { deviceState, type DeviceResource } from "./DeviceDetails";
import { Mark } from "./Matrix";
import type { OnTaskChange } from "./TaskDetailPage";

const status = (s: string) => labelFor(TASK_STATUS_LABELS, s);

/** Uploading a participant's signed consent form from the task page, and opening one (D-144):
 * the task is loaded again after an upload, so its consent and buttons follow at once. */
export function useSignedForms(task: work.TaskDetail, onChange: OnTaskChange) {
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

/** A side panel with its small title. */
function SideCard({
  id,
  icon,
  title,
  extra,
  children,
}: {
  id: string;
  icon: IconName;
  title: string;
  extra?: ReactNode;
  children: ReactNode;
}) {
  return (
    <section className="card side-card" aria-labelledby={id}>
      <div className="side-card__head">
        <h2 id={id}>
          <Icon name={icon} size={18} />
          {title}
        </h2>
        {extra}
      </div>
      {children}
    </section>
  );
}

function Fact({ label, children }: { label: string; children: ReactNode }) {
  return (
    <div className="facts__row">
      <dt>{label}</dt>
      <dd>{children}</dd>
    </div>
  );
}

/** Change the moderator (with a reason): closed under the summary until it is needed. */
function Reassign({ task, onChange }: { task: work.TaskDetail; onChange: OnTaskChange }) {
  return (
    <details className="side-more">
      <summary>Reassign moderator</summary>
      <Assignment task={task} onChange={onChange} />
    </details>
  );
}

/** Choose the task's moderator; with a reason when one is already assigned. `card`: as the page's
 * work card (a task with nobody assigned yet). */
export function Assignment({
  task,
  onChange,
  card = false,
}: {
  task: work.TaskDetail;
  onChange: OnTaskChange;
  card?: boolean;
}) {
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
      className={card ? "card work-card assign-card" : "assign-form"}
      onSubmit={(e) => {
        e.preventDefault();
        void run(async () => {
          onChange(await work.assignModerator(task.id, userId, reason), "Moderator assigned.");
          setUserId("");
          setReason("");
        });
      }}
    >
      {card ? <h2>{task.moderator_id ? "Reassign moderator" : "Assign moderator"}</h2> : null}
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
        icon="userPlus"
        busy={busy !== null}
        disabled={!userId || (Boolean(task.moderator_id) && !reason.trim())}
      >
        {task.moderator_id ? "Reassign" : "Assign"}
      </Button>
    </form>
  );
}

/** Status, recording type, priority, moderator, QC Executive, dates: one line each. */
export function TaskSummary({
  task,
  audio,
  onChange,
}: {
  task: work.TaskDetail;
  audio: AudioQcResource;
  onChange: OnTaskChange;
}) {
  const qcView = audio.state.status === "loaded" ? audio.state.data : null;
  return (
    <SideCard id="task-summary-title" icon="tasks" title="Summary">
      <dl className="facts">
        <Fact label="Status">
          <StatusBadge status={task.status} label={status(task.status)} />
          {task.status === "ON_HOLD" && task.held_from ? (
            <span className="muted"> from {status(task.held_from)}</span>
          ) : null}
        </Fact>
        <Fact label="Recording type">
          <span className="cell-icon">
            <Icon name={task.recording_mode === "TELEPHONY" ? "phone" : "mic"} size={15} />
            <span>{labelFor(MODE_LABELS, task.recording_mode)}</span>
          </span>
        </Fact>
        <Fact label="Priority">
          <span className={`priority priority--${task.priority.toLowerCase()}`}>
            {labelFor(PRIORITY_LABELS, task.priority)}
          </span>
        </Fact>
        <Fact label="Moderator">
          {task.moderator_name ?? <span className="muted">Not assigned</span>}
        </Fact>
        {qcView ? (
          <Fact label="QC Executive">
            {qcView.qc_name ?? <span className="muted">Not assigned</span>}
          </Fact>
        ) : null}
        {task.due_at ? <Fact label="Due">{day(task.due_at)}</Fact> : null}
        <Fact label="Created">{day(task.created_at)}</Fact>
        {task.reason_code ? (
          <Fact label="Reason">{labelFor(REASON_LABELS, task.reason_code)}</Fact>
        ) : null}
      </dl>
      {task.can_reassign && task.moderator_id ? <Reassign task={task} onChange={onChange} /> : null}
    </SideCard>
  );
}

type Sided = readonly ["A" | "B", work.Party];

/** The signed consent form's cell: the file (opens it) or "Missing", and Upload or Replace. */
function FormCell({
  party,
  busy,
  onView,
  onFile,
}: {
  party: work.Party;
  busy: string | null;
  onView: (doc: work.ParticipantDocument) => void;
  onFile: (file: File) => void;
}) {
  const doc = party.consent_form ?? null;
  return (
    <span className="mx-file">
      {doc ? (
        <button
          type="button"
          className="mx-file__open"
          title={`${doc.file_name} · ${uploadedText(doc)}`}
          aria-label={`View the signed consent form of ${party.participant_code}`}
          disabled={busy !== null}
          onClick={() => onView(doc)}
        >
          {busy === `view-${doc.id}` ? (
            <span className="spinner" aria-hidden="true" />
          ) : (
            <Icon name="ok" size={16} />
          )}
          <span className="mx-file__name">{doc.file_name}</span>
        </button>
      ) : (
        <Mark ok={false}>Missing</Mark>
      )}
      {party.can_upload_consent_form ? (
        <UploadButton
          compact
          label={`${doc ? "Replace" : "Upload"} consent form of ${party.participant_code}`}
          busy={busy === `upload-${party.id}`}
          disabled={busy !== null}
          onFile={onFile}
        />
      ) : null}
    </span>
  );
}

/** Both participants side by side (D-152): a row per fact, a column per person. */
export function ParticipantsMatrix({
  task,
  devices,
  onChange,
}: {
  task: work.TaskDetail;
  devices: DeviceResource;
  onChange: OnTaskChange;
}) {
  const { can } = useAuth();
  const { busy, error, message, upload, view } = useSignedForms(task, onChange);
  const [opened, setOpened] = useState<work.Party | null>(null);
  const people: Sided[] = [
    ["A", task.participant_a],
    ["B", task.participant_b],
  ];
  const forms =
    task.consent_mode === "UPLOAD" &&
    people.some(([, p]) => p.consent_form || p.can_upload_consent_form);
  const asksDevices = Boolean(task.device_fields?.length);
  const manages = can("participants.manage");
  return (
    <SideCard id="task-people-title" icon="people" title="Participants">
      <DataTable className="matrix people-matrix" label="Both participants">
        <thead>
          <tr>
            <th scope="col">
              <span className="sr-only">Detail</span>
            </th>
            {people.map(([side]) => (
              <th key={side} scope="col" className={`mx-${side.toLowerCase()}`}>
                Participant {side}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          <tr>
            <th scope="row">Code</th>
            {people.map(([side, p]) => (
              <td key={side}>
                <span className="code-tag">{p.participant_code}</span>
              </td>
            ))}
          </tr>
          <tr>
            <th scope="row">Name</th>
            {people.map(([side, p]) => (
              <td key={side} className="mx-name">
                {p.display_label ?? <span className="muted">Hidden</span>}
              </td>
            ))}
          </tr>
          <tr>
            <th scope="row">Consent</th>
            {people.map(([side, p]) => {
              const { label, tone } = consentAnswer(p.consent_status, task.consent_mode);
              return (
                <td key={side} title={p.consent_at ? `Since ${when(p.consent_at)}` : undefined}>
                  <StatusBadge tone={tone} label={label} />
                </td>
              );
            })}
          </tr>
          {forms ? (
            <tr>
              <th scope="row">Consent form</th>
              {people.map(([side, p]) => (
                <td key={side}>
                  <FormCell
                    party={p}
                    busy={busy}
                    onView={(doc) => view(p, doc)}
                    onFile={upload(p)}
                  />
                </td>
              ))}
            </tr>
          ) : null}
          {asksDevices ? (
            <tr>
              <th scope="row">Device details</th>
              {people.map(([side]) => {
                const s = deviceState(task, devices, side);
                return (
                  <td key={side}>
                    {s.ok === null ? (
                      <span className="muted">{s.text}</span>
                    ) : (
                      <Mark ok={s.ok} title={s.title}>
                        {s.text}
                      </Mark>
                    )}
                  </td>
                );
              })}
            </tr>
          ) : null}
          {manages ? (
            <tr>
              <th scope="row">Speaker details</th>
              {people.map(([side, p]) => (
                <td key={side}>
                  <button
                    type="button"
                    className="linkish"
                    aria-label={`View the details of ${p.participant_code}`}
                    onClick={() => setOpened(p)}
                  >
                    <Icon name="eye" size={15} />
                    View
                  </button>
                </td>
              ))}
            </tr>
          ) : null}
        </tbody>
      </DataTable>
      <ErrorNotice error={error} />
      <SuccessNotice message={message} />
      {opened ? (
        <Modal title="Participant details" onClose={() => setOpened(null)} wide>
          <ParticipantDetails
            projectId={task.project_id}
            participantId={opened.id}
            consentMode={task.consent_mode}
          />
        </Modal>
      ) : null}
    </SideCard>
  );
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

/** The newest entries this many at first; "Show all" for the rest. */
const FIRST = 3;

export function Timeline({ taskId, version }: { taskId: string; version: string }) {
  const { state, reload } = useResource(() => work.getTimeline(taskId), [taskId, version]);
  const [text, setText] = useState("");
  const [all, setAll] = useState(false);
  const { busy, error, message, run } = useAction(reload);
  const entries = state.status === "loaded" ? [...state.data].reverse() : [];
  const shown = all ? entries : entries.slice(0, FIRST);
  return (
    <SideCard
      id="timeline-title"
      icon="history"
      title="History"
      extra={
        entries.length > FIRST ? (
          <button
            type="button"
            className="linkish"
            aria-expanded={all}
            onClick={() => setAll(!all)}
          >
            {all ? "Show the newest" : `Show all (${entries.length})`}
          </button>
        ) : null
      }
    >
      {state.status === "loading" ? <LoadingState /> : null}
      {state.status === "failed" ? <ErrorState error={state.error} onRetry={reload} /> : null}
      {state.status === "loaded" ? (
        <ol className="list timeline timeline--compact">
          {shown.map((e, i) => {
            const { title, detail } = entryText(e);
            return (
              <li key={`${e.at}-${i}`}>
                <div className="timeline__title">{title}</div>
                {detail ? <div className="timeline__detail">{detail}</div> : null}
                <span className="muted">
                  {when(e.at)} · {e.actor ?? "Platform"} · {ENTRY_KIND[e.kind]}
                </span>
              </li>
            );
          })}
        </ol>
      ) : null}
      <form
        className="comment-form"
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
    </SideCard>
  );
}
