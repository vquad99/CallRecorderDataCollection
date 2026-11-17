// Every table sits in this frame: on a narrow screen the table scrolls sideways inside it and the
// page itself never gets wider than the screen. Use it for every table (lint checks).
import type { ReactNode } from "react";

export function DataTable({
  label,
  caption,
  className,
  children,
}: {
  /** The table's name for screen readers when no caption is shown. */
  label?: string;
  /** A visible caption above the rows. */
  caption?: ReactNode;
  className?: string;
  children: ReactNode;
}) {
  return (
    <div className="table-wrap">
      <table className={className ? `table ${className}` : "table"} aria-label={label}>
        {caption ? <caption className="muted">{caption}</caption> : null}
        {children}
      </table>
    </div>
  );
}
