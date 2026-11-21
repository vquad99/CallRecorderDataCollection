// Phone calls on a telephony task (D-101, D-103, D-111, D-113, D-127): everything happens in this
// portal (owner: no provider screen or app). Both participants have agreed on their consent form
// first; then the moderator follows one button at a time: Start call (the phone system rings A),
// "A answered - call B", "B answered - start recording", "Stop and close call". The platform then
// fetches the recording. Every state shown comes from the server; nothing is shown as connected
// on its own (TEL-037). The provider's own answers are in a technical log for the Super Admin.
// Start call waits for the moderator's phone line to be Ready (D-133), and the line is told when
// a call opens and when it is over, so it is made Ready again for the next one. Before Start call
// and on the call the project's reminders show (D-147); Send to QC waits for both speakers'
// device details.
import { useEffect, useRef, useState, useSyncExternalStore, type ReactNode } from "react";

import * as tel from "../../api/telephony";
import * as work from "../../api/work";
import { useAuth } from "../../auth/AuthContext";
import { useConfirm } from "../../components/ConfirmDialog";
import { DataTable } from "../../components/DataTable";
import { Button } from "../../components/form/Button";
import { IconTile } from "../../components/Icon";
import { ErrorNotice } from "../../components/Notice";
import { ErrorState, LoadingState } from "../../components/StateViews";
import { useAction } from "../../hooks/useAction";
import { usePolling } from "../../hooks/usePolling";
import { useResource } from "../../hooks/useResource";
import { clock, time, when } from "../../lib/format";
import { labelFor } from "../../lib/labels";
import { CallBadge } from "../calls/callUi";
import { usePhoneLine, type PhoneLine } from "../phoneline/PhoneLine";
import { seatLog } from "../phoneline/seatLink";
import { devicesWait } from "./DeviceDetails";
import { ListenLatest } from "./Listen";
import { Reminders } from "./Reminders";
import type { OnTaskChange } from "./TaskDetailPage";

const REFRESH_MS = 5000;

/** Calls of a task, fetched again every few seconds while one is still moving on its own. */
function useCalls(taskId: string) {
  return usePolling(
    () => tel.listCalls(taskId),
    [taskId],
    REFRESH_MS,
    (calls) => calls.some((c) => tel.MOVING.includes(c.state)),
  );
}

type Calls = ReturnType<typeof useCalls>;

const useIsSuperAdmin = () => Boolean(useAuth().user?.roles.includes("SUPER_ADMIN"));

/** Why a call went wrong, in plain words for the moderator and the project admin. */
const PROBLEM_WORDS: Record<string, string> = {
  PROVIDER_REFUSED:
    "The phone system did not place the call. Ask your admin to check the phone settings.",
  PROVIDER_UNREACHABLE:
    "The phone system did not answer. The phone may still ring: wait a minute before calling again.",
  PHONE_NOT_SUPPORTED:
    "This phone number cannot be called. Ask your admin to check the participant's number.",
  SEVERAL_CALLS: "Several calls in the phone system fit this one. Choose the right one below.",
  NUMBER_NOT_CONFIRMED: "The phone system did not show the number. Choose the right call below.",
  RECORDING_NOT_FOUND: "The phone system has no recording of this call yet.",
  SEARCH_FAILED: "The phone system could not be searched for the recording.",
  DOWNLOAD_FAILED: "The recording could not be downloaded from the phone system.",
  UNREADABLE_AUDIO: "The phone system's file is not readable audio.",
  SESSION_GONE: "The chosen call is no longer listed by the phone system.",
};
const problem = (call: tel.Call) =>
  PROBLEM_WORDS[call.failure_code ?? ""] ??
  "Something went wrong with this call. Ask your admin to look at it.";

/** The call's history in plain words; null leaves out a provider-level step (it stays in the
 * Super Admin's technical log). A kind not listed shows the server's own words. */
