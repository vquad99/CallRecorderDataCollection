// Capacity settings, editable without a deployment (CAP-002). Only the number of staff accounts is
// a limit the platform keeps (D-059); the other figures are for planning and limit nothing.
// D-158: the page is "Settings"; the capacity targets are one section with its Save on the title
// bar, the account limit and the planning figures its two parts (they are saved together).
import { useId, useState, type FormEvent } from "react";

import { getSettings, updateSettings, type Setting } from "../../api/admin";
import { ApiError } from "../../api/client";
import { Button } from "../../components/form/Button";
import { TextField } from "../../components/form/TextField";
import { ErrorNotice, SuccessNotice } from "../../components/Notice";
import { ErrorState, LoadingState } from "../../components/StateViews";
import { StatusBadge } from "../../components/StatusBadge";
import { useAction } from "../../hooks/useAction";
import { useResource } from "../../hooks/useResource";
import "./settings.css";

const LIMIT = "capacity.staff_accounts";
/** Names in the order the page shows them. */
const LABELS: Record<string, string> = {
  [LIMIT]: "Staff accounts",
  "capacity.total_hours_per_day": "Total recording hours per day",
  "capacity.face_to_face_hours_per_day": "Face-to-face hours per day",
  "capacity.telephony_hours_per_day": "Phone call hours per day",
  "capacity.concurrent_conferences": "Simultaneous phone conferences",
  "capacity.participants_per_conversation": "Participants per conversation",
};
const ORDER = Object.keys(LABELS);
const label = (s: Setting) => LABELS[s.key] ?? s.key;
const place = (s: Setting) => (ORDER.includes(s.key) ? ORDER.indexOf(s.key) : ORDER.length);
/** Figures grouped in thousands, as international readers write them: "1,000,000" (D-158). */
const count = (n: number) => n.toLocaleString("en-US");
const allowed = (s: Setting) => `Allowed: ${count(s.min_value)} to ${count(s.max_value)}.`;
/** A setting with one possible value is shown, never edited or sent. */
const fixed = (s: Setting) => s.min_value === s.max_value;

function Form({ settings, onSaved }: { settings: Setting[]; onSaved: (s: Setting[]) => void }) {
  const titleId = useId();
  const limitId = useId();
  const planningId = useId();
  const sorted = [...settings].sort((a, b) => place(a) - place(b));
  const editable = sorted.filter((s) => !fixed(s));
  const limit = editable.filter((s) => s.key === LIMIT);
  const planning = editable.filter((s) => s.key !== LIMIT);
  const [values, setValues] = useState<Record<string, string>>(
    Object.fromEntries(editable.map((s) => [s.key, String(s.value ?? "")])),
  );
  const { busy, error, message, run } = useAction();

  function submit(event: FormEvent) {
    event.preventDefault();
    void run(async () => {
      const changed: Record<string, number> = {};
      for (const s of editable) {
        const text = (values[s.key] ?? "").trim();
        if (text === String(s.value ?? "")) continue;
        const n = Number(text);
        if (!/^\d+$/.test(text) || n < s.min_value || n > s.max_value) {
          throw new ApiError({
            status: 422,
            code: "INVALID_VALUE",
            message: `${label(s)}: enter a whole number from ${count(s.min_value)} to ${count(s.max_value)}.`,
          });
        }
        if (n !== s.value) changed[s.key] = n;
      }
      if (Object.keys(changed).length === 0) return "Nothing changed.";
      onSaved(await updateSettings(changed));
      return "Saved. New values apply immediately.";
    });
  }

  const field = (s: Setting, hint: string) => (
    <TextField
      key={s.key}
      label={label(s)}
      hint={hint}
      type="number"
      inputMode="numeric"
      min={s.min_value}
      max={s.max_value}
      step={1}
      value={values[s.key] ?? ""}
      onChange={(e) => setValues({ ...values, [s.key]: e.target.value })}
    />
  );

  return (
    <form onSubmit={submit} noValidate>
      <section className="card capacity" aria-labelledby={titleId}>
        <div className="card__head">
          <h2 id={titleId}>Capacity targets</h2>
          <Button type="submit" icon="check" busy={busy !== null}>
            Save targets
          </Button>
        </div>
        <ErrorNotice error={error} />
        <SuccessNotice message={message} />
        {limit.length > 0 ? (
          <fieldset className="plain-fieldset" aria-labelledby={limitId}>
            <div className="subhead">
              <h3 id={limitId}>
                Account limit <StatusBadge tone="warning" label="Enforced" />
              </h3>
            </div>
            <div className="form-grid">
              {limit.map((s) =>
                field(s, `New or re-enabled accounts above this number are refused. ${allowed(s)}`),
              )}
            </div>
          </fieldset>
        ) : null}
        <fieldset className="plain-fieldset" aria-labelledby={planningId}>
          <h3 className="subhead" id={planningId}>
            Planning figures
          </h3>
          <p className="muted">For reference only; nothing in the platform is limited by these.</p>
          <div className="form-grid">{planning.map((s) => field(s, allowed(s)))}</div>
          {sorted.filter(fixed).map((s) => (
            <p key={s.key}>
              {label(s)}: {s.value === null ? "-" : count(s.value)}{" "}
              <span className="muted">(fixed)</span>
            </p>
          ))}
        </fieldset>
      </section>
    </form>
  );
}

export function SettingsPage() {
  const { state, reload, replace } = useResource(getSettings, []);
  return (
    <section aria-labelledby="settings-title" className="stack">
      <div className="page-header">
        <div className="page-header__text">
          <h1 id="settings-title">Settings</h1>
          <p className="page-header__lead">
            The account limit and daily planning figures. Changes apply at once.
          </p>
        </div>
      </div>
      {state.status === "loading" ? <LoadingState /> : null}
      {state.status === "failed" ? <ErrorState error={state.error} onRetry={reload} /> : null}
      {state.status === "loaded" ? <Form settings={state.data} onSaved={replace} /> : null}
    </section>
  );
}
