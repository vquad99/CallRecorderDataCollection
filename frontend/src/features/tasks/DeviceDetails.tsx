// The device each speaker used (D-147): the moderator fills it for both people before sending the
// recording to QC (on the task page and on the recorder, near Send to QC); from QC on everyone who
// sees the task reads it. Only the details the project asks are shown. "Same as last time" offers
// a person's details from their last conversation in the project; nothing is filled in by itself.
// The server judges again: Send to QC is refused while an asked detail is missing.
import { useId, useState } from "react";

import * as devices from "../../api/devices";
import type * as work from "../../api/work";
import { Button } from "../../components/form/Button";
import { TextField } from "../../components/form/TextField";
import { IconTile } from "../../components/Icon";
import { ErrorNotice, SuccessNotice } from "../../components/Notice";
import { ErrorState, LoadingState } from "../../components/StateViews";
import { useAction } from "../../hooks/useAction";
import { useResource } from "../../hooks/useResource";
import { when } from "../../lib/format";
import { DEVICE_FIELDS, deviceLabel, MAX_DEVICE_TEXT } from "./deviceFields";
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

/** "Participant A P000001 Asha": the code, and the name for people who may see it. */
function Who({ task, side }: { task: work.TaskDetail; side: Side }) {
  const p = side === "A" ? task.participant_a : task.participant_b;
  return (
    <>
      Participant {side} <span className="code-tag">{p.participant_code}</span>
      {p.display_label ? ` ${p.display_label}` : null}
    </>
  );
}

/** Yes and No as two radio buttons under the question. */
function YesNo({
  label,
  value,
  onChange,
}: {
  label: string;
  value: boolean | null;
  onChange: (value: boolean) => void;
}) {
  const name = useId();
  return (
    <fieldset className="field">
      <legend className="field__label">{label}</legend>
      <span className="device__choices">
        {[true, false].map((choice) => (
          <label key={String(choice)} className="checkbox">
            <input
              type="radio"
              name={name}
              checked={value === choice}
              onChange={() => onChange(choice)}
            />
            {choice ? "Yes" : "No"}
          </label>
        ))}
      </span>
    </fieldset>
  );
}

function DeviceForm({
  task,
  details,
  busy,
  onSave,
}: {
  task: work.TaskDetail;
  details: devices.DeviceDetails;
  busy: boolean;
  onSave: (entries: (Values & { side: Side })[]) => void;
}) {
  const start = Object.fromEntries(
    details.participants.map((p) => [p.side, valuesOf(p.details)]),
  ) as Record<Side, Values>;
  const [values, setValues] = useState(start);
  const set = (side: Side, patch: Partial<Values>) =>
    setValues({ ...values, [side]: { ...values[side], ...patch } });
  const asked = DEVICE_FIELDS.filter((f) => details.fields.includes(f.key));
  const changed = JSON.stringify(values) !== JSON.stringify(start);
  return (
    <form
      noValidate
      onSubmit={(e) => {
        e.preventDefault();
        onSave(details.participants.map((p) => ({ side: p.side, ...values[p.side] })));
      }}
    >
      <p className="field__hint devices__hint">
        Call type: {details.call_type}. Fill these for both speakers before you send the recording
        to QC.
      </p>
      <div className="devices">
        {details.participants.map((p) => {
          const v = values[p.side];
          const left = asked.filter((f) => v[f.key] === null || v[f.key] === "");
          return (
            <fieldset key={p.side} className="device">
              <legend className="device__who">
                <Who task={task} side={p.side} />
              </legend>
              {p.last_time ? (
                <div className="device__last">
                  <Button
                    variant="secondary"
                    icon="history"
                    onClick={() => p.last_time && set(p.side, valuesOf(p.last_time))}
                  >
                    Same as last time ({p.last_time.task_code})
                  </Button>
                </div>
              ) : null}
              <div className="form-grid">
                {asked
                  .filter((f) => !f.yesNo)
                  .map((f) => (
                    <TextField
                      key={f.key}
                      label={f.label}
                      maxLength={MAX_DEVICE_TEXT}
                      value={(v[f.key] as string | null) ?? ""}
                      onChange={(e) => set(p.side, { [f.key]: e.target.value })}
                    />
                  ))}
              </div>
              <div className="device__yesno">
                {asked
                  .filter((f) => f.yesNo)
                  .map((f) => (
                    <YesNo
                      key={f.key}
                      label={f.label}
                      value={v[f.key] as boolean | null}
                      onChange={(answer) => set(p.side, { [f.key]: answer })}
                    />
                  ))}
              </div>
              {left.length > 0 ? (
                <p className="muted device__last">
                  Still to fill: {left.map((f) => f.label).join(", ")}.
                </p>
              ) : null}
            </fieldset>
          );
        })}
      </div>
      <div className="actions">
        <Button type="submit" icon="check" busy={busy} disabled={!changed}>
          Save device details
        </Button>
      </div>
    </form>
  );
}

/** Read only: what was filled, by whom and when. */
function DeviceFacts({ task, details }: { task: work.TaskDetail; details: devices.DeviceDetails }) {
  return (
    <>
      <p className="field__hint devices__hint">Call type: {details.call_type}.</p>
      <div className="devices">
        {details.participants.map((p) => (
          <div key={p.side} className="device">
            <h3 className="device__who">
              <Who task={task} side={p.side} />
            </h3>
            <dl className="checks">
              {details.fields.map((key) => (
                <div key={key} className="checks__row">
                  <dt>{deviceLabel(key)}</dt>
                  <dd>{shown(p.details[key])}</dd>
                </div>
              ))}
            </dl>
            <p className="muted device__last">
              {p.filled_at
                ? `Filled in by ${p.filled_by ?? "someone"}, ${when(p.filled_at)}.`
                : "Not filled in."}
            </p>
          </div>
        ))}
      </div>
    </>
  );
}

function DeviceCard({
  task,
  onSaved,
}: {
  task: work.TaskDetail;
  onSaved?: (() => void) | undefined;
}) {
  const titleId = useId();
  const { state, reload, replace } = useResource(
    () => devices.getDeviceDetails(task.id),
    [task.id, task.status],
  );
  const { busy, error, message, run } = useAction();
  const save = (entries: (Values & { side: Side })[]) =>
    void run(async () => {
      replace(await devices.saveDeviceDetails(task.id, entries));
      onSaved?.();
      return "Device details saved.";
    });
  return (
    <section className="card" aria-labelledby={titleId}>
      <h2 id={titleId} className="with-icon">
        <IconTile name="phone" size={28} />
        Device details
      </h2>
      {state.status === "loading" ? <LoadingState /> : null}
      {state.status === "failed" ? <ErrorState error={state.error} onRetry={reload} /> : null}
      {state.status === "loaded" ? (
        state.data.editable ? (
          <DeviceForm
            // Saved values come back from the server: the form starts again from them.
            key={state.data.participants.map((p) => p.filled_at ?? "").join("|")}
            task={task}
            details={state.data}
            busy={busy !== null}
            onSave={save}
          />
        ) : (
          <DeviceFacts task={task} details={state.data} />
        )
      ) : null}
      <ErrorNotice error={error} />
      <SuccessNotice message={message} />
    </section>
  );
}

/** The card, where the project asks device details; `onSaved` lets the page load the task again
 * (its Send to QC follows what is still missing). */
export function DeviceDetailsCard({
  task,
  onSaved,
}: {
  task: work.TaskDetail;
  onSaved?: () => void;
}) {
  if (!task.device_fields?.length) return null;
  return <DeviceCard task={task} onSaved={onSaved} />;
}
