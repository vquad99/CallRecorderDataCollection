// A link back to the list or page a detail page belongs to, above its title.
import type { ReactNode } from "react";
import { Link } from "react-router";

import { Icon } from "./Icon";

export function BackLink({ to, children }: { to: string; children: ReactNode }) {
  return (
    <Link className="back-link" to={to}>
      <Icon name="previous" size={14} />
      {children}
    </Link>
  );
}
