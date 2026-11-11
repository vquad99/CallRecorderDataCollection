// Accessible text input (FND-019): visible label, hint and error tied to the input.
import { useId, type InputHTMLAttributes } from "react";

interface TextFieldProps extends Omit<InputHTMLAttributes<HTMLInputElement>, "id"> {
  label: string;
  hint?: string;
  example?: string; // shown faded under the box (D-086)
  error?: string;
}

export function TextField({
  label,
  hint,
  example,
  error,
  required,
  ...inputProps
}: TextFieldProps) {
  const id = useId();
  const hintId = hint ? `${id}-hint` : undefined;
  const exampleId = example ? `${id}-example` : undefined;
  const errorId = error ? `${id}-error` : undefined;
  const describedBy = [hintId, exampleId, errorId].filter(Boolean).join(" ") || undefined;

  return (
    <div className={`field${error ? " field--invalid" : ""}`}>
      <label htmlFor={id} className="field__label">
        {label}
        {required ? <span aria-hidden="true"> *</span> : null}
      </label>
      {hint ? (
        <p id={hintId} className="field__hint">
          {hint}
        </p>
      ) : null}
      <input
        id={id}
        className="field__input"
        required={required}
        aria-invalid={error ? true : undefined}
        aria-describedby={describedBy}
        {...inputProps}
      />
      {example ? (
        <p id={exampleId} className="field__hint">
          {example}
        </p>
      ) : null}
      {error ? (
        <p id={errorId} className="field__error">
          {error}
        </p>
      ) : null}
    </div>
  );
}
