// A project's Progress tab (D-148; plain tables since D-153): what was collected against the
// project's targets, and what is still needed to finish. The key figures in one line; "Still
// needed" near the top for the people who recruit (speakers by age band and gender, by district,
// the conversations still to make, and whether the registered people can give them); the shares
// in one balance table; the conversations by status and the completed minutes as two small
// tables; the definitions folded away. On the title row, the tab as a file (owner's request; D-158
// puts the buttons there as on every page, and when the figures were read under the title): Excel
// with a sheet per table, one long CSV table, or the browser's print (Save as PDF) as a clean
// report: the menus left out, every row shown, the definitions open. For the people who manage
// the project, like the other tabs (D-104). Loaded with the tab, not with the first screen.
import { useEffect, useId, useRef, useState, type RefObject } from "react";
import { flushSync } from "react-dom";

import { apiDownload } from "../../api/client";
import {
  getProgress,
  progressExportPath,
  type AgeGenderNeed,
  type ConversationNeed,
  type Need,
  type ProgressExportFormat,
  type ProjectProgress,
  type Share,
  type ShareRow,
  type StillNeeded,
} from "../../api/progress";
import {
  Figure,
  FigureLine,
  MatrixTable,
  Panel,
  ShareTable,
  TargetBar,
  type MatrixSection,
} from "../../components/charts/Charts";
import { stageParts } from "../../components/charts/stages";
import { DataTable } from "../../components/DataTable";
import { Button } from "../../components/form/Button";
import { ErrorNotice } from "../../components/Notice";
import { ErrorState, LoadingState } from "../../components/StateViews";
import { useAction } from "../../hooks/useAction";
import { useFirstRows } from "../../hooks/useFirstRows";
import { useResource } from "../../hooks/useResource";
import { when } from "../../lib/format";
import { PageActions, PageLead, useProject } from "./ProjectDetailPage";
import "./progress.css";

/** A length for people: "6 h 12 min", "45 min", "30 s". */
export function spokenLength(ms: number): string {
  const seconds = Math.round(ms / 1000);
  if (seconds < 60) return `${seconds} s`;
  const minutes = Math.round(seconds / 60);
  if (minutes < 60) return `${minutes} min`;
  const h = Math.floor(minutes / 60);
  const m = minutes % 60;
  return m ? `${h} h ${m} min` : `${h} h`;
}

const number = (n: number) => (Number.isInteger(n) ? String(n) : n.toFixed(1));
/** A percent, as the rest of the app writes one: "40%", "12.5%". */
const pct = (n: number) => `${number(n)}%`;
/** A variance in percentage points: "+4%", "−6%", "0%". */
export const variance = (n: number) =>
  n > 0 ? `+${number(n)}%` : n < 0 ? `−${number(-n)}%` : "0%";
/** "1 speaker", "3 speakers". */
const count = (n: number, one: string, many = `${one}s`) => `${n} ${n === 1 ? one : many}`;

const BASIS = {
  speakers: (n: number) =>
    `Percent of the ${n} speaker${n === 1 ? "" : "s"} with an approved conversation.`,
  conversations: (n: number) => `Percent of the ${n} approved conversation${n === 1 ? "" : "s"}.`,
};

/** Districts shown before "Show all": the client's list has eight. */
const FIRST_DISTRICTS = 10;

// ---------------------------------------------------------------------- still needed (D-153)

/** A still-needed number: bold, green when nothing more is needed, "-" without a target (D-158). */
function Still({ n }: { n: number | null }) {
  if (n === null) return <span className="need need--none">-</span>;
  return <span className={n === 0 ? "need need--met" : "need"}>{n}</span>;
}

/** One cell of the age band x gender matrix: still needed in bold, then the target, done and
 * registered in small type. */
function NeedCell({ need, what }: { need: Need; what: string }) {
  const parts = [
    ...(need.target === null ? [] : [`target ${need.target}`]),
    `done ${need.done}`,
    `registered ${need.registered}`,
  ];
  return (
    <td
      className="num need-cell"
      title={`${what}: ${need.still_needed === null ? "no target" : `${need.still_needed} still needed`}, ${parts.join(", ")}`}
    >
      <Still n={need.still_needed} />
      {/* One line on a wide screen ("target 100 · done 2 · registered 0"), one each on a phone. */}
      <span className="need__sub">
        {parts.map((p) => (
          <span key={p} className="need__part">
            {p}
          </span>
        ))}
      </span>
    </td>
  );
}

