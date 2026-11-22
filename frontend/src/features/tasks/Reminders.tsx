// What the moderator reads before recording (the recorder) and before calling (the call card),
// D-147: the speaker-ID line built from the task's own people, what to talk about and avoid, and
// the project's tips for the task's mode. The project sets the words on its Rules tab. D-158: a
// section with its title on the title bar on the recorder; a part of the call card under a line
// across it (never a box inside a section).
import { useId } from "react";

import type * as work from "../../api/work";
import "./moderator.css";

/** "Asha" from "Asha Naik"; null when the name is not shown to this user (D-128). */
const firstName = (label: string | null) => label?.trim().split(/\s+/)[0] || null;

/** `inline`: a part of another section (the call card) instead of a section of its own.
 * `extra`: one more line at the end (the recorder's silence limit). */
export function Reminders({
  task,
  extra,
  inline = false,
}: {
  task: work.TaskDetail;
  extra?: string;
  inline?: boolean;
}) {
  const titleId = useId();
  const r = task.reminders;
  const people = [task.participant_a, task.participant_b];
  const said = r?.speaker_id ?? false;
  const lines = [
    ...(r?.topics.length
      ? [{ key: "topics", lead: "Talk about:", text: r.topics.join(", ") }]
      : []),
    ...(r?.avoid.length ? [{ key: "avoid", lead: "Avoid:", text: r.avoid.join(", ") }] : []),
    ...(r?.tips ?? []).map((tip, i) => ({ key: `tip-${i}`, lead: "", text: tip })),
    ...(extra ? [{ key: "extra", lead: "", text: extra }] : []),
  ];
  if (!said && lines.length === 0) return null;
  return (
    <section
      className={inline ? "reminders" : "card reminders"}
      role="note"
      aria-labelledby={titleId}
    >
      {inline ? (
        <h3 id={titleId} className="subhead">
          Reminders
        </h3>
      ) : (
        <h2 id={titleId}>Reminders</h2>
      )}
      <ul>
        {said ? (
          <li>
            Ask each speaker to start with:
            <ul>
              {people.map((p) => (
                <li key={p.id}>
                  “I am {firstName(p.display_label) ?? "<their name>"} and speaker ID{" "}
                  {p.participant_code}”
                </li>
              ))}
            </ul>
          </li>
        ) : null}
        {lines.map((line) => (
          <li key={line.key}>
            {line.lead ? <strong>{line.lead} </strong> : null}
            {line.text}
          </li>
        ))}
      </ul>
    </section>
  );
}
