// Payments (D-137): what moderators and participants earned on approved tasks, at each project's
// rate per approved minute, with the rates themselves. For the Super Admin and Project Admins.
// One row per person and project (each project has its own rates); the days are approval days in
// India time. A project with no rate yet shows its minutes and "No rate set". A long list is shown
// a page at a time; its totals and the CSV always cover every row. D-158: one filter bar for the
// page (the project, the days and the search), the tab's table in a section of its own with the
// CSV download on its title bar, and the rates' first rows with the rest on request.
import { useId, useState, type ReactNode } from "react";
import { useSearchParams } from "react-router";

import * as pay from "../../api/payments";
import { DataTable } from "../../components/DataTable";
import { Button, IconButton } from "../../components/form/Button";
import { Select } from "../../components/form/Select";
import { TextField } from "../../components/form/TextField";
import { Modal } from "../../components/Modal";
import { ErrorNotice, SuccessNotice } from "../../components/Notice";
import { Pagination } from "../../components/Pagination";
import { ErrorState, LoadingState } from "../../components/StateViews";
import { useAction } from "../../hooks/useAction";
import { useDebounced } from "../../hooks/useDebounced";
import { useFirstRows } from "../../hooks/useFirstRows";
import { useResource } from "../../hooks/useResource";
import { rupees, typedDay, when } from "../../lib/format";
import "./payments.css";

const VIEWS: { id: pay.Payee; label: string }[] = [
  { id: "moderators", label: "Moderators" },
  { id: "participants", label: "Participants" },
];
const NO_RATE = "No rate set";
/** Rows drawn at once: thousands of participants stay quick to show and to scroll. */
const PAGE_SIZE = 50;

const rate = (value: string | null) => (value === null ? NO_RATE : `${rupees(value)} / min`);
const amount = (value: string | null) => (value === null ? NO_RATE : rupees(value));

/** The totals line under a tab's table, and the minutes left out of the amount. */
function Totals({ totals, columns }: { totals: pay.PayTotals; columns: number }) {
  return (
    <tfoot>
      <tr>
        <th scope="row" colSpan={columns}>
          Total
        </th>
        <td className="num">{totals.count}</td>
        <td className="num">{totals.minutes}</td>
        <td />
        <td className="num">
          <strong>{rupees(totals.amount)}</strong>
          {Number(totals.minutes_without_rate) > 0 ? (
            <div className="muted">
              Not in it: {totals.minutes_without_rate} min with no rate set
            </div>
          ) : null}
        </td>
      </tr>
    </tfoot>
  );
}

/** One page of a tab's rows, and the totals of them all. */
interface Shown<Row> {
  rows: Row[];
  totals: pay.PayTotals;
}

function ModeratorTable({ rows, totals }: Shown<pay.ModeratorPay>) {
  return (
    <DataTable label="Moderator payments">
      <thead>
        <tr>
          <th scope="col">Project</th>
          <th scope="col">Moderator</th>
          <th scope="col" className="num">
            Approved tasks
          </th>
          <th scope="col" className="num">
            Approved minutes
          </th>
          <th scope="col" className="num">
            Rate
          </th>
          <th scope="col" className="num">
            Amount
          </th>
        </tr>
      </thead>
      <tbody>
        {rows.map((r) => (
          <tr key={`${r.project_id}-${r.user_id}`}>
            <td>{r.project_code}</td>
            <td>{r.name}</td>
            <td className="num">{r.approved_tasks}</td>
            <td className="num">{r.approved_minutes}</td>
            <td className="num">{rate(r.rate)}</td>
            <td className="num">{amount(r.amount)}</td>
          </tr>
        ))}
      </tbody>
      <Totals totals={totals} columns={2} />
    </DataTable>
  );
}

