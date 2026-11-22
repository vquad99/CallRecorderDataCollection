// Pieces of the task page's matrices (D-152): a compact Yes / No switch made of two radio buttons
// (one keyboard stop, arrows move between Yes and No), and a tick or a cross with its words.
import { useId, type ReactNode } from "react";

import { Icon } from "../../components/Icon";
import "./moderator.css";

export type YesNoAnswer = "yes" | "no";

/** Yes and No side by side as one radio group; `label` names the group ("Is echo present? –
 * Participant A"). The chosen answer is filled; an answer that fails the recording is rose. */
export function YesNo({
  label,
  value,
  onChange,
  failsOn = null,
}: {
  label: string;
  value: YesNoAnswer | undefined | null;
  onChange: (answer: YesNoAnswer) => void;
  /** The answer that fails the recording (QC checklist), if any. */
  failsOn?: YesNoAnswer | null;
}) {
  const name = useId();
  return (
    <div className="yn" role="radiogroup" aria-label={label}>
      {(["yes", "no"] as const).map((a) => {
        const on = value === a;
        return (
          <label key={a} className={`yn__opt${on ? (a === failsOn ? " is-fail" : " is-on") : ""}`}>
            <input
              type="radio"
              className="yn__input"
              name={name}
              value={a}
              checked={on}
              onChange={() => onChange(a)}
            />
            {a === "yes" ? "Yes" : "No"}
          </label>
        );
      })}
    </div>
  );
}

/** A tick (fine) or a cross (missing, fails) before its words; the words carry the meaning. */
export function Mark({
  ok,
  children,
  title,
}: {
  ok: boolean;
  children: ReactNode;
  title?: string | undefined;
}) {
  return (
    <span className={`mark ${ok ? "mark--ok" : "mark--no"}`} title={title}>
      <Icon name={ok ? "ok" : "failed"} size={16} />
      <span>{children}</span>
    </span>
  );
}