/** How to read the matrix, above it (a caption would scroll away with the table on a phone). */
function MatrixKey({ byGender }: { byGender: boolean }) {
  return (
    <p className="muted needs-key">
      In bold: speakers still needed. Under it: the target, those done (an approved conversation)
      and those registered (in the project, no approved conversation yet).
      {byGender ? " Total: everyone, people without a gender too." : ""}
    </p>
  );
}

function SpeakersMatrix({ speakers }: { speakers: StillNeeded["speakers"] }) {
  const row = (r: AgeGenderNeed, total = false) => (
    <tr key={r.key}>
      <th scope="row">{r.label}</th>
      <NeedCell need={r.male} what={`${total ? "All ages" : r.label}, male`} />
      <NeedCell need={r.female} what={`${total ? "All ages" : r.label}, female`} />
      <NeedCell need={r.total} what={`${total ? "All ages" : r.label}, everyone`} />
    </tr>
  );
  return (
    <DataTable label="Speakers still needed by age band and gender" className="needs" bleed>
      <thead>
        <tr>
          <th scope="col">{speakers.by_age ? "Age band" : "Ages"}</th>
          <th scope="col" className="num">
            Male
          </th>
          <th scope="col" className="num">
            Female
          </th>
          <th scope="col" className="num">
            Total
          </th>
        </tr>
      </thead>
      <tbody>{speakers.rows.map((r) => row(r))}</tbody>
      {speakers.rows.length > 1 ? <tfoot>{row(speakers.total, true)}</tfoot> : null}
    </DataTable>
  );
}

function DistrictsTable({ districts }: { districts: StillNeeded["districts"] }) {
  if (!districts.has_target)
    return (
      <p className="muted">
        No districts listed: list them on the Rules tab (Targets) to see who is needed by district.
      </p>
    );
  const cells = (d: StillNeeded["districts"]["rows"][number]) => (
    <>
      <td className="num">{d.target ?? "-"}</td>
      <td className="num">{d.done}</td>
      <td className="num">{d.registered}</td>
      <td className="num">
        <Still n={d.still_needed} />
      </td>
    </>
  );
  return (
    <DataTable label="Speakers still needed by native district" bleed>
      <thead>
        <tr>
          <th scope="col">Native district</th>
          <th scope="col" className="num">
            Target
          </th>
          <th scope="col" className="num">
            Done
          </th>
          <th scope="col" className="num">
            Registered
          </th>
          <th scope="col" className="num">
            Still needed
          </th>
        </tr>
      </thead>
      <tbody>
        {districts.rows.map((d) => (
          <tr key={d.key}>
            <th scope="row">{d.label}</th>
            {cells(d)}
          </tr>
        ))}
      </tbody>
      {districts.total ? (
        <tfoot>
          <tr>
            <th scope="row">Total</th>
            {cells(districts.total)}
          </tr>
        </tfoot>
      ) : null}
    </DataTable>
  );
}

function ConversationsTable({ rows }: { rows: ConversationNeed[] }) {
  return (
    <DataTable label="Conversations still to make" bleed>
      <thead>
        <tr>
          {/* The sub-heading says it: for screen readers only, as on the dashboard (D-159). */}
          <th scope="col">
            <span className="sr-only">Conversations</span>
          </th>
          <th scope="col" className="num">
            Target
          </th>
          <th scope="col" className="num">
            Approved
          </th>
          <th scope="col" className="num">
            Open tasks
          </th>
          <th scope="col" className="num">
            Still to make
          </th>
        </tr>
      </thead>
      <tbody>
        {rows.map((c) => (
          <tr key={c.key}>
            <th scope="row">{c.label}</th>
            <td className="num">{c.target ?? "-"}</td>
            <td className="num">{c.approved}</td>
            <td className="num">{c.in_pipeline}</td>
            <td className="num">
              <Still n={c.still_to_make} />
            </td>
          </tr>
        ))}
      </tbody>
    </DataTable>
  );
}

