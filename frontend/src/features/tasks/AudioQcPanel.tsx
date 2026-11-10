// Audio quality card on the task page (D-079): what the automatic check measured, who checks the
// recording, a player, and the QC Executive's decision. The server decides who may do what; this
// only shows the controls it allows.
import { useState } from "react";

import * as qc from "../../api/audioQc";
import type { ApiError } from "../../api/client";
import { listMembers } from "../../api/projects";
import { assetUrl } from "../../api/recordings";
import type * as work from "../../api/work";
import { Icon } from "../../components/Icon";
import { ErrorNotice } from "../../components/Notice";
import { ErrorState, LoadingState } from "../../components/StateViews";
import { StatusBadge } from "../../components/StatusBadge";
import { Button } from "../../components/form/Button";
import { Select } from "../../components/form/Select";
import { TextField } from "../../components/form/TextField";
import { toApiError, useResource } from "../../hooks/useResource";

const TONE: Record<string, string> = {
  PASS: "APPROVED",
  NEEDS_REVIEW: "AUDIO_QC",
  FAIL: "REJECTED",
  RETURN: "RETURNED",
};
const CHECK_TONE: Record<qc.CheckState, string> = {
  PASS: "APPROVED",
  FAIL: "REJECTED",
  REVIEW: "AUDIO_QC",
  INFO: "DRAFT",
  NOT_APPLICABLE: "DRAFT",
};
const words = (s: string) => s.toLowerCase().replace(/_/g, " ");
const when = (iso: string) => new Date(iso).toLocaleString();

function Outcome({ outcome }: { outcome: qc.QcOutcome }) {
  return <StatusBadge status={TONE[outcome] ?? "DRAFT"} label={qc.OUTCOME_LABELS[outcome]} />;
}

