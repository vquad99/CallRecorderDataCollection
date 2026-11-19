// Accessible button (FND-019): defaults to type="button"; busy state is announced. "danger" is for
// an action that deletes, rejects or ends something. An icon (D-141) sits before the label in its
// own colour; while busy, the spinner takes its place so the button keeps its width.
import type { ButtonHTMLAttributes } from "react";
import { Link } from "react-router";

import { Icon, type IconName } from "../Icon";

interface ButtonProps extends ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: "primary" | "secondary" | "danger";
  busy?: boolean;
  icon?: IconName;
}

export function Button({
  variant = "primary",
  busy = false,
  icon,
  type = "button",
  disabled,
  children,
  ...rest
}: ButtonProps) {
  return (
    <button
      type={type}
      className={`button button--${variant}`}
      disabled={disabled || busy}
      aria-busy={busy || undefined}
      {...rest}
    >
      {busy ? (
        <span className="spinner" aria-hidden="true" />
      ) : icon ? (
        <Icon name={icon} size={16} />
      ) : null}
      {children}
    </button>
  );
}

interface IconButtonProps extends Omit<ButtonHTMLAttributes<HTMLButtonElement>, "children"> {
  icon: IconName;
  /** The words: shown on hover, and the button's name for screen readers. */
  label: string;
  busy?: boolean;
  /** A page to open instead of an action. */
  to?: string;
}

/** A table row's action as its icon only (D-141), so a row with several actions stays one line. */
export function IconButton({ icon, label, busy = false, to, disabled, ...rest }: IconButtonProps) {
  const inside = (
    <>
      {busy ? <span className="spinner" aria-hidden="true" /> : <Icon name={icon} size={18} />}
      <span className="sr-only">{label}</span>
    </>
  );
  return to ? (
    <Link className="icon-button" to={to} title={label}>
      {inside}
    </Link>
  ) : (
    <button
      type="button"
      className="icon-button"
      title={label}
      disabled={disabled || busy}
      aria-busy={busy || undefined}
      {...rest}
    >
      {inside}
    </button>
  );
}
