// Payments (D-137): what moderators and participants earned on approved tasks, at each project's
// rate per approved minute, with the rates themselves. For the Super Admin and Project Admins.
// One row per person and project (each project has its own rates); the days are approval days in
// India time. A project with no rate yet shows its minutes and "No rate set".
import { useState, type ReactNode } from "react";
import { useSearchParams } from "react-router";

import * as pay from "../../api/payments";
import { DataTable } from "../../components/DataTable";
import { Button } from "../../components/form/Button";
import { Select } from "../../components/form/Select";
import { TextField } from "../../components/form/TextField";
import { IconTile } from "../../components/Icon";
import { Modal } from "../../components/Modal";
import { ErrorNotice, SuccessNotice } from "../../components/Notice";
import { ErrorState, LoadingState } from "../../components/StateViews";
import { useAction } from "../../hooks/useAction";
import { useDebounced } from "../../hooks/useDebounced";
import { useResource } from "../../hooks/useResource";
import { rupees, when } from "../../lib/format";

const VIEWS: { id: pay.Payee; label: string }[] = [
  { id: "moderators", label: "Moderators" },
  { id: "participants", label: "Participants" },
];
const NO_RATE = "No rate set";

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

function ModeratorTable({ data }: { data: pay.Payments<pay.ModeratorPay> }) {
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
        {data.rows.map((r) => (
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
      <Totals totals={data.totals} columns={2} />
    </DataTable>
  );
}

function ParticipantTable({ data }: { data: pay.Payments<pay.ParticipantPay> }) {
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
        {data.rows.map((r) => (
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
      <Totals totals={data.totals} columns={3} />
    </DataTable>
  );
}

/** One tab: a search, the CSV download, and the table `show` draws from what `load` gives. */
function Earnings<Row>({
  who,
  filters,
  load,
  show,
}: {
  who: pay.Payee;
  filters: pay.PayFilters;
  load: (filters: pay.PayFilters) => Promise<pay.Payments<Row>>;
  show: (data: pay.Payments<Row>) => ReactNode;
}) {
  const [search, setSearch] = useState("");
  const query = useDebounced(search.trim());
  const asked = { ...filters, search: query || undefined };
  const { state, reload } = useResource(() => load(asked), [JSON.stringify(asked)]);
  const download = useAction();
  return (
    <div className="stack stack--tight">
      <div className="filters" role="group" aria-label="Search and download">
        <TextField
          label={who === "moderators" ? "Search by name" : "Search by code or name"}
          type="search"
          value={search}
          onChange={(e) => setSearch(e.target.value)}
        />
        <Button
          variant="secondary"
          icon="fileCsv"
          busy={download.busy !== null}
          onClick={() => void download.run(() => pay.downloadPay(who, asked))}
        >
          Download CSV
        </Button>
      </div>
      <ErrorNotice error={download.error} />
      {state.status === "loading" ? <LoadingState label="Loading payments" /> : null}
      {state.status === "failed" ? <ErrorState error={state.error} onRetry={reload} /> : null}
      {state.status === "loaded" ? (
        state.data.rows.length ? (
          show(state.data)
        ) : (
          <p className="muted">No approved work in this choice.</p>
        )
      ) : null}
    </div>
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
  return (
    <section className="card stack stack--tight" aria-labelledby="rates-title">
      <h2 id="rates-title">Rates</h2>
      <p className="muted">
        Each project pays a fixed amount per approved minute. Every change is kept in the audit log.
        A new rate also applies to work approved before.
      </p>
      <SuccessNotice message={message} />
      {projects.length === 0 ? (
        <p className="muted">You have no projects.</p>
      ) : (
        <DataTable label="Rates per project">
          <thead>
            <tr>
              <th scope="col">Project</th>
              <th scope="col">Moderators</th>
              <th scope="col">Participants</th>
              <th scope="col">Last changed</th>
              <th scope="col">
                <span className="sr-only">Change</span>
              </th>
            </tr>
          </thead>
          <tbody>
            {projects.map((p) => (
              <tr key={p.project_id}>
                <td>
                  {p.project_code}
                  <div className="muted">{p.project_name}</div>
                </td>
                <td>{rate(p.moderator_rate)}</td>
                <td>{rate(p.participant_rate)}</td>
                <td>{p.updated_at ? `${when(p.updated_at)} · ${p.updated_by ?? "-"}` : "-"}</td>
                <td>
                  <Button
                    variant="secondary"
                    icon="pencil"
                    aria-label={`Change rates of ${p.project_code}`}
                    onClick={() => {
                      setMessage(null);
                      setEditing(p);
                    }}
                  >
                    Change
                  </Button>
                </td>
              </tr>
            ))}
          </tbody>
        </DataTable>
      )}
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
    </section>
  );
}

export function PaymentsPage() {
  const [params, setParams] = useSearchParams();
  const view: pay.Payee = params.get("view") === "participants" ? "participants" : "moderators";
  const rates = useResource(() => pay.listRates(), []);
  const [projectId, setProjectId] = useState("");
  const [from, setFrom] = useState("");
  const [to, setTo] = useState("");
  // Amounts change with the rates: the tab is loaded again after a rate is saved.
  const [version, setVersion] = useState(0);
  const backwards = from !== "" && to !== "" && from > to;
  const projects = rates.state.status === "loaded" ? rates.state.data : [];
  const filters: pay.PayFilters = {
    project_id: projectId || undefined,
    date_from: from || undefined,
    date_to: to || undefined,
  };
  return (
    <section aria-labelledby="payments-title" className="stack">
      <div className="page-header">
        <div className="page-header__text">
          <h1 id="payments-title">
            <IconTile name="money" />
            Payments
          </h1>
          <p className="page-header__lead">
            What moderators and participants earned on approved tasks, at each project&apos;s rate
            per approved minute.
          </p>
        </div>
      </div>
      <div className="filters" role="group" aria-label="Project and approval days">
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
      </div>
      <p className="muted">
        Only approved tasks count, by the day they were approved (India time). A moderator is paid
        on the full length of the tasks they recorded; each participant on their half of every
        session.
      </p>
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
            onClick={() =>
              setParams(v.id === "participants" ? { view: "participants" } : {}, { replace: true })
            }
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
            filters={filters}
            load={pay.moderatorPay}
            show={(data) => <ModeratorTable data={data} />}
          />
        ) : (
          <Earnings
            key={`participants-${version}`}
            who="participants"
            filters={filters}
            load={pay.participantPay}
            show={(data) => <ParticipantTable data={data} />}
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
