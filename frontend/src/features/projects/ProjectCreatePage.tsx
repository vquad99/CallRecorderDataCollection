// Create a project (PROJ-001). The platform gives the code: PRJ0001, PRJ0002, ... (D-083).
import { useNavigate } from "react-router";

import { createProject } from "../../api/projects";
import { BackLink } from "../../components/BackLink";
import { ErrorNotice } from "../../components/Notice";
import { useAction } from "../../hooks/useAction";
import { EMPTY_FIELDS, ProjectForm } from "./ProjectForm";

export function ProjectCreatePage() {
  const navigate = useNavigate();
  const { busy, error, run } = useAction();

  return (
    <section aria-labelledby="new-project-title" className="stack">
      <BackLink to="/projects">All projects</BackLink>
      <h1 id="new-project-title">New project</h1>
      {/* D-145: the rules have their own tab; a new project starts with the usual ones. */}
      <p className="muted">
        The project&apos;s rules (speaker ages and details, pairing, consent, approval) start with
        the usual values. Change them on the project&apos;s <strong>Rules</strong> tab once it is
        created.
      </p>
      <ErrorNotice error={error} />
      <ProjectForm
        initial={EMPTY_FIELDS}
        submitLabel="Create project"
        busy={busy !== null}
        onSubmit={(fields) =>
          void run(async () => {
            const project = await createProject(fields);
            // Back to the project list with a note (D-084): a new project starts as Draft.
            void navigate("/projects", {
              state: {
                created:
                  `${project.code} ${project.name} created. It starts as Draft: open it and ` +
                  "click Make active before adding tasks.",
              },
            });
          })
        }
      />
    </section>
  );
}