/** Whether the registered speakers can give the conversations still to make, in one sentence,
 * from the server's count of more speakers needed: it weighs each conversation's two speakers,
 * the conversations per speaker and, when the project says so, each pair only once (D-143). */
export function capacityText(capacity: StillNeeded["capacity"]): string | null {
  const { limit, registered, conversations_to_make: toMake } = capacity;
  if (toMake === null) return null;
  if (toMake === 0) return "No more conversations are needed beyond the open tasks.";
  const people = count(registered, "registered speaker");
  const talks = `the ${count(toMake, "conversation")} still to make`;
  const pairs = capacity.unique_pairs ? " (each pair of speakers only once)" : "";
  const rules = [
    ...(limit === null ? [] : [`each at most ${count(limit, "conversation")}`]),
    ...(capacity.unique_pairs ? ["each pair of speakers only once"] : []),
  ];
  const more = capacity.more_speakers_needed ?? 0;
  if (more === 0)
    return `The ${people} can give ${talks}${rules.length > 0 ? ` (${rules.join(", ")})` : ""}.`;
  const needed = `${count(more, "more speaker")} ${more === 1 ? "is" : "are"} needed for ${talks}`;
  if (limit !== null && registered > 0)
    return `Even if every one of the ${people} records ${count(limit, "conversation")}, ${needed}${pairs}.`;
  return `${needed} (${rules.length > 0 ? rules.join(", ") : "a conversation takes two speakers"}).`;
}

function StillNeededPanel({ needed }: { needed: StillNeeded }) {
  const speakers = needed.speakers.total.total.still_needed;
  const toMake = needed.conversations[0]?.still_to_make ?? null;
  const parts = [
    ...(speakers === null ? [] : [count(speakers, "more speaker")]),
    ...(toMake === null ? [] : [count(toMake, "more conversation")]),
  ];
  const capacity = capacityText(needed.capacity);
  const id = useId();
  // No note on the bar: the first line under it starts "To reach the targets" (D-159).
  return (
    <Panel title="Still needed">
      <p className="needs-lead">
        {parts.length > 0 ? (
          <>
            To reach the targets: <strong>{parts.join(" and ")}</strong>.
          </>
        ) : (
          "No speakers or conversations target: set them on the Rules tab (Targets)."
        )}
        {capacity ? ` ${capacity}` : ""}
      </p>
      {/* Three parts, each under a line edge to edge, its table edge to edge too (D-158). */}
      <section className="needs-part stack stack--tight" aria-labelledby={`${id}-ages`}>
        <h3 id={`${id}-ages`} className="subhead">
          Speakers by age band and gender
        </h3>
        {needed.speakers.target === null ? (
          <p className="muted">No speakers target: the table shows who there is.</p>
        ) : null}
        <MatrixKey byGender={needed.speakers.by_gender} />
        <SpeakersMatrix speakers={needed.speakers} />
      </section>
      <section className="needs-part stack stack--tight" aria-labelledby={`${id}-districts`}>
        <h3 id={`${id}-districts`} className="subhead">
          Speakers by native district
        </h3>
        <DistrictsTable districts={needed.districts} />
      </section>
      <section className="needs-part stack stack--tight" aria-labelledby={`${id}-talks`}>
        <h3 id={`${id}-talks`} className="subhead">
          Conversations
        </h3>
        <ConversationsTable rows={needed.conversations} />
      </section>
    </Panel>
  );
}

// ---------------------------------------------------------------------- the shares (D-148)

interface Group {
  key: string;
  title: string;
  share: Share;
  noTarget: string;
}

/** Every share in one table: a section per group, the actual count and percent against the
 * target percent, the variance, and a bar with a tick at the target. `districts` are the
 * districts shown: the first ones, or all of them on request and when printed. */
