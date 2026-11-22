// Import users from CSV with a preview before anything is written (USER-005).
import { useState } from "react";

import { confirmImport, previewImport, ROLE_CODES, type ImportRow } from "../../api/admin";
import { BackLink } from "../../components/BackLink";
import { Button } from "../../components/form/Button";
import { Icon } from "../../components/Icon";
import { ErrorNotice, SuccessNotice } from "../../components/Notice";
import { useAction } from "../../hooks/useAction";
import { DataTable } from "../../components/DataTable";
import { plural } from "../../lib/format";
import "./users.css";

const SAMPLE =
  "email,display_name,roles\n" +
  "moderator@example.org,Asha Rao,MODERATOR\n" +
  "reviewer@example.org,Ravi Kumar,QC_EXECUTIVE;CLIENT_VIEWER\n";

/** Save the sample as a CSV file the admin fills in, as for tasks (D-085). */
function downloadSample() {
  const url = URL.createObjectURL(new Blob([SAMPLE], { type: "text/csv" }));
  const link = document.createElement("a");
  link.href = url;
  link.download = "users_template.csv";
  link.click();
  URL.revokeObjectURL(url);
}

export function UserImportPage() {
  const [csv, setCsv] = useState("");
  const [fileName, setFileName] = useState<string | null>(null);
  const [rows, setRows] = useState<ImportRow[] | null>(null);
  const { busy, error, message, run, setMessage } = useAction();

  async function loadFile(file: File | undefined) {
    if (!file) return;
    setCsv(await file.text());
    setFileName(file.name);
    setRows(null);
    setMessage(null);
  }

  const valid = rows?.filter((r) => r.errors.length === 0).length ?? 0;
  // D-158: the file and the rows are sections of their own, each titled on a bar.
  return (
    <section aria-labelledby="import-title" className="stack">
      <BackLink to="/admin/users">All users</BackLink>
      <h1 id="import-title">Import users</h1>
      <section className="card" aria-labelledby="import-file-title">
        <h2 id="import-file-title">CSV file</h2>
        <p>
          A CSV file with the header <code>email,display_name,roles</code> and one person per row.
          Separate several roles with a semicolon. Each new account is sent an invitation to set its
          password. Nothing is written until you check the rows and import them.
        </p>
        <p>
          Role codes:
          {ROLE_CODES.map((code) => (
            <span key={code}>
              {" "}
              <code>{code}</code>
            </span>
          ))}
        </p>
        <div className="actions">
          <Button variant="secondary" icon="fileCsv" onClick={downloadSample}>
            Download sample CSV
          </Button>
          <label className="button button--secondary">
            <Icon name="fileUp" size={16} />
            Choose a CSV file
            <input
              type="file"
              accept=".csv,text/csv"
              className="sr-only"
              onChange={(e) => void loadFile(e.target.files?.[0])}
            />
          </label>
          {/* Outside the label, so the file box keeps one name for screen readers. */}
          <span className="muted" aria-live="polite">
            {fileName ?? "No file chosen"}
          </span>
          <Button
            icon="eye"
            disabled={!csv}
            busy={busy === "preview"}
            onClick={() =>
              void run(async () => setRows((await previewImport(csv)).rows), "preview")
            }
          >
            Preview
          </Button>
        </div>
      </section>
      <ErrorNotice error={error} />
      <SuccessNotice message={message} />
      {rows ? (
        <section className="card" aria-labelledby="import-rows-title">
          <h2 id="import-rows-title">Rows</h2>
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
          <div className="actions import-rows__go">
            <Button
              icon="fileUp"
              disabled={valid === 0}
              busy={busy === "import"}
              onClick={() =>
                void run(async () => {
                  const done = await confirmImport(csv);
                  setRows(null);
                  return (
                    `${plural(done.created, "user")} created, ${done.skipped.length} skipped.` +
                    (done.invites_failed
                      ? ` ${plural(done.invites_failed, "invitation email")} could not be sent:` +
                        ` use "Send password link" on the user's page.`
                      : "")
                  );
                }, "import")
              }
            >
              Import {plural(valid, "valid row")}
            </Button>
          </div>
        </section>
      ) : null}
    </section>
  );
}
