// Project detail tabs. Forms appear only for roles that may change the project; the server
// enforces the same rules (PROJ-002..011, USER-003). An archived project is read only: its
// settings, audio rules, languages and retention wait until it is reopened (PROJ-010). Each list
// is a titled section, a settings form has its Save on its section's title bar, and a row is
// removed with the bin (D-158).
import { Fragment, useId, useState, type ReactNode } from "react";

import { ROLE_LABELS } from "../../api/admin";
import * as api from "../../api/projects";
import { useAuth } from "../../auth/AuthContext";
import { useConfirm } from "../../components/ConfirmDialog";
import { DataTable } from "../../components/DataTable";
import { Button, IconButton } from "../../components/form/Button";
import { Select } from "../../components/form/Select";
import { TextField } from "../../components/form/TextField";
import type { IconName } from "../../components/Icon";
import { ErrorNotice, SuccessNotice } from "../../components/Notice";
import { EmptyState, ErrorState, LoadingState } from "../../components/StateViews";
import { useAction } from "../../hooks/useAction";
import { useResource } from "../../hooks/useResource";
import { useUnsavedChanges } from "../../hooks/useUnsavedChanges";
import { labelFor, MODE_LABELS, PROJECT_STATUS_LABELS } from "../../lib/labels";
import { LANGUAGES, languageLabel } from "./choices";
import { useProject } from "./ProjectDetailPage";
import { ProjectForm } from "./ProjectForm";
import "./overview.css";

/** Said on a page an archived project keeps read only, to someone who could change it otherwise. */
const ARCHIVED_NOTE = "Read only. Reopen the project to change it.";
/** A person's roles in words: "Moderator, QC Executive"; "-" for none (D-158). */
const rolesOf = (roles: readonly string[]) =>
  roles.map((r) => ROLE_LABELS[r] ?? r).join(", ") || "-";

/** A person's name with their email under it, which may break after its "@" only: on a phone the
 * table then fits, its Actions in view (D-158). */
function Person({ name, email }: { name: string; email: string | null | undefined }) {
  const at = email ? email.indexOf("@") + 1 : 0;
  return (
    <>
      {name}
      {email ? (
        <div className="muted">
          {at > 0 ? (
            <>
              {email.slice(0, at)}
              <wbr />
              {email.slice(at)}
            </>
          ) : (
            email
          )}
        </div>
      ) : null}
    </>
  );
}
const accepts = (p: api.Project) =>
  p.accepts_new_work
    ? "This project accepts new work."
    : "This project does not accept new work until it is active.";

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
      <p>{accepts(project)}</p>
      {project.status_reason ? (
        <p className="muted">Reason given last: {project.status_reason}</p>
      ) : null}
      {/* Even rows of buttons on a phone, not a ragged stack (D-158). */}
      <div className="actions page-actions">
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

/** "10 h a day", or for a project made before D-153 with both types, each type's. */
function dailyTarget(p: api.Project): string {
  const days = [
    ["FACE_TO_FACE", p.allows_face_to_face, p.target_face_to_face_hours_per_day],
    ["TELEPHONY", p.allows_telephony, p.target_telephony_hours_per_day],
  ] as const;
  const set = days.filter(([, allowed, hours]) => allowed && Number(hours) > 0);
  if (set.length === 0) return "No daily target";
  // International grouping (1,000), as on Settings (D-158).
  const text = (hours: string) => `${Number(hours).toLocaleString("en-US")} h a day`;
  return set.length === 1 && set[0]
    ? text(set[0][2])
    : set.map(([mode, , hours]) => `${MODE_LABELS[mode]}: ${text(hours)}`).join(", ");
}

/** The project in a few words, for members who do not manage it (Moderator, QC Executive, Client
 * Viewer): no settings form to look at, and nothing internal (who sees phone numbers, the consent
 * policy). */