const EVENT_WORDS: Record<string, ((call: tel.Call) => string) | null> = {
  DIAL_REQUESTED: (c) => `Call started to participant A (number ending ${c.phone_hint})`,
  DIAL_ACCEPTED: () => "The phone system is ringing participant A",
  DIAL_FAILED: (c) => problem(c),
  B_DIAL_REQUESTED: (c) => `Asked to ring participant B (number ending ${c.b_phone_hint ?? "?"})`,
  B_DIAL_ACCEPTED: () => "The phone system is ringing participant B",
  B_DIAL_FAILED: () => "The phone system could not ring participant B",
  SEARCHING: null,
  SEARCH_ERROR: null,
  FETCH_ERROR: null,
  DOWNLOADED: null,
  MATCHED: () => "Recording found",
  MATCH_CHOSEN: () => "Recording chosen by hand",
  NEEDS_MATCH: () => "Several recordings fit: someone must choose the right one",
  FETCH_FAILED: () => "The recording could not be fetched",
  RECORDED: () => "Recording stored",
  CALL_CANCELLED: (c) =>
    `Call cancelled: ${labelFor(tel.CANCEL_REASONS, c.cancel_reason)}${c.note ? `. ${c.note}` : ""}`,
};

/** Ask why, then cancel the call (the reason comes from a fixed list; Other needs a note). */
function CancelButton({ call, onChange }: { call: tel.Call; onChange: () => void }) {
  const confirm = useConfirm();
  return (
    <>
      <Button
        variant="secondary"
        icon="phoneX"
        onClick={() =>
          confirm.ask({
            title: "Cancel this call?",
            message: "The call ends here. Start a new call when you are ready.",
            confirmLabel: "Cancel the call",
            danger: true,
            reasons: tel.CANCEL_REASONS,
            commentLabel: "Note",
            action: async ({ reason, comment }) => {
              await tel.cancelCall(call.id, reason as tel.CancelReason, comment);
              onChange();
            },
          })
        }
      >
        Cancel this call
      </Button>
      {confirm.dialog}
    </>
  );
}

/** Pick the right recording or look again: for the moderator and project admins. */
function CallFixer({ call, onChange }: { call: tel.Call; onChange: () => void }) {
  const { busy, error, run } = useAction(onChange);
  return (
    <div className="stack">
      <p>{problem(call)}</p>
      {call.state === "NEEDS_MATCH" && call.candidates.length > 0 ? (
        <DataTable className="call-candidates" caption="Calls in the phone system at that time">
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
                    icon="ok"
                    busy={busy === c.key}
                    disabled={busy !== null}
                    onClick={() => void run(() => tel.chooseMatch(call.id, c.key), c.key)}
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
        </DataTable>
      ) : null}
      <div className="actions">
        <Button
          variant="secondary"
          icon="refresh"
          busy={busy === "retry"}
          disabled={busy !== null}
          onClick={() => void run(() => tel.retryCall(call.id), "retry")}
        >
          Look for the recording again
        </Button>
      </div>
      <ErrorNotice error={error} />
    </div>
  );
}

const B_DIALS = 3; // as the server allows in one call

/** The call in progress, one main button at a time (D-127). Each button does what the moderator
 * says happened and the next step together: "A answered" ticks A and rings B; "B answered" ticks
 * B and marks where the recording starts; "Stop and close" marks the end and closes the call. */
