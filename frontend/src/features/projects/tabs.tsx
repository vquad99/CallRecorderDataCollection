// Project detail tabs. Forms appear only for roles that may change the project; the server
// enforces the same rules (PROJ-002..011, USER-003).
import { useState, type FormEvent } from "react";

import { apiBase, type ApiError } from "../../api/client";
import { ROLE_LABELS } from "../../api/admin";
import * as api from "../../api/projects";
import { useAuth } from "../../auth/AuthContext";
import { Button } from "../../components/form/Button";
import { Select } from "../../components/form/Select";
import { TextField } from "../../components/form/TextField";
import { ErrorNotice, SuccessNotice } from "../../components/Notice";
import { EmptyState, ErrorState, LoadingState } from "../../components/StateViews";
import { toApiError, useResource } from "../../hooks/useResource";
import { LANGUAGES, languageLabel } from "./choices";
import { useProject } from "./ProjectDetailPage";
import { ProjectForm } from "./ProjectForm";
import { STATUS_LABELS } from "./ProjectsPage";

function useAction() {
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<ApiError | null>(null);
  const [message, setMessage] = useState<string | null>(null);
  /** Runs an action; resolves true when it worked, false when its error is now shown. */
  async function run(action: () => Promise<unknown>): Promise<boolean> {
    setBusy(true);
    setError(null);
    setMessage(null);
    try {
      const text = await action();
      if (typeof text === "string") setMessage(text);
      return true;
    } catch (err) {
      setError(toApiError(err));
      return false;
    } finally {
      setBusy(false);
    }
  }
  return { busy, error, message, run };
}

export function OverviewTab() {
  const { project, replace } = useProject();
  const { can } = useAuth();
  const canManage = can("projects.manage");
  const { busy, error, message, run } = useAction();
  const next = api.NEXT_STATUSES[project.status];
  const [target, setTarget] = useState<api.ProjectStatus>(next[0] ?? project.status);
  const [reason, setReason] = useState("");

  return (
    <div className="stack">
      <p>
        {project.accepts_new_work
          ? "This project accepts new work."
          : "This project does not accept new work until it is active."}
        {project.status_reason ? ` Last status reason: ${project.status_reason}` : ""}
      </p>
      <ProjectForm
        key={project.status}
        initial={{
          name: project.name,
          description: project.description,
          allows_telephony: project.allows_telephony,
          allows_face_to_face: project.allows_face_to_face,
          target_telephony_hours_per_day: project.target_telephony_hours_per_day,
          target_face_to_face_hours_per_day: project.target_face_to_face_hours_per_day,
          phone_visibility_policy: project.phone_visibility_policy,
          consent_policy_version: project.consent_policy_version,
          consent_text: project.consent_text,
        }}
        submitLabel="Save project"
        busy={busy}
        disabled={!canManage || project.status === "ARCHIVED"}
        onSubmit={(fields) =>
          void run(async () => {
            replace(await api.updateProject(project.id, fields));
            return "Saved.";
          })
        }
      />
      {canManage ? (
        <form
          className="card"
          onSubmit={(e: FormEvent) => {
            e.preventDefault();
            void run(async () => {
              replace(await api.changeProjectStatus(project.id, target, reason));
              setReason("");
              return "Status changed.";
            });
          }}
        >
          <h2>Status</h2>
          <Select
            label="Change status to"
            value={target}
            onChange={(e) => setTarget(e.target.value as api.ProjectStatus)}
            options={next.map((s) => ({ value: s, label: STATUS_LABELS[s] ?? s }))}
          />
          <TextField
            label="Reason"
            hint="Required when archiving or reopening."
            value={reason}
            onChange={(e) => setReason(e.target.value)}
          />
          <Button type="submit" busy={busy}>
            Change status
          </Button>
        </form>
      ) : null}
      <ErrorNotice error={error} />
      <SuccessNotice message={message} />
    </div>
  );
}

