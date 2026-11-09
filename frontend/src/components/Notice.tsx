// Inline success / error messages for forms.
import type { ApiError } from "../api/client";

export function ErrorNotice({ error }: { error: ApiError | null }) {
  if (!error) return null;
  return (
    <p className="notice notice--error" role="alert">
      {error.message}
      {error.requestId ? (
        <span className="notice__meta"> (reference {error.requestId})</span>
      ) : null}
    </p>
  );
}

export function SuccessNotice({ message }: { message: string | null }) {
  if (!message) return null;
  return (
    <p className="notice notice--success" role="status">
      {message}
    </p>
  );
}