function CallSteps({ call, onChange }: { call: tel.Call; onChange: () => Promise<unknown> }) {
  const { busy, error, run } = useAction();
  const [now, setNow] = useState(() => Date.now());
  const aOn = "A_JOINED" in call.checklist;
  const bOn = "B_JOINED" in call.checklist;
  const started = call.record_started_at ?? null;
  const stopped = call.record_stopped_at ?? null;
  const bLeft = B_DIALS - (call.b_dial_attempts ?? 0);
  useEffect(() => {
    if (!started || stopped) return;
    const timer = window.setInterval(() => setNow(Date.now()), 1000);
    return () => window.clearInterval(timer);
  }, [started, stopped]);
  const elapsed = started
    ? Math.max(0, Math.round(((stopped ? Date.parse(stopped) : now) - Date.parse(started)) / 1000))
    : 0;
  const step = (key: string, ...actions: (() => Promise<unknown>)[]) =>
    void run(async () => {
      try {
        for (const action of actions) await action();
      } finally {
        await onChange();
      }
    }, key);
  const tick = (item: tel.ChecklistItem) => () => tel.tickChecklist(call.id, item, true);
  const ringB = () => tel.callParticipantB(call.id);
  const startRecording = () => tel.markRecording(call.id, "start");
  const stopRecording = () => tel.markRecording(call.id, "stop");
  const close = () => tel.closeCall(call.id, "");

  let words: string;
  let main: ReactNode;
  let extra: ReactNode = null;
  if (!aOn) {
    words = `Ringing participant A (number ending ${call.phone_hint}). Click when they answer.`;
    main = (
      <Button icon="phone" busy={busy === "a"} onClick={() => step("a", tick("A_JOINED"), ringB)}>
        A answered – call B
      </Button>
    );
  } else if (!bOn && !call.b_dial_attempts) {
    // A is on the line but B was not rung (the request for B failed): ring B from here.
    words = "Participant A is on the line.";
    main = (
      <Button icon="phone" busy={busy === "ring"} onClick={() => step("ring", ringB)}>
        Call participant B
      </Button>
    );
  } else if (!bOn) {
    words = `Ringing participant B (number ending ${call.b_phone_hint ?? "?"}). Click when they answer.`;
    main = (
      <Button
        icon="record"
        busy={busy === "b"}
        onClick={() => step("b", tick("B_JOINED"), startRecording)}
      >
        B answered – start recording
      </Button>
    );
    extra =
      bLeft > 0 ? (
        <Button
          variant="secondary"
          icon="phone"
          busy={busy === "ring"}
          onClick={() => step("ring", ringB)}
        >
          Ring B again ({bLeft} left)
        </Button>
      ) : null;
  } else if (!started) {
    words = "Both are on the line.";
    main = (
      <Button icon="record" busy={busy === "rec"} onClick={() => step("rec", startRecording)}>
        Start recording
      </Button>
    );
  } else if (!stopped) {
    words = `Recording · ${clock(elapsed)}. Stay muted and listen. Click when they have finished.`;
    main = (
      <Button icon="stop" busy={busy === "stop"} onClick={() => step("stop", stopRecording, close)}>
        Stop and close call
      </Button>
    );
  } else {
    words = `Recording stopped (${clock(elapsed)}).`;
    main = (
      <Button icon="ok" busy={busy === "close"} onClick={() => step("close", close)}>
        Close call
      </Button>
    );
  }
  return (
    <div className="stack">
      <p aria-live="polite">{words}</p>
      <div className="actions">
        {main}
        {extra}
      </div>
      <ErrorNotice error={error} />
    </div>
  );
}

/** Why Start call waits for the phone line (D-133); null when it need not: the line is Ready, or
 * the seat is made Ready in TxContact's Chirp app (`seat` null). */
function lineWait(seat: tel.SeatLogin | null | undefined, line: PhoneLine | null): string | null {
  if (!seat) return null;
  if (!seat.agent_id || !seat.has_password)
    return "Ask your admin to save your phone seat password.";
  if (!line) return "Reload this page to connect your phone line.";
  if (line.status === "ready") return null;
  if (line.status === "failed") {
    return "Your phone line is not connected. Click Try again at the top of the page.";
  }
  return "Your phone line is not Ready yet. Start call works once the top of the page says “Phone line: Ready”.";
}

