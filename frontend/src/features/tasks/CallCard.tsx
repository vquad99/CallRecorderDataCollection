// Phone calls on a telephony task (D-101, D-103): the moderator starts the call, TxContact rings
// participant A and connects them to the moderator's TxContact seat, the moderator adds B from the
// TxContact screen, ticks the checklist, and closes the call here when A and B have finished. The
// platform then fetches the recording. Every state shown comes from the server; nothing is shown
// as connected on its own (TEL-037).
import { useCallback, useEffect, useRef, useState, type ReactNode } from "react";

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
import { CallBadge, when, words } from "../calls/callUi";
import { Player } from "./AudioQcPanel";

const REFRESH_MS = 5000;

/** Calls of a task. While one is still moving on its own the list is fetched again every few
 * seconds, quietly: what is on screen stays (an open form, a typed note) until the new answer
 * replaces it. */
function useCalls(taskId: string) {
  const { state, reload, replace } = useResource(() => tel.listCalls(taskId), [taskId]);
  // Answers can come back out of order (several ticks in a row): only the newest request's
  // answer is shown, so an older list never replaces a newer one.
  const newest = useRef(0);
  const refresh = useCallback(() => {
    const mine = ++newest.current;
    return tel
      .listCalls(taskId)
      .then((data) => {
        if (mine === newest.current) replace(data);
      })
      .catch(() => undefined);
  }, [taskId, replace]);
  const moving = state.status === "loaded" && state.data.some((c) => tel.MOVING.includes(c.state));
  useEffect(() => {
    if (!moving) return;
    const timer = window.setInterval(() => void refresh(), REFRESH_MS);
    return () => window.clearInterval(timer);
  }, [moving, refresh]);
  return { state, reload, refresh };
}

type Calls = ReturnType<typeof useCalls>;

/** Pick the right TxContact call or look again: for the moderator and project admins. */
function CallFixer({ call, onChange }: { call: tel.Call; onChange: () => void }) {
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
        <div className="table-wrap">
          <table className="table call-candidates">
            <caption className="muted">TxContact calls at the time of this call</caption>
            <thead>
              <tr>
                {/* The choice comes first: on a narrow screen it is visible without scrolling. */}
                <th scope="col">Choose</th>
                <th scope="col">Started</th>
                <th scope="col">Length</th>
                <th scope="col">Numbers end in</th>
                <th scope="col">File</th>
              </tr>
            </thead>
            <tbody>
              {call.candidates.map((c) => (
                <tr key={c.key}>
                  <td>
                    <Button
                      variant="secondary"
                      busy={busy === c.key}
                      onClick={() => act(c.key, () => tel.chooseMatch(call.id, c.key))}
                    >
                      This is the call
                    </Button>
                  </td>
                  <td>{when(c.start)}</td>
                  <td>{c.duration ? `${c.duration} s` : "-"}</td>
                  <td>
                    {c.from_hint || "?"} / {c.to_hint || "?"}
                  </td>
                  <td className="call-file">{c.file}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      ) : null}
      <div className="actions">
        <Button
          variant="secondary"
          busy={busy === "retry"}
          onClick={() => act("retry", () => tel.retryCall(call.id))}
        >
          <Icon name="refresh" size={15} />
          Look for the recording again
        </Button>
      </div>
      <ErrorNotice error={error} />
    </div>
  );
}

