// One project with its own menu (D-150): overview, progress, team, participants, tasks, audio
// rules, rules, languages, retention, export (PROJ-*), as a second panel beside the side menu; on a
// phone, a row of chips at the top. The Rules page's sections are its sub-items, each opened on its
// own. Only people who manage projects (Super Admin, Project Admin) have the other pages, the Rules
// (D-145) and the Progress page (D-148) among them (D-104): everyone else has the overview, no
// menu, and another page's address answers "No access". A page puts its own buttons on the title
// row, on the right as on every list page, and a short line under its title (D-158).
import { useEffect, useRef, useState, type ReactNode } from "react";
import { createPortal } from "react-dom";
import { NavLink, Outlet, useLocation, useMatch, useOutletContext, useParams } from "react-router";

import { getProject, type Project } from "../../api/projects";
import { useAuth } from "../../auth/AuthContext";
import { BackLink } from "../../components/BackLink";
import { Icon, type IconName } from "../../components/Icon";
import { PageHeader } from "../../components/PageHeader";
import { EmptyState, ErrorState, LoadingState } from "../../components/StateViews";
import { usePageTitle } from "../../hooks/usePageTitle";
import { useResource } from "../../hooks/useResource";
import { StatusBadge } from "../../components/StatusBadge";
import { labelFor, PROJECT_STATUS_LABELS } from "../../lib/labels";
import "./overview.css";

export interface ProjectContext {
  project: Project;
  replace: (project: Project) => void;
  /** The title row's places for a page's buttons and its line under the title (D-158); not
   * there until the row is on the screen, nor on the overview of someone with no menu. */
  header?: { actions: HTMLElement | null; lead: HTMLElement | null };
}

export function useProject(): ProjectContext {
  return useOutletContext<ProjectContext>();
}

/** A page's own buttons, on the title row on the right as on every list page (D-158). Drawn from
 * inside the page, so they keep its state; nothing outside a project's page. */
export function PageActions({ children }: { children: ReactNode }) {
  const slot = useOutletContext<ProjectContext | undefined>()?.header?.actions;
  return slot ? createPortal(children, slot) : null;
}

/** A short line under the page's title, such as when its figures were read (D-158). */
export function PageLead({ children }: { children: ReactNode }) {
  const slot = useOutletContext<ProjectContext | undefined>()?.header?.lead;
  return slot ? createPortal(children, slot) : null;
}

/** The Rules page's sections, in order (D-145..D-149), each opened at rules/<key> (D-150). */
export const RULE_SECTIONS: readonly { key: string; title: string; icon: IconName }[] = [
  { key: "speakers", title: "Speakers", icon: "people" },
  { key: "consent", title: "Consent", icon: "verified" },
  { key: "approval", title: "Approval", icon: "ok" },
  { key: "qc-checklist", title: "QC checklist", icon: "tasks" },
  { key: "devices", title: "Device details", icon: "phone" },
  { key: "reminders", title: "Reminders for moderators", icon: "mic" },
  { key: "audio-progress", title: "Audio and progress", icon: "waveform" },
  { key: "targets", title: "Targets", icon: "target" },
  { key: "export", title: "Export format", icon: "fileZip" },
];

const PAGES: { to: string; label: string; icon: IconName; perm?: string }[] = [
  { to: "", label: "Overview", icon: "info" },
  { to: "progress", label: "Progress", icon: "chart", perm: "projects.manage" },
  { to: "team", label: "Team", icon: "users", perm: "projects.manage" },
  { to: "participants", label: "Participants", icon: "people", perm: "projects.manage" },
  { to: "tasks", label: "Tasks", icon: "tasks", perm: "projects.manage" },
  { to: "audio", label: "Audio rules", icon: "waveform", perm: "projects.manage" },
  { to: "rules", label: "Rules", icon: "fileText", perm: "projects.manage" },
  { to: "languages", label: "Languages", icon: "comment", perm: "projects.manage" },
  { to: "retention", label: "Retention", icon: "clock", perm: "projects.manage" },
  { to: "export", label: "Export", icon: "download", perm: "projects.manage" },
];

