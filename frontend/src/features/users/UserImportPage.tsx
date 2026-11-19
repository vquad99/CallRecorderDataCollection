// Import users from CSV with a preview before anything is written (USER-005).
import { useState } from "react";

import { confirmImport, previewImport, type ImportRow } from "../../api/admin";
import { BackLink } from "../../components/BackLink";
import { Button } from "../../components/form/Button";
import { ErrorNotice, SuccessNotice } from "../../components/Notice";
import { useAction } from "../../hooks/useAction";
import { DataTable } from "../../components/DataTable";

export function UserImportPage() {
  const [csv, setCsv] = useState("");
  const [rows, setRows] = useState<ImportRow[] | null>(null);
  const { busy, error, message, run, setMessage } = useAction();

  async function loadFile(file: File | undefined) {
    if (!file) return;
    setCsv(await file.text());
    setRows(null);
    setMessage(null);
  }

  const valid = rows?.filter((r) => r.errors.length === 0).length ?? 0;
  return (
    <section aria-labelledby="import-title" className="stack">
      <BackLink to="/admin/users">All users</BackLink>
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
      <span>
        <Button
          icon="eye"
          disabled={!csv}
          busy={busy === "preview"}
          onClick={() => void run(async () => setRows((await previewImport(csv)).rows), "preview")}
        >
          Preview
        </Button>
      </span>
      <ErrorNotice error={error} />
      <SuccessNotice message={message} />
      {rows ? (
        <>
          <p>
            {valid} valid, {rows.length - valid} with problems. Only valid rows are imported.
          </p>
          <DataTable>
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
          </DataTable>
          <span>
            <Button
              icon="fileUp"
              disabled={valid === 0}
              busy={busy === "import"}
              onClick={() =>
                void run(async () => {
                  const done = await confirmImport(csv);
                  setRows(null);
                  return (
                    `${done.created} user(s) created, ${done.skipped.length} skipped` +
                    (done.invites_failed
                      ? `, ${done.invites_failed} invitation email(s) failed.`
                      : ".")
                  );
                }, "import")
              }
            >
              Import {valid} valid row(s)
            </Button>
          </span>
        </>
      ) : null}
    </section>
  );
}
