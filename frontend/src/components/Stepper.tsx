// A horizontal progress stepper. Labels are drawn by the stylesheet from data attributes and the
// whole thing is one image for screen readers, so it never duplicates text already on the page.
import { Icon } from "./Icon";

export function Stepper({
  steps,
  current,
  label,
  halted = false,
}: {
  steps: readonly string[];
  /** Index of the step in progress; steps before it are done. steps.length = all done. */
  current: number;
  label: string;
  halted?: boolean;
}) {
  return (
    <div className="stepper" role="img" aria-label={label}>
      {steps.map((s, i) => {
        const state = i < current ? "done" : i === current ? (halted ? "halted" : "now") : "todo";
        return (
          <span key={s} className={`stepper__step stepper__step--${state}`} data-label={s}>
            <span className="stepper__dot">
              {state === "done" ? <Icon name="check" size={12} weight="bold" /> : i + 1}
            </span>
          </span>
        );
      })}
    </div>
  );
}