export function TeamTab() {
  const { project } = useProject();
  const { can } = useAuth();
  const canEdit = can("projects.members");
  const members = useResource(() => api.listMembers(project.id), [project.id]);
  const [search, setSearch] = useState("");
  const [candidates, setCandidates] = useState<api.Candidate[] | null>(null);
  const { busy, error, message, run } = useAction();

  return (
    <div className="stack">
      {members.state.status === "loading" ? <LoadingState /> : null}
      {members.state.status === "failed" ? (
        <ErrorState error={members.state.error} onRetry={members.reload} />
      ) : null}
      {members.state.status === "loaded" && members.state.data.length === 0 ? (
        <EmptyState title="No members yet" />
      ) : null}
      {members.state.status === "loaded" && members.state.data.length > 0 ? (
        <table className="table">
          <thead>
            <tr>
              <th scope="col">Name</th>
              <th scope="col">Roles</th>
              {canEdit ? <th scope="col">Action</th> : null}
            </tr>
          </thead>
          <tbody>
            {members.state.data.map((m) => (
              <tr key={m.user_id}>
                <td>
                  {m.display_name} {m.email ? <span className="muted">{m.email}</span> : null}
                </td>
                <td>{m.roles.map((r) => ROLE_LABELS[r] ?? r).join(", ")}</td>
                {canEdit ? (
                  <td>
                    <Button
                      variant="secondary"
                      busy={busy}
                      onClick={() =>
                        void run(async () => {
                          await api.removeMember(project.id, m.user_id);
                          members.reload();
                          return `${m.display_name} removed.`;
                        })
                      }
                    >
                      Remove
                    </Button>
                  </td>
                ) : null}
              </tr>
            ))}
          </tbody>
        </table>
      ) : null}
      {canEdit ? (
        <form
          className="card"
          onSubmit={(e) => {
            e.preventDefault();
            void run(async () => setCandidates(await api.listCandidates(project.id, search)));
          }}
        >
          <h2>Add people</h2>
          {can("users.manage") ? (
            <TextField
              label="Find by name or email"
              type="search"
              value={search}
              onChange={(e) => setSearch(e.target.value)}
            />
          ) : (
            <TextField
              label="Email address"
              hint="Type the person's full email address."
              type="email"
              value={search}
              onChange={(e) => setSearch(e.target.value)}
            />
          )}
          <Button type="submit" variant="secondary" busy={busy}>
            Search
          </Button>
          {candidates?.length === 0 ? (
            <p>No matching active users who are not already members.</p>
          ) : null}
          {candidates && candidates.length > 0 ? (
            <ul className="list">
              {candidates.map((c) => (
                <li key={c.user_id}>
                  {c.display_name} ({c.email}) -{" "}
                  {c.roles.map((r) => ROLE_LABELS[r] ?? r).join(", ")}{" "}
                  <Button
                    busy={busy}
                    onClick={() =>
                      void run(async () => {
                        await api.addMember(project.id, c.user_id);
                        setCandidates(candidates.filter((x) => x.user_id !== c.user_id));
                        members.reload();
                        return `${c.email} added.`;
                      })
                    }
                  >
                    Add
                  </Button>
                </li>
              ))}
            </ul>
          ) : null}
        </form>
      ) : null}
      <ErrorNotice error={error} />
      <SuccessNotice message={message} />
    </div>
  );
}

