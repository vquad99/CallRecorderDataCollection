// Face-to-face recorder (FTF-001..015). Captures raw samples with an AudioWorklet, uploads 5-second
// chunks as it goes, and never claims to keep recording after the tab is closed or the device sleeps.
import { useCallback, useEffect, useRef, useState } from "react";
import { Link, useParams } from "react-router";

import type { ApiError } from "../../api/client";
import { getProject } from "../../api/projects";
import * as rec from "../../api/recordings";
import { getTask } from "../../api/work";
import { Button } from "../../components/form/Button";
import { Select } from "../../components/form/Select";
import { ErrorNotice, SuccessNotice } from "../../components/Notice";
import { EmptyState, ErrorState, LoadingState } from "../../components/StateViews";
import { toApiError, useResource } from "../../hooks/useResource";
import { ChunkUploader } from "./uploader";
import { Icon, IconTile } from "../../components/Icon";
import { Stepper } from "../../components/Stepper";

const CHUNK_SECONDS = 5;
// Kept well under the server's MAX_CHUNK_BYTES (8 MB) even for many channels at high rates.
const MAX_CHUNK_BYTES = 4_000_000;
const TEST_SECONDS = 5;
const NO_AUDIO_SECONDS = 5;
const CONSTRAINTS = {
  echoCancellation: false,
  noiseSuppression: false,
  autoGainControl: false,
  channelCount: 1,
};

type Phase =
  "idle" | "opening" | "ready" | "testing" | "recording" | "finishing" | "processing" | "done";

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

const clock = (seconds: number) =>
  `${Math.floor(seconds / 60)}:${String(Math.floor(seconds % 60)).padStart(2, "0")}`;

function Recovery({ open, onDone }: { open: rec.Recording; onDone: () => void }) {
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<ApiError | null>(null);
  const run = (action: () => Promise<unknown>) => {
    setBusy(true);
    setError(null);
    action()
      .then(onDone)
      .catch((err: unknown) => setError(toApiError(err)))
      .finally(() => setBusy(false));
  };
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
          busy={busy}
          disabled={open.chunks_received === 0}
          onClick={() =>
            run(async () => {
              if (open.state === "RECORDING")
                await rec.markInterrupted(open.id, "Page closed or reloaded during recording");
              await rec.completeRecording(open.id, open.chunks_received);
            })
          }
        >
          Keep the saved {clock(open.saved_seconds)}
        </Button>
        <Button
          variant="secondary"
          busy={busy}
          onClick={() => run(() => rec.discardRecording(open.id, "Discarded after interruption"))}
        >
          Discard it
        </Button>
      </div>
      <ErrorNotice error={error} />
    </section>
  );
}