function ProjectSummary({ project }: { project: api.Project }) {
  const types = [
    project.allows_telephony ? MODE_LABELS.TELEPHONY : "",
    project.allows_face_to_face ? MODE_LABELS.FACE_TO_FACE : "",
  ].filter(Boolean);
  const rows: [string, ReactNode][] = [
    ["Name", project.name],
    [
      "Description",
      project.description.trim() ? (
        <span className="project-summary__text">{project.description}</span>
      ) : (
        <span className="muted">No description</span>
      ),
    ],
    ["Recording type", types.length > 0 ? types.join(", ") : <span className="muted">-</span>],
    ["Daily target", dailyTarget(project)],
    ["New work", accepts(project)],
  ];
  return (
    <section className="card project-summary" aria-labelledby="summary-title">
      <h2 id="summary-title">About this project</h2>
      <dl className="project-summary__list">
        {rows.map(([term, value]) => (
          <div key={term} className="project-summary__row">
            <dt>{term}</dt>
            <dd>{value}</dd>
          </div>
        ))}
      </dl>
    </section>
  );
}

export function OverviewTab() {
  const { project, replace } = useProject();
  const { can } = useAuth();
  const canManage = can("projects.manage");
  const { busy, error, message, run } = useAction();
  // Each save starts the form again from what the server kept (hours "2" come back as "2.00"),
  // so nothing saved still counts as an unsaved change; a status change keeps what is typed.
  const [saves, setSaves] = useState(0);
  if (!canManage) return <ProjectSummary project={project} />;
  return (
    <div className="stack">
      <ProjectStatus />
      <ProjectForm
        key={saves}
        initial={api.projectSettings(project)}
        submitLabel="Save project"
        busy={busy !== null}
        disabled={project.status === "ARCHIVED"}
        readOnlyNote={ARCHIVED_NOTE}
        guardUnsaved
        saveOnBar
        notices={
          <>
            <ErrorNotice error={error} />
            <SuccessNotice message={message} />
          </>
        }
        onSubmit={(fields) =>
          void run(async () => {
            // Only the settings are this page's: the rules go back as they are now, including
            // what someone else saved on the Rules tab meanwhile (D-145).
            replace(await api.saveProjectPart(project, api.SETTINGS_KEYS, fields));
            setSaves((n) => n + 1);
            return "Saved.";
          })
        }
      />
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
      message:
        "They no longer see this project or its tasks; their account stays. Someone with open tasks here (to record, call or check) must have those tasks reassigned first.",
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
      <ErrorNotice error={error} />
      <SuccessNotice message={message} />
      {/* D-158: the members are a titled section, as "Add people" under it is. */}
      <section className="card" aria-labelledby="members-title">
        <h2 id="members-title">Members</h2>
        {members.state.status === "loading" ? <LoadingState /> : null}
        {members.state.status === "failed" ? (
          <ErrorState error={members.state.error} onRetry={members.reload} />
        ) : null}
        {members.state.status === "loaded" && members.state.data.length === 0 ? (
          <EmptyState title="No members yet" />
        ) : null}
        {members.state.status === "loaded" && members.state.data.length > 0 ? (
          <DataTable label="Members">
            <thead>
              <tr>
                <th scope="col">Name</th>
                <th scope="col">Roles</th>
                {canEdit ? (
                  <th scope="col" className="actions-col">
                    Actions
                  </th>
                ) : null}
              </tr>
            </thead>
            <tbody>
              {members.state.data.map((m) => (
                <tr key={m.user_id}>
                  <td className="team-person">
                    <Person name={m.display_name} email={m.email} />
                  </td>
                  <td>{rolesOf(m.roles)}</td>
                  {canEdit ? (
                    <td className="actions">
                      {/* One way to remove, as in every list (D-158): the bin, its words on
                          hover and for screen readers. */}
                      <IconButton
                        icon="trash"
                        label={`Remove ${m.display_name}`}
                        disabled={busy !== null}
                        onClick={() => remove(m)}
                      />
                    </td>
                  ) : null}
                </tr>
              ))}
            </tbody>
          </DataTable>
        ) : null}
      </section>
      {canEdit ? (
        <form
          className="card"
          aria-labelledby="add-people-title"
          onSubmit={(e) => {
            e.preventDefault();
            void run(
              async () => setCandidates(await api.listCandidates(project.id, search)),
              "search",
            );
          }}
        >
          <h2 id="add-people-title">Add people</h2>
          <div className="team-search">
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
          </div>
          {candidates?.length === 0 ? (
            <p className="muted">No matching active users who are not already members.</p>
          ) : null}
          {/* Who was found: a table like the members above it, edge to edge (D-158). */}
          {candidates && candidates.length > 0 ? (
            <DataTable label="People found">
              <thead>
                <tr>
                  <th scope="col">Name</th>
                  <th scope="col">Roles</th>
                  <th scope="col" className="actions-col">
                    Actions
                  </th>
                </tr>
              </thead>
              <tbody>
                {candidates.map((c) => (
                  <tr key={c.user_id}>
                    <td className="team-person">
                      <Person name={c.display_name} email={c.email} />
                    </td>
                    <td>{rolesOf(c.roles)}</td>
                    <td className="actions">
                      <Button
                        variant="secondary"
                        icon="userPlus"
                        aria-label={`Add ${c.display_name}`}
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
                    </td>
                  </tr>
                ))}
              </tbody>
            </DataTable>
          ) : null}
        </form>
      ) : null}
      {confirm.dialog}
    </div>
  );
}