export function AudioRulesTab() {
  const { project, replace } = useProject();
  const { can } = useAuth();
  const canManage = can("projects.manage");
  const [rules, setRules] = useState<api.AudioRule[]>(project.audio_rules);
  const { busy, error, message, run } = useAction();
  const update = (i: number, patch: Partial<api.AudioRule>) =>
    setRules(rules.map((r, j) => (j === i ? { ...r, ...patch } : r)));

  return (
    <form
      className="stack"
      onSubmit={(e) => {
        e.preventDefault();
        void run(async () => {
          const saved = await api.setAudioRules(project.id, rules);
          replace(saved);
          setRules(saved.audio_rules);
          return "Audio rules saved.";
        });
      }}
    >
      {rules.map((r, i) => (
        <fieldset key={r.mode} className="card" disabled={!canManage}>
          <legend>{r.mode === "TELEPHONY" ? "Telephony" : "Face-to-face"}</legend>
          <TextField
            label="Sample rate (Hz)"
            type="number"
            value={String(r.sample_rate)}
            onChange={(e) => update(i, { sample_rate: Number(e.target.value) })}
          />
          <Select
            label="Bit depth"
            value={String(r.bit_depth)}
            onChange={(e) =>
              update(i, { bit_depth: Number(e.target.value) as api.AudioRule["bit_depth"] })
            }
            options={[
              { value: "16", label: "16-bit" },
              { value: "24", label: "24-bit" },
              { value: "32", label: "32-bit" },
            ]}
          />
          <Select
            label="Channels"
            value={String(r.channels)}
            onChange={(e) =>
              update(i, { channels: Number(e.target.value) as api.AudioRule["channels"] })
            }
            options={[
              { value: "1", label: "Mono (1)" },
              { value: "2", label: "Stereo (2)" },
            ]}
          />
          <TextField
            label="Maximum silence (%)"
            type="number"
            min={0}
            max={100}
            value={r.max_silence_pct}
            onChange={(e) => update(i, { max_silence_pct: e.target.value })}
          />
          <TextField
            label="Maximum clipping (%)"
            hint="Leave empty for no limit."
            type="number"
            min={0}
            max={100}
            value={r.max_clipping_pct ?? ""}
            onChange={(e) =>
              update(i, { max_clipping_pct: e.target.value === "" ? null : e.target.value })
            }
          />
          <TextField
            label="Minimum duration (seconds)"
            type="number"
            min={0}
            value={String(r.min_duration_seconds)}
            onChange={(e) => update(i, { min_duration_seconds: Number(e.target.value) })}
          />
          <TextField
            label="Maximum duration (seconds)"
            hint="Leave empty for no limit."
            type="number"
            min={1}
            value={r.max_duration_seconds === null ? "" : String(r.max_duration_seconds)}
            onChange={(e) =>
              update(i, {
                max_duration_seconds: e.target.value === "" ? null : Number(e.target.value),
              })
            }
          />
        </fieldset>
      ))}
      {canManage ? (
        <Button type="submit" busy={busy}>
          Save audio rules
        </Button>
      ) : null}
      <ErrorNotice error={error} />
      <SuccessNotice message={message} />
    </form>
  );
}

export function LanguagesTab() {
  const { project, replace } = useProject();
  const { can } = useAuth();
  const canManage = can("projects.manage");
  const [code, setCode] = useState("");
  const [dialect, setDialect] = useState("");
  const { busy, error, message, run } = useAction();
  const save = (languages: api.Language[], text: string) =>
    run(async () => {
      replace(await api.setLanguages(project.id, languages));
      return text;
    });

  return (
    <div className="stack">
      {project.languages.length === 0 ? <EmptyState title="No languages yet" /> : null}
      <ul className="list">
        {project.languages.map((l) => (
          <li key={`${l.language_code}/${l.dialect}`}>
            {languageLabel(l.language_code)}
            {l.dialect ? `, ${l.dialect}` : ""}{" "}
            {canManage ? (
              <Button
                variant="secondary"
                busy={busy}
                onClick={() =>
                  void save(
                    project.languages.filter((x) => x !== l),
                    "Language removed.",
                  )
                }
              >
                Remove
              </Button>
            ) : null}
          </li>
        ))}
      </ul>
      {canManage ? (
        <form
          className="card"
          onSubmit={(e) => {
            e.preventDefault();
            void save(
              [...project.languages, { language_code: code.trim(), dialect: dialect.trim() }],
              "Language added.",
            ).then((saved) => {
              // Keep what was typed when saving failed, so it can be corrected and sent again.
              if (saved) {
                setCode("");
                setDialect("");
              }
            });
          }}
        >
          <Select
            label="Language code"
            required
            value={code}
            onChange={(e) => setCode(e.target.value)}
            options={[
              { value: "", label: "Choose a language" },
              ...LANGUAGES.map((l) => ({ value: l.code, label: languageLabel(l.code) })),
            ]}
          />
          <TextField
            label="Dialect"
            hint="Optional."
            value={dialect}
            onChange={(e) => setDialect(e.target.value)}
          />
          <Button type="submit" busy={busy} disabled={!code.trim()}>
            Add language
          </Button>
        </form>
      ) : null}
      <ErrorNotice error={error} />
      <SuccessNotice message={message} />
    </div>
  );
}

