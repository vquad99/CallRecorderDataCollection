// The device each speaker used (D-147): the moderator fills it for both people before sending the
// recording to QC (on the task page, near Send to QC); from QC on everyone who sees the task reads
// it. Only the details the project asks are shown. "Same as last time" offers a person's details
// from their last conversation in the project; nothing is filled in by itself. The server judges
// again: Send to QC is refused while an asked detail is missing. One matrix (D-152): a row per
// detail, a column per speaker, the boxes and Yes / No switches in the cells.
import { useId, useState } from "react";

import * as devices from "../../api/devices";
import type * as work from "../../api/work";
import { DataTable } from "../../components/DataTable";
import { Button } from "../../components/form/Button";
import { ErrorNotice, SuccessNotice } from "../../components/Notice";
import { ErrorState, LoadingState } from "../../components/StateViews";
import { useAction } from "../../hooks/useAction";
import { useResource, type Resource } from "../../hooks/useResource";
import { when } from "../../lib/format";
import { DEVICE_FIELDS, deviceLabel, MAX_DEVICE_TEXT } from "./deviceFields";
import { Mark, YesNo } from "./Matrix";
import "./moderator.css";

type Side = "A" | "B";
type Values = devices.DeviceValues;

/** Why Send to QC waits for the device details, or null when it need not. */
export function devicesWait(task: work.TaskDetail): string | null {
  const missing = task.device_details_missing ?? [];
  return missing.length > 0
    ? `Fill in the device details of ${missing.join(" and ")} first (Device details card).`
    : null;
}

/** Statuses with device details: filled while In progress or Recorded, read only after. A
 * cancelled task keeps what was filled (FEW-10); its card shows only when something was. */
const SHOWS_DEVICES: readonly string[] = [
  "IN_PROGRESS",
  "RECORDED",
  "AUDIO_QC",
  "CONSENT_FIX",
  "ADMIN_REVIEW",
  "APPROVED",
  "REJECTED",
  "CANCELLED",
];

/** The task's device details, loaded once for the card and the participants matrix; nothing is
 * asked of the server where the project asks none or the session has not started. */
export function useDeviceDetails(task: work.TaskDetail) {
  const asked = Boolean(task.device_fields?.length) && SHOWS_DEVICES.includes(task.status);
  const resource = useResource<devices.DeviceDetails | null>(
    () => (asked ? devices.getDeviceDetails(task.id) : Promise.resolve(null)),
    [task.id, task.status, asked],
  );
  return { ...resource, asked };
}
export type DeviceResource = ReturnType<typeof useDeviceDetails>;

const valuesOf = (v: Values): Values => ({
  device_make: v.device_make,
  device_model: v.device_model,
  bluetooth_earphones: v.bluetooth_earphones,
  wired_earphones: v.wired_earphones,
  loudspeaker_on: v.loudspeaker_on,
});

const shown = (value: string | boolean | null) =>
  value === null || value === ""
    ? "Not answered"
    : value === true
      ? "Yes"
      : value === false
        ? "No"
        : value;

const partyOf = (task: work.TaskDetail, side: Side) =>
  side === "A" ? task.participant_a : task.participant_b;

/** A speaker's column heading: "Participant A", their code and, for people who may see it, name,
 * each on a line of its own (D-158: a name is never split across lines). */
function Who({ task, side }: { task: work.TaskDetail; side: Side }) {
  const p = partyOf(task, side);
  return (
    <span className="mx-who">
      <span className="mx-who__side">Participant {side}</span>{" "}
      <span className="mx-who__meta">
        <span className="code-tag">{p.participant_code}</span>
        {p.display_label ? (
          <>
            {" "}
            <span className="mx-who__name">{p.display_label}</span>
          </>
        ) : null}
      </span>
    </span>
  );
}

const toAnswer = (v: boolean | null) => (v === true ? "yes" : v === false ? "no" : null);

const startOf = (details: devices.DeviceDetails) =>
  Object.fromEntries(details.participants.map((p) => [p.side, valuesOf(p.details)])) as Record<
    Side,
    Values
  >;

