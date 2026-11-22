// Face-to-face recorder (FTF-001..015). Captures raw samples with an AudioWorklet at the project's
// delivery rate (normally 16000 Hz, owner 2026-11-17: the file is kept as recorded, never
// converted), uploads 5-second chunks as it goes, and never claims to keep recording after the tab
// is closed or the device sleeps. The project's reminders show before recording; after it, the
// speakers' device details are filled beside Send to QC (D-147).
import { useCallback, useEffect, useRef, useState, type ReactNode } from "react";
import { Link, useNavigate, useParams } from "react-router";

import { getProject } from "../../api/projects";
import * as rec from "../../api/recordings";
import { getTask, transitionTask } from "../../api/work";
import { useAuth } from "../../auth/AuthContext";
import { BackLink } from "../../components/BackLink";
import { useConfirm } from "../../components/ConfirmDialog";
import { DataTable } from "../../components/DataTable";
import { Button } from "../../components/form/Button";
import { Select } from "../../components/form/Select";
import { Icon } from "../../components/Icon";
import { ErrorNotice, SuccessNotice } from "../../components/Notice";
import { EmptyState, ErrorState, LoadingState } from "../../components/StateViews";
import { Stepper } from "../../components/Stepper";
import { useAction } from "../../hooks/useAction";
import { usePageTitle } from "../../hooks/usePageTitle";
import { useResource } from "../../hooks/useResource";
import { clock, plural } from "../../lib/format";
import { labelFor, TASK_STATUS_LABELS } from "../../lib/labels";
import { DeviceDetailsCard, devicesWait } from "../tasks/DeviceDetails";
import { Reminders } from "../tasks/Reminders";
import { ChunkUploader } from "./uploader";
import "./recorder.css";

const CHUNK_SECONDS = 5;
// Kept well under the server's MAX_CHUNK_BYTES (8 MB) even for many channels at high rates.
const MAX_CHUNK_BYTES = 4_000_000;
const TEST_SECONDS = 5;
const NO_AUDIO_SECONDS = 5;
/** The face-to-face delivery rate when a project has no rule of its own (the server's default). */
const DEFAULT_RATE = 16000;
const CONSTRAINTS = {
  echoCancellation: false,
  noiseSuppression: false,
  autoGainControl: false,
  channelCount: 1,
};

type Phase =
  "idle" | "opening" | "ready" | "testing" | "recording" | "finishing" | "processing" | "done";

const STEPS = ["Microphone", "Sound check", "Record", "Save", "Done"];
const STEP_OF: Record<Phase, number> = {
  idle: 0,
  opening: 0,
  ready: 1,
  testing: 1,
  recording: 2,
  finishing: 3,
  processing: 3,
  done: 5,
};

type CaptureMessage =
  { samples: Float32Array; channels: number } | { layoutChanged: { from: number; to: number } };

/** Channel 1 of interleaved samples. */
function firstChannel(samples: Float32Array, channels: number): Float32Array {
  if (channels === 1) return samples;
  const out = new Float32Array(samples.length / channels);
  for (let i = 0; i < out.length; i++) out[i] = samples[i * channels] ?? 0;
  return out;
}

function supported(): boolean {
  return (
    typeof navigator !== "undefined" &&
    Boolean(navigator.mediaDevices?.getUserMedia) &&
    "AudioWorkletNode" in window
  );
}

function micMessage(err: unknown): string {
  const name = err instanceof DOMException ? err.name : "";
  if (name === "NotAllowedError")
    return "Microphone permission was refused. Allow the microphone for this site in the browser settings, then try again.";
  if (name === "NotFoundError") return "No microphone was found. Connect one and try again.";
  if (name === "NotReadableError")
    return "The microphone is in use by another program or cannot be opened.";
  return "The microphone could not be opened.";
}

