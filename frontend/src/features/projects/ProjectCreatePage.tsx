// Create a project (PROJ-001).
import { useState } from "react";
import { useNavigate } from "react-router";

import type { ApiError } from "../../api/client";
import { createProject } from "../../api/projects";
import { TextField } from "../../components/form/TextField";
import { ErrorNotice } from "../../components/Notice";
import { toApiError } from "../../hooks/useResource";
import { EMPTY_FIELDS, ProjectForm } from "./ProjectForm";

export function ProjectCreatePage() {
  const navigate = useNavigate();
  const [code, setCode] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<ApiError | null>(null);

  return (
    <section aria-labelledby="new-project-title" className="stack">
      <h1 id="new-project-title">New project</h1>
      <ErrorNotice error={error} />
      <ProjectForm
        initial={EMPTY_FIELDS}
        submitLabel="Create project"
        busy={busy}
        extra={
          <TextField
            label="Project code"
            hint="2-40 letters, digits, dash or underscore. Stored in capitals."
            required
            value={code}
            onChange={(e) => setCode(e.target.value)}
          />
        }
        onSubmit={(fields) => {
          setBusy(true);
          setError(null);
          createProject({ ...fields, code })
            .then((project) => navigate(`/projects/${project.id}`))
            .catch((err: unknown) => setError(toApiError(err)))
            .finally(() => setBusy(false));
        }}
      />
    </section>
  );
}