const KIND_LABELS: Record<string, string> = {
  PROVIDER_ORIGINAL_TRACK: "Provider original tracks",
  PROVIDER_ORIGINAL_MIXED: "Provider mixed recordings",
  TELEPHONY_FINAL_STEREO: "Final telephony WAV",
  CONSENT_RECORDING: "Consent recordings",
  BROWSER_ORIGINAL: "Browser original captures",
  FTF_DERIVED_PCM: "Face-to-face 16 kHz WAV",
  TELEPHONY_DERIVED_PCM: "Phone call 16 kHz WAV",
  TRANSCRIPT_FILE: "Transcript files",
  EXPORT_PACKAGE: "Export packages",
};

/** Example periods shown faded under each box (D-086); nothing is filled in for the admin. */
const KIND_EXAMPLES: Record<string, string> = {
  PROVIDER_ORIGINAL_TRACK: "Example: 30 (one month)",
  PROVIDER_ORIGINAL_MIXED: "Example: 30 (one month)",
  TELEPHONY_FINAL_STEREO: "Example: 365 (one year)",
  CONSENT_RECORDING: "Example: 1825 (five years)",
  BROWSER_ORIGINAL: "Example: 30 (one month)",
  FTF_DERIVED_PCM: "Example: 365 (one year)",
  TELEPHONY_DERIVED_PCM: "Example: 365 (one year)",
  TRANSCRIPT_FILE: "Example: 365 (one year)",
  EXPORT_PACKAGE: "Example: 90 (three months)",
};

export function RetentionTab() {
  const { project, replace } = useProject();
  const { can } = useAuth();
  const canManage = can("projects.manage");
  const initial = Object.fromEntries(
    project.retention_rules.map((r) => [r.asset_kind, String(r.retain_days)]),
  );
  const [days, setDays] = useState<Record<string, string>>(initial);
  const { busy, error, message, run } = useAction();

  return (
    <form
      className="card"
      onSubmit={(e) => {
        e.preventDefault();
        void run(async () => {
          const rules = Object.entries(days)
            .filter(([, v]) => v.trim() !== "")
            .map(([asset_kind, v]) => ({ asset_kind, retain_days: Number(v) }));
          replace(await api.setRetention(project.id, rules));
          return "Retention saved.";
        });
      }}
    >
      <fieldset disabled={!canManage} className="plain-fieldset">
        <p>Days to keep each kind of file. Leave empty when no rule is set yet.</p>
        {api.ASSET_KINDS.map((kind) => (
          <TextField
            key={kind}
            label={KIND_LABELS[kind] ?? kind}
            {...(KIND_EXAMPLES[kind] ? { example: KIND_EXAMPLES[kind] } : {})}
            type="number"
            min={1}
            value={days[kind] ?? ""}
            onChange={(e) => setDays({ ...days, [kind]: e.target.value })}
          />
        ))}
        {canManage ? (
          <Button type="submit" busy={busy}>
            Save retention
          </Button>
        ) : null}
      </fieldset>
      <ErrorNotice error={error} />
      <SuccessNotice message={message} />
    </form>
  );
}