export function AudioRulesTab() {
  const { project, replace } = useProject();
  const { can } = useAuth();
  const canManage = can("projects.manage");
  const canEdit = canManage && project.status !== "ARCHIVED";
  const [rules, setRules] = useState<api.AudioRule[]>(project.audio_rules);
  const { busy, error, message, run } = useAction();
  const leaveGuard = useUnsavedChanges(
    canEdit && busy === null && !api.sameValue(rules, project.audio_rules),
  );
  const update = (i: number, patch: Partial<api.AudioRule>) =>
    setRules(rules.map((r, j) => (j === i ? { ...r, ...patch } : r)));
  const id = useId();
  // One section with its Save on the title bar (D-158): titled with the project's recording type,
  // or, for a project made before D-153 with both, one part per type under one Save.
  const several = rules.length > 1;
  const title = several
    ? "Face-to-face and phone call"
    : rules[0]
      ? labelFor(MODE_LABELS, rules[0].mode)
      : "Audio rules";

  return (
    <>
      <form
        className="card"
        aria-labelledby={`${id}-title`}
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
        <div className="card__head">
          <h2 id={`${id}-title`}>{title}</h2>
          {canEdit ? (
            <Button type="submit" icon="check" busy={busy !== null}>
              Save audio rules
            </Button>
          ) : null}
        </div>
        {canManage && !canEdit ? <p className="notice notice--info">{ARCHIVED_NOTE}</p> : null}
        <ErrorNotice error={error} />
        <SuccessNotice message={message} />
        {rules.map((r, i) => (
          <Fragment key={r.mode}>
            {several ? (
              <h3 id={`${id}-${r.mode}`} className="subhead">
                {labelFor(MODE_LABELS, r.mode)}
              </h3>
            ) : null}
            <fieldset
              className="plain-fieldset"
              aria-labelledby={several ? `${id}-${r.mode}` : `${id}-title`}
              disabled={!canEdit}
            >
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
          </Fragment>
        ))}
      </form>
      {leaveGuard}
    </>
  );
}

/** The last choice of the language list: a code typed by hand, for a language the list does not
 * have (POL-02). Not a language code itself: those have no colon. */
const OTHER_LANGUAGE = "other:";
/** A language code as the server takes it (BCP 47 style): two or three small letters, then any
 * parts after a dash, like sw, fil or en-US. */
const LANGUAGE_CODE = /^[a-z]{2,3}(-[A-Za-z0-9]{2,8})*$/;

