// Participants of a project (PART-*). Names and phone numbers appear only for roles allowed to see
// them; the server decides what each role receives. Adding, editing, the consent history and the
// details open in the same windows as on the Participants page.
import { useState } from "react";

import { apiDownload } from "../../api/client";
import * as work from "../../api/work";
import { useAuth } from "../../auth/AuthContext";
import { useConfirm } from "../../components/ConfirmDialog";
import { DataTable } from "../../components/DataTable";
import { Button, IconButton } from "../../components/form/Button";
import { TextField } from "../../components/form/TextField";
import { ErrorNotice, SuccessNotice } from "../../components/Notice";
import { Pagination } from "../../components/Pagination";
import { EmptyState, ErrorState, LoadingState } from "../../components/StateViews";
import { useAction } from "../../hooks/useAction";
import { useDebounced } from "../../hooks/useDebounced";
import { useResource } from "../../hooks/useResource";
import { addedText, useParticipantWindows } from "../participants/ParticipantEditor";
import "../participants/participants.css";
import { languageLabel } from "./choices";
import { useProject } from "./ProjectDetailPage";

/** People who already exist in another of the caller's projects, added here as they are (D-090). */
function AddExisting({
  projectId,
  refresh,
  busy,
  onAdd,
}: {
  projectId: string;
  refresh: number;
  busy: boolean;
  onAdd: (codes: string[]) => void;
}) {
  const [typed, setTyped] = useState("");
  const [ticked, setTicked] = useState<string[]>([]);
  const search = useDebounced(typed.trim());
  const found = useResource(
    () => work.linkCandidates(projectId, search),
    [projectId, search, refresh],
  );
  const people = found.state.status === "loaded" ? found.state.data : [];
  // Only people still on offer can stay ticked (the list changes as they are added).
  const shown = people.map((c) => c.participant_code);
  const chosen = ticked.filter((code) => shown.includes(code));
  const flip = (code: string) =>
    setTicked(chosen.includes(code) ? chosen.filter((x) => x !== code) : [...chosen, code]);
  return (
    <section className="card pick" aria-labelledby="add-existing-title">
      <div className="pick__head">
        <div>
          <h2 id="add-existing-title">Add an existing participant</h2>
          <p className="muted">
            People from your other projects who are not in this one yet. They keep their code,
            details and consent history.
          </p>
        </div>
        {found.state.status === "loaded" ? (
          <span className="pick__count">
            {people.length === 1 ? "1 person" : `${people.length} people`}
          </span>
        ) : null}
      </div>
      <TextField
        label="Search your other projects"
        type="search"
        placeholder="Code or name, e.g. P000123"
        value={typed}
        onChange={(e) => setTyped(e.target.value)}
      />
      {found.state.status === "loading" ? <LoadingState label="Searching" /> : null}
      {found.state.status === "failed" ? (
        <ErrorState error={found.state.error} onRetry={found.reload} />
      ) : null}
      {found.state.status === "loaded" && people.length === 0 ? (
        <p className="pick__empty">
          {search ? `No one matches "${search}".` : "No one to add: everyone is already here."}
        </p>
      ) : null}
      {people.length > 0 ? (
        <div className="actions">
          <label className="checkbox">
            <input
              type="checkbox"
              checked={chosen.length === shown.length}
              onChange={(e) => setTicked(e.target.checked ? shown : [])}
            />
            <span>Select all shown ({shown.length})</span>
          </label>
          <Button
            icon="plus"
            busy={busy}
            disabled={chosen.length === 0}
            onClick={() => {
              onAdd(chosen);
              setTicked([]);
            }}
          >
            Add selected ({chosen.length})
          </Button>
        </div>
      ) : null}
      {people.length > 0 ? (
        <ul className="pick__list">
          {people.map((c) => (
            <li key={c.id} className="pick__row">
              <input
                type="checkbox"
                aria-label={`Select ${c.participant_code}`}
                checked={chosen.includes(c.participant_code)}
                onChange={() => flip(c.participant_code)}
              />
              <span className="pick__code">{c.participant_code}</span>
              <span className="pick__name">{c.display_label ?? "Name hidden"}</span>
              <span className="pick__meta">
                {languageLabel(c.language_code)}
                {c.dialect ? ` · ${c.dialect}` : ""}
              </span>
              <Button
                variant="secondary"
                icon="plus"
                busy={busy}
                aria-label={`Add ${c.participant_code}`}
                onClick={() => onAdd([c.participant_code])}
              >
                Add
              </Button>
            </li>
          ))}
        </ul>
      ) : null}
    </section>
  );
}