function ParticipantTable({ rows, totals }: Shown<pay.ParticipantPay>) {
  return (
    <DataTable label="Participant payments">
      <thead>
        <tr>
          <th scope="col">Project</th>
          <th scope="col">Code</th>
          <th scope="col">Name</th>
          <th scope="col" className="num">
            Approved sessions
          </th>
          <th scope="col" className="num">
            Payable minutes
          </th>
          <th scope="col" className="num">
            Rate
          </th>
          <th scope="col" className="num">
            Amount
          </th>
        </tr>
      </thead>
      <tbody>
        {rows.map((r) => (
          <tr key={`${r.project_id}-${r.participant_id}`}>
            <td>{r.project_code}</td>
            <td>
              <span className="code-tag">{r.participant_code}</span>
            </td>
            <td>{r.name ?? "-"}</td>
            <td className="num">{r.approved_sessions}</td>
            <td className="num">{r.payable_minutes}</td>
            <td className="num">{rate(r.rate)}</td>
            <td className="num">{amount(r.amount)}</td>
          </tr>
        ))}
      </tbody>
      <Totals totals={totals} columns={3} />
    </DataTable>
  );
}

/** One tab (D-158): a section titled `title` with the CSV download on its title bar and the table
 * `show` draws for one page of what `load` gives, with the totals of every row; the pages under
 * the section. */
function Earnings<Row>({
  who,
  title,
  filters,
  load,
  show,
}: {
  who: pay.Payee;
  title: string;
  filters: pay.PayFilters;
  load: (filters: pay.PayFilters) => Promise<pay.Payments<Row>>;
  show: (shown: Shown<Row>) => ReactNode;
}) {
  const titleId = useId();
  const key = JSON.stringify(filters);
  const { state, reload } = useResource(() => load(filters), [key]);
  // Another choice or search starts again at its first page.
  const [paging, setPaging] = useState({ key, page: 1 });
  const download = useAction();
  const rows = state.status === "loaded" ? state.data.rows : [];
  const pages = Math.max(1, Math.ceil(rows.length / PAGE_SIZE));
  const page = Math.min(paging.key === key ? paging.page : 1, pages);
  return (
    <>
      <section className="card pay-section" aria-labelledby={titleId}>
        <div className="card__head">
          <h2 id={titleId}>{title}</h2>
          <Button
            variant="secondary"
            icon="fileCsv"
            busy={download.busy !== null}
            onClick={() => void download.run(() => pay.downloadPay(who, filters))}
          >
            Download CSV
          </Button>
        </div>
        <p className="muted">
          Only approved tasks count, by the day they were approved (India time). A moderator is paid
          on the full length of the tasks they recorded; each participant on their half of every
          session.
        </p>
        <ErrorNotice error={download.error} />
        {state.status === "loading" ? <LoadingState label="Loading payments" /> : null}
        {state.status === "failed" ? <ErrorState error={state.error} onRetry={reload} /> : null}
        {state.status === "loaded" ? (
          rows.length ? (
            show({
              rows: rows.slice((page - 1) * PAGE_SIZE, page * PAGE_SIZE),
              totals: state.data.totals,
            })
          ) : (
            <p className="muted">No approved work in this choice.</p>
          )
        ) : null}
      </section>
      {pages > 1 ? (
        <Pagination
          page={page}
          pageSize={PAGE_SIZE}
          total={rows.length}
          onPage={(p) => setPaging({ key, page: p })}
        />
      ) : null}
    </>
  );
}

