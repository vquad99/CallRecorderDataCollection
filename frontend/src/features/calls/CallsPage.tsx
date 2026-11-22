// Phone calls (D-101, D-102, D-103): how calls are going, from the platform's own call records,
// plus TxContact's own count of calls per hour; and, on its own tab, every call with a link to its
// task. Moderators see a plain list of their own calls (D-104). The figures are laid out plainly
// (D-154): the key figures as one line, one chart (calls per day), and a heading over each table;
// the calls per hour as one matrix (our count and TxContact's, hour by hour). D-158: the filters
// and the key figures are white sections of their own, and the sections sharing a row are about
// the same height.
import { useState, type ReactNode } from "react";
import { Link, useSearchParams } from "react-router";

import { listAllProjects } from "../../api/projects";
import * as tel from "../../api/telephony";
import { useAuth } from "../../auth/AuthContext";
import {
  CellBar,
  DayChart,
  Figure,
  FigureLine,
  MatrixTable,
  Panel,
  ShareTable,
  type MatrixSection,
} from "../../components/charts/Charts";
import { stageParts } from "../../components/charts/stages";
import { DataTable } from "../../components/DataTable";
import { Button } from "../../components/form/Button";
import { Select } from "../../components/form/Select";
import { ErrorNotice } from "../../components/Notice";
import { Pagination } from "../../components/Pagination";
import { ErrorState, LoadingState } from "../../components/StateViews";
import { useAction } from "../../hooks/useAction";
import { useFirstRows } from "../../hooks/useFirstRows";
import { useResource } from "../../hooks/useResource";
import { duration, plural, when } from "../../lib/format";
import { labelFor } from "../../lib/labels";
import { CallBadge } from "./callUi";

const minutes = (m: number | null) => duration(m === null ? null : m * 60);
const pct = (part: number, whole: number) => (whole > 0 ? Math.round((part / whole) * 100) : 0);
const HOURS = Array.from({ length: 24 }, (_, h) => h);
const two = (h: number) => String(h).padStart(2, "0");

/** TxContact's own hour-of-day counts: its answer's shape is not described, so a map or list of
 * numbers is read; anything else is only described, with the answer for the Super Admin. */
function useProviderHours(days: number) {
  const { state, reload } = useResource(() => tel.providerTraffic(days), [days]);
  if (state.status !== "loaded") return { state, reload, hours: null, source: null };
  const t = state.data;
  if (!t.available) return { state, reload, hours: null, source: null };
  const hours = HOURS.map(() => 0);
  let readable = false;
  const source = t.data;
  if (Array.isArray(source) && source.every((v) => typeof v === "number")) {
    source.slice(0, 24).forEach((v, i) => (hours[i] = v as number));
    readable = true;
  } else if (source && typeof source === "object") {
    for (const [k, v] of Object.entries(source as Record<string, unknown>)) {
      const h = Number.parseInt(k, 10);
      if (Number.isInteger(h) && h >= 0 && h < 24 && typeof v === "number") {
        hours[h] = v;
        readable = true;
      }
    }
  }
  return { state, reload, hours: readable ? hours : null, source };
}

/** One row of the hours matrix: a count per shown hour, each cell shaded by its share of the
 * row's busiest hour. */
function HourCells({ hours, shown }: { hours: number[]; shown: number[] }) {
  const max = Math.max(1, ...hours);
  return (
    <>
      {shown
        .map((h) => ({ h, n: hours[h] ?? 0 }))
        .map(({ h, n }) => (
          <td
            key={h}
            className="num"
            style={
              n > 0
                ? {
                    background: `color-mix(in srgb, var(--icon-blue) ${Math.round((n / max) * 38) + 4}%, transparent)`,
                  }
                : undefined
            }
          >
            {/* An hour with no call shows "-", as every empty cell does (D-158). */}
            {n > 0 ? n : <span className="muted">-</span>}
          </td>
        ))}
    </>
  );
}

/** Calls started in each hour of the day as one matrix (D-154): our own count, and TxContact's
 * own count beside it (or why it is missing). */
