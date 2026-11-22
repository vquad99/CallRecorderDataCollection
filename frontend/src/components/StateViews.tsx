// Shared loading, empty and error states (FND-018).
import type { ReactNode } from "react";

import type { ApiError } from "../api/client";
import { EmptyArt } from "./Art";
import { Button } from "./form/Button";

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
  level = "h2",
}: {
  title: string;
  message?: string;
  action?: ReactNode;
  /** h1 when the state is the whole page (the not-found page), so the page has its title. */
  level?: "h1" | "h2";
}) {
  const Title = level;
  return (
    <div className="state state--empty">
      <EmptyArt />
      <Title className="state__title">{title}</Title>
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
  action,
}: {
  title?: string;
  message?: string;
  requestId?: string | null;
  /** An API failure: supplies the title, message and the server's reference. */
  error?: ApiError;
  onRetry?: () => void;
  /** Another way on, beside Try again (a link). */
  action?: ReactNode;
}) {
  const reference = requestId ?? error?.requestId ?? null;
  const retry = onRetry ? (
    <Button variant="secondary" icon="refresh" onClick={onRetry}>
      Try again
    </Button>
  ) : null;
  return (
    <div className="state state--error" role="alert">
      <h2 className="state__title">
        {title ?? (error ? errorTitle(error) : "Something went wrong")}
      </h2>
      <p>{message ?? error?.message ?? ""}</p>
      {reference ? <p className="state__meta">Reference: {reference}</p> : null}
      {action ? (
        <div className="actions">
          {retry}
          {action}
        </div>
      ) : (
        retry
      )}
    </div>
  );
}
