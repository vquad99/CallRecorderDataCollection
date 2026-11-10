// Shared loading, empty and error states (FND-018).
import type { ReactNode } from "react";

import type { ApiError } from "../api/client";
import { EmptyArt } from "./Art";

/** A plain title for what went wrong, so every page names failures the same way. */
export function errorTitle(error: ApiError): string {
  if (error.code === "NETWORK_ERROR") return "Connection problem";
  if (error.status === 403) return "No access";
  if (error.status === 404) return "Not found";
  if (error.status === 503) return "Not available";
  return "Something went wrong";
}

export function LoadingState({ label = "Loading" }: { label?: string }) {
  return (
    <div className="state state--loading" role="status" aria-live="polite">
      <span className="spinner" aria-hidden="true" />
      <span>{label}…</span>
    </div>
  );
}

export function EmptyState({
  title,
  message,
  action,
}: {
  title: string;
  message?: string;
  action?: ReactNode;
}) {
  return (
    <div className="state state--empty">
      <EmptyArt />
      <h2 className="state__title">{title}</h2>
      {message ? <p>{message}</p> : null}
      {action}
    </div>
  );
}

export function ErrorState({
  title,
  message,
  requestId,
  error,
  onRetry,
}: {
  title?: string;
  message?: string;
  requestId?: string | null;
  /** An API failure: supplies the title, message and the server's reference. */
  error?: ApiError;
  onRetry?: () => void;
}) {
  const reference = requestId ?? error?.requestId ?? null;
  return (
    <div className="state state--error" role="alert">
      <h2 className="state__title">
        {title ?? (error ? errorTitle(error) : "Something went wrong")}
      </h2>
      <p>{message ?? error?.message ?? ""}</p>
      {reference ? <p className="state__meta">Reference: {reference}</p> : null}
      {onRetry ? (
        <button type="button" className="button button--secondary" onClick={onRetry}>
          Try again
        </button>
      ) : null}
    </div>
  );
}
