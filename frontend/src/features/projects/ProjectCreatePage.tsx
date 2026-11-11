// Create a project (PROJ-001). The platform gives the code: PRJ0001, PRJ0002, ... (D-083).
import { useState } from "react";
import { useNavigate } from "react-router";

import type { ApiError } from "../../api/client";
import { createProject } from "../../api/projects";
import { ErrorNotice } from "../../components/Notice";
import { toApiError } from "../../hooks/useResource";
import { EMPTY_FIELDS, ProjectForm } from "./ProjectForm";

export function ProjectCreatePage() {
  const navigate = useNavigate();
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
        onSubmit={(fields) => {
          setBusy(true);
          setError(null);
          createProject(fields)
            // Back to the project list with a note (D-084): a new project starts as Draft.
            .then((project) =>
              navigate("/projects", {
                state: {
                  created:
                    `${project.code} ${project.name} created. It starts as Draft: open it and ` +
                    "change its status to Active before adding tasks.",
                },
              }),
            )
            .catch((err: unknown) => setError(toApiError(err)))
            .finally(() => setBusy(false));
        }}
      />
    </section>
  );
}
