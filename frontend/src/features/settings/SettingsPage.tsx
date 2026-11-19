// Capacity targets, editable without a deployment (CAP-002).
import { useState, type FormEvent } from "react";

import { getSettings, updateSettings, type Setting } from "../../api/admin";
import { Button } from "../../components/form/Button";
import { TextField } from "../../components/form/TextField";
import { ErrorNotice, SuccessNotice } from "../../components/Notice";
import { ErrorState, LoadingState } from "../../components/StateViews";
import { useAction } from "../../hooks/useAction";
import { useResource } from "../../hooks/useResource";
import { IconTile } from "../../components/Icon";

const LABELS: Record<string, string> = {
  "capacity.staff_accounts": "Staff accounts",
  "capacity.concurrent_conferences": "Simultaneous phone conferences",
  "capacity.participants_per_conversation": "Participants per conversation",
  "capacity.total_hours_per_day": "Total recording hours per day",
  "capacity.face_to_face_hours_per_day": "Face-to-face hours per day",
  "capacity.telephony_hours_per_day": "Phone call hours per day",
};

function Form({ settings, onSaved }: { settings: Setting[]; onSaved: (s: Setting[]) => void }) {
  const [values, setValues] = useState<Record<string, string>>(
    Object.fromEntries(settings.map((s) => [s.key, String(s.value ?? "")])),
  );
  const { busy, error, message, run } = useAction();

  function submit(event: FormEvent) {
    event.preventDefault();
    void run(async () => {
      const changed = Object.fromEntries(
        settings
          .filter((s) => String(s.value ?? "") !== values[s.key])
          .map((s) => [s.key, Number(values[s.key])]),
      );
      if (Object.keys(changed).length === 0) return "Nothing changed.";
      onSaved(await updateSettings(changed));
      return "Saved. New values apply immediately.";
    });
  }

  return (
    <form onSubmit={submit} noValidate className="card">
      <div className="form-grid">
        {settings.map((s) => (
          <TextField
            key={s.key}
            label={LABELS[s.key] ?? s.key}
            hint={`Allowed: ${s.min_value} to ${s.max_value}`}
            type="number"
            min={s.min_value}
            max={s.max_value}
            value={values[s.key] ?? ""}
            onChange={(e) => setValues({ ...values, [s.key]: e.target.value })}
          />
        ))}
      </div>
      <ErrorNotice error={error} />
      <SuccessNotice message={message} />
      <Button type="submit" busy={busy !== null}>
        Save targets
      </Button>
    </form>
  );
}

export function SettingsPage() {
  const { state, reload, replace } = useResource(getSettings, []);
  return (
    <section aria-labelledby="settings-title" className="stack">
      <h1 id="settings-title">
        <IconTile name="settings" />
        Capacity targets
      </h1>
      <p>Targets used for planning and reports. They are goals, not proof of capacity.</p>
      {state.status === "loading" ? <LoadingState /> : null}
      {state.status === "failed" ? <ErrorState error={state.error} onRetry={reload} /> : null}
      {state.status === "loaded" ? <Form settings={state.data} onSaved={replace} /> : null}
    </section>
  );
}
