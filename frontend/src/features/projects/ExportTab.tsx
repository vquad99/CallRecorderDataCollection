// A project's Export tab (D-094, D-105): reports as one table (CSV or TSV), and recordings as a
// bundle that is prepared in the background, listed here with its state, and downloaded through a
// link that works for a few minutes. A bundle is laid out as the project's Rules tab says (D-149):
// the speaker-pair delivery format, with what is not on file counted, or the platform's own layout.
import { useState } from "react";
import { Link } from "react-router";

import { apiDownload } from "../../api/client";
import * as api from "../../api/projects";
import { useAuth } from "../../auth/AuthContext";
import { useConfirm } from "../../components/ConfirmDialog";
import { DataTable } from "../../components/DataTable";
import { Button } from "../../components/form/Button";
import { Select } from "../../components/form/Select";
import { TextField } from "../../components/form/TextField";
import { Icon, type IconName } from "../../components/Icon";
import { ErrorNotice, SuccessNotice } from "../../components/Notice";
import { ErrorState, LoadingState } from "../../components/StateViews";
import { StatusBadge, type Tone } from "../../components/StatusBadge";
import { useAction } from "../../hooks/useAction";
import { useDebounced } from "../../hooks/useDebounced";
import { usePolling } from "../../hooks/usePolling";
import { useResource } from "../../hooks/useResource";
import { plural, typedDay, when } from "../../lib/format";
import { labelFor, MODE_LABELS } from "../../lib/labels";
import { languageLabel } from "./choices";
import { exampleAudioName } from "./delivery";
import { useProject } from "./ProjectDetailPage";
import { onlyMode } from "./recordingType";
import "./export.css";

const REPORTS: { value: api.ReportContent; label: string; detail: string }[] = [
  {
    value: "progress",
    label: "Progress report",
    detail:
      "One row per task: status, people, length, checks, approval date, phone calls. " +
      "Times in India time (IST).",
  },
  {
    value: "participants",
    label: "Participant minutes",
    detail:
      "One row per participant: recorded, approved and payable minutes. Each approved " +
      "conversation is split equally, so 5 minutes gives each participant 2.5.",
  },
];
const CONTENTS: { value: api.BundleContent; label: string; detail: string; icon: IconName }[] = [
  {
    value: "both",
    label: "Audio + metadata",
    detail: "Each recording's audio, its details file and its consent record.",
    icon: "fileZip",
  },
  {
    value: "audio",
    label: "Audio only",
    detail: "Each recording's 16 kHz WAV.",
    icon: "fileAudio",
  },
  {
    value: "metadata",
    label: "Metadata only",
    detail: "Each recording's details file (JSON) and consent record.",
    icon: "fileText",
  },
];
/** A table file's icon: CSV and TSV are both spreadsheets. */
const TABLE_ICON: Record<api.TableFormat, IconName> = { csv: "fileCsv", tsv: "table" };
const STATE: Record<api.ExportState, [Tone, string]> = {
  QUEUED: ["neutral", "Waiting"],
  RUNNING: ["progress", "Being prepared"],
  READY: ["success", "Ready"],
  FAILED: ["danger", "Failed"],
  EXPIRED: ["neutral", "Removed"],
};
const CONTENT_WORDS: Record<string, string> = {
  both: "Audio + metadata",
  audio: "Audio only",
  metadata: "Metadata only",
};
const POLL_MS = 3000;
/** The count is asked for once the choice has stopped changing for this long: counting a large
 * project takes the server a second or more. */
const COUNT_PAUSE_MS = 400;

/** "3 items missing" in the speaker-pair delivery format (the rows of its MISSING.csv). */
const missingWords = (n: number) => `${n} ${n === 1 ? "item" : "items"} missing`;

const megabytes = (n: number) =>
  n >= 1e9
    ? `about ${(n / 1e9).toFixed(1)} GB`
    : n >= 1e6
      ? `about ${Math.ceil(n / 1e6)} MB`
      : "less than 1 MB";

