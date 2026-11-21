// Project detail tabs. Forms appear only for roles that may change the project; the server
// enforces the same rules (PROJ-002..011, USER-003).
import { useState } from "react";

import { ROLE_LABELS } from "../../api/admin";
import * as api from "../../api/projects";
import { useAuth } from "../../auth/AuthContext";
import { useConfirm } from "../../components/ConfirmDialog";
import { DataTable } from "../../components/DataTable";
import { Button } from "../../components/form/Button";
import { Select } from "../../components/form/Select";
import { TextField } from "../../components/form/TextField";
import type { IconName } from "../../components/Icon";
import { ErrorNotice, SuccessNotice } from "../../components/Notice";
import { EmptyState, ErrorState, LoadingState } from "../../components/StateViews";
import { useAction } from "../../hooks/useAction";
import { useResource } from "../../hooks/useResource";
import { labelFor, MODE_LABELS, PROJECT_STATUS_LABELS } from "../../lib/labels";
import { LANGUAGES, languageLabel } from "./choices";
import { useProject } from "./ProjectDetailPage";
import { ProjectForm } from "./ProjectForm";

/** The button for each status move, and what it does in a sentence. */
function statusMove(from: api.ProjectStatus, to: api.ProjectStatus) {
  if (to === "ACTIVE")
    return from === "DRAFT" || from === "PAUSED"
      ? { label: "Make active", what: "The project accepts new work again." }
      : { label: "Reopen", what: "The project becomes active and accepts new work." };
  if (to === "PAUSED") return { label: "Pause", what: "No new work starts until it is active." };
  if (to === "COMPLETED")
    return { label: "Mark as completed", what: "The project is finished; no new work starts." };
  return { label: "Archive", what: "The project is closed and read only." };
}
const STATUS_ICON: Record<api.ProjectStatus, IconName> = {
  DRAFT: "pencil",
  ACTIVE: "resume",
  PAUSED: "pause",
  COMPLETED: "ok",
  ARCHIVED: "archive",
};

/** One button for each status the project can move to; a confirmation, with a reason where the
 * server needs one (archiving, reopening). */
function ProjectStatus() {
  const { project, replace } = useProject();
  const [message, setMessage] = useState<string | null>(null);
  const confirm = useConfirm(setMessage);
  const move = (to: api.ProjectStatus) => {
    const { label, what } = statusMove(project.status, to);
    confirm.ask({
      title: `${label} ${project.code}?`,
      message: what,
      confirmLabel: label,
      danger: to === "ARCHIVED",
      ...(api.needsStatusReason(project.status, to) ? { askReason: "Reason" } : {}),
      action: async ({ comment }) => {
        replace(await api.changeProjectStatus(project.id, to, comment));
        return `Status changed to ${labelFor(PROJECT_STATUS_LABELS, to)}.`;
      },
    });
  };
  return (
    <section className="card stack stack--tight" aria-labelledby="status-title">
      <h2 id="status-title">Status</h2>
      <p>
        {project.accepts_new_work
          ? "This project accepts new work."
          : "This project does not accept new work until it is active."}
      </p>
      {project.status_reason ? (
        <p className="muted">Reason given last: {project.status_reason}</p>
      ) : null}
      <div className="actions">
        {api.NEXT_STATUSES[project.status].map((to) => (
          <Button
            key={to}
            variant={to === "ACTIVE" ? "primary" : "secondary"}
            icon={STATUS_ICON[to]}
            onClick={() => move(to)}
          >
            {statusMove(project.status, to).label}
          </Button>
        ))}
      </div>
      <SuccessNotice message={message} />
      {confirm.dialog}
    </section>
  );
}

