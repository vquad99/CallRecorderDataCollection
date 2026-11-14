// A project's Export tab (D-094, D-105): reports as one table (CSV or TSV), and recordings as a
// bundle that is prepared in the background, listed here with its state, and downloaded through a
// link that works for a few minutes.
import { useCallback, useEffect, useRef, useState } from "react";

import { apiBase, type ApiError } from "../../api/client";
import * as api from "../../api/projects";
import { useAuth } from "../../auth/AuthContext";
import { Button } from "../../components/form/Button";
import { Select } from "../../components/form/Select";
import { TextField } from "../../components/form/TextField";
import { Icon } from "../../components/Icon";
import { ErrorNotice, SuccessNotice } from "../../components/Notice";
import { ErrorState, LoadingState } from "../../components/StateViews";
import { StatusBadge } from "../../components/StatusBadge";
import { toApiError, useResource } from "../../hooks/useResource";
import { languageLabel } from "./choices";
import { useProject } from "./ProjectDetailPage";
import "./export.css";

const REPORTS: { value: api.ReportContent; label: string; detail: string }[] = [
  {
    value: "progress",
    label: "Progress report",
    detail: "One row per task: status, people, length, checks, approval date, phone calls.",
  },
  {
    value: "participants",
    label: "Participant minutes",
    detail:
      "One row per participant: recorded, approved and payable minutes. Each approved " +
      "conversation is split equally, so 5 minutes gives each participant 2.5.",
  },
];
const CONTENTS: { value: api.BundleContent; label: string; detail: string }[] = [
  {
    value: "both",
    label: "Audio + metadata",
    detail: "Each recording's audio, its details file and its consent record.",
  },
  { value: "audio", label: "Audio only", detail: "Each recording's 16 kHz WAV." },
  {
    value: "metadata",
    label: "Metadata only",
    detail: "Each recording's details file (JSON) and consent record.",
  },
];
const STATE: Record<api.ExportState, [string, string]> = {
  QUEUED: ["DRAFT", "Waiting"],
  RUNNING: ["IN_PROGRESS", "Being prepared"],
  READY: ["APPROVED", "Ready"],
  FAILED: ["REJECTED", "Failed"],
  EXPIRED: ["ARCHIVED", "Removed"],
};
const CONTENT_WORDS: Record<string, string> = {
  both: "Audio + metadata",
  audio: "Audio only",
  metadata: "Metadata only",
};
const MODE_WORDS: Record<string, string> = {
  FACE_TO_FACE: "Face-to-face",
  TELEPHONY: "Telephony",
};
const POLL_MS = 3000;

const megabytes = (n: number) =>
  n >= 1e9
    ? `about ${(n / 1e9).toFixed(1)} GB`
    : n >= 1e6
      ? `about ${Math.ceil(n / 1e6)} MB`
      : "less than 1 MB";
const when = (iso: string | null) => (iso ? new Date(iso).toLocaleString() : "-");
const plural = (n: number, word: string) => `${n} ${word}${n === 1 ? "" : "s"}`;

/** What was chosen for an export, in words: "Audio + metadata · every finished recording · ..." */
function chosen(job: api.ExportJob): string {
  const f = job.filters;
  return [
    CONTENT_WORDS[job.content] ?? job.content,
    job.scope === "approved" ? "approved tasks" : "every finished recording",
    f.mode ? MODE_WORDS[f.mode] : null,
    f.language ? languageLabel(f.language) : null,
    f.recorded_from || f.recorded_to
      ? `${f.recorded_from ?? "start"} to ${f.recorded_to ?? "today"}`
      : null,
    f.originals ? "with originals" : null,
    f.contact ? "with names and contact details" : null,
    job.table_format.toUpperCase(),
  ]
    .filter(Boolean)
    .join(" · ");
}

