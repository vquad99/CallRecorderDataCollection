// A box of text that grows with its words (D-157, D-158), for a project's details and its Rules:
// the same words, unseen, in the same grid cell behind the box set its height, so no line is cut
// and the box never scrolls on its own. Its styles are .grow-box in overview.css, loaded with every
// project page and with the project form.
import type { TextareaHTMLAttributes } from "react";

import "./overview.css";

export function GrowBox({
  value,
  ...props
}: Omit<TextareaHTMLAttributes<HTMLTextAreaElement>, "value" | "className"> & { value: string }) {
  return (
    <div className="grow-box" data-value={value}>
      <textarea {...props} className="field__input" value={value} />
    </div>
  );
}