const EXPORT_CHOICES: { value: api.ExportContent; label: string; detail: string }[] = [
  {
    value: "both",
    label: "Audio + metadata",
    detail: "Each recording's audio, its details file and its consent record, in one ZIP.",
  },
  { value: "audio", label: "Audio only", detail: "Each recording's 16 kHz WAV, in one ZIP." },
  {
    value: "metadata",
    label: "Metadata only",
    detail: "Each recording's details file (JSON) and consent record, in one ZIP.",
  },
  {
    value: "progress",
    label: "Progress report",
    detail: "One spreadsheet row per task: status, people, length, checks, approval date.",
  },
  {
    value: "participants",
    label: "Participant minutes",
    detail:
      "One row per participant: recorded, approved and payable minutes. Each approved " +
      "conversation is split equally, so 5 minutes gives each participant 2.5.",
  },
];

const megabytes = (n: number) =>
  n >= 1e9 ? `${(n / 1e9).toFixed(1)} GB` : `${Math.ceil(n / 1e6)} MB`;

/** The whole project in one download (D-094). Every ZIP also holds manifest.csv. */
export function ExportTab() {
  const { project } = useProject();
  const [content, setContent] = useState<api.ExportContent>("both");
  const [scope, setScope] = useState<api.ExportScope>("approved");
  const summary = useResource(
    () => api.exportSummary(project.id, content, scope),
    [project.id, content, scope],
  );
  const files = content !== "progress" && content !== "participants";
  const ready = summary.state.status === "loaded" ? summary.state.data : null;
  const empty = files && ready !== null && ready.recordings === 0;
  return (
    <div className="stack export">
      <fieldset className="export__choices">
        <legend className="field__label">What to export</legend>
        {EXPORT_CHOICES.map((c) => (
          <label key={c.value} className="export__choice">
            <input
              type="radio"
              name="export-content"
              value={c.value}
              checked={content === c.value}
              onChange={() => setContent(c.value)}
            />
            <strong>{c.label}</strong>
            <span className="muted">{c.detail}</span>
          </label>
        ))}
      </fieldset>
      {files ? (
        <Select
          label="Which recordings"
          value={scope}
          onChange={(e) => setScope(e.target.value as api.ExportScope)}
          options={[
            { value: "approved", label: "Approved tasks only" },
            { value: "finished", label: "Every finished recording, approved or not" },
          ]}
        />
      ) : null}
      <div className="card export__go">
        <div>
          {summary.state.status === "loading" ? (
            <LoadingState label="Loading what the export holds" />
          ) : null}
          {summary.state.status === "failed" ? (
            <ErrorState error={summary.state.error} onRetry={summary.reload} />
          ) : null}
          {ready ? (
            <p className="export__summary">
              {files ? (
                <>
                  <strong>
                    {ready.recordings} recording{ready.recordings === 1 ? "" : "s"}
                  </strong>
                  {content !== "metadata" && ready.audio_bytes > 0
                    ? ` · about ${megabytes(ready.audio_bytes)} of audio`
                    : ""}
                </>
              ) : (
                <strong>
                  {content === "participants"
                    ? `Every participant in ${project.code}`
                    : `Every task in ${project.code}`}
                </strong>
              )}
              <span className="muted mono">{ready.file_name}</span>
            </p>
          ) : null}
          {empty ? (
            <p className="muted">
              Nothing to export yet: no {scope === "approved" ? "approved " : ""}task has a finished
              recording.
            </p>
          ) : null}
        </div>
        {ready && !empty ? (
          <a
            className="button button--primary"
            href={`${apiBase()}${api.exportPath(project.id, content, scope)}`}
            download={ready.file_name}
          >
            Download
          </a>
        ) : (
          <span className="button button--primary is-disabled" aria-disabled="true">
            Download
          </span>
        )}
      </div>
    </div>
  );
}
