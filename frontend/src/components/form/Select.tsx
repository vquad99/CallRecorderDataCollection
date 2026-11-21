// Accessible select with a visible label (FND-019).
import { useId, type SelectHTMLAttributes } from "react";

interface SelectProps extends Omit<SelectHTMLAttributes<HTMLSelectElement>, "id"> {
  label: string;
  /** A disabled option is shown but cannot be chosen; its label says why. */
  options: readonly { value: string; label: string; disabled?: boolean }[];
}

export function Select({ label, options, required, ...props }: SelectProps) {
  const id = useId();
  return (
    <div className="field">
      <label htmlFor={id} className="field__label">
        {label}
        {required ? <span aria-hidden="true"> *</span> : null}
      </label>
      <select id={id} className="field__input" required={required} {...props}>
        {options.map((o) => (
          <option key={o.value} value={o.value} disabled={o.disabled}>
            {o.label}
          </option>
        ))}
      </select>
    </div>
  );
}
