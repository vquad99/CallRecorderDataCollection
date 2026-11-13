// Phone calls on a telephony task (D-101): the moderator starts the call, TxContact rings participant
// A and connects them to the moderator's TxContact seat, the moderator adds B from the TxContact
// screen, and closes the call here when A and B have finished. The platform then fetches the
// recording. Every state shown comes from the server; nothing is shown as connected on its own
// (TEL-037).
import { useEffect, useRef, useState, type ReactNode } from "react";

import type { ApiError } from "../../api/client";
import * as rec from "../../api/recordings";
import * as tel from "../../api/telephony";
import * as work from "../../api/work";
import { Button } from "../../components/form/Button";
import { Select } from "../../components/form/Select";
import { TextField } from "../../components/form/TextField";
import { Icon } from "../../components/Icon";
import { ErrorNotice } from "../../components/Notice";
import { ErrorState, LoadingState } from "../../components/StateViews";
import { toApiError, useResource } from "../../hooks/useResource";
import { Player } from "./AudioQcPanel";

const REFRESH_MS = 5000;

/** Calls of a task, refreshed every few seconds while one is still moving on its own. */
function useCalls(taskId: string) {
  const resource = useResource(() => tel.listCalls(taskId), [taskId]);
  const { state, reload } = resource;
  const moving = state.status === "loaded" && state.data.some((c) => tel.MOVING.includes(c.state));
  useEffect(() => {
    if (!moving) return;
    const timer = window.setInterval(reload, REFRESH_MS);
    return () => window.clearInterval(timer);
  }, [moving, reload]);
  return resource;
}

type Calls = ReturnType<typeof useCalls>;

function when(at: string | null): string {
  return at ? new Date(at).toLocaleString() : "-";
}