/** The project's menu: a panel beside the side menu, a scrolling row of chips on a phone. */
function ProjectMenu({ project, pages }: { project: Project; pages: typeof PAGES }) {
  const { pathname } = useLocation();
  const onRules = useMatch("/projects/:projectId/rules/*") !== null;
  const list = useRef<HTMLUListElement>(null);
  // On a phone the row scrolls sideways: bring the current page into view.
  useEffect(() => {
    const row = list.current;
    const items = row?.querySelectorAll<HTMLElement>('[aria-current="page"]');
    const current = items?.[items.length - 1];
    if (!row || !current || row.scrollWidth <= row.clientWidth) return;
    row.scrollLeft = current.offsetLeft - (row.clientWidth - current.offsetWidth) / 2;
  }, [pathname]);
  return (
    <div className="section-panel">
      <div className="section-panel__head">
        <BackLink to="/projects">All projects</BackLink>
        <p className="section-panel__title">
          <span className="section-panel__code">{project.code}</span>
          <StatusBadge
            status={project.status}
            label={labelFor(PROJECT_STATUS_LABELS, project.status)}
          />
        </p>
        <p className="section-panel__name">{project.name}</p>
      </div>
      <nav aria-label="Project sections" className="section-nav">
        <ul ref={list} className="section-nav__list">
          {pages.map((p) => (
            <li key={p.label}>
              <NavLink
                to={p.to}
                end={p.to === ""}
                className="section-nav__link"
                // Rules holds the current page (one of its sections) rather than being it.
                aria-current={p.to === "rules" ? "true" : "page"}
              >
                {({ isActive }) => (
                  <>
                    <Icon
                      name={p.icon}
                      size={16}
                      tone="text"
                      weight={isActive ? "fill" : "regular"}
                    />
                    {p.label}
                  </>
                )}
              </NavLink>
              {p.to === "rules" && onRules ? (
                <ul className="section-nav__sub">
                  {RULE_SECTIONS.map((s) => (
                    <li key={s.key}>
                      <NavLink to={`rules/${s.key}`} className="section-nav__sublink">
                        {s.title}
                      </NavLink>
                    </li>
                  ))}
                </ul>
              ) : null}
            </li>
          ))}
        </ul>
      </nav>
    </div>
  );
}

export function ProjectDetailPage() {
  const { projectId = "" } = useParams();
  const { can } = useAuth();
  const onOverview = useMatch({ path: "/projects/:projectId", end: true }) !== null;
  const page = useMatch("/projects/:projectId/:page/*")?.params.page ?? "";
  const section = useMatch("/projects/:projectId/rules/:section")?.params.section;
  // The title row's places for a page's buttons and its line under the title (D-158).
  const [actions, setActions] = useState<HTMLElement | null>(null);
  const [lead, setLead] = useState<HTMLElement | null>(null);
  const { state, reload, replace } = useResource(() => getProject(projectId), [projectId]);
  const loaded = state.status === "loaded" ? state.data : null;
  // The browser tab: the project on its overview; elsewhere the page (with the Rules section)
  // and the project's code, so several projects open in tabs can be told apart.
  usePageTitle(
    ...(!loaded
      ? []
      : onOverview
        ? [`${loaded.code} · ${loaded.name}`]
        : [
            RULE_SECTIONS.find((s) => s.key === section)?.title,
            PAGES.find((p) => p.to === page)?.label ?? "Project",
            loaded.code,
          ]),
  );
  if (state.status === "loading") return <LoadingState label="Loading project" />;
  if (state.status === "failed") {
    // A project that is gone or not one's own: still a titled page with the way back.
    return (
      <section aria-labelledby="project-title" className="stack">
        <BackLink to="/projects">All projects</BackLink>
        <h1 id="project-title">Project</h1>
        <ErrorState error={state.error} onRetry={reload} />
      </section>
    );
  }
  const project = state.data;
  // The Export page also needs the right to export.
  const pages = PAGES.filter(
    (p) => (!p.perm || can(p.perm)) && (p.to !== "export" || can("exports.create")),
  );
  const badge = (
    <StatusBadge status={project.status} label={labelFor(PROJECT_STATUS_LABELS, project.status)} />
  );
  const content =
    onOverview || can("projects.manage") ? (
      <Outlet context={{ project, replace, header: { actions, lead } } satisfies ProjectContext} />
    ) : (
      <EmptyState
        title="No access"
        message="Only the project's administrators see this part of a project."
      />
    );
  const projectTitle = `${project.code} · ${project.name}`;

  // One page only (the overview): no menu to choose from (D-104).
  if (pages.length <= 1)
    return (
      <section aria-labelledby="project-title" className="stack">
        <BackLink to="/projects">All projects</BackLink>
        <div className="page-header__title">
          <h1 id="project-title">{projectTitle}</h1>
          {badge}
        </div>
        {content}
      </section>
    );

  // The overview is titled with the project; every other page with its own name.
  const title = onOverview
    ? projectTitle
    : (pages.find((p) => p.to === page)?.label ?? projectTitle);
  return (
    <div className="section-layout">
      <ProjectMenu project={project} pages={pages} />
      <section aria-labelledby="project-title" className="section-layout__main stack">
        <PageHeader id="project-title" title={title} leadRef={setLead} actionsRef={setActions} />
        {content}
      </section>
    </div>
  );
}
