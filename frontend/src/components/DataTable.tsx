// Every table sits in this frame: on a narrow screen the table scrolls sideways inside it and the
// page itself never gets wider than the screen. Use it for every table (lint checks).
import type { ReactNode } from "react";

export function DataTable({
  label,
  caption,
  className,
  bleed = false,
  children,
}: {
  /** The table's name for screen readers when no caption is shown. */
  label?: string;
  /** A visible caption above the rows. */
  caption?: ReactNode;
  className?: string;
  /** Inside a section but not its direct child: run edge to edge as a direct child does, its
   * first and last cells in line with the section's title (D-158). Its parent must be as wide as
   * the section's inside. */
  bleed?: boolean;
  children: ReactNode;
}) {
  return (
    <div className={bleed ? "table-wrap bleed" : "table-wrap"}>
      <table className={className ? `table ${className}` : "table"} aria-label={label}>
        {caption ? <caption className="muted">{caption}</caption> : null}
        {children}
      </table>
    </div>
  );
}