/** An audio context at exactly the delivery rate with the microphone connected, or null when the
 * browser cannot do it (older Firefox refuses to connect a microphone to such a context). The
 * recording is never converted to another rate (owner, 2026-11-17). */
function contextAt(rate: number, media: MediaStream) {
  let audio: AudioContext | null = null;
  try {
    audio = new AudioContext({ sampleRate: rate });
    const source = audio.createMediaStreamSource(media);
    if (audio.sampleRate !== rate) throw new Error("rate not kept");
    return { audio, source };
  } catch {
    void audio?.close();
    return null;
  }
}

/** A recording that did not finish (the tab closed, the device slept, the microphone stopped):
 * keep what reached the server, which is then prepared and shown like any recording (`onKept`),
 * or discard it (`onDiscarded`). `cause`: what stopped it on this page just now; without it, it
 * is a recording an earlier visit left open. */
function Recovery({
  open,
  cause = null,
  onKept,
  onDiscarded,
}: {
  open: rec.Recording;
  cause?: string | null;
  onKept: (id: string) => void;
  onDiscarded: () => void;
}) {
  const confirm = useConfirm();
  const { busy, error, run } = useAction();
  const keep = async () => {
    const kept = await run(async () => {
      if (open.state === "RECORDING")
        await rec.markInterrupted(open.id, "Page closed or reloaded during recording");
      await rec.completeRecording(open.id, open.chunks_received);
    });
    if (kept) onKept(open.id);
  };
  const discard = () =>
    confirm.ask({
      title: "Discard the saved audio?",
      message: `The ${clock(open.saved_seconds)} that reached the server is deleted. This cannot be undone.`,
      confirmLabel: "Discard it",
      danger: true,
      action: async () => {
        await rec.discardRecording(open.id, "Discarded after interruption");
        onDiscarded();
      },
    });
  return (
    <section className="card" role="alert" aria-labelledby="recovery-title">
      <h2 id="recovery-title">
        {cause ? "The recording stopped" : "An earlier recording did not finish"}
      </h2>
      <p>
        {cause ??
          "It stopped before it was completed (for example the tab was closed, the device slept or the connection was lost)."}{" "}
        {clock(open.saved_seconds)} of audio reached the server and is kept. Nothing after that was
        recorded.
      </p>
      <div className="actions">
        <Button
          icon="ok"
          busy={busy !== null}
          disabled={open.chunks_received === 0}
          onClick={() => void keep()}
        >
          Keep the saved {clock(open.saved_seconds)}
        </Button>
        <Button variant="secondary" icon="trash" disabled={busy !== null} onClick={discard}>
          Discard it
        </Button>
      </div>
      <ErrorNotice error={error} />
      {confirm.dialog}
    </section>
  );
}

/** Right after a good recording (D-120): listen above, then send it to QC or record again,
 * without going back to the task page. `waits`: why Send to QC waits (the device details of
 * both people come first, D-147). */
export function AfterRecording({
  taskId,
  onAgain,
  waits = null,
}: {
  taskId: string;
  onAgain: () => void;
  waits?: string | null;
}) {
  const navigate = useNavigate();
  const { busy, error, run } = useAction();
  return (
    <section className="card stack" aria-labelledby="after-title">
      <h2 id="after-title">Listen, then send it to QC</h2>
      <p>Listen to the recording above. If it is good, send it to QC; if not, record it again.</p>
      {waits ? (
        <p id="after-qc-waits" className="muted">
          {waits}
        </p>
      ) : null}
      <div className="actions">
        <Button
          icon="send"
          busy={busy === "AUDIO_QC"}
          disabled={busy !== null || waits !== null}
          aria-describedby={waits ? "after-qc-waits" : undefined}
          onClick={() =>
            void run(async () => {
              await transitionTask(taskId, "AUDIO_QC", "", "");
              void navigate(`/tasks/${taskId}`, {
                state: { message: "Sent to QC. A QC Executive checks it next." },
              });
            }, "AUDIO_QC")
          }
        >
          Send to QC
        </Button>
        <Button
          variant="secondary"
          icon="record"
          busy={busy === "IN_PROGRESS"}
          disabled={busy !== null}
          onClick={() =>
            void run(async () => {
              await transitionTask(taskId, "IN_PROGRESS", "", "");
              onAgain();
            }, "IN_PROGRESS")
          }
        >
          Record again
        </Button>
      </div>
      <ErrorNotice error={error} />
    </section>
  );
}

