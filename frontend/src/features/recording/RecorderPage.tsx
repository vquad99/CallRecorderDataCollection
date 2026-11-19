// Face-to-face recorder (FTF-001..015). Captures raw samples with an AudioWorklet at the project's
// delivery rate (normally 16000 Hz, owner 2026-11-17: the file is kept as recorded, never
// converted), uploads 5-second chunks as it goes, and never claims to keep recording after the tab
// is closed or the device sleeps.
import { useCallback, useEffect, useRef, useState } from "react";
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
import { Icon, IconTile } from "../../components/Icon";
import { ErrorNotice, SuccessNotice } from "../../components/Notice";
import { EmptyState, ErrorState, LoadingState } from "../../components/StateViews";
import { Stepper } from "../../components/Stepper";
import { useAction } from "../../hooks/useAction";
import { useResource } from "../../hooks/useResource";
import { clock } from "../../lib/format";
import { labelFor, TASK_STATUS_LABELS } from "../../lib/labels";
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

function Recovery({ open, onDone }: { open: rec.Recording; onDone: () => void }) {
  const confirm = useConfirm();
  const { busy, error, run } = useAction(onDone);
  const discard = () =>
    confirm.ask({
      title: "Discard the saved audio?",
      message: `The ${clock(open.saved_seconds)} that reached the server is deleted. This cannot be undone.`,
      confirmLabel: "Discard it",
      danger: true,
      action: async () => {
        await rec.discardRecording(open.id, "Discarded after interruption");
        onDone();
      },
    });
  return (
    <section className="card" role="alert" aria-labelledby="recovery-title">
      <h2 id="recovery-title">An earlier recording did not finish</h2>
      <p>
        It stopped before it was completed (for example the tab was closed, the device slept or the
        connection was lost). {clock(open.saved_seconds)} of audio reached the server and is kept.
        Nothing after that was recorded.
      </p>
      <div className="actions">
        <Button
          icon="ok"
          busy={busy !== null}
          disabled={open.chunks_received === 0}
          onClick={() =>
            void run(async () => {
              if (open.state === "RECORDING")
                await rec.markInterrupted(open.id, "Page closed or reloaded during recording");
              await rec.completeRecording(open.id, open.chunks_received);
            })
          }
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
 * without going back to the task page. */
export function AfterRecording({ taskId, onAgain }: { taskId: string; onAgain: () => void }) {
  const navigate = useNavigate();
  const { busy, error, run } = useAction();
  return (
    <section className="card stack" aria-labelledby="after-title">
      <h2 id="after-title">Listen, then send it to QC</h2>
      <p>Listen to the recording above. If it is good, send it to QC; if not, record it again.</p>
      <div className="actions">
        <Button
          icon="send"
          busy={busy === "AUDIO_QC"}
          disabled={busy !== null}
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

/** The saved recording: one file to listen to; the Super Admin also sees every file made. */
export function Result({ recording }: { recording: rec.Recording }) {
  const superAdmin = Boolean(useAuth().user?.roles.includes("SUPER_ADMIN"));
  const [src, setSrc] = useState<string | null>(null);
  const file = rec.deliveryAsset(recording.assets);
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
            The browser reported {recording.device_channel_count ?? "no count"} channel(s) for the
            microphone; {recording.channel_count} captured and kept; the recording file is made from
            the{" "}
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

  const [phase, setPhase] = useState<Phase>("idle");
  const [error, setError] = useState<string | null>(null);
  const [rateRefused, setRateRefused] = useState(false);
  const { error: apiError, run } = useAction();
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

  const openMicrophone = async (id: string) => {
    setError(null);
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
          const message = `The microphone switched from ${from} to ${to} channel(s), so capture stopped.`;
          if (phaseRef.current === "recording" && recordingId.current) {
            setError(`${message} The audio saved so far is kept.`);
            void rec
              .markInterrupted(recordingId.current, "Microphone channel layout changed")
              .then(() => existing.reload());
          } else {
            setError(`${message} Choose the microphone again.`);
          }
          teardown();
          setPhaseBoth("idle");
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
            setError("The microphone stopped. The audio saved so far is kept.");
            void rec
              .markInterrupted(recordingId.current, "Microphone stopped")
              .then(() => existing.reload());
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
      uploader.current = new ChunkUploader(
        (seq, body, sha) => rec.putChunk(created.id, seq, body, sha),
        // Whole frames per chunk: every chunk holds the same seconds of every channel.
        Math.min(
          Math.round(audio.sampleRate * CHUNK_SECONDS),
          Math.floor(MAX_CHUNK_BYTES / (4 * captured)),
        ) * captured,
        { onProgress: (sent, waiting) => setProgress({ sent, waiting }), onProblem: setProblem },
      );
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
    });
    setPhaseBoth(saved ? "done" : "idle");
  };

  if (
    task.state.status === "loading" ||
    existing.state.status === "loading" ||
    project.state.status === "loading"
  )
    return <LoadingState label="Loading task" />;
  if (task.state.status === "failed")
    return <ErrorState error={task.state.error} onRetry={task.reload} />;
  if (project.state.status === "failed")
    return <ErrorState error={project.state.error} onRetry={project.reload} />;
  const t = task.state.data;
  const back = (
    <Link className="button button--secondary" to={`/tasks/${t.id}`}>
      <Icon name="previous" size={16} />
      Back to the task
    </Link>
  );
  if (t.recording_mode !== "FACE_TO_FACE" || !t.is_moderator) {
    return (
      <EmptyState
        title="Not available"
        message={
          t.recording_mode === "TELEPHONY"
            ? "Phone tasks are recorded from the task page."
            : "Only the assigned moderator records face-to-face tasks."
        }
        action={back}
      />
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

  return (
    <section aria-labelledby="rec-title" className="stack">
      <BackLink to={`/tasks/${t.id}`}>Back to the task</BackLink>
      <h1 id="rec-title">
        <IconTile name="mic" />
        Record task {t.task_code}
      </h1>
      <div className="card">
        <Stepper
          steps={STEPS}
          current={STEP_OF[phase]}
          label={`Recording step: ${STEPS[Math.min(STEP_OF[phase], STEPS.length - 1)]}`}
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
      <p className="card callout">
        <Icon name="info" size={18} />
        Place the microphone between the two speakers, no more than 2.5 feet from each, and do not
        move it. At most {Number(rules?.max_silence_pct ?? 25)}% of the recording may be silence.
      </p>
      {open && phase !== "recording" && phase !== "finishing" && recordingId.current !== open.id ? (
        <Recovery open={open} onDone={() => existing.reload()} />
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
              <Button variant="secondary" icon="waveform" onClick={() => void runTest()}>
                Test ({TEST_SECONDS} s, then play back)
              </Button>
              <Button icon="record" onClick={() => void start()}>
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
      {result ? <Result recording={result} /> : null}
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
          <AfterRecording
            taskId={t.id}
            onAgain={() => {
              setResult(null);
              setPhaseBoth("idle");
              task.reload();
              existing.reload();
            }}
          />
        </>
      ) : null}
    </section>
  );
}