/** A project's two rates, in a window over the page. */
function RatesForm({
  rates,
  onSaved,
  onClose,
}: {
  rates: pay.ProjectRates;
  onSaved: (saved: pay.ProjectRates) => void;
  onClose: () => void;
}) {
  const [moderator, setModerator] = useState(rates.moderator_rate ?? "");
  const [participant, setParticipant] = useState(rates.participant_rate ?? "");
  const { busy, error, run } = useAction();
  return (
    <Modal title={`Rates for ${rates.project_code}`} onClose={onClose}>
      <form
        className="stack stack--tight"
        onSubmit={(e) => {
          e.preventDefault();
          void run(async () => {
            onSaved(
              await pay.setRates(rates.project_id, {
                moderator_rate: moderator.trim() || null,
                participant_rate: participant.trim() || null,
              }),
            );
          });
        }}
      >
        <p className="muted">
          Rupees per approved minute. Leave a box empty when there is no rate.
        </p>
        <TextField
          label="Moderators (₹ per approved minute)"
          type="number"
          min={0}
          step="0.01"
          inputMode="decimal"
          value={moderator}
          onChange={(e) => setModerator(e.target.value)}
        />
        <TextField
          label="Participants (₹ per approved minute)"
          type="number"
          min={0}
          step="0.01"
          inputMode="decimal"
          value={participant}
          onChange={(e) => setParticipant(e.target.value)}
        />
        <ErrorNotice error={error} />
        <div className="actions">
          <Button type="submit" busy={busy !== null}>
            Save rates
          </Button>
        </div>
      </form>
    </Modal>
  );
}

function Rates({
  projects,
  onSaved,
}: {
  projects: pay.ProjectRates[];
  onSaved: (saved: pay.ProjectRates) => void;
}) {
  const [editing, setEditing] = useState<pay.ProjectRates | null>(null);
  const [message, setMessage] = useState<string | null>(null);
  // A long list of projects shows its first rows, the rest on request (the button on the
  // section's title bar, as on the dashboard, D-158).
  const { shown, more } = useFirstRows(projects);
  return (
    <>
      <section className="card pay-section" aria-labelledby="rates-title">
        <div className="card__head">
          <h2 id="rates-title">Rates</h2>
          {more}
        </div>
        <p className="muted">
          Each project pays a fixed amount per approved minute. Every change is kept in the audit
          log. A new rate also applies to work approved before.
        </p>
        <SuccessNotice message={message} />
        {projects.length === 0 ? (
          <p className="muted">You have no projects.</p>
        ) : (
          <DataTable label="Rates per project" className="rates-table">
            <thead>
              <tr>
                <th scope="col">Project</th>
                <th scope="col">Moderators</th>
                <th scope="col">Participants</th>
                <th scope="col" className="rates-table__extra">
                  Last changed
                </th>
                <th scope="col">
                  <span className="sr-only">Change</span>
                </th>
              </tr>
            </thead>
            <tbody>
              {shown.map((p) => (
                <tr key={p.project_id}>
                  <td>
                    {p.project_code}{" "}
                    <span className="muted rates-table__extra">{p.project_name}</span>
                  </td>
                  <td>{rate(p.moderator_rate)}</td>
                  <td>{rate(p.participant_rate)}</td>
                  <td className="rates-table__extra">
                    {p.updated_at ? `${when(p.updated_at)} · ${p.updated_by ?? "-"}` : "-"}
                  </td>
                  <td className="actions">
                    <IconButton
                      icon="pencil"
                      label={`Change rates of ${p.project_code}`}
                      onClick={() => {
                        setMessage(null);
                        setEditing(p);
                      }}
                    />
                  </td>
                </tr>
              ))}
            </tbody>
          </DataTable>
        )}
      </section>
      {editing ? (
        <RatesForm
          rates={editing}
          onClose={() => setEditing(null)}
          onSaved={(saved) => {
            setEditing(null);
            setMessage(`Rates of ${saved.project_code} saved.`);
            onSaved(saved);
          }}
        />
      ) : null}
    </>
  );
}