/** The saved recording: one file to listen to; the Super Admin also sees every file made.
 * `maxSilence`: the project's silence limit in percent; more silence than that is said at once,
 * while both speakers are still there (UXW-12). It is a warning: QC listens and decides. */
export function Result({
  recording,
  maxSilence,
}: {
  recording: rec.Recording;
  maxSilence?: number;
}) {
  const superAdmin = Boolean(useAuth().user?.roles.includes("SUPER_ADMIN"));
  const [src, setSrc] = useState<string | null>(null);
  const file = rec.deliveryAsset(recording.assets);
  const tooSilent = file !== undefined && maxSilence !== undefined && file.silence_pct > maxSilence;
  return (
    <section className="card stack stack--tight" aria-labelledby="result-title">
      <h2 id="result-title">
        {recording.state === "READY" ? "Recording saved" : "Processing failed"}
      </h2>
      {recording.state === "FAILED" ? (
        <p role="alert">
          The recording could not be prepared ({recording.failure_reason}). The uploaded audio is
          kept; ask your admin.
        </p>
      ) : null}
      <p className="muted">Recorded at {recording.native_sample_rate} Hz.</p>
      {file ? (
        <dl className="checks">
          <div className="checks__row">
            <dt>File</dt>
            <dd>Recording, {rec.formatLabel(file)}</dd>
          </div>
          <div className="checks__row">
            <dt>Length</dt>
            <dd>{clock(file.duration_ms / 1000)}</dd>
          </div>
          <div className="checks__row">
            <dt>Silence</dt>
            <dd>{file.silence_pct.toFixed(1)}%</dd>
          </div>
        </dl>
      ) : null}
      {file && tooSilent ? (
        <p className="notice notice--warning" role="status">
          {file.silence_pct.toFixed(1)}% of this recording is silence; this project allows at most{" "}
          {maxSilence}%. Listen to it, and record again while both speakers are here if it is not
          good.
        </p>
      ) : null}
      {file ? (
        <span>
          <Button
            variant="secondary"
            icon="play"
            onClick={() => void rec.assetUrl(file.id, "play").then((r) => setSrc(r.url))}
          >
            Listen
          </Button>
        </span>
      ) : null}
      {src ? (
        // Raw recording for review: there are no captions for it.
        // eslint-disable-next-line jsx-a11y/media-has-caption
        <audio controls src={src} aria-label="Recorded conversation" />
      ) : null}
      {superAdmin ? (
        <details className="tech-log">
          <summary>Technical details</summary>
          <p className="muted">
            The browser reported{" "}
            {recording.device_channel_count === null
              ? "no channel count"
              : plural(recording.device_channel_count, "channel")}{" "}
            for the microphone; {recording.channel_count} captured and kept; the recording file is
            made from the{" "}
            {recording.channel_handling === "mono" ? "single channel" : recording.channel_handling}.
          </p>
          <DataTable label="Files of this recording">
            <thead>
              <tr>
                <th scope="col">File</th>
                <th scope="col">Format</th>
                <th scope="col">Length</th>
                <th scope="col">Silence</th>
              </tr>
            </thead>
            <tbody>
              {recording.assets.map((a) => (
                <tr key={a.id}>
                  <td>{a.kind === "BROWSER_ORIGINAL" ? "Original capture" : "Recording"}</td>
                  <td>
                    {rec.formatLabel(a)}, {a.bit_depth}-bit ({a.codec})
                  </td>
                  <td>{clock(a.duration_ms / 1000)}</td>
                  <td>{a.silence_pct.toFixed(1)}%</td>
                </tr>
              ))}
            </tbody>
          </DataTable>
        </details>
      ) : null}
    </section>
  );
}