/** What was chosen for an export, in words: "Audio + metadata · every finished recording · ..." */
function chosen(job: api.ExportJob): string {
  const f = job.filters;
  return [
    f.layout === "CLIENT" ? "Speaker-pair format" : null,
    CONTENT_WORDS[job.content] ?? job.content,
    job.scope === "approved" ? "approved tasks" : "every finished recording",
    f.mode ? labelFor(MODE_LABELS, f.mode) : null,
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

/** The reports, each saved as one table. Fetched like any request, so a refusal (or a session
 * that ended) is said on the page instead of a failed browser download. */
function Reports({ projectId }: { projectId: string }) {
  const { busy, error, run } = useAction();
  return (
    <section className="card stack stack--tight" aria-labelledby="export-reports">
      <h2 id="export-reports">Reports</h2>
      <ErrorNotice error={error} />
      {/* What a report holds is written under its name, so its downloads stay in view on a
          phone too. */}
      <DataTable label="Reports" className="export__reports">
        <thead>
          <tr>
            <th scope="col">Report</th>
            <th scope="col">Download</th>
          </tr>
        </thead>
        <tbody>
          {REPORTS.map((r) => (
            <tr key={r.value}>
              <th scope="row">
                {r.label}
                <span className="export__detail">{r.detail}</span>
              </th>
              <td className="actions">
                {(["csv", "tsv"] as const).map((format) => {
                  const key = `${r.value}-${format}`;
                  return (
                    <Button
                      key={format}
                      variant="secondary"
                      icon={TABLE_ICON[format]}
                      busy={busy === key}
                      disabled={busy !== null}
                      aria-label={`${r.label} as ${format.toUpperCase()}`}
                      onClick={() =>
                        void run(() => apiDownload(api.reportPath(projectId, r.value, format)), key)
                      }
                    >
                      {format.toUpperCase()}
                    </Button>
                  );
                })}
              </td>
            </tr>
          ))}
        </tbody>
      </DataTable>
    </section>
  );
}

/** Which layout a bundle of this project takes (D-149), with the way to change it. */
function LayoutNote() {
  const { project } = useProject();
  const client = project.export_layout === "CLIENT";
  const example = exampleAudioName(
    project.audio_name_pattern,
    project.speaker_id_style,
    project.conversation_id_style,
  );
  return (
    <p className="export__layout">
      <Icon name="info" size={18} />
      <span>
        {client ? (
          <>
            Laid out in the <strong>speaker-pair delivery format</strong>: face_to_face/ and
            telephonic/ audio named like <span className="mono">{example}</span>, a metadata file
            per speaker and per speaker of each conversation, consent forms and address proofs under
            speakers/, and MISSING.csv listing what is not on file.
          </>
        ) : (
          <>
            Laid out in the <strong>platform&apos;s own layout</strong>: a folder for face-to-face
            recordings and one for phone calls, with each recording&apos;s details file and consent
            record.
          </>
        )}{" "}
        <Link to={`/projects/${project.id}/rules/export`}>Change it under Rules</Link>.
      </span>
    </p>
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

/** What an export's count depends on: the values the summary sends. The tables' format and the
 * contact details change the files, not which recordings go in. */
type Counted = Omit<api.ExportChoice, "table_format" | "contact">;

const counted = (c: api.ExportChoice): Counted => ({
  content: c.content,
  scope: c.scope,
  mode: c.mode,
  language: c.language,
  recorded_from: c.recorded_from,
  recorded_to: c.recorded_to,
  originals: c.originals,
});

const backwardsDays = (c: Pick<api.ExportChoice, "recorded_from" | "recorded_to">) =>
  c.recorded_from !== null && c.recorded_to !== null && c.recorded_from > c.recorded_to;

function BundleForm({ onAsked }: { onAsked: (job: api.ExportJob) => void }) {
  const { project } = useProject();
  const { can } = useAuth();
  const [choice, setChoice] = useState<api.ExportChoice>(START);
  const { busy, error, run } = useAction();
  const set = (patch: Partial<api.ExportChoice>) => setChoice((c) => ({ ...c, ...patch }));
  // A project of one recording type (D-153) has nothing to choose between.
  const bothTypes = onlyMode(project) === null;
  // The days as asked: a year still being typed (0002, 0020, 0202) is no day yet.
  const asked: api.ExportChoice = {
    ...choice,
    recorded_from: typedDay(choice.recorded_from) || null,
    recorded_to: typedDay(choice.recorded_to) || null,
    // Originals go with the audio; a details-only export cannot carry them.
    originals: choice.originals && choice.content !== "metadata",
  };
  const typing = [choice.recorded_from, choice.recorded_to].some(
    (d) => d !== null && typedDay(d) === "",
  );
  const backwards = backwardsDays(asked);
  const key = JSON.stringify(counted(asked));
  const settled = useDebounced(key, COUNT_PAUSE_MS);
  const summary = useResource(() => {
    const c = JSON.parse(settled) as Counted;
    return backwardsDays(c)
      ? Promise.resolve(null)
      : api.exportSummary(project.id, { ...START, ...c });
  }, [project.id, settled]);
  // The count shown is always for the choice on screen: while it is asked again, it waits.
  const counting = !backwards && (settled !== key || summary.state.status === "loading");
  const ready = !counting && summary.state.status === "loaded" ? summary.state.data : null;
  const empty = ready !== null && ready.recordings === 0;
  // "2 face-to-face, 1 phone call · about 240 MB of audio"; no split by type in a project of one.
  const detail = ready
    ? [
        bothTypes
          ? `${ready.face_to_face} face-to-face, ${plural(ready.telephony, "phone call")}`
          : null,
        asked.content !== "metadata" && ready.audio_bytes > 0
          ? `${megabytes(ready.audio_bytes)} of audio`
          : null,
      ]
        .filter(Boolean)
        .join(" · ")
    : "";
  const languages = [...new Set(project.languages.map((l) => l.language_code))];

  const prepare = () => void run(async () => onAsked(await api.requestExport(project.id, asked)));

  return (
    <section className="card stack" aria-labelledby="export-bundle">
      <h2 id="export-bundle">Recordings</h2>
      <div>
        <p className="muted">
          One ZIP file: each recording&apos;s files, a table of the recordings, and a list of every
          file with its checksum.
        </p>
        <LayoutNote />
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
            <strong className="export__choice-title">
              <Icon name={c.icon} size={18} />
              {c.label}
            </strong>
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
            { value: "finished", label: "Every finished recording" },
          ]}
        />
        {bothTypes ? (
          <Select
            label="Recording type"
            value={choice.mode ?? ""}
            onChange={(e) => set({ mode: (e.target.value || null) as api.ExportChoice["mode"] })}
            options={[
              { value: "", label: "Every recording type" },
              { value: "FACE_TO_FACE", label: "Face-to-face only" },
              { value: "TELEPHONY", label: "Phone calls only" },
            ]}
          />
        ) : null}
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
          name="table_format"
          value={choice.table_format}
          onChange={(e) => set({ table_format: e.target.value as api.TableFormat })}
          options={[
            { value: "csv", label: "CSV" },
            { value: "tsv", label: "TSV" },
          ]}
        />
      </div>
      {can("projects.manage") || can("participants.export") ? (
        <div className="stack stack--tight">
          {can("projects.manage") ? (
            <label className="checkbox">
              <input
                type="checkbox"
                checked={asked.originals}
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
          {counting ? <LoadingState label="Counting the recordings" /> : null}
          {!counting && summary.state.status === "failed" ? (
            <ErrorState error={summary.state.error} onRetry={summary.reload} />
          ) : null}
          {ready ? (
            <p className="export__summary">
              <strong>{plural(ready.recordings, "recording")}</strong>
              {ready.recordings > 0 && detail ? <span>{detail}</span> : null}
              {ready.recordings > 0 && ready.layout === "CLIENT" ? (
                <span className={ready.missing > 0 ? "export__missing" : "muted"}>
                  {ready.missing > 0 ? missingWords(ready.missing) : "Nothing missing"}
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
        <Button
          icon="fileZip"
          busy={busy !== null}
          disabled={!ready || empty || backwards || typing}
          onClick={prepare}
        >
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
  const { busy, error, message, run, setMessage } = useAction(onChanged);
  const confirm = useConfirm(setMessage);
  const download = (job: api.ExportJob) =>
    void run(async () => {
      const link = await api.exportLink(projectId, job.id);
      const a = document.createElement("a");
      a.href = link.url;
      a.rel = "noopener";
      a.click();
      return `Downloading ${link.file_name}. The link works for ${Math.round(link.valid_seconds / 60)} minutes.`;
    }, job.id);
  const remove = (job: api.ExportJob) =>
    confirm.ask({
      title: `Remove ${job.file_name}?`,
      message: "The prepared file is deleted. You can prepare it again later.",
      confirmLabel: "Remove",
      danger: true,
      action: async () => {
        await api.removeExport(projectId, job.id);
        onChanged();
        return `${job.file_name} removed.`;
      },
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
        <DataTable label="Prepared exports">
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
                    <span className="export__file">
                      <Icon name="fileZip" size={18} />
                      <span className="mono">{job.file_name}</span>
                    </span>
                    <div className="muted">{chosen(job)}</div>
                    {job.state === "FAILED" && job.error ? (
                      <div className="export__error">{job.error}</div>
                    ) : null}
                  </td>
                  <td>
                    <StatusBadge status={tone} label={label} />
                  </td>
                  <td>
                    {job.recordings}
                    {job.missing > 0 ? (
                      <div className="export__missing">{missingWords(job.missing)}</div>
                    ) : null}
                  </td>
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
                        icon="download"
                        busy={busy === job.id}
                        disabled={busy !== null}
                        onClick={() => download(job)}
                        aria-label={`Download ${job.file_name}`}
                      >
                        Download
                      </Button>
                    ) : null}
                    {job.state === "READY" || job.state === "QUEUED" ? (
                      <Button
                        variant="secondary"
                        icon="trash"
                        busy={busy === job.id}
                        disabled={busy !== null}
                        onClick={() => remove(job)}
                        aria-label={`Remove ${job.file_name}`}
                      >
                        Remove
                      </Button>
                    ) : null}
                  </td>
                </tr>
              );
            })}
          </tbody>
        </DataTable>
      )}
      {confirm.dialog}
    </section>
  );
}

/** The project's exports, looked at again every few seconds while one is being prepared. */
const preparing = (jobs: api.ExportJob[]) =>
  jobs.some((j) => j.state === "QUEUED" || j.state === "RUNNING");

export function ExportTab() {
  const { project } = useProject();
  const exports = usePolling(
    async () => (await api.listExports(project.id)).items,
    [project.id],
    POLL_MS,
    preparing,
  );
  const jobs = exports.state.status === "loaded" ? exports.state.data : null;
  return (
    <div className="stack export">
      <BundleForm
        onAsked={(job) => {
          exports.replace([job, ...(jobs ?? []).filter((j) => j.id !== job.id)]);
          void exports.refresh();
        }}
      />
      {exports.state.status === "loading" ? <LoadingState label="Loading the exports" /> : null}
      {exports.state.status === "failed" ? (
        <ErrorState error={exports.state.error} onRetry={exports.reload} />
      ) : null}
      {jobs ? (
        <ExportList projectId={project.id} jobs={jobs} onChanged={() => void exports.refresh()} />
      ) : null}
      <Reports projectId={project.id} />
    </div>
  );
}