export function LanguagesTab() {
  const { project, replace } = useProject();
  const { can } = useAuth();
  const canManage = can("projects.manage");
  const canEdit = canManage && project.status !== "ARCHIVED";
  const [choice, setChoice] = useState("");
  const [typed, setTyped] = useState("");
  const [dialect, setDialect] = useState("");
  const { busy, error, message, run, setMessage } = useAction();
  const confirm = useConfirm(setMessage);
  const other = choice === OTHER_LANGUAGE;
  const code = other ? typed.trim() : choice;
  const codeOk = other ? LANGUAGE_CODE.test(code) : code !== "";
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
      {canManage && !canEdit ? <p className="notice notice--info">{ARCHIVED_NOTE}</p> : null}
      <ErrorNotice error={error} />
      <SuccessNotice message={message} />
      {/* D-158: the languages are a titled section, as "Add a language" under it is. */}
      <section className="card" aria-labelledby="languages-title">
        <h2 id="languages-title">Project languages</h2>
        {project.languages.length === 0 ? (
          <EmptyState title="No languages yet" />
        ) : (
          <DataTable label="Languages">
            <thead>
              <tr>
                <th scope="col">Language</th>
                <th scope="col">Dialect</th>
                {canEdit ? (
                  <th scope="col" className="actions-col">
                    Actions
                  </th>
                ) : null}
              </tr>
            </thead>
            <tbody>
              {project.languages.map((l) => (
                <tr key={`${l.language_code}/${l.dialect}`}>
                  <td>{languageLabel(l.language_code)}</td>
                  <td>{l.dialect || <span className="muted">-</span>}</td>
                  {canEdit ? (
                    <td className="actions">
                      {/* One way to remove, as in every list (D-158). */}
                      <IconButton
                        icon="trash"
                        label={`Remove ${name(l)}`}
                        disabled={busy !== null}
                        onClick={() => remove(l)}
                      />
                    </td>
                  ) : null}
                </tr>
              ))}
            </tbody>
          </DataTable>
        )}
      </section>
      {canEdit ? (
        <form
          className="card"
          aria-labelledby="add-language-title"
          onSubmit={(e) => {
            e.preventDefault();
            if (!codeOk) return;
            void run(async () => {
              const languages = [
                ...project.languages,
                { language_code: code, dialect: dialect.trim() },
              ];
              replace(await api.setLanguages(project.id, languages));
              // Cleared only when saved: after a failure what was typed can be corrected.
              setChoice("");
              setTyped("");
              setDialect("");
              return "Language added.";
            }, "add");
          }}
        >
          <h2 id="add-language-title">Add a language</h2>
          <Select
            label="Language"
            required
            value={choice}
            onChange={(e) => setChoice(e.target.value)}
            options={[
              { value: "", label: "Choose a language" },
              ...LANGUAGES.map((l) => ({ value: l.code, label: languageLabel(l.code) })),
              { value: OTHER_LANGUAGE, label: "Other (type the code)" },
            ]}
          />
          {other ? (
            <TextField
              label="Language code"
              required
              hint="For example sw (Swahili), fil (Filipino) or en-US (English as spoken in the United States)."
              value={typed}
              maxLength={35}
              autoCapitalize="off"
              autoComplete="off"
              spellCheck={false}
              {...(typed.trim() !== "" && !codeOk
                ? {
                    error:
                      "Type two or three small letters, then any parts after a dash, like sw or en-US.",
                  }
                : {})}
              onChange={(e) => setTyped(e.target.value)}
            />
          ) : null}
          <TextField
            label="Dialect"
            hint="Optional."
            value={dialect}
            onChange={(e) => setDialect(e.target.value)}
          />
          <Button type="submit" icon="plus" busy={busy === "add"} disabled={!codeOk}>
            Add language
          </Button>
        </form>
      ) : null}
      {confirm.dialog}
    </div>
  );
}

type AssetKind = (typeof api.ASSET_KINDS)[number];

const KIND_LABELS: Record<AssetKind, string> = {
  BROWSER_ORIGINAL: "Browser original captures",
  FTF_DERIVED_PCM: "Face-to-face 16 kHz WAV",
  PROVIDER_ORIGINAL_MIXED: "Phone system mixed recordings",
  TELEPHONY_DERIVED_PCM: "Phone call 16 kHz WAV",
};