export function RecorderPage() {
  const { taskId = "" } = useParams();
  const task = useResource(() => getTask(taskId), [taskId]);
  const projectId = task.state.status === "loaded" ? task.state.data.project_id : "";
  const project = useResource(
    () => (projectId ? getProject(projectId) : Promise.resolve(null)),
    [projectId],
  );
  const existing = useResource(() => rec.listRecordings(taskId), [taskId]);
  const loaded = task.state.status === "loaded" ? task.state.data : null;
  usePageTitle(loaded ? `Record ${loaded.task_code}` : null);

  const [phase, setPhase] = useState<Phase>("idle");
  const [error, setError] = useState<string | null>(null);
  // What stopped the recording on this page just now (the microphone): said with its saved audio.
  const [stopped, setStopped] = useState<string | null>(null);
  const [rateRefused, setRateRefused] = useState(false);
  // `busy`: Start recording is on its way; a second click or a sound check waits for it (FEW-08).
  const { busy, error: apiError, run } = useAction();
  const [devices, setDevices] = useState<MediaDeviceInfo[]>([]);
  const [deviceId, setDeviceId] = useState("");
  const [level, setLevel] = useState(0);
  const [elapsed, setElapsed] = useState(0);
  const [progress, setProgress] = useState({ sent: 0, waiting: 0 });
  const [problem, setProblem] = useState<string | null>(null);
  const [result, setResult] = useState<rec.Recording | null>(null);

  const stream = useRef<MediaStream | null>(null);
  const ctx = useRef<AudioContext | null>(null);
  const uploader = useRef<ChunkUploader | null>(null);
  const recordingId = useRef<string | null>(null);
  const testBuffer = useRef<Float32Array[]>([]);
  const phaseRef = useRef<Phase>("idle");
  // Channels the capture really delivers; unknown until the first block of audio arrives, and
  // recording cannot start before then (the server and the stored file both depend on it).
  const channels = useRef<number | null>(null);

  const setPhaseBoth = (p: Phase) => {
    phaseRef.current = p;
    setPhase(p);
  };

  const teardown = useCallback(() => {
    stream.current?.getTracks().forEach((t) => t.stop());
    void ctx.current?.close();
    stream.current = null;
    ctx.current = null;
  }, []);

  useEffect(() => teardown, [teardown]);

  useEffect(() => {
    const warn = (event: BeforeUnloadEvent) => {
      if (phaseRef.current === "recording" || phaseRef.current === "finishing")
        event.preventDefault();
    };
    window.addEventListener("beforeunload", warn);
    return () => window.removeEventListener("beforeunload", warn);
  }, []);

  useEffect(() => {
    if (phase !== "recording") return;
    const started = Date.now();
    const id = window.setInterval(() => setElapsed((Date.now() - started) / 1000), 250);
    return () => window.clearInterval(id);
  }, [phase]);

  const rules =
    project.state.status === "loaded"
      ? project.state.data?.audio_rules.find((r) => r.mode === "FACE_TO_FACE")
      : undefined;
  const rate = rules?.sample_rate ?? DEFAULT_RATE;
  const maxSilence = Number(rules?.max_silence_pct ?? 25);

  /** The capture ended by itself during a recording (FEW-01): what reached the server is kept,
   * the microphone is let go, and the page offers to keep or discard the saved audio, saying
   * what happened (`cause`). */
  const interrupt = (cause: string, reason: string) => {
    const id = recordingId.current;
    uploader.current = null; // parts still on their way are refused once it is interrupted
    setProblem(null);
    setError(null);
    setStopped(cause);
    teardown();
    setPhaseBoth("idle");
    if (id)
      void rec
        .markInterrupted(id, reason)
        .catch(() => undefined) // still open: the same card offers to keep it
        .finally(() => existing.reload());
  };

  /** The recording is complete on the server: wait for its files, then show them with Send to QC
   * and Record again (FEW-02), after Stop and save and after keeping an interrupted one. */
  const finishSaving = async (id: string) => {
    setError(null);
    setStopped(null);
    setProblem(null);
    setPhaseBoth("processing");
    teardown();
    for (;;) {
      const current = await rec.getRecording(id);
      if (current.state === "READY" || current.state === "FAILED") {
        setResult(current);
        break;
      }
      await new Promise((resolve) => setTimeout(resolve, 2000));
    }
    setPhaseBoth("done");
    // The task moved to Recorded meanwhile; the page shows it as it is now.
    void getTask(taskId)
      .then(task.replace)
      .catch(() => undefined);
  };

  /** Back to the start after a step that failed: the recording may still be open on the server,
   * and its card then offers to keep or discard it (FEW-01). */
  const backToStart = () => {
    teardown();
    setPhaseBoth("idle");
    existing.reload();
  };

  const keepSaved = async (id: string) => {
    if (!(await run(() => finishSaving(id)))) backToStart();
  };

  /** A new recording of the same task, from the start of the page. */
  const startOver = () => {
    setResult(null);
    setPhaseBoth("idle");
    task.reload();
    existing.reload();
  };

  const openMicrophone = async (id: string) => {
    setError(null);
    setStopped(null);
    teardown();
    channels.current = null;
    setPhaseBoth("opening");
    let media: MediaStream;
    try {
      media = await navigator.mediaDevices.getUserMedia({
        audio: { ...CONSTRAINTS, ...(id ? { deviceId: { exact: id } } : {}) },
      });
    } catch (err) {
      setError(micMessage(err));
      setPhaseBoth("idle");
      return;
    }
    stream.current = media;
    const opened = contextAt(rate, media);
    if (!opened) {
      teardown();
      setRateRefused(true);
      setPhaseBoth("idle");
      return;
    }
    const { audio, source } = opened;
    ctx.current = audio;
    try {
      const list = (await navigator.mediaDevices.enumerateDevices()).filter(
        (d) => d.kind === "audioinput",
      );
      setDevices(list);
      await audio.audioWorklet.addModule("/recorder-worklet.js");
      const node = new AudioWorkletNode(audio, "raw-capture");
      const mute = audio.createGain();
      mute.gain.value = 0;
      source.connect(node);
      node.connect(mute).connect(audio.destination);
      node.port.onmessage = (event: MessageEvent<CaptureMessage>) => {
        if ("layoutChanged" in event.data) {
          const { from, to } = event.data.layoutChanged;
          const message = `The microphone switched from ${from} to ${plural(to, "channel")}, so capture stopped.`;
          if (phaseRef.current === "recording" && recordingId.current) {
            interrupt(message, "Microphone channel layout changed");
          } else {
            setError(`${message} Choose the microphone again.`);
            teardown();
            setPhaseBoth("idle");
          }
          return;
        }
        const { samples } = event.data;
        if (channels.current === null) {
          channels.current = event.data.channels;
          if (phaseRef.current === "opening") setPhaseBoth("ready");
        }
        let sum = 0;
        for (const s of samples) sum += s * s;
        const db = 10 * Math.log10(sum / samples.length + 1e-12);
        setLevel(Math.max(0, Math.min(1, (db + 60) / 60)));
        if (phaseRef.current === "recording") uploader.current?.push(samples);
        if (phaseRef.current === "testing")
          testBuffer.current.push(firstChannel(samples, event.data.channels));
      };
      const track = media.getAudioTracks()[0];
      if (track) {
        track.onended = () => {
          if (phaseRef.current === "recording" && recordingId.current) {
            interrupt("The microphone stopped.", "Microphone stopped");
          } else if (ctx.current === audio) {
            // Unplugged before recording: nothing would arrive, so it is chosen again.
            setError("The microphone stopped. Check it, then choose it again.");
            teardown();
            setPhaseBoth("idle");
          }
        };
      }
      window.setTimeout(() => {
        if (ctx.current === audio && channels.current === null) {
          setError("No audio is arriving from the microphone. Check it, then choose it again.");
          teardown();
          setPhaseBoth("idle");
        }
      }, NO_AUDIO_SECONDS * 1000);
    } catch (err) {
      setError(micMessage(err));
      teardown();
      setPhaseBoth("idle");
    }
  };

  const runTest = async () => {
    if (!ctx.current) return;
    testBuffer.current = [];
    setPhaseBoth("testing");
    await new Promise((resolve) => setTimeout(resolve, TEST_SECONDS * 1000));
    setPhaseBoth("ready");
    const audio = ctx.current;
    const parts = testBuffer.current;
    const length = parts.reduce((n, p) => n + p.length, 0);
    const buffer = audio.createBuffer(1, Math.max(length, 1), audio.sampleRate);
    const data = buffer.getChannelData(0);
    let offset = 0;
    for (const p of parts) {
      data.set(p, offset);
      offset += p.length;
    }
    const player = audio.createBufferSource();
    player.buffer = buffer;
    player.connect(audio.destination);
    player.start();
  };

  const start = async () => {
    const audio = ctx.current;
    const track = stream.current?.getAudioTracks()[0];
    const captured = channels.current;
    if (!audio || !track || captured === null) return;
    const settings = track.getSettings();
    await run(async () => {
      const created = await rec.startRecording(taskId, {
        // The context's own rate: the project's rate, checked when the microphone was opened.
        native_sample_rate: audio.sampleRate,
        channel_count: captured,
        device_channel_count: settings.channelCount ?? null,
        echo_cancellation:
          typeof settings.echoCancellation === "boolean" ? settings.echoCancellation : null,
        noise_suppression:
          typeof settings.noiseSuppression === "boolean" ? settings.noiseSuppression : null,
        auto_gain_control:
          typeof settings.autoGainControl === "boolean" ? settings.autoGainControl : null,
        device_label: track.label,
        user_agent: navigator.userAgent,
      });
      recordingId.current = created.id;
      // Its answers count only while it is this page's uploader (not after an interruption).
      const up: ChunkUploader = new ChunkUploader(
        (seq, body, sha) => rec.putChunk(created.id, seq, body, sha),
        // Whole frames per chunk: every chunk holds the same seconds of every channel.
        Math.min(
          Math.round(audio.sampleRate * CHUNK_SECONDS),
          Math.floor(MAX_CHUNK_BYTES / (4 * captured)),
        ) * captured,
        {
          onProgress: (sent, waiting) => {
            if (uploader.current === up) setProgress({ sent, waiting });
          },
          onProblem: (message) => {
            if (uploader.current === up) setProblem(message);
          },
        },
      );
      uploader.current = up;
      setProgress({ sent: 0, waiting: 0 });
      setElapsed(0);
      setPhaseBoth("recording");
    });
  };

  const stop = async () => {
    const id = recordingId.current;
    const up = uploader.current;
    if (!id || !up) return;
    setPhaseBoth("finishing");
    const saved = await run(async () => {
      const count = await up.finish();
      await rec.completeRecording(id, count);
      await finishSaving(id);
    });
    if (!saved) {
      setStopped("The recording could not be saved.");
      backToStart();
    }
  };

  if (
    task.state.status === "loading" ||
    existing.state.status === "loading" ||
    project.state.status === "loading"
  )
    return <LoadingState label="Loading task" />;
  if (task.state.status === "failed")
    return (
      <Frame back="/tasks" backLabel="All tasks" title="Record task">
        <ErrorState error={task.state.error} onRetry={task.reload} />
      </Frame>
    );
  const t = task.state.data;
  const title = `Record task ${t.task_code}`;
  if (project.state.status === "failed")
    return (
      <Frame back={`/tasks/${t.id}`} backLabel="Back to the task" title={title}>
        <ErrorState error={project.state.error} onRetry={project.reload} />
      </Frame>
    );
  if (t.recording_mode !== "FACE_TO_FACE" || !t.is_moderator) {
    return (
      <Frame back={`/tasks/${t.id}`} backLabel="Back to the task" title={title}>
        <EmptyState
          title="Not available"
          message={
            t.recording_mode === "TELEPHONY"
              ? "Phone tasks are recorded from the task page."
              : "Only the assigned moderator records face-to-face tasks."
          }
          action={
            <Link className="button button--secondary" to={`/tasks/${t.id}`}>
              <Icon name="previous" size={16} />
              Open the task page
            </Link>
          }
        />
      </Frame>
    );
  }
  const open =
    existing.state.status === "loaded"
      ? existing.state.data.find((r) => r.state === "RECORDING" || r.state === "INTERRUPTED")
      : undefined;
  // D-119: no recording until both participants have consent.
  const waitingConsent = t.consent_missing;
  const canRecord =
    supported() &&
    !rateRefused &&
    !open &&
    t.status === "IN_PROGRESS" &&
    waitingConsent.length === 0;
  // A recording that could not be prepared stopped at Save: it is not shown as done.
  const step = phase === "done" && result?.state === "FAILED" ? STEP_OF.processing : STEP_OF[phase];

  return (
    <Frame back={`/tasks/${t.id}`} backLabel="Back to the task" title={title}>
      <div className="card">
        <Stepper
          steps={STEPS}
          current={step}
          label={`Recording step: ${STEPS[Math.min(step, STEPS.length - 1)]}`}
        />
      </div>
      {!supported() ? (
        <ErrorState
          title="This browser cannot record here"
          message="Use a current version of Chrome or Edge on a computer."
        />
      ) : null}
      {rateRefused ? (
        <ErrorState
          title={`This browser cannot record at ${rate} Hz`}
          message="Use the latest Chrome or Edge."
        />
      ) : null}
      {/* The project's reminders for face-to-face (D-147), with its silence limit. */}
      <Reminders task={t} extra={`At most ${maxSilence}% of the recording may be silence.`} />
      {/* Whatever stopped it (this page or an earlier one), an unfinished recording is kept or
          discarded here (FEW-01); once kept it is prepared and shown below (FEW-02). */}
      {open && phase === "idle" ? (
        <Recovery
          open={open}
          cause={stopped}
          onKept={(id) => void keepSaved(id)}
          onDiscarded={() => {
            setStopped(null);
            existing.reload();
          }}
        />
      ) : stopped && phase === "idle" ? (
        <p className="notice notice--error" role="alert">
          {stopped} The audio saved so far is kept.
        </p>
      ) : null}
      {t.status !== "IN_PROGRESS" && phase !== "processing" && phase !== "done" ? (
        <p className="notice">
          The task must be in progress to record. Now it is:{" "}
          {labelFor(TASK_STATUS_LABELS, t.status)}.
        </p>
      ) : null}
      {t.status === "IN_PROGRESS" && waitingConsent.length > 0 ? (
        <p className="notice notice--error" role="alert">
          Participant {waitingConsent.join(" and ")} has not agreed on the consent form yet.
          Recording starts once both have agreed (see the{" "}
          <Link to={`/tasks/${t.id}`}>task page</Link>).
        </p>
      ) : null}
      {canRecord &&
      (phase === "idle" || phase === "opening" || phase === "ready" || phase === "testing") ? (
        <div className="card stack">
          {phase === "idle" ? (
            <span>
              <Button icon="mic" onClick={() => void openMicrophone(deviceId)}>
                Allow microphone
              </Button>
            </span>
          ) : null}
          {devices.length > 0 ? (
            <Select
              label="Microphone"
              value={deviceId}
              onChange={(e) => {
                setDeviceId(e.target.value);
                void openMicrophone(e.target.value);
              }}
              options={[
                { value: "", label: "Default microphone" },
                ...devices.map((d, i) => ({
                  value: d.deviceId,
                  label: d.label || `Microphone ${i + 1}`,
                })),
              ]}
            />
          ) : null}
          {phase === "opening" ? <p role="status">Opening the microphone…</p> : null}
          {phase !== "idle" ? (
            <div className="field">
              <label htmlFor="level" className="field__label">
                Input level
              </label>
              <meter id="level" min={0} max={1} low={0.2} high={0.9} optimum={0.6} value={level} />
            </div>
          ) : null}
          {phase === "ready" ? (
            <div className="actions">
              <Button
                variant="secondary"
                icon="waveform"
                disabled={busy !== null}
                onClick={() => void runTest()}
              >
                Test ({TEST_SECONDS} s, then play back)
              </Button>
              <Button icon="record" busy={busy !== null} onClick={() => void start()}>
                Start recording
              </Button>
            </div>
          ) : null}
          {phase === "testing" ? <p role="status">Test recording… speak now.</p> : null}
        </div>
      ) : null}
      {phase === "recording" || phase === "finishing" ? (
        <div className="card stack recorder-live">
          <p className="status" role="status" aria-live="off">
            <span className="rec-dot" aria-hidden="true" />
            {phase === "recording" ? "Recording" : "Finishing upload"} {clock(elapsed)}
          </p>
          <meter aria-label="Input level" min={0} max={1} value={level} />
          <p>
            Saved parts: {progress.sent}; waiting to upload: {progress.waiting}. Keep this tab open
            and the computer awake.
          </p>
          {phase === "recording" ? (
            <span>
              <Button icon="stop" onClick={() => void stop()}>
                Stop and save
              </Button>
            </span>
          ) : null}
        </div>
      ) : null}
      {phase === "processing" ? <LoadingState label="Preparing the recording" /> : null}
      {result ? <Result recording={result} maxSilence={maxSilence} /> : null}
      {problem ? (
        <p className="notice notice--error" role="alert">
          {problem}
        </p>
      ) : null}
      {error ? (
        <p className="notice notice--error" role="alert">
          {error}
        </p>
      ) : null}
      <ErrorNotice error={apiError} />
      {phase === "done" && result?.state === "READY" ? (
        <>
          <SuccessNotice message="The task is now marked as recorded." />
          {/* D-147: filled here, near Send to QC; the task is loaded again quietly once saved. */}
          <DeviceDetailsCard task={t} onSaved={() => void getTask(taskId).then(task.replace)} />
          <AfterRecording taskId={t.id} waits={devicesWait(t)} onAgain={startOver} />
        </>
      ) : null}
      {phase === "done" && result?.state === "FAILED" ? (
        // Not a dead end: the task is still in progress, so the conversation can be recorded
        // again while both speakers are here; the failed one stays on file for the admin.
        <div className="actions">
          <Button variant="secondary" icon="record" onClick={startOver}>
            Record again
          </Button>
        </div>
      ) : null}
    </Frame>
  );
}

/** The page's frame: the way back and the title stay whatever the page shows below, also when
 * the task cannot be loaded (POL-13). */
function Frame({
  back,
  backLabel,
  title,
  children,
}: {
  back: string;
  backLabel: string;
  title: string;
  children: ReactNode;
}) {
  return (
    <section aria-labelledby="rec-title" className="stack">
      <BackLink to={back}>{backLabel}</BackLink>
      <h1 id="rec-title">{title}</h1>
      {children}
    </section>
  );
}