function Reports({ projectId }: { projectId: string }) {
  return (
    <section className="card stack stack--tight" aria-labelledby="export-reports">
      <h2 id="export-reports">Reports</h2>
      <ul className="export__reports">
        {REPORTS.map((r) => (
          <li key={r.value} className="export__report">
            <div>
              <strong>{r.label}</strong>
              <p className="muted">{r.detail}</p>
            </div>
            <div className="actions">
              {(["csv", "tsv"] as const).map((format) => (
                <a
                  key={format}
                  className="button button--secondary"
                  href={`${apiBase()}${api.reportPath(projectId, r.value, format)}`}
                  download
                  aria-label={`${r.label} as ${format.toUpperCase()}`}
                >
                  <Icon name="upload" size={15} />
                  {format.toUpperCase()}
                </a>
              ))}
            </div>
          </li>
        ))}
      </ul>
    </section>
  );
}

const START: api.ExportChoice = {
  content: "both",
  scope: "approved",
  table_format: "csv",
  mode: null,
  language: null,
  recorded_from: null,
  recorded_to: null,
  originals: false,
  contact: false,
};

function BundleForm({ onAsked }: { onAsked: (job: api.ExportJob) => void }) {
  const { project } = useProject();
  const { can } = useAuth();
  const [choice, setChoice] = useState<api.ExportChoice>(START);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<ApiError | null>(null);
  const set = (patch: Partial<api.ExportChoice>) => {
    setChoice((c) => ({ ...c, ...patch }));
    setError(null);
  };
  const backwards =
    choice.recorded_from !== null &&
    choice.recorded_to !== null &&
    choice.recorded_from > choice.recorded_to;
  // Originals go with the audio; a details-only export cannot carry them.
  const originals = choice.originals && choice.content !== "metadata";
  const asked = { ...choice, originals };
  const summary = useResource(
    () => (backwards ? Promise.resolve(null) : api.exportSummary(project.id, asked)),
    [project.id, JSON.stringify(asked), backwards],
  );
  const ready = summary.state.status === "loaded" ? summary.state.data : null;
  const empty = ready !== null && ready.recordings === 0;
  const languages = [...new Set(project.languages.map((l) => l.language_code))];

  function prepare() {
    setBusy(true);
    setError(null);
    api
      .requestExport(project.id, asked)
      .then(onAsked)
      .catch((err: unknown) => setError(toApiError(err)))
      .finally(() => setBusy(false));
  }

  return (
    <section className="card stack" aria-labelledby="export-bundle">
      <div>
        <h2 id="export-bundle">Recordings</h2>
        <p className="muted">
          One ZIP with a folder for face-to-face and one for telephony recordings, a table of the
          recordings, and a list of every file with its checksum.
        </p>
      </div>
      <fieldset className="export__choices">
        <legend className="field__label">What to export</legend>
        {CONTENTS.map((c) => (
          <label key={c.value} className="export__choice">
            <input
              type="radio"
              name="export-content"
              value={c.value}
              checked={choice.content === c.value}
              onChange={() => set({ content: c.value })}
            />
            <strong>{c.label}</strong>
            <span className="muted">{c.detail}</span>
          </label>
        ))}
      </fieldset>
      <div className="filters">
        <Select
          label="Which recordings"
          value={choice.scope}
          onChange={(e) => set({ scope: e.target.value as api.ExportScope })}
          options={[
            { value: "approved", label: "Approved tasks only" },
            { value: "finished", label: "Every finished recording, approved or not" },
          ]}
        />
        <Select
          label="Recording type"
          value={choice.mode ?? ""}
          onChange={(e) => set({ mode: (e.target.value || null) as api.ExportChoice["mode"] })}
          options={[
            { value: "", label: "Face-to-face and telephony" },
            { value: "FACE_TO_FACE", label: "Face-to-face only" },
            { value: "TELEPHONY", label: "Telephony only" },
          ]}
        />
        <Select
          label="Language"
          value={choice.language ?? ""}
          onChange={(e) => set({ language: e.target.value || null })}
          options={[
            { value: "", label: "Every language" },
            ...languages.map((code) => ({ value: code, label: languageLabel(code) })),
          ]}
        />
        <TextField
          label="Recorded from"
          type="date"
          value={choice.recorded_from ?? ""}
          onChange={(e) => set({ recorded_from: e.target.value || null })}
        />
        <TextField
          label="Recorded to"
          type="date"
          value={choice.recorded_to ?? ""}
          {...(backwards ? { error: "Must not be before the first day" } : {})}
          onChange={(e) => set({ recorded_to: e.target.value || null })}
        />
        <Select
          label="Tables as"
          value={choice.table_format}
          onChange={(e) => set({ table_format: e.target.value as api.TableFormat })}
          options={[
            { value: "csv", label: "CSV (comma separated)" },
            { value: "tsv", label: "TSV (tab separated)" },
          ]}
        />
      </div>
      {can("projects.manage") || can("participants.export") ? (
        <div className="stack stack--tight">
          {can("projects.manage") ? (
            <label className="checkbox">
              <input
                type="checkbox"
                checked={originals}
                disabled={choice.content === "metadata"}
                onChange={(e) => set({ originals: e.target.checked })}
              />
              <span>
                Also include the original recordings
                <span className="muted"> (as recorded, before any processing; much larger)</span>
              </span>
            </label>
          ) : null}
          {can("participants.export") ? (
            <label className="checkbox">
              <input
                type="checkbox"
                checked={choice.contact}
                onChange={(e) => set({ contact: e.target.checked })}
              />
              <span>
                Also include names, phone numbers and email addresses
                <span className="muted"> (personal data: only when the receiver needs it)</span>
              </span>
            </label>
          ) : null}
        </div>
      ) : null}
      <ErrorNotice error={error} />
      <div className="export__go">
        <div>
          {summary.state.status === "loading" ? (
            <LoadingState label="Counting the recordings" />
          ) : null}
          {summary.state.status === "failed" ? (
            <ErrorState error={summary.state.error} onRetry={summary.reload} />
          ) : null}
          {ready ? (
            <p className="export__summary">
              <strong>{plural(ready.recordings, "recording")}</strong>
              {ready.recordings > 0 ? (
                <span>
                  {ready.face_to_face} face-to-face, {ready.telephony} telephony
                  {choice.content !== "metadata" && ready.audio_bytes > 0
                    ? ` · ${megabytes(ready.audio_bytes)} of audio`
                    : ""}
                </span>
              ) : null}
            </p>
          ) : null}
          {empty ? (
            <p className="muted">
              Nothing to export: no {choice.scope === "approved" ? "approved " : ""}task with a
              finished recording fits this choice.
            </p>
          ) : null}
        </div>
        <Button busy={busy} disabled={!ready || empty || backwards} onClick={prepare}>
          Prepare export
        </Button>
      </div>
    </section>
  );
}

