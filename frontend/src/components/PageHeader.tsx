// A page's title row, the same on every page (D-161, D-162): the title with one short line under it,
// the page's buttons on the right. The row is as tall as the title and its line, the buttons are
// centred on it and the last one ends where the sections under it end, so moving between pages the
// title, the line, the buttons and the filter bar stay in the same place.
import type { ReactNode, Ref } from "react";

export function PageHeader({
  id,
  title,
  lead,
  actions,
  actionsLabel,
  leadRef,
  actionsRef,
}: {
  /** The heading's id, for the page's aria-labelledby. */
  id: string;
  title: ReactNode;
  /** One short line under the title. */
  lead?: ReactNode;
  /** The page's buttons, the main one last. */
  actions?: ReactNode;
  /** Names the buttons as a group for a screen reader. */
  actionsLabel?: string;
  /** For a page whose sub-pages fill in the line and the buttons themselves (a project's pages). */
  leadRef?: Ref<HTMLParagraphElement>;
  actionsRef?: Ref<HTMLDivElement>;
}) {
  return (
    <div className="page-header">
      <div className="page-header__text">
        <h1 id={id}>{title}</h1>
        <p ref={leadRef} className="page-header__lead">
          {lead}
        </p>
      </div>
      {actions || actionsRef ? (
        <div
          ref={actionsRef}
          className="actions"
          role={actionsLabel ? "group" : undefined}
          aria-label={actionsLabel}
        >
          {actions}
        </div>
      ) : null}
    </div>
  );
}