function Result({ recording }: { recording: rec.Recording }) {
  const [src, setSrc] = useState<string | null>(null);
  const derived = recording.assets.find((a) => a.kind === "FTF_DERIVED_PCM");
  return (
    <section className="card" aria-labelledby="result-title">
      <h2 id="result-title">
        {recording.state === "READY" ? "Recording saved" : "Processing failed"}
      </h2>
      {recording.state === "FAILED" ? (
        <p role="alert">
          The files could not be prepared ({recording.failure_reason}). The uploaded audio is kept;
          ask an administrator.
        </p>
      ) : null}
      <p>
        Channels: the browser reported {recording.device_channel_count ?? "no count"} for the
        microphone; {recording.channel_count} captured and kept in the original; delivery file made
        from the{" "}
        {recording.channel_handling === "mono" ? "single channel" : recording.channel_handling}.
      </p>
      <table className="table">
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
              <td>{a.kind === "BROWSER_ORIGINAL" ? "Original capture" : "16 kHz delivery file"}</td>
              <td>
                {a.sample_rate} Hz, {a.bit_depth}-bit,{" "}
                {a.channels === 1 ? "mono" : `${a.channels} channels`} ({a.codec})
              </td>
              <td>{clock(a.duration_ms / 1000)}</td>
              <td>{a.silence_pct.toFixed(1)}%</td>
            </tr>
          ))}
        </tbody>
      </table>
      {derived ? (
        <Button
          variant="secondary"
          onClick={() => void rec.assetUrl(derived.id, "play").then((r) => setSrc(r.url))}
        >
          Listen
        </Button>
      ) : null}
      {src ? (
        // Raw recording for review: there are no captions for it.
        // eslint-disable-next-line jsx-a11y/media-has-caption
        <audio controls src={src} aria-label="Recorded conversation" />
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
  const [apiError, setApiError] = useState<ApiError | null>(null);
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

  const openMicrophone = async (id: string) => {
    setError(null);
    teardown();
    channels.current = null;
    setPhaseBoth("opening");
    try {
      const media = await navigator.mediaDevices.getUserMedia({
        audio: { ...CONSTRAINTS, ...(id ? { deviceId: { exact: id } } : {}) },
      });
      stream.current = media;
      const list = (await navigator.mediaDevices.enumerateDevices()).filter(
        (d) => d.kind === "audioinput",
      );
      setDevices(list);
      const audio = new AudioContext();
      ctx.current = audio;
      await audio.audioWorklet.addModule("/recorder-worklet.js");
      const source = audio.createMediaStreamSource(media);
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
    setApiError(null);
    const settings = track.getSettings();
    try {
      const created = await rec.startRecording(taskId, {
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
    } catch (err) {
      setApiError(toApiError(err));
    }
  };

  const stop = async () => {
    const id = recordingId.current;
    const up = uploader.current;
    if (!id || !up) return;
    setPhaseBoth("finishing");
    try {
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
      setPhaseBoth("done");
    } catch (err) {
      setApiError(toApiError(err));
      setPhaseBoth("idle");
    }
  };

  if (task.state.status === "loading" || existing.state.status === "loading")
    return <LoadingState label="Loading task" />;
  if (task.state.status === "failed")
    return <ErrorState error={task.state.error} onRetry={task.reload} />;
  const t = task.state.data;
  if (t.recording_mode !== "FACE_TO_FACE" || !t.is_moderator) {
    return (
      <EmptyState
        title="Not available"
        message="Only the assigned moderator records face-to-face tasks."
      />
    );
  }
  const open =
    existing.state.status === "loaded"
      ? existing.state.data.find((r) => r.state === "RECORDING" || r.state === "INTERRUPTED")
      : undefined;
  const rules =
    project.state.status === "loaded"
      ? project.state.data?.audio_rules.find((r) => r.mode === "FACE_TO_FACE")
      : undefined;

  return (
    <section aria-labelledby="rec-title" className="stack">
      <h1 id="rec-title">
        <IconTile name="mic" tone="rose" />
        Record task {t.task_code}
      </h1>
      <div className="card">
        <Stepper
          steps={["Mic access", "Sound check", "Capture", "Upload", "Files ready"]}
          current={
            {
              idle: 0,
              opening: 0,
              ready: 1,
              testing: 1,
              recording: 2,
              finishing: 3,
              processing: 3,
              done: 5,
            }[phase] ?? 0
          }
          label={`Recording steps: ${phase}`}
        />
      </div>
      <p>
        <Link to={`/tasks/${t.id}`}>Back to the task</Link>
      </p>
      {!supported() ? (
        <ErrorState
          title="This browser cannot record here"
          message="Use a current version of Chrome or Edge on a computer."
        />
      ) : null}
      {rules ? (
        <p className="card callout">
          <Icon name="info" size={18} />
          Project audio rules: delivered as {rules.sample_rate} Hz, {rules.bit_depth}-bit,{" "}
          {rules.channels === 1 ? "mono" : "stereo"}; at most {rules.max_silence_pct}% silence.
          Place the microphone between the two speakers, no more than 2.5 feet from each, and do not
          move it.
        </p>
      ) : null}
      {open && phase !== "recording" && phase !== "finishing" && recordingId.current !== open.id ? (
        <Recovery open={open} onDone={() => existing.reload()} />
      ) : null}
      {t.status !== "IN_PROGRESS" && phase !== "processing" && phase !== "done" ? (
        <p className="notice">
          The task must be in progress to record. Current status:{" "}
          {t.status.toLowerCase().replace(/_/g, " ")}.
        </p>
      ) : null}
      {supported() &&
      !open &&
      t.status === "IN_PROGRESS" &&
      (phase === "idle" || phase === "opening" || phase === "ready" || phase === "testing") ? (
        <div className="card stack">
          {phase === "idle" ? (
            <Button onClick={() => void openMicrophone(deviceId)}>
              <Icon name="mic" size={16} weight="fill" />
              Allow microphone
            </Button>
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
              <Button variant="secondary" onClick={() => void runTest()}>
                Test ({TEST_SECONDS} s, then play back)
              </Button>
              <Button onClick={() => void start()}>
                <Icon name="record" size={16} weight="fill" />
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
            <Button onClick={() => void stop()}>
              <Icon name="stop" size={16} weight="fill" />
              Stop and save
            </Button>
          ) : null}
        </div>
      ) : null}
      {phase === "processing" ? <LoadingState label="Preparing the files" /> : null}
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
        <SuccessNotice message="The task is now marked as recorded." />
      ) : null}
    </section>
  );
}