export function OverviewTab() {
  const { project, replace } = useProject();
  const { can } = useAuth();
  const canManage = can("projects.manage");
  const { busy, error, message, run } = useAction();
  return (
    <div className="stack">
      {canManage ? (
        <ProjectStatus />
      ) : (
        <p>
          {project.accepts_new_work
            ? "This project accepts new work."
            : "This project does not accept new work until it is active."}
        </p>
      )}
      <ProjectForm
        key={project.status}
        initial={api.projectSettings(project)}
        submitLabel="Save project"
        busy={busy !== null}
        disabled={!canManage || project.status === "ARCHIVED"}
        onSubmit={(fields) =>
          void run(async () => {
            // The rules are kept as they are: they are changed on the Rules tab (D-145).
            replace(
              await api.updateProject(project.id, { ...api.projectRules(project), ...fields }),
            );
            return "Saved.";
          })
        }
      />
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
  const { busy, error, message, run, setMessage } = useAction();
  const confirm = useConfirm(setMessage);
  const remove = (m: api.Member) =>
    confirm.ask({
      title: `Remove ${m.display_name} from ${project.code}?`,
      message: "They no longer see this project or its tasks. Their account stays.",
      confirmLabel: "Remove",
      danger: true,
      action: async () => {
        await api.removeMember(project.id, m.user_id);
        members.reload();
        return `${m.display_name} removed.`;
      },
    });

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
        <DataTable>
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
                  <td className="actions">
                    <Button
                      variant="secondary"
                      icon="userMinus"
                      disabled={busy !== null}
                      onClick={() => remove(m)}
                    >
                      Remove
                    </Button>
                  </td>
                ) : null}
              </tr>
            ))}
          </tbody>
        </DataTable>
      ) : null}
      {canEdit ? (
        <form
          className="card"
          onSubmit={(e) => {
            e.preventDefault();
            void run(
              async () => setCandidates(await api.listCandidates(project.id, search)),
              "search",
            );
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
          <Button type="submit" variant="secondary" icon="search" busy={busy === "search"}>
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
                    icon="userPlus"
                    busy={busy === `add-${c.user_id}`}
                    disabled={busy !== null}
                    onClick={() =>
                      void run(async () => {
                        await api.addMember(project.id, c.user_id);
                        setCandidates(candidates.filter((x) => x.user_id !== c.user_id));
                        members.reload();
                        return `${c.email} added.`;
                      }, `add-${c.user_id}`)
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
      {confirm.dialog}
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
          <legend>{labelFor(MODE_LABELS, r.mode)}</legend>
          <div className="form-grid">
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
          </div>
        </fieldset>
      ))}
      {canManage ? (
        <Button type="submit" busy={busy !== null}>
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
  const { busy, error, message, run, setMessage } = useAction();
  const confirm = useConfirm(setMessage);
  const name = (l: api.Language) =>
    `${languageLabel(l.language_code)}${l.dialect ? `, ${l.dialect}` : ""}`;
  const remove = (l: api.Language) =>
    confirm.ask({
      title: `Remove ${name(l)}?`,
      message: "New participants and tasks can no longer use it. Existing ones keep it.",
      confirmLabel: "Remove",
      danger: true,
      action: async () => {
        replace(
          await api.setLanguages(
            project.id,
            project.languages.filter((x) => x !== l),
          ),
        );
        return "Language removed.";
      },
    });

  return (
    <div className="stack">
      {project.languages.length === 0 ? (
        <EmptyState title="No languages yet" />
      ) : (
        <ul className="card list list--rows">
          {project.languages.map((l) => (
            <li key={`${l.language_code}/${l.dialect}`}>
              {name(l)}
              {canManage ? (
                <Button
                  variant="secondary"
                  icon="trash"
                  disabled={busy !== null}
                  onClick={() => remove(l)}
                >
                  Remove
                </Button>
              ) : null}
            </li>
          ))}
        </ul>
      )}
      {canManage ? (
        <form
          className="card"
          onSubmit={(e) => {
            e.preventDefault();
            void run(async () => {
              const languages = [
                ...project.languages,
                { language_code: code.trim(), dialect: dialect.trim() },
              ];
              replace(await api.setLanguages(project.id, languages));
              // Cleared only when saved: after a failure what was typed can be corrected.
              setCode("");
              setDialect("");
              return "Language added.";
            }, "add");
          }}
        >
          <Select
            label="Language"
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
          <Button type="submit" icon="plus" busy={busy === "add"} disabled={!code.trim()}>
            Add language
          </Button>
        </form>
      ) : null}
      <ErrorNotice error={error} />
      <SuccessNotice message={message} />
      {confirm.dialog}
    </div>
  );
}

const KIND_LABELS: Record<string, string> = {
  PROVIDER_ORIGINAL_TRACK: "Phone system original tracks",
  PROVIDER_ORIGINAL_MIXED: "Phone system mixed recordings",
  TELEPHONY_FINAL_STEREO: "Final phone call WAV",
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
          <Button type="submit" busy={busy !== null}>
            Save retention
          </Button>
        ) : null}
      </fieldset>
      <ErrorNotice error={error} />
      <SuccessNotice message={message} />
    </form>
  );
}
