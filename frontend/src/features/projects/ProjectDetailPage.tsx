// One project with tabs: overview, team, audio rules, languages, retention (PROJ-*).
import { NavLink, Outlet, useOutletContext, useParams } from "react-router";

import { getProject, type Project } from "../../api/projects";
import { ErrorState, LoadingState } from "../../components/StateViews";
import { useResource } from "../../hooks/useResource";
import { STATUS_LABELS } from "./ProjectsPage";
import { StatusBadge } from "../../components/StatusBadge";

export interface ProjectContext {
  project: Project;
  replace: (project: Project) => void;
}

export function useProject(): ProjectContext {
  return useOutletContext<ProjectContext>();
}

const TABS = [
  { to: "", label: "Overview", end: true },
  { to: "team", label: "Team", end: false },
  { to: "participants", label: "Participants", end: false },
  { to: "audio", label: "Audio rules", end: false },
  { to: "languages", label: "Languages", end: false },
  { to: "retention", label: "Retention", end: false },
];

export function ProjectDetailPage() {
  const { projectId = "" } = useParams();
  const { state, reload, replace } = useResource(() => getProject(projectId), [projectId]);
  if (state.status === "loading") return <LoadingState label="Loading project" />;
  if (state.status === "failed") return <ErrorState error={state.error} onRetry={reload} />;
  const project = state.data;
  return (
    <section aria-labelledby="project-title" className="stack">
      <div className="page-header">
        <h1 id="project-title">
          {project.code} · {project.name}
        </h1>
        <StatusBadge
          status={project.status}
          label={STATUS_LABELS[project.status] ?? project.status}
        />
      </div>
      <nav aria-label="Project sections" className="tabs">
        {TABS.map((t) => (
          <NavLink key={t.label} to={t.to} end={t.end} className="tabs__link">
            {t.label}
          </NavLink>
        ))}
      </nav>
      <Outlet context={{ project, replace } satisfies ProjectContext} />
    </section>
  );
}
