// Phone calls on a telephony task (D-101, D-103, D-111, D-113): everything happens in this portal
// (owner: no provider screen or app). The moderator notes both people's consent, starts the call,
// the phone system (TxContact) rings participant A and then B, the moderator marks where the
// conversation starts and stops, and closes the call.
// The platform then fetches the recording. Every state shown comes from the server; nothing is
// shown as connected on its own (TEL-037). Moderators read plain words; the provider's own answers
// are in a technical log for the Super Admin.
import { useEffect, useRef, useState, type ReactNode } from "react";

import * as tel from "../../api/telephony";
import * as work from "../../api/work";
import { useAuth } from "../../auth/AuthContext";
import { useConfirm } from "../../components/ConfirmDialog";
import { DataTable } from "../../components/DataTable";
import { Button } from "../../components/form/Button";
import { TextField } from "../../components/form/TextField";
import { Icon } from "../../components/Icon";
import { ErrorNotice } from "../../components/Notice";
import { ErrorState, LoadingState } from "../../components/StateViews";
import { useAction } from "../../hooks/useAction";
import { usePolling } from "../../hooks/usePolling";
import { useResource } from "../../hooks/useResource";
import { clock, time, when } from "../../lib/format";
import { labelFor } from "../../lib/labels";
import { CallBadge } from "../calls/callUi";
import { ListenLatest } from "./Listen";
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
          busy={busy === "retry"}
          disabled={busy !== null}
          onClick={() => void run(() => tel.retryCall(call.id), "retry")}
        >
          <Icon name="refresh" size={15} />
          Look for the recording again
        </Button>
      </div>
      <ErrorNotice error={error} />
    </div>
  );
}

/** What the moderator confirms while on the call; each tick is saved and kept in the history.
 * The box shows the tick at once (it is the moderator's own answer, not the provider's state) and
 * takes it back, with the reason, if the server refuses it. */
