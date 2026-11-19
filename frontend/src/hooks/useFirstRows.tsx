// A long table's first rows, and a button that shows the rest (the Phone calls page, the
// dashboard's moderators).
import { useState } from "react";

import { Button } from "../components/form/Button";

const FIRST_ROWS = 10;

export function useFirstRows<T>(rows: T[], first = FIRST_ROWS) {
  const [all, setAll] = useState(false);
  const more =
    rows.length > first ? (
      <span>
        <Button variant="secondary" aria-expanded={all} onClick={() => setAll(!all)}>
          {all ? "Show fewer" : `Show all (${rows.length})`}
        </Button>
      </span>
    ) : null;
  return { shown: all ? rows : rows.slice(0, first), more };
}