/** The moderator's card on a telephony task: start the session, call, close, then send to QC. */
function CallCard({
  task,
  calls,
  onChange,
}: {
  task: work.TaskDetail;
  calls: Calls;
  onChange: OnTaskChange;
}) {
  const status = useResource(() => tel.telephonyStatus(), []);
  const refresh = () => void calls.refresh();
  const { busy, error, run } = useAction();
  const line = usePhoneLine();
  const latest = calls.state.status === "loaded" ? calls.state.data[0] : undefined;
  // The line follows this task's call: on it while it is open, made Ready again once it is over.
  useEffect(() => {
    if (!line || !latest) return;
    if (latest.state === "DIALLING") line.onCall(latest.id);
    else if (line.call === latest.id) line.onCall(null);
  }, [line, latest]);

  const canStartSession =
    task.status !== "RECORDED" && task.allowed_transitions.includes("IN_PROGRESS");
  const calling = task.status === "IN_PROGRESS";
  const review = task.status === "RECORDED" && task.allowed_transitions.includes("AUDIO_QC");
  if (!canStartSession && !calling && !review) return null;

  const move = (to: work.TaskStatus, message: string) =>
    void run(async () => onChange(await work.transitionTask(task.id, to, "", ""), message), to);
  const callAction = (key: string, action: () => Promise<tel.Call>) =>
    void run(async () => {
      await action();
      refresh();
    }, key);
  const cancel = (call: tel.Call) => <CancelButton call={call} onChange={refresh} />;
  const startCall = () =>
    callAction("start", async () => {
      line?.onCall("starting"); // TxContact moves the seat while the call is placed: leave it
      try {
        const call = await tel.startCall(task.id);
        line?.onCall(call.state === "DIALLING" ? call.id : null);
        return call;
      } catch (failure) {
        line?.onCall(null);
        throw failure;
      }
    });

  let title = "Start the session";
  let body: ReactNode = (
    <p>Start the session, then call participant A from here. Their phone will ring.</p>
  );
  let go: ReactNode = (
    <Button
      icon="play"
      busy={busy === "IN_PROGRESS"}
      onClick={() => move("IN_PROGRESS", "Session started.")}
    >
      Start session
    </Button>
  );

  if (review) {
    // D-147: the device details of both people come before QC.
    const devices = devicesWait(task);
    title = "Check the call recording";
    body = (
      <div className="record-card__listen">
        <p>Listen to the recording. If it is good, send it to QC; if not, call again.</p>
        <ListenLatest taskId={task.id} />
      </div>
    );
    go = (
      <>
        <Button
          icon="send"
          busy={busy === "AUDIO_QC"}
          disabled={busy !== null || devices !== null}
          aria-describedby={devices ? "call-qc-waits" : undefined}
          onClick={() => move("AUDIO_QC", "Sent to QC. A QC Executive checks it next.")}
        >
          Send to QC
        </Button>
        {devices ? (
          <p id="call-qc-waits" className="muted">
            {devices}
          </p>
        ) : null}
        <Button
          variant="secondary"
          icon="phone"
          busy={busy === "IN_PROGRESS"}
          disabled={busy !== null}
          onClick={() => move("IN_PROGRESS", "Ready to call again.")}
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
      body = <p>Phone calls are not set up yet. Ask your admin to set up the phone system.</p>;
      go = null;
    } else if (!latest || ["DIAL_FAILED", "CANCELLED", "RECORDED"].includes(latest.state)) {
      const waiting = task.consent_missing;
      const noLine = lineWait(status.state.data.seat_login, line);
      title = "Ready to call";
      body = (
        <>
          {waiting.length > 0 ? (
            <p className="notice">
              Participant {waiting.join(" and ")} has not agreed on the consent form yet. The call
              can start once both have agreed.
            </p>
          ) : noLine ? (
            <p className="notice">{noLine}</p>
          ) : (
            <p>
              Click Start call: participant A&apos;s phone rings (
              {task.participant_a.participant_code}). Then follow the button on this card.
            </p>
          )}
          {latest?.state === "DIAL_FAILED" ? (
            <p className="notice notice--error" role="alert">
              The last call could not be placed. {problem(latest)}
            </p>
          ) : null}
          <Reminders task={task} inline />
        </>
      );
      go = (
        <Button
          icon="phone"
          busy={busy === "start"}
          disabled={waiting.length > 0 || noLine !== null}
          onClick={startCall}
        >
          Start call
        </Button>
      );
    } else if (latest.state === "DIALLING") {
      title = "On the call";
      body = (
        <>
          <CallSteps call={latest} onChange={calls.refresh} />
          <Reminders task={task} inline />
        </>
      );
      go = cancel(latest);
    } else if (latest.state === "WAITING_FOR_RECORDING") {
      title = "Fetching the recording";
      body = (
        <p aria-live="polite">
          The call is closed. The recording is being fetched from the phone system; this page
          updates on its own.
        </p>
      );
      go = cancel(latest);
    } else {
      title = tel.CALL_STATE_LABELS[latest.state];
      body = <CallFixer call={latest} onChange={refresh} />;
      go = cancel(latest);
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

/** Every call of a telephony task with its history, for everyone who sees the task. A project
 * admin can also pick the recording, look again, or end a call that is stuck. The Super Admin
 * also sees the provider's own answers. */
function CallHistory({ task, calls }: { task: work.TaskDetail; calls: Calls }) {
  const { state, reload } = calls;
  const superAdmin = useIsSuperAdmin();
  const manages = task.can_assign && !task.is_moderator;
  const refresh = () => void calls.refresh();
  return (
    <section className="card" aria-labelledby="calls-title">
      <h2 id="calls-title" className="with-icon">
        <IconTile name="phone" size={28} />
        Phone calls
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
                    {when(c.dialled_at)} · {c.moderator_name ?? "Moderator"}
                  </span>
                </span>
              </summary>
              {manages && tel.CANCELLABLE.includes(c.state) ? (
                <div className="call__manage">
                  {["NEEDS_MATCH", "FETCH_FAILED"].includes(c.state) ? (
                    <CallFixer call={c} onChange={refresh} />
                  ) : null}
                  <CancelButton call={c} onChange={refresh} />
                </div>
              ) : null}
              <ol className="list timeline">
                {c.events.flatMap((e, n) => {
                  const words = EVENT_WORDS[e.kind];
                  if (words === null) return [];
                  return [
                    <li key={`${e.at}-${n}`}>
                      <span className="muted">
                        {when(e.at)} · {e.actor ?? "Platform"}
                      </span>
                      <div>{words ? words(c) : e.text}</div>
                    </li>,
                  ];
                })}
              </ol>
              {superAdmin ? <TechnicalLog call={c} /> : null}
            </details>
          ))
        : null}
      {superAdmin ? <PhoneLineLog /> : null}
    </section>
  );
}

