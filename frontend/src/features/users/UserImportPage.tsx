// Import users from CSV with a preview before anything is written (USER-005).
import { useState } from "react";

import { confirmImport, previewImport, type ImportRow } from "../../api/admin";
import type { ApiError } from "../../api/client";
import { Button } from "../../components/form/Button";
import { ErrorNotice, SuccessNotice } from "../../components/Notice";
import { toApiError } from "../../hooks/useResource";

export function UserImportPage() {
  const [csv, setCsv] = useState("");
  const [rows, setRows] = useState<ImportRow[] | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<ApiError | null>(null);
  const [result, setResult] = useState<string | null>(null);

  async function loadFile(file: File | undefined) {
    if (!file) return;
    setCsv(await file.text());
    setRows(null);
    setResult(null);
  }

  async function run(action: () => Promise<void>) {
    setBusy(true);
    setError(null);
    try {
      await action();
    } catch (err) {
      setError(toApiError(err));
    } finally {
      setBusy(false);
    }
  }

  const valid = rows?.filter((r) => r.errors.length === 0).length ?? 0;
  return (
    <section aria-labelledby="import-title" className="stack">
      <h1 id="import-title">Import users</h1>
      <p>
        CSV with the header <code>email,display_name,roles</code>. Separate several roles with a
        semicolon.
      </p>
      <div className="field">
        <label htmlFor="csv-file" className="field__label">
          CSV file
        </label>
        <input
          id="csv-file"
          type="file"
          accept=".csv,text/csv"
          onChange={(e) => void loadFile(e.target.files?.[0])}
        />
      </div>
      <Button
        disabled={!csv}
        busy={busy}
        onClick={() => void run(async () => setRows((await previewImport(csv)).rows))}
      >
        Preview
      </Button>
      <ErrorNotice error={error} />
      <SuccessNotice message={result} />
      {rows ? (
        <>
          <p>
            {valid} valid, {rows.length - valid} with problems. Only valid rows are imported.
          </p>
          <div className="table-wrap">
            <table className="table">
              <thead>
                <tr>
                  <th scope="col">Line</th>
                  <th scope="col">Email</th>
                  <th scope="col">Name</th>
                  <th scope="col">Roles</th>
                  <th scope="col">Problems</th>
                </tr>
              </thead>
              <tbody>
                {rows.map((r) => (
                  <tr key={r.line} className={r.errors.length ? "row--invalid" : ""}>
                    <td>{r.line}</td>
                    <td>{r.email}</td>
                    <td>{r.display_name}</td>
                    <td>{r.roles.join("; ")}</td>
                    <td>{r.errors.join("; ") || "OK"}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <Button
            disabled={valid === 0}
            busy={busy}
            onClick={() =>
              void run(async () => {
                const done = await confirmImport(csv);
                setResult(
                  `${done.created} user(s) created, ${done.skipped.length} skipped` +
                    (done.invites_failed
                      ? `, ${done.invites_failed} invitation email(s) failed.`
                      : "."),
                );
                setRows(null);
              })
            }
          >
            Import {valid} valid row(s)
          </Button>
        </>
      ) : null}
    </section>
  );
}