/** Example periods shown faded under each box (D-086); nothing is filled in for the admin. */
const KIND_EXAMPLES: Record<AssetKind, string> = {
  BROWSER_ORIGINAL: "Example: 30 (one month)",
  FTF_DERIVED_PCM: "Example: 365 (one year)",
  PROVIDER_ORIGINAL_MIXED: "Example: 30 (one month)",
  TELEPHONY_DERIVED_PCM: "Example: 365 (one year)",
};

/** The days of each kind as the project has them saved, as typed text. */
const daysOf = (p: api.Project): Partial<Record<string, string>> =>
  Object.fromEntries(p.retention_rules.map((r) => [r.asset_kind, String(r.retain_days)]));

/** What is wrong with typed days, or undefined: a whole number from 1, or nothing. */
const daysProblem = (value: string) =>
  value === "" || (/^\d+$/.test(value) && Number(value) >= 1)
    ? undefined
    : "Type a whole number of days, 1 or more, or leave it empty.";

export function RetentionTab() {
  const { project, replace } = useProject();
  const { can } = useAuth();
  const canManage = can("projects.manage");
  const canEdit = canManage && project.status !== "ARCHIVED";
  const [days, setDays] = useState(() => daysOf(project));
  const { busy, error, message, run } = useAction();
  const saved = daysOf(project);
  const typed = (kind: AssetKind) => (days[kind] ?? "").trim();
  const dirty = api.ASSET_KINDS.some((kind) => typed(kind) !== (saved[kind] ?? ""));
  const leaveGuard = useUnsavedChanges(canEdit && busy === null && dirty);
  const wrong = api.ASSET_KINDS.some((kind) => daysProblem(typed(kind)) !== undefined);

  return (
    <>
      <form
        className="card retention"
        aria-labelledby="retention-title"
        noValidate
        onSubmit={(e) => {
          e.preventDefault();
          if (wrong) return;
          void run(async () => {
            // Only the kinds a rule can delete are sent: an older rule for another kind goes.
            const rules = api.ASSET_KINDS.filter((kind) => typed(kind) !== "").map((kind) => ({
              asset_kind: kind,
              retain_days: Number(typed(kind)),
            }));
            const result = await api.setRetention(project.id, rules);
            replace(result);
            setDays(daysOf(result));
            return "Retention saved.";
          });
        }}
      >
        {/* The Save on the section's title bar, as on the Rules pages (D-158). */}
        <div className="card__head">
          <h2 id="retention-title">Days to keep each kind of file</h2>
          {canEdit ? (
            <Button type="submit" icon="check" busy={busy !== null} disabled={wrong}>
              Save retention
            </Button>
          ) : null}
        </div>
        <p className="field__hint retention__note">
          An automatic job deletes a file permanently once it is older than the days set for its
          kind, counted from when it was stored. Only the files of closed tasks (approved, rejected
          or cancelled) are deleted. Leave a box empty to keep that kind of file.
        </p>
        {canManage && !canEdit ? <p className="notice notice--info">{ARCHIVED_NOTE}</p> : null}
        <ErrorNotice error={error} />
        <SuccessNotice message={message} />
        <fieldset disabled={!canEdit} className="plain-fieldset">
          <div className="form-grid">
            {api.ASSET_KINDS.map((kind) => {
              const problem = daysProblem(typed(kind));
              return (
                <TextField
                  key={kind}
                  label={KIND_LABELS[kind]}
                  example={KIND_EXAMPLES[kind]}
                  type="number"
                  min={1}
                  step={1}
                  value={days[kind] ?? ""}
                  {...(problem ? { error: problem } : {})}
                  onChange={(e) => setDays({ ...days, [kind]: e.target.value })}
                />
              );
            })}
          </div>
        </fieldset>
      </form>
      {leaveGuard}
    </>
  );
}