const minutesText = (value: number | undefined) =>
  value === undefined ? "–" : value.toLocaleString("en-IN", { maximumFractionDigits: 2 });

export function ParticipantsTab() {
  const { project } = useProject();
  const { can, user } = useAuth();
  const canManage = can("participants.manage");
  // The participant's own page, read-only: Super Admin only (D-100).
  const canOpenPage = Boolean(user?.roles.includes("SUPER_ADMIN"));
  const [search, setSearch] = useState("");
  const [page, setPage] = useState(1);
  const [addingExisting, setAddingExisting] = useState(false);
  const [refresh, setRefresh] = useState(0);
  const query = useDebounced(search.trim());
  const list = useResource(
    () => work.listParticipants(project.id, { search: query, page, page_size: 25 }),
    [project.id, query, page],
  );
  const { busy, error, message, run, setMessage } = useAction(list.reload);
  const confirm = useConfirm(setMessage);
  const windows = useParticipantWindows({
    projectId: project.id,
    languages: project.languages,
    onSaved: (text) => {
      setMessage(text);
      list.reload();
    },
  });

  // The server sends minutes only to people who may export the project (D-095).
  const showMinutes =
    list.state.status === "loaded" && list.state.data.items.some((p) => p.minutes != null);

  const remove = (p: work.Participant) =>
    confirm.ask({
      title: `Delete ${p.participant_code}?`,
      message: "Their personal data is removed. Their code stays in the records.",
      askReason: "Why is this participant deleted?",
      confirmLabel: "Delete",
      danger: true,
      action: async ({ comment }) => {
        await work.deleteParticipant(project.id, p.id, comment);
        list.reload();
        return `${p.participant_code} deleted.`;
      },
    });

  return (
    <div className="stack">
      <div className="actions">
        {canManage ? (
          <Button icon="userPlus" onClick={() => windows.open({ kind: "add" })}>
            Add participant
          </Button>
        ) : null}
        {canManage ? (
          <Button
            variant="secondary"
            icon={addingExisting ? "close" : "people"}
            onClick={() => setAddingExisting(!addingExisting)}
          >
            {addingExisting ? "Close search" : "Add existing participant"}
          </Button>
        ) : null}
        {can("participants.export") ? (
          <Button
            variant="secondary"
            icon="fileCsv"
            busy={busy === "export"}
            onClick={() =>
              void run(async () => {
                await apiDownload(
                  `/api/v1/projects/${project.id}/participants/export`,
                  "participants.csv",
                );
                return "Contact list downloaded.";
              }, "export")
            }
          >
            Export contacts
          </Button>
        ) : null}
      </div>
      {addingExisting ? (
        <AddExisting
          projectId={project.id}
          refresh={refresh}
          busy={busy === "link"}
          onAdd={(codes) =>
            void run(async () => {
              // One after the other: each is checked and audited on its own; a refusal names
              // who was not added and keeps the ones that were. Each is emailed this project's
              // consent form by the server (D-129).
              const added: work.AddedParticipant[] = [];
              try {
                for (const code of codes) {
                  added.push(await work.linkParticipant(project.id, code));
                }
              } finally {
                setRefresh((n) => n + 1);
              }
              const [first] = added;
              return added.length === 1 && first
                ? addedText(first, " to this project")
                : `${added.length} participants added to this project. ${[
                    ...new Set(added.map((p) => p.consent_email)),
                  ].join(" ")}`;
            }, "link")
          }
        />
      ) : null}
      <ErrorNotice error={error} />
      <SuccessNotice message={message} />
      <TextField
        label="Search by code or name"
        type="search"
        value={search}
        onChange={(e) => {
          setSearch(e.target.value);
          setPage(1);
        }}
      />
      {list.state.status === "loading" ? <LoadingState label="Loading participants" /> : null}
      {list.state.status === "failed" ? (
        <ErrorState error={list.state.error} onRetry={list.reload} />
      ) : null}
      {list.state.status === "loaded" && list.state.data.items.length === 0 ? (
        <EmptyState title="No participants yet" />
      ) : null}
      {list.state.status === "loaded" && list.state.data.items.length > 0 ? (
        <>
          <DataTable>
            <thead>
              <tr>
                <th scope="col">Code</th>
                <th scope="col">Name</th>
                <th scope="col">Phone</th>
                <th scope="col">Language</th>
                {showMinutes ? (
                  <>
                    <th scope="col" className="num">
                      Recorded min
                    </th>
                    <th scope="col" className="num">
                      Approved min
                    </th>
                    <th
                      scope="col"
                      className="num"
                      title="Half of approved: two participants share each conversation"
                    >
                      Payable min
                    </th>
                  </>
                ) : null}
                <th scope="col">Actions</th>
              </tr>
            </thead>
            <tbody>
              {list.state.data.items.map((p) => (
                <tr key={p.id}>
                  <td>{p.participant_code}</td>
                  <td>{p.display_label ?? <span className="muted">Hidden</span>}</td>
                  <td>
                    {p.phone ?? (p.has_phone ? <span className="muted">Hidden</span> : "None")}
                  </td>
                  <td>
                    {languageLabel(p.language_code)}
                    {p.dialect ? <div className="muted">{p.dialect}</div> : null}
                  </td>
                  {showMinutes ? (
                    <>
                      <td className="num">{minutesText(p.minutes?.recorded_minutes)}</td>
                      <td className="num">{minutesText(p.minutes?.approved_minutes)}</td>
                      <td className="num">
                        <strong>{minutesText(p.minutes?.payable_minutes)}</strong>
                      </td>
                    </>
                  ) : null}
                  <td className="actions">
                    {canOpenPage ? (
                      <IconButton
                        icon="eye"
                        label="Their page"
                        to={`/projects/${project.id}/participants/${p.id}/page`}
                      />
                    ) : null}
                    {p.consent_visible ? (
                      <IconButton
                        icon="history"
                        label="Consent history"
                        onClick={() => windows.open({ kind: "history", participant: p })}
                      />
                    ) : null}
                    {canManage ? (
                      <>
                        {p.has_email && p.consent_status !== "GIVEN" ? (
                          <IconButton
                            icon="mail"
                            label="Email consent form again"
                            busy={busy === `email-${p.id}`}
                            disabled={busy !== null}
                            onClick={() =>
                              void run(() => work.emailConsentForm(project.id, p), `email-${p.id}`)
                            }
                          />
                        ) : null}
                        <IconButton
                          icon="pencil"
                          label="Edit"
                          onClick={() => windows.open({ kind: "edit", participant: p })}
                        />
                        <IconButton
                          icon="trash"
                          label="Delete"
                          disabled={busy !== null}
                          onClick={() => remove(p)}
                        />
                      </>
                    ) : null}
                  </td>
                </tr>
              ))}
            </tbody>
          </DataTable>
          <Pagination page={page} pageSize={25} total={list.state.data.total} onPage={setPage} />
        </>
      ) : null}
      {windows.dialog}
      {confirm.dialog}
    </div>
  );
}