function ExportList({
  projectId,
  jobs,
  onChanged,
}: {
  projectId: string;
  jobs: api.ExportJob[];
  onChanged: () => void;
}) {
  const [busy, setBusy] = useState<string | null>(null);
  const [error, setError] = useState<ApiError | null>(null);
  const [message, setMessage] = useState<string | null>(null);

  function act(job: api.ExportJob, action: () => Promise<string>) {
    setBusy(job.id);
    setError(null);
    setMessage(null);
    action()
      .then((text) => {
        setMessage(text);
        onChanged();
      })
      .catch((err: unknown) => {
        setError(toApiError(err));
        onChanged();
      })
      .finally(() => setBusy(null));
  }
  const download = (job: api.ExportJob) =>
    act(job, async () => {
      const link = await api.exportLink(projectId, job.id);
      const a = document.createElement("a");
      a.href = link.url;
      a.rel = "noopener";
      a.click();
      return `Downloading ${link.file_name}. The link works for ${Math.round(link.valid_seconds / 60)} minutes.`;
    });
  const remove = (job: api.ExportJob) =>
    act(job, async () => {
      await api.removeExport(projectId, job.id);
      return `${job.file_name} removed.`;
    });

  return (
    <section className="card stack stack--tight" aria-labelledby="export-list">
      <h2 id="export-list">Prepared exports</h2>
      <ErrorNotice error={error} />
      <SuccessNotice message={message} />
      {jobs.length === 0 ? (
        <p className="muted">
          No export has been prepared yet. A prepared export stays here for a day, then it is
          removed.
        </p>
      ) : (
        <div className="table-wrap">
          <table className="table" aria-label="Prepared exports">
            <thead>
              <tr>
                <th scope="col">Asked</th>
                <th scope="col">What</th>
                <th scope="col">State</th>
                <th scope="col">Recordings</th>
                <th scope="col">Size</th>
                <th scope="col">Kept until</th>
                <th scope="col">Actions</th>
              </tr>
            </thead>
            <tbody>
              {jobs.map((job) => {
                const [tone, label] = STATE[job.state];
                return (
                  <tr key={job.id}>
                    <td>
                      {when(job.created_at)}
                      <div className="muted">{job.requested_by ?? "-"}</div>
                    </td>
                    <td>
                      <span className="mono">{job.file_name}</span>
                      <div className="muted">{chosen(job)}</div>
                      {job.state === "FAILED" && job.error ? (
                        <div className="export__error">{job.error}</div>
                      ) : null}
                    </td>
                    <td>
                      <StatusBadge status={tone} label={label} />
                    </td>
                    <td>{job.recordings}</td>
                    <td>{job.state === "READY" ? megabytes(job.size_bytes) : "-"}</td>
                    <td>
                      {job.state === "READY" ? when(job.expires_at) : "-"}
                      {job.downloads > 0 ? (
                        <div className="muted">Downloaded {plural(job.downloads, "time")}</div>
                      ) : null}
                    </td>
                    <td className="actions">
                      {job.state === "READY" ? (
                        <Button
                          variant="secondary"
                          busy={busy === job.id}
                          onClick={() => download(job)}
                          aria-label={`Download ${job.file_name}`}
                        >
                          <Icon name="upload" size={15} />
                          Download
                        </Button>
                      ) : null}
                      {job.state === "READY" || job.state === "QUEUED" ? (
                        <Button
                          variant="secondary"
                          busy={busy === job.id}
                          onClick={() => remove(job)}
                          aria-label={`Remove ${job.file_name}`}
                        >
                          <Icon name="trash" size={15} />
                          Remove
                        </Button>
                      ) : null}
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      )}
    </section>
  );
}

/** The project's exports, looked at again every few seconds while one is being prepared. A
 * refresh never empties the list: the newest answer replaces the one before. */
function useExports(projectId: string) {
  const [jobs, setJobs] = useState<api.ExportJob[] | null>(null);
  const [error, setError] = useState<ApiError | null>(null);
  const latest = useRef(0);
  const refresh = useCallback(() => {
    const mine = ++latest.current;
    api
      .listExports(projectId)
      .then((page) => {
        if (mine !== latest.current) return;
        setJobs(page.items);
        setError(null);
      })
      .catch((err: unknown) => {
        if (mine === latest.current) setError(toApiError(err));
      });
  }, [projectId]);
  useEffect(() => {
    refresh();
  }, [refresh]);
  const open = jobs?.some((j) => j.state === "QUEUED" || j.state === "RUNNING") ?? false;
  useEffect(() => {
    if (!open) return;
    const timer = window.setInterval(refresh, POLL_MS);
    return () => window.clearInterval(timer);
  }, [open, refresh]);
  return { jobs, error, refresh, setJobs };
}

export function ExportTab() {
  const { project } = useProject();
  const { jobs, error, refresh, setJobs } = useExports(project.id);
  return (
    <div className="stack export">
      <BundleForm
        onAsked={(job) => {
          setJobs((before) => [job, ...(before ?? []).filter((j) => j.id !== job.id)]);
          refresh();
        }}
      />
      {jobs === null && error === null ? <LoadingState label="Loading the exports" /> : null}
      {jobs === null && error !== null ? <ErrorState error={error} onRetry={refresh} /> : null}
      {jobs !== null ? <ExportList projectId={project.id} jobs={jobs} onChanged={refresh} /> : null}
      <Reports projectId={project.id} />
    </div>
  );
}