function Checks({ result }: { result: qc.QcResult }) {
  return (
    <table className="table">
      <caption className="sr-only">Automatic checks</caption>
      <thead>
        <tr>
          <th scope="col">Check</th>
          <th scope="col">Result</th>
          <th scope="col">Measured</th>
          <th scope="col">Allowed</th>
        </tr>
      </thead>
      <tbody>
        {result.checks.map((c) => (
          <tr key={c.code}>
            <td>
              {qc.CHECK_LABELS[c.code] ?? words(c.code)}
              {c.message ? <div className="muted">{c.message}</div> : null}
            </td>
            <td>
              <StatusBadge status={CHECK_TONE[c.state]} label={qc.STATE_LABELS[c.state]} />
            </td>
            <td>{c.measured}</td>
            <td>{c.expected}</td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}

function Player({ assetId }: { assetId: string }) {
  const [src, setSrc] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<ApiError | null>(null);
  if (src) {
    return (
      // Speech recordings carry no captions; the details are in the checks table above.
      // eslint-disable-next-line jsx-a11y/media-has-caption
      <audio controls src={src} className="player" aria-label="Recording being checked" />
    );
  }
  return (
    <div>
      <Button
        variant="secondary"
        busy={busy}
        onClick={() => {
          setBusy(true);
          setError(null);
          assetUrl(assetId, "play")
            .then((r) => setSrc(r.url))
            .catch((err: unknown) => setError(toApiError(err)))
            .finally(() => setBusy(false));
        }}
      >
        <Icon name="play" size={15} />
        Listen
      </Button>
      <ErrorNotice error={error} />
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
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<ApiError | null>(null);
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
        setBusy(true);
        setError(null);
        qc.assignQc(task.id, userId, reason)
          .then((v) => {
            onChange(v);
            setUserId("");
            setReason("");
          })
          .catch((err: unknown) => setError(toApiError(err)))
          .finally(() => setBusy(false));
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
        busy={busy}
        disabled={!userId || (reassigning && !reason.trim())}
      >
        {reassigning ? "Reassign QC" : "Assign QC"}
      </Button>
    </form>
  );
}

function DecisionForm({
  taskId,
  view,
  automatic,
  onDecided,
}: {
  taskId: string;
  view: qc.AudioQcView;
  automatic: qc.QcResult | undefined;
  onDecided: () => void;
}) {
  const [outcome, setOutcome] = useState<qc.Decision | "">("");
  const [reason, setReason] = useState("");
  const [comment, setComment] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<ApiError | null>(null);
  const reasons = outcome === "FAIL" || outcome === "RETURN" ? view.reasons[outcome] : null;
  const overriding = outcome === "PASS" && automatic?.outcome === "FAIL";
  const needsComment = overriding || reason === "OTHER";
  return (
    <form
      aria-labelledby="qc-decision-title"
      onSubmit={(e) => {
        e.preventDefault();
        if (!outcome) return;
        setBusy(true);
        setError(null);
        qc.decideQc(taskId, outcome, reason, comment)
          .then(onDecided)
          .catch((err: unknown) => setError(toApiError(err)))
          .finally(() => setBusy(false));
      }}
    >
      <h3 id="qc-decision-title">Your decision</h3>
      <Select
        label="Decision"
        value={outcome}
        onChange={(e) => {
          setOutcome(e.target.value as qc.Decision);
          setReason("");
        }}
        options={[
          { value: "", label: "Choose" },
          { value: "PASS", label: "Pass: approve the recording" },
          { value: "RETURN", label: "Return: record again" },
          { value: "FAIL", label: "Fail: reject the recording" },
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
      <TextField
        label="Comment"
        hint={
          overriding
            ? "The automatic check failed: say why this passes."
            : "Required when the reason is 'other'."
        }
        required={needsComment}
        value={comment}
        onChange={(e) => setComment(e.target.value)}
      />
      <ErrorNotice error={error} />
      <Button
        type="submit"
        busy={busy}
        disabled={!outcome || (Boolean(reasons) && !reason) || (needsComment && !comment.trim())}
      >
        <Icon name="verified" size={16} />
        Save decision
      </Button>
    </form>
  );
}

export function AudioQcPanel({
  task,
  onDecided,
}: {
  task: work.TaskDetail;
  onDecided: () => void;
}) {
  const { state, reload, replace } = useResource(() => qc.getAudioQc(task.id), [task.id]);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<ApiError | null>(null);
  if (state.status === "loading") return <LoadingState label="Loading audio check" />;
  if (state.status === "failed") return <ErrorState error={state.error} onRetry={reload} />;
  const view = state.data;
  const automatic = view.results.find((r) => r.automated);
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
        {automatic ? (
          <div className="checks__row">
            <dt>Automatic check</dt>
            <dd>
              {automatic.comment} · {when(automatic.created_at)}
            </dd>
          </div>
        ) : (
          <div className="checks__row">
            <dt>Automatic check</dt>
            <dd>Not run yet</dd>
          </div>
        )}
      </dl>
      {automatic ? <Checks result={automatic} /> : null}
      {automatic?.asset_id && (view.can_decide || view.can_recheck) ? (
        <Player assetId={automatic.asset_id} />
      ) : null}
      {view.can_recheck ? (
        <div className="actions">
          <Button
            variant="secondary"
            busy={busy}
            onClick={() => {
              setBusy(true);
              setError(null);
              qc.recheckQc(task.id)
                .then((v) => {
                  replace(v);
                  if (v.task_status !== task.status) onDecided();
                })
                .catch((err: unknown) => setError(toApiError(err)))
                .finally(() => setBusy(false));
            }}
          >
            <Icon name="waveform" size={15} />
            Check the stored file again
          </Button>
        </div>
      ) : null}
      <ErrorNotice error={error} />
      {view.can_assign ? <AssignQc task={task} view={view} onChange={replace} /> : null}
      {view.can_decide ? (
        <DecisionForm taskId={task.id} view={view} automatic={automatic} onDecided={onDecided} />
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
                  {d.reason_code ? ` ${words(d.reason_code)}` : ""}
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