/** What this browser's phone line sent to and received from TxContact (D-133), for the Super
 * Admin: kept in the page's memory only, never with the seat password. */
function PhoneLineLog() {
  const entries = useSyncExternalStore(seatLog.subscribe, seatLog.entries);
  if (entries.length === 0) return null;
  return (
    <details className="tech-log">
      <summary>Phone line log (this browser)</summary>
      <ol className="list">
        {entries.map((e, n) => (
          <li key={`${e.at}-${n}`}>
            <span className="muted">
              {time(e.at)} · {e.kind}
            </span>
            <div className="mono break">{e.text}</div>
          </li>
        ))}
      </ol>
    </details>
  );
}

/** The provider's own answers, seat and file details, for the Super Admin only. */
function TechnicalLog({ call }: { call: tel.Call }) {
  return (
    <details className="tech-log">
      <summary>Technical log</summary>
      <p className="muted">
        Seat {call.agent_id} · provider {call.provider}
        {call.provider_session_id ? ` · call ${call.provider_session_id}` : ""}
        {call.failure_detail ? ` · ${call.failure_detail}` : ""}
      </p>
      <ol className="list">
        {call.events.map((e, n) => (
          <li key={`${e.at}-${n}`}>
            <span className="muted">
              {when(e.at)} · {e.kind}
            </span>
            <div className="mono break">{e.text}</div>
          </li>
        ))}
      </ol>
    </details>
  );
}

/** The phone-call part of a telephony task page: the moderator's card, the consent card right
 * under it (recording waits for consent, D-119), the speakers' device details (D-147) and the call
 * history. They share one list of calls. When a call's recording is stored, the server has moved
 * the task to Recorded, so the page is told to fetch the task again. */
export function PhoneCalls({
  task,
  onChange,
  onTaskStale,
  consent,
  devices = null,
}: {
  task: work.TaskDetail;
  onChange: OnTaskChange;
  onTaskStale: () => void;
  consent: ReactNode;
  devices?: ReactNode;
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
      {consent}
      {devices}
      <CallHistory task={task} calls={calls} />
    </>
  );
}