export function PaymentsPage() {
  const [params, setParams] = useSearchParams();
  const view: pay.Payee = params.get("view") === "participants" ? "participants" : "moderators";
  const rates = useResource(() => pay.listRates(), []);
  const [projectId, setProjectId] = useState("");
  const [from, setFrom] = useState("");
  const [to, setTo] = useState("");
  // The search is the tab's: another tab starts without one.
  const [search, setSearch] = useState("");
  // Asked once typing pauses; an emptied box at once.
  const settled = useDebounced(search.trim());
  const query = search.trim() ? settled : "";
  // Amounts change with the rates: the tab is loaded again after a rate is saved.
  const [version, setVersion] = useState(0);
  // The days as asked: a year still being typed (0002, 0020, 0202) is no day yet.
  const fromDay = typedDay(from);
  const toDay = typedDay(to);
  const backwards = fromDay !== "" && toDay !== "" && fromDay > toDay;
  const projects = rates.state.status === "loaded" ? rates.state.data : [];
  const filters: pay.PayFilters = {
    project_id: projectId || undefined,
    date_from: fromDay || undefined,
    date_to: toDay || undefined,
    search: query || undefined,
  };
  const narrowed = Boolean(projectId || from || to || search);
  return (
    <section aria-labelledby="payments-title" className="stack">
      <div className="page-header">
        <div className="page-header__text">
          <h1 id="payments-title">Payments</h1>
          <p className="page-header__lead">
            What moderators and participants earned on approved tasks, at each project&apos;s rate
            per approved minute.
          </p>
        </div>
      </div>
      {/* One filter bar for the page, a section of its own (D-158). */}
      <div className="filters payments-filters" role="group" aria-label="Filters">
        <Select
          label="Project"
          value={projectId}
          onChange={(e) => setProjectId(e.target.value)}
          options={[
            { value: "", label: "All my projects" },
            ...projects.map((p) => ({
              value: p.project_id,
              label: `${p.project_code} · ${p.project_name}`,
            })),
          ]}
        />
        <TextField
          label="Approved from"
          type="date"
          value={from}
          onChange={(e) => setFrom(e.target.value)}
        />
        <TextField
          label="Approved to"
          type="date"
          value={to}
          {...(backwards ? { error: "Must not be before the first day" } : {})}
          onChange={(e) => setTo(e.target.value)}
        />
        <TextField
          label={view === "moderators" ? "Search by name" : "Search by code or name"}
          type="search"
          value={search}
          onChange={(e) => setSearch(e.target.value)}
        />
        {narrowed ? (
          <Button
            variant="secondary"
            icon="filterX"
            onClick={() => {
              setProjectId("");
              setFrom("");
              setTo("");
              setSearch("");
            }}
          >
            Clear filters
          </Button>
        ) : null}
      </div>
      <div className="tabs" role="tablist" aria-label="Who is paid">
        {VIEWS.map((v) => (
          <button
            key={v.id}
            type="button"
            role="tab"
            id={`payments-tab-${v.id}`}
            aria-selected={view === v.id}
            aria-controls="payments-panel"
            className={view === v.id ? "tabs__link active" : "tabs__link"}
            onClick={() => {
              if (v.id !== view) setSearch("");
              setParams(v.id === "participants" ? { view: "participants" } : {}, { replace: true });
            }}
          >
            {v.label}
          </button>
        ))}
      </div>
      <div
        id="payments-panel"
        role="tabpanel"
        aria-labelledby={`payments-tab-${view}`}
        className="stack"
      >
        {backwards ? null : view === "moderators" ? (
          <Earnings
            key={`moderators-${version}`}
            who="moderators"
            title="Moderator payments"
            filters={filters}
            load={pay.moderatorPay}
            show={(shown) => <ModeratorTable {...shown} />}
          />
        ) : (
          <Earnings
            key={`participants-${version}`}
            who="participants"
            title="Participant payments"
            filters={filters}
            load={pay.participantPay}
            show={(shown) => <ParticipantTable {...shown} />}
          />
        )}
      </div>
      {rates.state.status === "loading" ? <LoadingState label="Loading rates" /> : null}
      {rates.state.status === "failed" ? (
        <ErrorState error={rates.state.error} onRetry={rates.reload} />
      ) : null}
      {rates.state.status === "loaded" ? (
        <Rates
          projects={projects}
          onSaved={(saved) => {
            rates.replace(projects.map((p) => (p.project_id === saved.project_id ? saved : p)));
            setVersion((n) => n + 1);
          }}
        />
      ) : null}
    </section>
  );
}