function Checklist({ call, onChange }: { call: tel.Call; onChange: () => Promise<unknown> }) {
  const [pending, setPending] = useState<Partial<Record<tel.ChecklistItem, boolean>>>({});
  const { error, run } = useAction();
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
              void run(async () => {
                await tel.tickChecklist(call.id, c.item, done);
                await onChange();
              }, c.item).finally(() => settle(c.item));
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

const B_DIALS = 3; // as the server allows in one call
const B_WORDS: Record<string, string> = {
  ACCEPTED: "The phone system is ringing participant B",
  REFUSED: "The phone system did not ring participant B",
  UNREACHABLE: "The phone system did not answer; B's phone may still ring",
};

/** Ring participant B into the call once A is on the line (D-111). */
function CallB({
  call,
  task,
  onChange,
}: {
  call: tel.Call;
  task: work.TaskDetail;
  onChange: () => Promise<unknown>;
}) {
  const { busy, error, run } = useAction();
  const aOn = "A_JOINED" in call.checklist;
  const bOn = "B_JOINED" in call.checklist;
  const tries = call.b_dial_attempts ?? 0;
  const left = B_DIALS - tries;
  return (
    <div className="call-b" role="group" aria-label="Participant B">
      <div>
        <strong>Participant B ({task.participant_b.participant_code})</strong>
        <p className="muted">
          {tries === 0
            ? aOn
              ? "A is on the call. Ring B now: B joins this call."
              : "Tick that participant A is on the call first."
            : `${B_WORDS[call.b_dial_status ?? ""] ?? "Asked to ring B"} (number ending ${
                call.b_phone_hint ?? "?"
              }${call.b_dialled_at ? `, at ${time(call.b_dialled_at)}` : ""}).${
                bOn ? "" : " When B answers, tick that B is on the call."
              }`}
        </p>
      </div>
      {bOn ? null : (
        <Button
          variant={tries === 0 ? "primary" : "secondary"}
          busy={busy !== null}
          disabled={!aOn || left <= 0}
          onClick={() =>
            void run(async () => {
              await tel.callParticipantB(call.id);
              await onChange();
            })
          }
        >
          <Icon name="phone" size={16} weight="fill" />
          {tries === 0 ? "Call participant B" : `Ring B again (${left} left)`}
        </Button>
      )}
      <ErrorNotice error={error} />
    </div>
  );
}

/** The moderator marks the conversation once both people are on the line and have agreed to be
 * recorded (D-113, D-119). The phone system records the whole call; the delivery file keeps only
 * what lies between Start and Stop. */
function RecordMarks({
  call,
  task,
  onChange,
}: {
  call: tel.Call;
  task: work.TaskDetail;
  onChange: () => Promise<unknown>;
}) {
  const { busy, error, run } = useAction();
  const [now, setNow] = useState(() => Date.now());
  const started = call.record_started_at ?? null;
  const stopped = call.record_stopped_at ?? null;
  const bothOn = "A_JOINED" in call.checklist && "B_JOINED" in call.checklist;
  const consented = task.consent_missing.length === 0;
  useEffect(() => {
    if (!started || stopped) return;
    const timer = window.setInterval(() => setNow(Date.now()), 1000);
    return () => window.clearInterval(timer);
  }, [started, stopped]);
  const elapsed = started
    ? Math.max(0, Math.round(((stopped ? Date.parse(stopped) : now) - Date.parse(started)) / 1000))
    : 0;
  const mark = (step: "start" | "stop") =>
    void run(async () => {
      await tel.markRecording(call.id, step);
      await onChange();
    }, step);
  return (
    <div className="call-b record-marks" role="group" aria-label="Recording">
      <div>
        <strong>
          {!started ? "Recording not started" : stopped ? "Recording stopped" : "Recording"}
          {started ? ` · ${clock(elapsed)}` : ""}
        </strong>
        <p className="muted">
          {!started
            ? !bothOn
              ? "Tick that A and B are on the call first."
              : !consented
                ? "Note both people's consent below first."
                : "Both people are on the line and agreed. Click Start recording when the conversation begins."
            : stopped
              ? `Kept: ${time(started)} to ${time(stopped)}. Only this part is delivered.`
              : `Since ${time(started)}. Click Stop recording when they have finished.`}
        </p>
      </div>
      <span className="actions">
        {!started || stopped ? (
          <Button
            variant={started ? "secondary" : "primary"}
            busy={busy === "start"}
            disabled={!bothOn || !consented}
            onClick={() => mark("start")}
          >
            <Icon name="record" size={16} />
            {started ? "Start again" : "Start recording"}
          </Button>
        ) : (
          <Button busy={busy === "stop"} onClick={() => mark("stop")}>
            <Icon name="stop" size={16} />
            Stop recording
          </Button>
        )}
      </span>
      <ErrorNotice error={error} />
    </div>
  );
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
  const [note, setNote] = useState("");
  const refresh = () => void calls.refresh();
  const { busy, error, run } = useAction();

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

  const latest = calls.state.status === "loaded" ? calls.state.data[0] : undefined;

  let title = "Start the session";
  let body: ReactNode = (
    <p>Start the session, then call participant A from here. Their phone will ring.</p>
  );
  let go: ReactNode = (
    <Button busy={busy === "IN_PROGRESS"} onClick={() => move("IN_PROGRESS", "Session started.")}>
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
        <Button
          busy={busy === "AUDIO_QC"}
          disabled={busy !== null}
          onClick={() => move("AUDIO_QC", "Sent to QC. A QC Executive checks it next.")}
        >
          Send to QC
        </Button>
        <Button
          variant="secondary"
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
      title = "Ready to call";
      body = (
        <>
          <ol className="record-card__steps record-card__steps--list">
            <li>Note both people&apos;s consent below.</li>
            <li className="is-now">
              Click Start call: the phone system rings participant A (
              {task.participant_a.participant_code}).
            </li>
            <li>When A answers, tick it and click Call participant B.</li>
            <li>
              When both are on the line, click Start recording; Stop recording when they finish,
              then Close call.
            </li>
          </ol>
          {latest?.state === "DIAL_FAILED" ? (
            <p className="notice notice--error" role="alert">
              The last call could not be placed. {problem(latest)}
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
      const ready =
        tel.CHECKLIST.every((c) => !c.required || c.item in latest.checklist) &&
        Boolean(latest.record_started_at);
      title = "On the call";
      body = (
        <>
          <p>
            The phone system is ringing participant A (number ending {latest.phone_hint}). When A is
            on the line, tick it, then call participant B. Stay on the call, muted, and listen: if
            the line is poor, cancel the call and choose <strong>Poor line quality</strong>.
          </p>
          <Checklist call={latest} onChange={calls.refresh} />
          <CallB call={latest} task={task} onChange={calls.refresh} />
          <RecordMarks call={latest} task={task} onChange={calls.refresh} />
          <TextField
            label="Note for the record (optional)"
            value={note}
            onChange={(e) => setNote(e.target.value)}
          />
          {ready ? null : (
            <p className="muted">
              To close the call: tick that both people are on the call, note their consent below,
              then start and stop the recording.
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
          {cancel(latest)}
        </>
      );
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
    </section>
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
 * under it (recording waits for consent, D-119), and the call history. They share one list of
 * calls. When a call's recording is stored, the server has moved the task to Recorded, so the
 * page is told to fetch the task again. */
export function PhoneCalls({
  task,
  onChange,
  onTaskStale,
  consent,
}: {
  task: work.TaskDetail;
  onChange: OnTaskChange;
  onTaskStale: () => void;
  consent: ReactNode;
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
      <CallHistory task={task} calls={calls} />
    </>
  );
}