function CallsByHour({
  ours,
  days,
  className,
}: {
  ours: number[];
  days: number;
  className: string;
}) {
  const superAdmin = Boolean(useAuth().user?.roles.includes("SUPER_ADMIN"));
  const provider = useProviderHours(days);
  const busiest = ours.indexOf(Math.max(...ours));
  // Only the hours from the first to the last with any call (on either row): the night stays out.
  const used = HOURS.filter((h) => (ours[h] ?? 0) > 0 || (provider.hours?.[h] ?? 0) > 0);
  const shown = used.length > 0 ? HOURS.slice(used[0], (used[used.length - 1] ?? 23) + 1) : HOURS;
  const theirs = provider.state;
  const providerRow =
    provider.hours !== null ? (
      <HourCells hours={provider.hours} shown={shown} />
    ) : (
      <td colSpan={shown.length} className="hours-matrix__note">
        {theirs.status === "loading" ? (
          "Asking TxContact…"
        ) : theirs.status === "failed" ? (
          <>
            {theirs.error.message}{" "}
            {/* A plain button (D-158): tap-sized on a phone, styled on this page too. */}
            <Button variant="secondary" onClick={provider.reload}>
              Try again
            </Button>
          </>
        ) : !theirs.data.available ? (
          `Not available: ${theirs.data.message}.`
        ) : (
          "TxContact answered, but not with counts per hour."
        )}
      </td>
    );
  return (
    <Panel className={className} title="Calls by hour of the day">
      <DataTable label="Calls by hour of the day" className="hours-matrix">
        <thead>
          <tr>
            <th scope="col">Hour</th>
            {shown.map((h) => (
              <th key={h} scope="col" className="num">
                {two(h)}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          <tr>
            <th scope="row">Calls made</th>
            <HourCells hours={ours} shown={shown} />
          </tr>
          <tr>
            <th scope="row">TxContact&apos;s own count</th>
            {providerRow}
          </tr>
        </tbody>
      </DataTable>
      {ours.some((n) => n > 0) ? (
        <p className="muted">
          Busiest hour: {two(busiest)}:00 ({plural(ours[busiest] ?? 0, "call")}).
        </p>
      ) : (
        <p className="muted">No calls in this period yet.</p>
      )}
      {superAdmin && provider.source !== null && provider.hours === null ? (
        <details className="tech-log">
          <summary>Technical details</summary>
          <pre className="calls-raw">{JSON.stringify(provider.source, null, 2)}</pre>
        </details>
      ) : null}
    </Panel>
  );
}

type ReasonRow = { key: string; label: string; n: number; max: number };

/** One kind of counted list: a row per reason with its count and a bar for its share of the
 * kind's largest. */
function reasonSection(
  key: string,
  title: string,
  counts: Record<string, number>,
  labels: Record<string, string>,
  empty: string,
): MatrixSection<ReasonRow> {
  const entries = Object.entries(counts);
  const max = Math.max(0, ...entries.map(([, n]) => n));
  return {
    key,
    title,
    empty,
    rows: entries.map(([k, n]) => ({ key: k, label: labelFor(labels, k), n, max })),
  };
}

/** Counted lists as a section of their own, one table edge to edge under its title (D-158: no
 * table framed inside a section, and two sections of their own instead of two tables of unlike
 * length side by side). */
function Reasons({
  title,
  sections,
  className,
}: {
  title: string;
  sections: MatrixSection<ReasonRow>[];
  className: string;
}) {
  return (
    <Panel className={className} title={title}>
      <MatrixTable<ReasonRow>
        label={title}
        head="Reason"
        columns={[
          {
            key: "n",
            label: "Count",
            num: true,
            cell: (r) => (
              <CellBar value={r.n} max={r.max}>
                {r.n}
              </CellBar>
            ),
          },
        ]}
        sections={sections}
        rowKey={(r) => r.key}
        rowLabel={(r) => r.label}
      />
    </Panel>
  );
}

const FUNNEL: { key: keyof tel.CallFunnel; label: string }[] = [
  { key: "dialled", label: "Calls started" },
  { key: "accepted", label: "Accepted by TxContact" },
  { key: "closed", label: "Closed by the moderator" },
  { key: "recorded", label: "Recording stored" },
  { key: "sent_to_qc", label: "Sent to QC (tasks)" },
  { key: "approved", label: "Approved (tasks)" },
];

/** From dial to approval: where calls are lost on the way. */
function Funnel({ funnel, className }: { funnel: tel.CallFunnel; className: string }) {
  return (
    <Panel className={className} title="From call to approval">
      <DataTable label="From call to approval" className="funnel">
        <thead>
          <tr>
            <th scope="col">Step</th>
            <th scope="col" className="num">
              Calls
            </th>
            <th scope="col" className="num">
              Of started
            </th>
          </tr>
        </thead>
        <tbody>
          {FUNNEL.map((f) => (
            <tr key={f.key}>
              <th scope="row">{f.label}</th>
              <td className="num">
                <CellBar value={funnel[f.key]} max={funnel.dialled}>
                  {funnel[f.key]}
                </CellBar>
              </td>
              <td className="num">
                {funnel.dialled > 0 ? `${pct(funnel[f.key], funnel.dialled)}%` : "-"}
              </td>
            </tr>
          ))}
        </tbody>
      </DataTable>
    </Panel>
  );
}

/** Every call the person may see, newest first, a page at a time. `days`: only the calls of the
 * period chosen on the page, as in its CSV (D-159); a moderator's own list has every call. */
function CallList({
  projectId,
  days,
  title,
  showModerator = true,
}: {
  projectId: string;
  days?: number;
  title: string;
  /** Left out of a moderator's own list, where every row would repeat their name (D-159). */
  showModerator?: boolean;
}) {
  const [page, setPage] = useState(1);
  const [state, setState] = useState("");
  const list = useResource(
    () =>
      tel.listAllCalls({
        project_id: projectId || undefined,
        state: state || undefined,
        days,
        page,
        page_size: 25,
      }),
    [projectId, state, days, page],
  );
  const loaded = list.state.status === "loaded" ? list.state.data : null;
  // D-158: the list is a section (its title bar with the compact "Show" filter, the table edge to
  // edge under it) and its pages sit under the section's frame, as on every other list.
  return (
    <>
      <section className="card calls-list" aria-labelledby="all-calls">
        <div className="card__head">
          <h2 id="all-calls">{title}</h2>
          <Select
            label="Show"
            value={state}
            onChange={(e) => {
              setState(e.target.value);
              setPage(1);
            }}
            options={[
              { value: "", label: "Every call" },
              { value: "NEEDS_PERSON", label: "Needs a person" },
              ...Object.entries(tel.CALL_STATE_LABELS).map(([value, label]) => ({ value, label })),
            ]}
          />
        </div>
        {list.state.status === "loading" ? <LoadingState /> : null}
        {list.state.status === "failed" ? (
          <ErrorState error={list.state.error} onRetry={list.reload} />
        ) : null}
        {loaded && loaded.items.length === 0 ? <p className="muted">No calls.</p> : null}
        {loaded && loaded.items.length > 0 ? (
          <DataTable>
            <thead>
              <tr>
                <th scope="col">Started</th>
                <th scope="col">Task</th>
                {showModerator ? <th scope="col">Moderator</th> : null}
                <th scope="col">State</th>
                {/* The lengths are numbers: on the right, as in every other table (D-159). */}
                <th scope="col" className="num">
                  Call
                </th>
                <th scope="col" className="num">
                  Recording
                </th>
                <th scope="col">Why</th>
              </tr>
            </thead>
            <tbody>
              {loaded.items.map((c) => (
                <tr key={c.id}>
                  <td>{when(c.dialled_at)}</td>
                  <td>
                    {/* Codes in monospace, as in every list (D-159). */}
                    <Link className="mono" to={`/tasks/${c.task_id}`}>
                      {c.task_code}
                    </Link>{" "}
                    <span className="muted mono">{c.project_code}</span>
                  </td>
                  {showModerator ? (
                    <td>
                      {c.moderator_name} <span className="muted">seat {c.agent_id}</span>
                    </td>
                  ) : null}
                  <td>
                    <CallBadge state={c.state} stale={c.stale} />
                  </td>
                  <td className="num">
                    {c.closed_at && c.state !== "DIAL_FAILED"
                      ? duration((Date.parse(c.closed_at) - Date.parse(c.dialled_at)) / 1000)
                      : "-"}
                  </td>
                  <td className="num">{duration(c.recording_seconds)}</td>
                  <td>
                    {c.cancel_reason
                      ? tel.CANCEL_REASONS[c.cancel_reason]
                      : c.failure_code && c.state !== "RECORDED"
                        ? labelFor(tel.FAILURE_LABELS, c.failure_code)
                        : "-"}
                  </td>
                </tr>
              ))}
            </tbody>
          </DataTable>
        ) : null}
      </section>
      {loaded && loaded.items.length > 0 ? (
        <Pagination
          page={loaded.page}
          pageSize={loaded.page_size}
          total={loaded.total}
          onPage={setPage}
        />
      ) : null}
    </>
  );
}

/** The calls of each moderator: the first rows, and the rest on request (the button on the
 * section's title bar, D-158). */
function ByModerator({ rows, className }: { rows: tel.ModeratorCalls[]; className: string }) {
  const { shown, more } = useFirstRows(rows);
  const most = Math.max(0, ...rows.map((m) => m.calls));
  return (
    <Panel className={className} title="By moderator" action={more}>
      {rows.length === 0 ? (
        <p className="muted">No calls in this period yet.</p>
      ) : (
        <DataTable label="By moderator" className="names">
          <thead>
            <tr>
              <th scope="col">Moderator</th>
              <th scope="col" className="num">
                Calls
              </th>
              <th scope="col" className="num">
                Recorded
              </th>
              <th scope="col" className="num">
                Failed or cancelled
              </th>
              <th scope="col" className="num">
                Recorded audio
              </th>
              <th scope="col" className="num">
                Average call
              </th>
            </tr>
          </thead>
          <tbody>
            {shown.map((m) => (
              <tr key={m.moderator_id}>
                <th scope="row">{m.name}</th>
                <td className="num">
                  <CellBar value={m.calls} max={most}>
                    {m.calls}
                  </CellBar>
                </td>
                <td className="num">{m.recorded}</td>
                <td className="num">{m.failed}</td>
                <td className="num">{minutes(m.recorded_minutes)}</td>
                <td className="num">{minutes(m.avg_call_minutes)}</td>
              </tr>
            ))}
          </tbody>
        </DataTable>
      )}
    </Panel>
  );
}

/** The calls of each project, the rest on request as above. */
function ByProject({ rows, className }: { rows: tel.ProjectCalls[]; className: string }) {
  const { shown, more } = useFirstRows(rows);
  const most = Math.max(0, ...rows.map((p) => p.calls));
  return (
    <Panel className={className} title="By project" action={more}>
      <DataTable label="By project" className="names">
        <thead>
          <tr>
            <th scope="col">Project</th>
            <th scope="col" className="num">
              Calls
            </th>
            <th scope="col" className="num">
              Recorded
            </th>
            <th scope="col" className="num">
              Failed or cancelled
            </th>
            <th scope="col" className="num">
              Recorded audio
            </th>
          </tr>
        </thead>
        <tbody>
          {shown.map((p) => (
            <tr key={p.project_id}>
              <th scope="row">
                {/* The code in monospace, as in every list (D-159). */}
                <Link className="mono" to={`/projects/${p.project_id}`}>
                  {p.code}
                </Link>{" "}
                <span className="muted">{p.name}</span>
              </th>
              <td className="num">
                <CellBar value={p.calls} max={most}>
                  {p.calls}
                </CellBar>
              </td>
              <td className="num">{p.recorded}</td>
              <td className="num">{p.failed}</td>
              <td className="num">{minutes(p.recorded_minutes)}</td>
            </tr>
          ))}
        </tbody>
      </DataTable>
    </Panel>
  );
}

function Figures({
  data,
  allProjects,
  days,
}: {
  data: tel.CallAnalytics;
  allProjects: boolean;
  days: number;
}) {
  const target = data.target_minutes_per_day;
  const byProject = allProjects && data.by_project.length > 1;
  return (
    <div className="dash">
      {data.truncated ? (
        <p role="status" className="muted">
          This period has more calls than one page of figures can count: the newest 50,000 are
          shown. Choose a project or a shorter period.
        </p>
      ) : null}
      <FigureLine label="Call figures">
        <Figure label="Calls" value={String(data.calls)} note={`${data.in_call} on a call now`} />
        <Figure
          label="Recorded"
          value={String(data.recorded)}
          note={data.success_pct === null ? "No calls yet" : `${data.success_pct}% of calls`}
        />
        <Figure
          label="Failed or cancelled"
          value={String(data.dial_failed + data.cancelled)}
          note={`${data.dial_failed} not placed · ${data.cancelled} cancelled`}
        />
        <Figure
          label="Needs a person"
          value={String(data.needs_person)}
          note={`${data.stale_calls} left open · ${data.waiting_for_recording} being fetched`}
        />
        <Figure
          label="Average call"
          value={minutes(data.avg_call_minutes)}
          note={
            data.calls_per_task === null
              ? ""
              : `${plural(data.calls_per_task, "call")} for each task`
          }
        />
        <Figure
          label="Recorded audio"
          value={minutes(data.recorded_minutes)}
          note={`arrives ${minutes(data.avg_fetch_minutes)} after closing`}
        />
        <Figure
          label="Today"
          value={minutes(data.today_recorded_minutes)}
          note={
            target === null ? (
              "Recorded today"
            ) : target > 0 ? (
              // The target stays whole on a narrow screen: "(5.0 h)", never "(5.0" over "h)"
              // (D-159).
              <>
                {pct(data.today_recorded_minutes, target)}% of the daily target{" "}
                <span className="nowrap">({minutes(target)})</span>
              </>
            ) : (
              "No daily target set"
            )
          }
        />
        <Figure
          label="Tasks not called yet"
          value={String(data.tasks_not_called)}
          note={`${plural(data.tasks_called_again, "task")} called more than once`}
        />
      </FigureLine>
      <div className="dash-grid">
        <div className="panel g-8">
          <DayChart
            title="Calls per day"
            wholeNumbers
            height={180}
            days={data.by_day}
            emptyText="No calls in this period yet."
            series={[
              { label: "Recorded", className: "series--recorded", value: (d) => d.recorded },
              { label: "Still open", className: "series--open", value: (d) => d.open },
              { label: "Failed or cancelled", className: "series--failed", value: (d) => d.failed },
            ]}
            columns={[
              { label: "Calls", value: (d) => d.calls },
              { label: "Recorded", value: (d) => d.recorded },
              { label: "Recorded audio", value: (d) => minutes(d.recorded_minutes) },
              { label: "Still open", value: (d) => d.open },
              { label: "Failed or cancelled", value: (d) => d.failed },
            ]}
          />
        </div>
        {/* D-158: sections of about the same height share a row: the moderators beside the
            longer list of reasons, the phone tasks beside the checks and QC decisions. Two to a
            row on a middle-sized screen, where one without a partner takes the whole width
            ("mid-whole", calls.css). */}
        <Funnel className="g-4 mid-whole" funnel={data.funnel} />
        <ByModerator className="g-8" rows={data.by_moderator} />
        <Reasons
          className="g-4 mid-whole"
          title="Cancelled calls and recording problems"
          sections={[
            reasonSection(
              "cancelled",
              "Why calls were cancelled",
              data.cancel_reasons,
              tel.CANCEL_REASONS,
              "None in this period.",
            ),
            reasonSection(
              "problems",
              "Problems getting the recording",
              data.problems,
              tel.FAILURE_LABELS,
              "None in this period.",
            ),
          ]}
        />
        <Panel className="g-6" title="Phone tasks by status">
          <ShareTable
            label="Phone tasks by status"
            head="Stage"
            countHead="Tasks"
            parts={stageParts(data.tasks_by_status)}
            emptyText="No phone tasks yet."
          />
        </Panel>
        <Reasons
          className="g-6"
          title="Checks and QC decisions"
          sections={[
            reasonSection(
              "checks",
              "Automatic audio check of call recordings",
              data.automatic_checks,
              tel.AUTOMATIC_CHECK_LABELS,
              "No call recording checked in this period.",
            ),
            reasonSection(
              "qc",
              "QC decisions on call recordings",
              data.qc_decisions,
              tel.QC_DECISION_LABELS,
              "No QC decision in this period.",
            ),
          ]}
        />
        <CallsByHour className="" ours={data.by_hour} days={days} />
        {byProject ? <ByProject className="" rows={data.by_project} /> : null}
      </div>
    </div>
  );
}

/** A project filter shared by both views: every project the person can see, not only the
 * newest hundred. */
function ProjectSelect({ value, onChange }: { value: string; onChange: (id: string) => void }) {
  const projects = useResource(() => listAllProjects(), []);
  return (
    <Select
      label="Project"
      value={value}
      onChange={(e) => onChange(e.target.value)}
      options={[
        { value: "", label: "All my projects" },
        ...(projects.state.status === "loaded" ? projects.state.data.items : []).map((p) => ({
          value: p.id,
          label: `${p.code} · ${p.name}`,
        })),
      ]}
    />
  );
}

/** The title row, with its actions on the right. */
function Header({ title, lead, actions }: { title: string; lead: string; actions?: ReactNode }) {
  return (
    <div className="page-header">
      <div className="page-header__text">
        <h1 id="calls-title">{title}</h1>
        <p className="page-header__lead">{lead}</p>
      </div>
      {actions ? <div className="actions">{actions}</div> : null}
    </div>
  );
}

/** The one row of filters under the title (D-154), a white bar of its own (D-158). */
function Filters({ children }: { children: ReactNode }) {
  return (
    <div className="filters" role="group" aria-label="Filters">
      {children}
    </div>
  );
}

/** For people who make calls but do not assign tasks (moderators): their own calls, as a list
 * with links to the tasks. The figures are for the people who run the project (D-104). */
function MyCalls() {
  const [projectId, setProjectId] = useState("");
  return (
    <section aria-labelledby="calls-title" className="stack">
      <Header
        title="My phone calls"
        lead="The calls you made, newest first. Open a task to continue with its call."
      />
      <Filters>
        <ProjectSelect value={projectId} onChange={setProjectId} />
      </Filters>
      <CallList key={projectId} projectId={projectId} title="My calls" showModerator={false} />
    </section>
  );
}

export function CallsPage() {
  const { can } = useAuth();
  return can("tasks.assign") ? <CallFigures /> : <MyCalls />;
}

const VIEWS = [
  { id: "figures", label: "Figures" },
  { id: "calls", label: "All calls" },
] as const;

function CallFigures() {
  const [params, setParams] = useSearchParams();
  const view = params.get("view") === "calls" ? "calls" : "figures";
  const [projectId, setProjectId] = useState("");
  const [days, setDays] = useState(30);
  const download = useAction();
  const { state, reload } = useResource(
    () =>
      view === "figures"
        ? tel.callAnalytics({ project_id: projectId || undefined, days })
        : Promise.resolve(null),
    [projectId, days, view],
  );
  return (
    <section aria-labelledby="calls-title" className="stack calls-page">
      <Header
        title="Phone calls"
        lead="Calls made through TxContact: how many and how they ended. Times are in India time (IST), here and in the CSV."
        actions={
          <Button
            variant="secondary"
            icon="fileCsv"
            busy={download.busy !== null}
            onClick={() =>
              void download.run(() =>
                tel.downloadCallsCsv({ project_id: projectId || undefined, days }),
              )
            }
          >
            Download calls (CSV)
          </Button>
        }
      />
      {/* D-158: the filters, the tabs and the figures 12 px apart, as on the dashboard. */}
      <div className="calls-body">
        <Filters>
          <ProjectSelect value={projectId} onChange={setProjectId} />
          <Select
            label="Period"
            value={String(days)}
            onChange={(e) => setDays(Number(e.target.value))}
            options={[
              { value: "7", label: "Last 7 days" },
              { value: "30", label: "Last 30 days" },
              { value: "90", label: "Last 90 days" },
            ]}
          />
        </Filters>
        <ErrorNotice error={download.error} />
        <div className="tabs" role="tablist" aria-label="Phone call views">
          {VIEWS.map((v) => (
            <button
              key={v.id}
              type="button"
              role="tab"
              id={`calls-tab-${v.id}`}
              aria-selected={view === v.id}
              aria-controls="calls-panel"
              className={view === v.id ? "tabs__link active" : "tabs__link"}
              onClick={() =>
                setParams(v.id === "calls" ? { view: "calls" } : {}, { replace: true })
              }
            >
              {v.label}
            </button>
          ))}
        </div>
        <div
          id="calls-panel"
          role="tabpanel"
          aria-labelledby={`calls-tab-${view}`}
          className="stack"
        >
          {view === "calls" ? (
            // The calls of the period chosen above, as in the CSV (D-159). A new list for each
            // project and period: it starts again at its first page.
            <CallList
              key={`${projectId}-${days}`}
              projectId={projectId}
              days={days}
              title="All calls"
            />
          ) : (
            <>
              {state.status === "loading" ? <LoadingState label="Loading call figures" /> : null}
              {state.status === "failed" ? (
                <ErrorState error={state.error} onRetry={reload} />
              ) : null}
              {state.status === "loaded" && state.data ? (
                <Figures data={state.data} allProjects={projectId === ""} days={days} />
              ) : null}
            </>
          )}
        </div>
      </div>
    </section>
  );
}