function BalanceMatrix({ data, districts }: { data: ProjectProgress; districts: ShareRow[] }) {
  const groups: Group[] = [
    {
      key: "age",
      title: "Age bands",
      share: data.age_bands,
      noTarget: "No age bands set: add them on the Rules tab.",
    },
    { key: "gender", title: "Gender", share: data.gender, noTarget: "No gender target set." },
    // A project that records one type has no split by type (D-153).
    ...(data.modes
      ? [
          {
            key: "modes",
            title: "Face-to-face and phone",
            share: data.modes,
            noTarget: "No target set.",
          },
        ]
      : []),
    {
      key: "districts",
      title: "Districts",
      share: { ...data.districts, rows: districts },
      noTarget: "No districts listed: the speakers' own native districts.",
    },
  ];
  // Each section's bars on its own scale (12.5 % of eight districts would be a sliver of 100).
  const scale = new Map(
    groups.map((g) => [
      g.key,
      Math.min(
        100,
        1.1 * Math.max(1, ...g.share.rows.map((r) => Math.max(r.percent, r.target_percent ?? 0))),
      ),
    ]),
  );
  const sections: MatrixSection<ShareRow & { group: string }>[] = groups.map((g) => ({
    key: g.key,
    title: g.title,
    note: `${g.share.total === 0 ? "No approved conversations yet." : BASIS[g.share.basis](g.share.total)}${g.share.has_target ? "" : ` ${g.noTarget}`}`,
    rows: g.share.total === 0 ? [] : g.share.rows.map((r) => ({ ...r, group: g.key })),
  }));
  return (
    <MatrixTable
      label="Balance against the targets"
      head="Group"
      groups={[
        { label: "Actual", span: 3, tone: "blue" },
        { label: "Target", span: 2, tone: "teal" },
      ]}
      columns={[
        { key: "count", label: "Count", num: true, cell: (r) => r.count },
        { key: "percent", label: "Share", num: true, cell: (r) => pct(r.percent) },
        {
          key: "bar",
          label: <span className="sr-only">Share against the target</span>,
          cell: (r) => (
            <TargetBar
              value={r.percent}
              target={r.target_percent}
              max={scale.get(r.group) ?? 100}
            />
          ),
        },
        {
          key: "target",
          label: "Share",
          num: true,
          cell: (r) => (r.target_percent === null ? "-" : pct(r.target_percent)),
        },
        {
          key: "variance",
          label: "Variance",
          num: true,
          cell: (r) =>
            r.variance === null ? (
              "-"
            ) : (
              <span
                className={
                  r.variance < 0
                    ? "variance variance--below"
                    : r.variance > 0
                      ? "variance variance--above"
                      : "variance"
                }
              >
                {variance(r.variance)}
              </span>
            ),
        },
      ]}
      sections={sections}
      rowKey={(r) => r.key}
      rowLabel={(r) => r.label}
    />
  );
}

// ---------------------------------------------------------------------- the page

/** Approved, and recorded but not yet approved: how many, their full length, their speech. */
function CompletedTable({ done }: { done: ProjectProgress["completed"] }) {
  const rows = [
    {
      key: "approved",
      label: "Approved",
      n: done.approved_conversations,
      full: done.approved_ms,
      speech: done.approved_effective_ms,
    },
    {
      key: "recorded",
      label: "Recorded, not yet approved",
      n: done.recorded_conversations,
      full: done.recorded_ms,
      speech: done.recorded_effective_ms,
    },
  ];
  return (
    <DataTable label="Completed">
      <thead>
        <tr>
          <th scope="col">Conversations</th>
          <th scope="col" className="num">
            Number
          </th>
          <th scope="col" className="num">
            Full length
          </th>
          <th scope="col" className="num">
            Effective speech
          </th>
        </tr>
      </thead>
      <tbody>
        {rows.map((r) => (
          <tr key={r.key}>
            <th scope="row">{r.label}</th>
            <td className="num">{r.n}</td>
            <td className="num">{spokenLength(r.full)}</td>
            <td className="num">{spokenLength(r.speech)}</td>
          </tr>
        ))}
      </tbody>
    </DataTable>
  );
}

/** True while the browser prints the page or saves it as PDF (from the button or its own menu):
 * the page then shows every row, and the definitions (`notes`) are opened for the print and
 * closed again after it unless they were open. */
