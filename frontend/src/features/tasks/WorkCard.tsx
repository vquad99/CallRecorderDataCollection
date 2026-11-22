// The person's next step on a task page as one section (D-091, D-092): start, record, check, call,
// approve or fix a consent form. D-158: its title sits on the section's title bar like every other
// section's; under it the steps or words on the left and the buttons on the right (under them on a
// phone). `after`: parts as wide as the section, under both (the call's reminders, the people whose
// form to replace, notices).
import type { ReactNode } from "react";

export function WorkCard({
  id,
  title,
  go,
  after,
  children,
}: {
  id: string;
  title: string;
  go?: ReactNode;
  after?: ReactNode;
  children: ReactNode;
}) {
  return (
    <section className="card record-card work-card" aria-labelledby={id}>
      <h2 id={id}>{title}</h2>
      <div className="record-card__body">
        <div className="record-card__text">{children}</div>
        {go ? <div className="record-card__go">{go}</div> : null}
      </div>
      {after}
    </section>
  );
}
