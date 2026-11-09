// Inline success / error messages for forms.
import type { ApiError } from "../api/client";

function fieldName(loc: unknown): string {
  const parts = Array.isArray(loc) ? loc.filter((p) => typeof p === "string" && p !== "body") : [];
  const last = String(parts[parts.length - 1] ?? "");
  const words = last.replace(/_/g, " ").trim();
  return words ? words.charAt(0).toUpperCase() + words.slice(1) : "Request";
}

/** "Field: what is wrong" for each problem in a validation error from the server. */
export function fieldProblems(error: ApiError): string[] {
  if (error.code !== "VALIDATION_ERROR" || !Array.isArray(error.details)) return [];
  return error.details.flatMap((d: unknown) => {
    if (!d || typeof d !== "object") return [];
    const { loc, msg } = d as { loc?: unknown; msg?: unknown };
    return typeof msg === "string" ? [`${fieldName(loc)}: ${msg}`] : [];
  });
}

export function ErrorNotice({ error }: { error: ApiError | null }) {
  if (!error) return null;
  const problems = fieldProblems(error);
  return (
    <div className="notice notice--error" role="alert">
      <p>
        {error.message}
        {error.requestId ? (
          <span className="notice__meta"> (reference {error.requestId})</span>
        ) : null}
      </p>
      {problems.length > 0 ? (
        <ul>
          {problems.map((p) => (
            <li key={p}>{p}</li>
          ))}
        </ul>
      ) : null}
    </div>
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
