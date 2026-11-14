// One project with tabs: overview, team, audio rules, languages, retention (PROJ-*).
// Only people who manage projects (Super Admin, Project Admin) see the tabs after Overview
// (D-104): everyone else has the overview, and a tab's address answers "No access".
import { NavLink, Outlet, useMatch, useOutletContext, useParams } from "react-router";

import { getProject, type Project } from "../../api/projects";
import { useAuth } from "../../auth/AuthContext";
import { EmptyState, ErrorState, LoadingState } from "../../components/StateViews";
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

const TABS: { to: string; label: string; end: boolean; perm?: string }[] = [
  { to: "", label: "Overview", end: true },
  { to: "team", label: "Team", end: false, perm: "projects.manage" },
  { to: "participants", label: "Participants", end: false, perm: "projects.manage" },
  { to: "audio", label: "Audio rules", end: false, perm: "projects.manage" },
  { to: "languages", label: "Languages", end: false, perm: "projects.manage" },
  { to: "retention", label: "Retention", end: false, perm: "projects.manage" },
  { to: "export", label: "Export", end: false, perm: "projects.manage" },
];

export function ProjectDetailPage() {
  const { projectId = "" } = useParams();
  const { can } = useAuth();
  const onOverview = useMatch({ path: "/projects/:projectId", end: true }) !== null;
  const { state, reload, replace } = useResource(() => getProject(projectId), [projectId]);
  if (state.status === "loading") return <LoadingState label="Loading project" />;
  if (state.status === "failed") return <ErrorState error={state.error} onRetry={reload} />;
  const project = state.data;
  // The Export tab also needs the right to export.
  const tabs = TABS.filter(
    (t) => (!t.perm || can(t.perm)) && (t.to !== "export" || can("exports.create")),
  );
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
      {tabs.length > 1 ? (
        <nav aria-label="Project sections" className="tabs">
          {tabs.map((t) => (
            <NavLink key={t.label} to={t.to} end={t.end} className="tabs__link">
              {t.label}
            </NavLink>
          ))}
        </nav>
      ) : null}
      {onOverview || can("projects.manage") ? (
        <Outlet context={{ project, replace } satisfies ProjectContext} />
      ) : (
        <EmptyState
          title="No access"
          message="Only the project's administrators see this part of a project."
        />
      )}
    </section>
  );
}