function usePrintView(notes: RefObject<HTMLDetailsElement | null>): boolean {
  const [printing, setPrinting] = useState(false);
  useEffect(() => {
    let wasOpen = false;
    const before = () => {
      // At once: the browser lays the page out for printing as soon as this returns.
      flushSync(() => setPrinting(true));
      if (notes.current) {
        wasOpen = notes.current.open;
        notes.current.open = true;
      }
    };
    const after = () => {
      setPrinting(false);
      if (notes.current) notes.current.open = wasOpen;
    };
    window.addEventListener("beforeprint", before);
    window.addEventListener("afterprint", after);
    return () => {
      window.removeEventListener("beforeprint", before);
      window.removeEventListener("afterprint", after);
    };
  }, [notes]);
  return printing;
}

/** The tab as a file (owner's request): an Excel workbook with a sheet per table, one long CSV
 * table (both made by the server from the same answer, audited), or the browser's print, which
 * also saves a PDF. On the page's title row (D-158): when the figures were read under the title,
 * the buttons on the right. A printed page starts with the project and the time of its figures. */
function ReportActions({ asOf }: { asOf: string }) {
  const { project } = useProject();
  const { busy, error, run } = useAction();
  const download = (format: ProgressExportFormat) =>
    void run(() => apiDownload(progressExportPath(project.id, format)), format);
  return (
    <>
      <PageLead>Figures as of {when(asOf)}</PageLead>
      <PageActions>
        <Button
          variant="secondary"
          icon="table"
          busy={busy === "xlsx"}
          onClick={() => download("xlsx")}
        >
          Download Excel
        </Button>
        <Button
          variant="secondary"
          icon="fileCsv"
          busy={busy === "csv"}
          onClick={() => download("csv")}
        >
          Download CSV
        </Button>
        <Button variant="secondary" icon="fileText" onClick={() => window.print()}>
          Print or save as PDF
        </Button>
      </PageActions>
      <ErrorNotice error={error} />
      <p className="progress-print-head">
        {project.code} · {project.name} · as of {when(asOf)}
      </p>
    </>
  );
}