/** "The call did not work": a reason from the fixed list, and a note for Other. */
function CancelForm({ call, onChange }: { call: tel.Call; onChange: () => void }) {
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
      className="stack call-cancel"
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

/** What the moderator confirms while on the call; each tick is saved and kept in the history.
 * The box shows the tick at once (it is the moderator's own answer, not the provider's state) and
 * takes it back, with the reason, if the server refuses it. */
function Checklist({ call, onChange }: { call: tel.Call; onChange: () => Promise<unknown> }) {
  const [pending, setPending] = useState<Partial<Record<tel.ChecklistItem, boolean>>>({});
  const [error, setError] = useState<ApiError | null>(null);
  const settle = (item: tel.ChecklistItem) =>
    setPending((p) => Object.fromEntries(Object.entries(p).filter(([k]) => k !== item)));
  return (
    <fieldset className="call-checklist">
      <legend>Call checklist</legend>
      {tel.CHECKLIST.map((c) => (
        <label key={c.item} className="checkbox">
          <input
            type="checkbox"
            checked={pending[c.item] ?? c.item in call.checklist}
            disabled={c.item in pending}
            onChange={(e) => {
              const done = e.target.checked;
              setPending((p) => ({ ...p, [c.item]: done }));
              setError(null);
              tel
                .tickChecklist(call.id, c.item, done)
                .then(onChange)
                .catch((err: unknown) => setError(toApiError(err)))
                .finally(() => settle(c.item));
            }}
          />
          <span>
            {c.label}
            {c.required ? <span className="muted"> (needed to close the call)</span> : null}
          </span>
        </label>
      ))}
      <ErrorNotice error={error} />
    </fieldset>
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
  const refresh = () => void calls.refresh();
  const callAction = (key: string, action: () => Promise<tel.Call>) => {
    setBusy(key);
    setError(null);
    action()
      .then(refresh)
      .catch((err: unknown) => setError(toApiError(err)))
      .finally(() => setBusy(null));
  };

  const latest = calls.state.status === "loaded" ? calls.state.data[0] : undefined;

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
        <p>Listen to the recording. If it is good, send it to QC; if not, call again.</p>
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
    if (status.state.status === "failed") {
      // Not knowing is not the same as "not set up": say what happened and offer to try again.
      return <ErrorState error={status.state.error} onRetry={status.reload} />;
    }
    if (!status.state.data.configured) {
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
              Sign in to your TxContact screen, then click Start call. TxContact rings participant A
              ({task.participant_a.participant_code}) and connects them to you.
            </li>
            <li>Add participant B from your TxContact screen, and tick the checklist.</li>
            <li>Record each person&apos;s consent below.</li>
            <li>Stay on the call, muted, and listen. When they have finished, close the call.</li>
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
      const ready = tel.CHECKLIST.every((c) => !c.required || c.item in latest.checklist);
      title = "On the call";
      body = (
        <>
          <p>
            TxContact was asked to ring participant A (number ending {latest.phone_hint}) on seat{" "}
            {latest.agent_id}. Add participant B from your TxContact screen. Stay on the call,
            muted, and listen: if the line is poor, cancel the call and choose{" "}
            <strong>Poor line quality</strong>.
          </p>
          <Checklist call={latest} onChange={calls.refresh} />
          <TextField
            label="Note for the record (optional)"
            value={note}
            onChange={(e) => setNote(e.target.value)}
          />
          {ready ? null : (
            <p className="muted">
              Tick both people on the call, and record their consent below, to close the call.
            </p>
          )}
        </>
      );
      go = (
        <>
          <Button
            busy={busy === "close"}
            disabled={!ready}
            onClick={() => callAction("close", () => tel.closeCall(latest.id, note))}
          >
            <Icon name="check" size={16} weight="bold" />
            Close call
          </Button>
          <CancelForm call={latest} onChange={refresh} />
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
      go = <CancelForm call={latest} onChange={refresh} />;
    } else {
      title = tel.CALL_STATE_LABELS[latest.state];
      body = <CallFixer call={latest} onChange={refresh} />;
      go = <CancelForm call={latest} onChange={refresh} />;
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

/** Every call of a telephony task with its full history, for everyone who sees the task. A
 * project admin can also pick the recording, look again, or end a call that is stuck. */
function CallHistory({ task, calls }: { task: work.TaskDetail; calls: Calls }) {
  const { state, reload } = calls;
  const manages = task.can_assign && !task.is_moderator;
  return (
    <section className="card" aria-labelledby="calls-title">
      <h2 id="calls-title">
        <Icon name="phone" size={18} /> Phone calls
      </h2>
      {state.status === "loading" ? <LoadingState /> : null}
      {state.status === "failed" ? <ErrorState error={state.error} onRetry={reload} /> : null}
      {state.status === "loaded" && state.data.length === 0 ? (
        <p className="muted">No calls yet.</p>
      ) : null}
      {state.status === "loaded"
        ? state.data.map((c, i) => (
            <details key={c.id} open={i === 0} className="call">
              <summary>
                <span className="call__summary">
                  Call {state.data.length - i} <CallBadge state={c.state} />
                  <span className="muted">
                    {when(c.dialled_at)} · {c.moderator_name ?? "Moderator"} · seat {c.agent_id}
                  </span>
                </span>
              </summary>
              {manages && tel.CANCELLABLE.includes(c.state) ? (
                <div className="call__manage">
                  {["NEEDS_MATCH", "FETCH_FAILED"].includes(c.state) ? (
                    <CallFixer call={c} onChange={() => void calls.refresh()} />
                  ) : null}
                  <CancelForm call={c} onChange={() => void calls.refresh()} />
                </div>
              ) : null}
              <ol className="list timeline">
                {c.events.map((e, n) => (
                  <li key={`${e.at}-${n}`}>
                    <span className="muted">
                      {when(e.at)} · {e.actor ?? "Platform"} · {words(e.kind)}
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
 * so the page is told to fetch the task again. */
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