/** The boxes and switches of both speakers; the section's title bar holds its Save (D-158). */
function DeviceForm({
  task,
  details,
  values,
  onChange,
}: {
  task: work.TaskDetail;
  details: devices.DeviceDetails;
  values: Record<Side, Values>;
  onChange: (side: Side, patch: Partial<Values>) => void;
}) {
  const set = onChange;
  const asked = DEVICE_FIELDS.filter((f) => details.fields.includes(f.key));
  const people = details.participants;
  return (
    <>
      <p className="field__hint devices__hint">
        Call type: {details.call_type}. Fill these for both speakers before you send the recording
        to QC.
      </p>
      <DataTable className="matrix devices-matrix" label="Device details of both speakers">
        <thead>
          <tr>
            <th scope="col">Detail</th>
            {people.map((p) => (
              <th key={p.side} scope="col" className={`mx-${p.side.toLowerCase()}`}>
                <Who task={task} side={p.side} />
                {p.last_time ? (
                  <Button
                    variant="secondary"
                    icon="history"
                    className="button button--secondary mx-last"
                    aria-label={`Same as last time (${p.last_time.task_code}) – Participant ${p.side}`}
                    onClick={() => p.last_time && set(p.side, valuesOf(p.last_time))}
                  >
                    Same as last time ({p.last_time.task_code})
                  </Button>
                ) : null}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {asked.map((f) => (
            <tr key={f.key}>
              <th scope="row">{f.label}</th>
              {people.map((p) => {
                const v = values[p.side][f.key];
                const name = `${f.label} – Participant ${p.side}`;
                return (
                  <td key={p.side}>
                    {f.yesNo ? (
                      <YesNo
                        label={name}
                        value={toAnswer(v as boolean | null)}
                        onChange={(a) => set(p.side, { [f.key]: a === "yes" })}
                      />
                    ) : (
                      <input
                        className="field__input mx-input"
                        aria-label={name}
                        maxLength={MAX_DEVICE_TEXT}
                        value={(v as string | null) ?? ""}
                        onChange={(e) => set(p.side, { [f.key]: e.target.value })}
                      />
                    )}
                  </td>
                );
              })}
            </tr>
          ))}
        </tbody>
        <tfoot>
          <tr>
            <th scope="row">Still to fill</th>
            {people.map((p) => {
              const left = asked.filter(
                (f) => values[p.side][f.key] === null || values[p.side][f.key] === "",
              );
              return (
                <td key={p.side} title={left.map((f) => f.label).join(", ") || undefined}>
                  {left.length > 0 ? (
                    <Mark ok={false}>
                      {left.length === 1 ? "1 detail" : `${left.length} details`}
                    </Mark>
                  ) : (
                    <Mark ok>Nothing</Mark>
                  )}
                </td>
              );
            })}
          </tr>
        </tfoot>
      </DataTable>
    </>
  );
}

/** Read only: what was filled, by whom and when, as the same matrix. */
function DeviceFacts({ task, details }: { task: work.TaskDetail; details: devices.DeviceDetails }) {
  const people = details.participants;
  return (
    <>
      <p className="field__hint devices__hint">Call type: {details.call_type}.</p>
      <DataTable className="matrix devices-matrix" label="Device details of both speakers">
        <thead>
          <tr>
            <th scope="col">Detail</th>
            {people.map((p) => (
              <th key={p.side} scope="col" className={`mx-${p.side.toLowerCase()}`}>
                <Who task={task} side={p.side} />
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {details.fields.map((key) => (
            <tr key={key}>
              <th scope="row">{deviceLabel(key)}</th>
              {people.map((p) => {
                const v = p.details[key];
                return (
                  <td key={p.side} className={v === null || v === "" ? "muted" : undefined}>
                    {shown(v)}
                  </td>
                );
              })}
            </tr>
          ))}
        </tbody>
        <tfoot>
          <tr>
            <th scope="row">Filled in</th>
            {people.map((p) => (
              <td key={p.side}>
                {p.filled_at
                  ? `Filled in by ${p.filled_by ?? "someone"}, ${when(p.filled_at)}.`
                  : "Not filled in."}
              </td>
            ))}
          </tr>
        </tfoot>
      </DataTable>
    </>
  );
}

function DeviceCard({
  task,
  resource,
  onSaved,
}: {
  task: work.TaskDetail;
  resource: DeviceResource;
  onSaved?: (() => void) | undefined;
}) {
  const titleId = useId();
  const { state, reload, replace } = resource;
  const { busy, error, message, run } = useAction();
  const details = state.status === "loaded" ? state.data : null;
  const editable = Boolean(details?.editable);
  // What is typed, until the server sends the details again: saved values come back from it (a
  // new filled_at), and the boxes start again from them.
  const stamp = details ? details.participants.map((p) => p.filled_at ?? "").join("|") : "";
  const [draft, setDraft] = useState<{ stamp: string; values: Record<Side, Values> } | null>(null);
  const start = details ? startOf(details) : null;
  const values = draft && draft.stamp === stamp ? draft.values : start;
  const changed = JSON.stringify(values) !== JSON.stringify(start);
  const set = (side: Side, patch: Partial<Values>) => {
    if (values) setDraft({ stamp, values: { ...values, [side]: { ...values[side], ...patch } } });
  };
  // A cancelled task: the card only when someone filled the details before it ended (FEW-10).
  const filled = Boolean(details?.participants.some((p) => p.filled_at));
  if (task.status === "CANCELLED" && state.status !== "failed" && !filled) return null;
  // D-158: one Save, on the section's title bar, the form round the whole section (as the
  // project's Rules); the matrix runs edge to edge under the bar.
  return (
    <form
      noValidate
      onSubmit={(e) => {
        e.preventDefault();
        if (!details || !values || !editable) return;
        const entries = details.participants.map((p) => ({ side: p.side, ...values[p.side] }));
        void run(async () => {
          replace(await devices.saveDeviceDetails(task.id, entries));
          onSaved?.();
          return "Device details saved.";
        });
      }}
    >
      <section className="card devices-card" aria-labelledby={titleId}>
        <div className="card__head">
          <h2 id={titleId}>Device details</h2>
          {editable ? (
            <Button type="submit" icon="check" busy={busy !== null} disabled={!changed}>
              Save device details
            </Button>
          ) : null}
        </div>
        {state.status === "loading" ? <LoadingState /> : null}
        {state.status === "failed" ? <ErrorState error={state.error} onRetry={reload} /> : null}
        <ErrorNotice error={error} />
        <SuccessNotice message={message} />
        {details && values && editable ? (
          <DeviceForm task={task} details={details} values={values} onChange={set} />
        ) : details ? (
          <DeviceFacts task={task} details={details} />
        ) : null}
      </section>
    </form>
  );
}

/** The card loading its own details (the recorder, where nothing else shows them). */
function OwnDeviceCard({
  task,
  onSaved,
}: {
  task: work.TaskDetail;
  onSaved?: (() => void) | undefined;
}) {
  const resource = useDeviceDetails(task);
  if (!resource.asked) return null;
  return <DeviceCard task={task} resource={resource} onSaved={onSaved} />;
}

/** The card, where the project asks device details; `onSaved` lets the page load the task again
 * (its Send to QC follows what is still missing). `resource`: the details the page loaded once
 * (the task page shares them with its participants matrix); without it the card loads them. */
export function DeviceDetailsCard({
  task,
  resource,
  onSaved,
}: {
  task: work.TaskDetail;
  resource?: DeviceResource;
  onSaved?: (() => void) | undefined;
}) {
  if (!resource) return <OwnDeviceCard task={task} onSaved={onSaved} />;
  if (!resource.asked) return null;
  return <DeviceCard task={task} resource={resource} onSaved={onSaved} />;
}

/** One speaker's device details in a word, for the participants matrix: filled, missing, or not
 * asked yet (before the session). */
export function deviceState(
  task: work.TaskDetail,
  resource: DeviceResource,
  side: Side,
): { ok: boolean | null; text: string; title?: string } {
  const data: Resource<devices.DeviceDetails | null> = resource.state;
  if (!resource.asked) return { ok: null, text: "Not yet" };
  if (data.status !== "loaded" || !data.data) return { ok: null, text: "…" };
  const p = data.data.participants.find((x) => x.side === side);
  if (!p) return { ok: null, text: "-" };
  if (p.missing.length === 0)
    return {
      ok: true,
      text: "Filled",
      title: p.filled_at ? `Filled in by ${p.filled_by ?? "someone"}, ${when(p.filled_at)}` : "",
    };
  const missingCodes = task.device_details_missing ?? [];
  return {
    ok: false,
    text: missingCodes.length > 0 || data.data.editable ? "Missing" : "Not filled",
    title: p.missing.map(deviceLabel).join(", "),
  };
}