function Body({ data, asOf }: { data: ProjectProgress; asOf: string }) {
  const done = data.completed;
  const effective = done.counts === "EFFECTIVE";
  const counted = effective ? "effective speech" : "full length";
  const talks = data.conversations;
  const people = data.speakers;
  const targetMs = done.target_hours === null ? null : done.target_hours * 3_600_000;
  const ofTarget = (percent: number | null) =>
    percent === null ? "No target set." : `${pct(percent)} of the target`;
  const notes = useRef<HTMLDetailsElement>(null);
  const printing = usePrintView(notes);
  // The first districts, the rest on request: the button on the section's title bar, as on the
  // dashboard (D-158). Printed, every district.
  const districts = useFirstRows(
    data.districts.rows,
    printing ? data.districts.rows.length : FIRST_DISTRICTS,
  );
  return (
    <div className="dash progress">
      <ReportActions asOf={asOf} />
      {talks.approved === 0 ? (
        <p className="notice notice--info">
          No approved conversations yet: the figures fill in as conversations are approved.
        </p>
      ) : null}
      <FigureLine label="Against the targets">
        <Figure
          label="Completed"
          value={spokenLength(done.completed_ms)}
          of={targetMs === null ? undefined : `of ${spokenLength(targetMs)}`}
          note={
            targetMs === null
              ? "No hours target: set one on the Rules tab."
              : `${ofTarget(done.percent_of_target)}, ${counted}`
          }
        />
        <Figure
          label="Approved conversations"
          value={String(talks.approved)}
          of={talks.target === null ? undefined : `/ ${talks.target}`}
          note={ofTarget(talks.percent_of_target)}
        />
        <Figure
          label="Speakers"
          value={String(people.with_approved)}
          of={people.target === null ? undefined : `/ ${people.target}`}
          note={
            people.target === null
              ? "with an approved conversation"
              : ofTarget(people.percent_of_target)
          }
        />
        <Figure
          label="Registered"
          value={String(people.registered)}
          note={
            people.limit === null || people.at_limit === null
              ? "in the project; no limit per speaker"
              : `in the project; ${people.at_limit} at the limit of ${count(people.limit, "conversation")}`
          }
        />
        <Figure
          label="Effective speech"
          value={done.effective_share_pct === null ? "-" : pct(done.effective_share_pct)}
          note="of the recorded audio"
        />
      </FigureLine>

      <StillNeededPanel needed={data.still_needed} />

      {/* What the variance is, as the first line under the bar, so the bar keeps to one row on a
          phone; the districts' Show all stays on the bar (D-159). */}
      <Panel title="Balance against the targets" action={districts.more}>
        <p className="muted">Variance: actual minus target.</p>
        <BalanceMatrix data={data} districts={districts.shown} />
      </Panel>

      {/* Each a full row (D-159): side by side, the shorter was stretched to the other's height,
          white space under its table, and its row names broke over two lines. */}
      <Panel title="Conversations by status">
        <ShareTable
          label="Conversations by status"
          head="Stage"
          countHead="Tasks"
          parts={stageParts(talks.by_status)}
          emptyText="No conversations yet."
        />
      </Panel>
      <Panel title="Completed">
        <CompletedTable done={done} />
        {done.not_measured > 0 ? (
          <p className="muted">
            {done.not_measured} approved conversation{done.not_measured === 1 ? " is" : "s are"} not
            measured yet: each counts as none until it is (shortly after it was made).
          </p>
        ) : null}
      </Panel>

      <details className="dash-notes" ref={notes}>
        <summary>How these are counted</summary>
        <dl className="definitions">
          <dt>Effective speech</dt>
          <dd>
            The time someone speaks in a recording: silence (quieter than −50 dBFS on every channel)
            is left out; gaps under 0.3 s between words count as speech and a sound under 0.1 s on
            its own (a click) does not. Measured by level, so loud background noise counts as
            speech; QC listens for noise.
          </dd>
          <dt>Completed</dt>
          <dd>
            The {counted} of the approved conversations, as the project&apos;s rules say (Rules tab,
            Audio and progress).
          </dd>
          <dt>Long pauses</dt>
          <dd>
            Silences inside the conversation longer than {data.pause_limit_seconds} s (the
            project&apos;s limit). The automatic check counts them.
          </dd>
          <dt>Still needed</dt>
          <dd>
            Each group&apos;s target is the speakers target shared out by the age band&apos;s
            percent times the gender&apos;s percent, or a district&apos;s equal share, in whole
            people that add up to the target: each group first gets the whole part of its share and
            the people left over go to the largest fractions. Done: speakers in the group with an
            approved conversation. Registered: people in the project with details in the group and
            no approved conversation yet. Still needed: the target less done and registered, never
            below 0. A total adds up its groups, so extra people in one group do not fill another,
            and people without an age, gender or district fill none.
          </dd>
          <dt>Conversations still to make</dt>
          <dd>
            The target less the approved conversations and the open tasks (not started, in progress,
            waiting for QC or approval). Each conversation needs two speakers; each speaker gives at
            most the project&apos;s conversations per speaker (rejected and cancelled ones aside)
            and, when the project says so, talks with each other speaker only once. More speakers
            needed: the fewest more people with whom the registered ones could give them all.
          </dd>
          <dt>Speakers and shares</dt>
          <dd>
            Speakers are the people with at least one approved conversation, each counted once. Age
            bands, gender and districts are shares of them, with their details as they are now
            (district: native district).
            {data.modes
              ? " Face-to-face and phone are shares of the approved conversations."
              : ""}{" "}
            People without a detail are under “Not given”. Each section&apos;s bars have their own
            scale; the tick is the target.
          </dd>
          <dt>Variance</dt>
          <dd>The actual percent minus the target percent: +4% is above the target, −6% below.</dd>
        </dl>
      </details>
    </div>
  );
}

export function ProgressTab() {
  const { project } = useProject();
  // The figures with the time they were read: what "as of" says on the page and when printed.
  const { state, reload } = useResource(
    () => getProgress(project.id).then((data) => ({ data, asOf: new Date().toISOString() })),
    [project.id],
  );
  if (state.status === "loading") return <LoadingState label="Loading progress" />;
  if (state.status === "failed") return <ErrorState error={state.error} onRetry={reload} />;
  return <Body data={state.data.data} asOf={state.data.asOf} />;
}