/** Pick the right TxContact call, look again, or give up: for the moderator and project admins. */
function CallFixer({ call, onChange }: { call: tel.Call; onChange: (c: tel.Call) => void }) {
  const [busy, setBusy] = useState<string | null>(null);
  const [error, setError] = useState<ApiError | null>(null);
  const act = (key: string, action: () => Promise<tel.Call>) => {
    setBusy(key);
    setError(null);
    action()
      .then(onChange)
      .catch((err: unknown) => setError(toApiError(err)))
      .finally(() => setBusy(null));
  };
  return (
    <div className="stack">
      {call.failure_detail ? <p>{call.failure_detail}</p> : null}
      {call.state === "NEEDS_MATCH" && call.candidates.length > 0 ? (
        <table className="table">
          <caption className="muted">TxContact calls at the time of this call</caption>
          <thead>
            <tr>
              <th scope="col">Started</th>
              <th scope="col">Length</th>
              <th scope="col">Numbers end in</th>
              <th scope="col">File</th>
              <th scope="col">
                <span className="visually-hidden">Choose</span>
              </th>
            </tr>
          </thead>
          <tbody>
            {call.candidates.map((c) => (
              <tr key={c.session_id}>
                <td>{when(c.start)}</td>
                <td>{c.duration ? `${c.duration} s` : "-"}</td>
                <td>
                  {c.from_hint || "?"} / {c.to_hint || "?"}
                </td>
                <td>{c.file}</td>
                <td>
                  <Button
                    variant="secondary"
                    busy={busy === c.session_id}
                    onClick={() => act(c.session_id, () => tel.chooseMatch(call.id, c.session_id))}
                  >
                    This is the call
                  </Button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      ) : null}
      <div className="actions">
        <Button
          variant="secondary"
          busy={busy === "retry"}
          onClick={() => act("retry", () => tel.retryCall(call.id))}
        >
          Look for the recording again
        </Button>
      </div>
      <ErrorNotice error={error} />
    </div>
  );
}

/** "The call did not work": a reason from the fixed list, and a note for Other. */
function CancelForm({ call, onChange }: { call: tel.Call; onChange: (c: tel.Call) => void }) {
  const [open, setOpen] = useState(false);
  const [reason, setReason] = useState<tel.CancelReason>("NO_ANSWER");
  const [note, setNote] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<ApiError | null>(null);
  if (!open) {
    return (
      <Button variant="secondary" onClick={() => setOpen(true)}>
        Cancel this call
      </Button>
    );
  }
  return (
    <form
      className="stack"
      onSubmit={(e) => {
        e.preventDefault();
        setBusy(true);
        setError(null);
        tel
          .cancelCall(call.id, reason, note)
          .then(onChange)
          .catch((err: unknown) => setError(toApiError(err)))
          .finally(() => setBusy(false));
      }}
    >
      <Select
        label="Why"
        value={reason}
        onChange={(e) => setReason(e.target.value as tel.CancelReason)}
        options={Object.entries(tel.CANCEL_REASONS).map(([value, label]) => ({ value, label }))}
      />
      <TextField label="Note" value={note} onChange={(e) => setNote(e.target.value)} />
      <div className="actions">
        <Button type="submit" variant="secondary" busy={busy}>
          Cancel the call
        </Button>
        <Button variant="secondary" onClick={() => setOpen(false)}>
          Keep it
        </Button>
      </div>
      <ErrorNotice error={error} />
    </form>
  );
}

/** The newest finished recording's delivery file, to listen to before sending it to QC. */
function ListenLatest({ taskId }: { taskId: string }) {
  const { state } = useResource(() => rec.listRecordings(taskId), [taskId]);
  if (state.status !== "loaded") return null;
  const latest = state.data.find((r) => r.state === "READY");
  const asset = latest ? rec.deliveryAsset(latest.assets) : undefined;
  return asset ? <Player assetId={asset.id} /> : <p className="muted">No recording yet.</p>;
}

/** The moderator's card on a telephony task: start the session, call, close, then send to QC. */
function CallCard({
  task,
  calls,
  onChange,
}: {
  task: work.TaskDetail;
  calls: Calls;
  onChange: (t: work.TaskDetail) => void;
}) {
  const status = useResource(() => tel.telephonyStatus(), []);
  const [busy, setBusy] = useState<string | null>(null);
  const [note, setNote] = useState("");
  const [error, setError] = useState<ApiError | null>(null);

  const canStartSession =
    task.status !== "RECORDED" && task.allowed_transitions.includes("IN_PROGRESS");
  const calling = task.status === "IN_PROGRESS";
  const review = task.status === "RECORDED" && task.allowed_transitions.includes("AUDIO_QC");
  if (!canStartSession && !calling && !review) return null;

  const move = (to: work.TaskStatus) => {
    setBusy(to);
    setError(null);
    work
      .transitionTask(task.id, to, "", "")
      .then(onChange)
      .catch((err: unknown) => setError(toApiError(err)))
      .finally(() => setBusy(null));
  };
  const callAction = (key: string, action: () => Promise<tel.Call>) => {
    setBusy(key);
    setError(null);
    action()
      .then(() => calls.reload())
      .catch((err: unknown) => setError(toApiError(err)))
      .finally(() => setBusy(null));
  };

  const latest = calls.state.status === "loaded" ? calls.state.data[0] : undefined;
  const configured = status.state.status === "loaded" && status.state.data.configured;

  let title = "Start the session";
  let body: ReactNode = (
    <p>Start the session, then call participant A from here. Their phone will ring.</p>
  );
  let go: ReactNode = (
    <Button busy={busy === "IN_PROGRESS"} onClick={() => move("IN_PROGRESS")}>
      Start session
    </Button>
  );

  if (review) {
    title = "Check the call recording";
    body = (
      <div className="record-card__listen">
        <ListenLatest taskId={task.id} />
      </div>
    );
    go = (
      <>
        <Button busy={busy === "AUDIO_QC"} onClick={() => move("AUDIO_QC")}>
          Send to QC
        </Button>
        <Button
          variant="secondary"
          busy={busy === "IN_PROGRESS"}
          onClick={() => move("IN_PROGRESS")}
        >
          Call again
        </Button>
      </>
    );
  } else if (calling) {
    if (status.state.status === "loading" || calls.state.status === "loading") {
      return <LoadingState label="Loading the phone call" />;
    }
    if (calls.state.status === "failed") {
      return <ErrorState error={calls.state.error} onRetry={calls.reload} />;
    }
    if (!configured) {
      title = "Phone calls are not set up";
      body = (
        <p>
          Phone calls are not configured on this server yet. Ask the Super Admin to add the
          TxContact details.
        </p>
      );
      go = null;
    } else if (!latest || ["DIAL_FAILED", "CANCELLED", "RECORDED"].includes(latest.state)) {
      title = "Ready to call";
      body = (
        <>
          <ol className="record-card__steps">
            <li className="is-now">
              Click Start call. TxContact rings participant A ({task.participant_a.participant_code}
              ) and connects them to your TxContact seat.
            </li>
            <li>Add participant B from your TxContact screen.</li>
            <li>Record each person&apos;s consent below.</li>
            <li>When A and B have finished, close the call here.</li>
          </ol>
          {latest?.state === "DIAL_FAILED" ? (
            <p role="alert">
              The last call could not be placed:{" "}
              {latest.failure_detail ?? "no answer from TxContact"}
            </p>
          ) : null}
        </>
      );
      go = (
        <Button
          busy={busy === "start"}
          onClick={() => callAction("start", () => tel.startCall(task.id))}
        >
          <Icon name="phone" size={16} weight="fill" />
          Start call
        </Button>
      );
    } else if (latest.state === "DIALLING") {
      title = "On the call";
      body = (
        <>
          <ol className="record-card__steps">
            <li className="is-done">
              TxContact is ringing participant A (number ending {latest.phone_hint}) on seat{" "}
              {latest.agent_id}.
            </li>
            <li className="is-now">Add participant B from your TxContact screen.</li>
            <li className="is-now">Record each person&apos;s consent below.</li>
            <li>When A and B have finished, close the call.</li>
          </ol>
          <TextField
            label="Note for the record (optional)"
            value={note}
            onChange={(e) => setNote(e.target.value)}
          />
        </>
      );
      go = (
        <>
          <Button
            busy={busy === "close"}
            onClick={() => callAction("close", () => tel.closeCall(latest.id, note))}
          >
            Close call
          </Button>
          <CancelForm call={latest} onChange={() => calls.reload()} />
        </>
      );
    } else if (latest.state === "WAITING_FOR_RECORDING") {
      title = "Fetching the recording";
      body = (
        <p aria-live="polite">
          The call is closed. The recording is being fetched from TxContact; this page updates on
          its own. Tries so far: {latest.fetch_attempts}.
        </p>
      );
      go = null;
    } else {
      title = tel.CALL_STATE_LABELS[latest.state];
      body = <CallFixer call={latest} onChange={() => calls.reload()} />;
      go = <CancelForm call={latest} onChange={() => calls.reload()} />;
    }
  }

  return (
    <section className="card record-card" aria-labelledby="call-card-title">
      <div className="record-card__text">
        <h2 id="call-card-title">{title}</h2>
        {body}
      </div>
      {go ? <div className="record-card__go">{go}</div> : null}
      <ErrorNotice error={error} />
    </section>
  );
}

/** Every call of a telephony task with its full history, for everyone who sees the task.
 * Project admins can also pick the recording or look again when a call needs a person. */
function CallHistory({ task, calls }: { task: work.TaskDetail; calls: Calls }) {
  const { state, reload } = calls;
  return (
    <section className="card" aria-labelledby="calls-title">
      <h2 id="calls-title">Phone calls</h2>
      {state.status === "loading" ? <LoadingState /> : null}
      {state.status === "failed" ? <ErrorState error={state.error} onRetry={reload} /> : null}
      {state.status === "loaded" && state.data.length === 0 ? (
        <p className="muted">No calls yet.</p>
      ) : null}
      {state.status === "loaded"
        ? state.data.map((c, i) => (
            <details key={c.id} open={i === 0} className="call">
              <summary>
                Call {state.data.length - i} · {tel.CALL_STATE_LABELS[c.state]} ·{" "}
                {when(c.dialled_at)} · {c.moderator_name ?? "Moderator"} · seat {c.agent_id}
              </summary>
              {task.can_assign &&
              !task.is_moderator &&
              ["NEEDS_MATCH", "FETCH_FAILED"].includes(c.state) ? (
                <CallFixer call={c} onChange={() => reload()} />
              ) : null}
              <ol className="list timeline">
                {c.events.map((e, n) => (
                  <li key={`${e.at}-${n}`}>
                    <span className="muted">
                      {when(e.at)} · {e.actor ?? "Platform"} ·{" "}
                      {e.kind.toLowerCase().replace(/_/g, " ")}
                    </span>
                    <div>{e.text}</div>
                  </li>
                ))}
              </ol>
            </details>
          ))
        : null}
    </section>
  );
}

/** The phone-call part of a telephony task page: the moderator's card and the call history share
 * one list of calls. When a call's recording is stored, the server has moved the task to Recorded,
 * so the task is loaded again. */
export function PhoneCalls({
  task,
  onChange,
  onTaskStale,
}: {
  task: work.TaskDetail;
  onChange: (t: work.TaskDetail) => void;
  onTaskStale: () => void;
}) {
  const calls = useCalls(task.id);
  const latest = calls.state.status === "loaded" ? calls.state.data[0] : undefined;
  const key = calls.state.status === "loaded" ? `${latest?.id ?? ""}:${latest?.state ?? ""}` : null;
  const seen = useRef<string | null>(null);
  useEffect(() => {
    if (key === null) return;
    const before = seen.current;
    seen.current = key;
    if (before !== null && before !== key && latest?.state === "RECORDED") onTaskStale();
  }, [key, latest?.state, onTaskStale]);
  return (
    <>
      {task.is_moderator ? <CallCard task={task} calls={calls} onChange={onChange} /> : null}
      <CallHistory task={task} calls={calls} />
    </>
  );
}
